package com.cyriderdebug.mcp;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.intellij.execution.ProgramRunnerUtil;
import com.intellij.execution.RunManager;
import com.intellij.execution.RunnerAndConfigurationSettings;
import com.intellij.execution.executors.DefaultDebugExecutor;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ProjectManager;
import com.intellij.openapi.vfs.LocalFileSystem;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.psi.search.FilenameIndex;
import com.intellij.psi.search.GlobalSearchScope;
import com.intellij.xdebugger.XDebugSession;
import com.intellij.xdebugger.XDebuggerManager;
import com.intellij.xdebugger.XExpression;
import com.intellij.xdebugger.XSourcePosition;
import com.intellij.xdebugger.breakpoints.*;
import com.intellij.xdebugger.frame.XExecutionStack;
import com.intellij.xdebugger.frame.XStackFrame;
import com.intellij.xdebugger.frame.XSuspendContext;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.QueryStringDecoder;
import io.netty.buffer.Unpooled;
import io.netty.handler.codec.http.*;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.ide.HttpRequestHandler;

import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Pattern;

/**
 * REST API handler bridging MCP server to Rider's XDebugger.
 * Registers under /api/rider-debug-mcp/* via built-in HTTP server.
 */
public class DebugBridgeHandler extends HttpRequestHandler {

    private static final String PREFIX = "/api/rider-debug-mcp";
    private static final Gson GSON = new GsonBuilder().serializeNulls().create();
    private static final Pattern BP_ID_PATTERN = Pattern.compile("/breakpoints/([^/]+)");

    @Override
    public boolean isSupported(@NotNull FullHttpRequest request) {
        return request.uri().startsWith(PREFIX);
    }

    @Override
    public boolean process(@NotNull QueryStringDecoder urlDecoder,
                           @NotNull FullHttpRequest request,
                           @NotNull ChannelHandlerContext context) {
        String path = urlDecoder.path().substring(PREFIX.length());
        HttpMethod method = request.method();

        Object result;
        try {
            result = route(path, method, urlDecoder, request);
        } catch (Exception e) {
            result = errorMap(e.getMessage() != null ? e.getMessage() : "Internal error");
        }

        sendJsonResponse(GSON.toJson(result), request, context);
        return true;
    }

    // ==================== Routing ====================

    private Object route(String path, HttpMethod method,
                         QueryStringDecoder decoder, FullHttpRequest request) {
        // Status
        if ("/status".equals(path)) return status();

        // Breakpoints
        if ("/breakpoints".equals(path) && method == HttpMethod.GET) return listBreakpoints();
        if ("/breakpoints".equals(path) && method == HttpMethod.POST) return addBreakpoint(readBody(request));
        if (path.matches("/breakpoints/[^/]+/enable") && method == HttpMethod.POST)
            return toggleBreakpoint(extractBpId(path), true);
        if (path.matches("/breakpoints/[^/]+/disable") && method == HttpMethod.POST)
            return toggleBreakpoint(extractBpId(path), false);
        if (path.matches("/breakpoints/[^/]+") && method == HttpMethod.DELETE)
            return removeBreakpoint(path.substring("/breakpoints/".length()));

        // Debug control
        if ("/debug/start".equals(path) && method == HttpMethod.POST) return startDebug(readBody(request));
        if ("/debug/stop".equals(path) && method == HttpMethod.POST) return sessionAction("stop");
        if ("/debug/pause".equals(path) && method == HttpMethod.POST) return sessionAction("pause");
        if ("/debug/resume".equals(path) && method == HttpMethod.POST) return sessionAction("resume");
        if ("/debug/stepOver".equals(path) && method == HttpMethod.POST) return sessionAction("stepOver");
        if ("/debug/stepInto".equals(path) && method == HttpMethod.POST) return sessionAction("stepInto");
        if ("/debug/stepOut".equals(path) && method == HttpMethod.POST) return sessionAction("stepOut");

        // Inspection
        if ("/debug/variables".equals(path) && method == HttpMethod.GET) return getVariables();
        if ("/debug/evaluate".equals(path) && method == HttpMethod.POST) return evaluate(readBody(request));
        if ("/debug/stackTrace".equals(path) && method == HttpMethod.GET) return getStackTrace();
        if ("/debug/threads".equals(path) && method == HttpMethod.GET) return getThreads();

        return errorMap("Unknown endpoint: " + path);
    }

    // ==================== Status ====================

    private Map<String, Object> status() {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("plugin", "rider-debug-mcp");
        map.put("version", "0.1.0");

        Project project = getProject();
        if (project == null) {
            map.put("active", false);
            return map;
        }

        XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
        map.put("active", session != null);
        map.put("paused", session != null && session.isPaused());
        map.put("stopped", session == null || session.isStopped());
        map.put("project", project.getName());
        return map;
    }

    // ==================== Breakpoints ====================

    private Map<String, Object> listBreakpoints() {
        Project project = getProject();
        if (project == null) return Map.of("breakpoints", List.of());

        List<Map<String, Object>> bps = new ArrayList<>();
        runOnEdt(() -> {
            XBreakpointManager mgr = XDebuggerManager.getInstance(project).getBreakpointManager();
            for (XBreakpoint<?> bp : mgr.getAllBreakpoints()) {
                if (bp instanceof XLineBreakpoint<?> lbp) {
                    String url = lbp.getFileUrl();
                    String fileName = url.contains("/") ? url.substring(url.lastIndexOf('/') + 1) : url;
                    int line = lbp.getLine() + 1;

                    Map<String, Object> entry = new LinkedHashMap<>();
                    entry.put("id", "bp-" + fileName + ":" + line);
                    entry.put("file", fileName);
                    entry.put("line", line);
                    entry.put("enabled", lbp.isEnabled());
                    XExpression cond = lbp.getConditionExpression();
                    entry.put("condition", cond != null ? cond.getExpression() : null);
                    bps.add(entry);
                }
            }
        });
        return Map.of("breakpoints", bps);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> addBreakpoint(Map<String, Object> body) {
        String file = (String) body.get("file");
        if (file == null) return errorMap("Missing 'file'");
        Number lineNum = (Number) body.get("line");
        if (lineNum == null) return errorMap("Missing 'line'");
        int line = lineNum.intValue();
        String condition = (String) body.get("condition");

        Project project = getProject();
        if (project == null) return errorMap("No project open");

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            VirtualFile vFile = findFile(file);
            if (vFile == null) {
                result.put("error", "File not found: " + file);
                return;
            }

            XBreakpointManager bpMgr = XDebuggerManager.getInstance(project).getBreakpointManager();

            // Find the first line breakpoint type
            XLineBreakpointType<?> lineType = null;
            for (XBreakpointType<?, ?> type : XBreakpointType.EXTENSION_POINT_NAME.getExtensionList()) {
                if (type instanceof XLineBreakpointType<?> lt) {
                    lineType = lt;
                    break;
                }
            }
            if (lineType == null) {
                result.put("error", "No line breakpoint type available");
                return;
            }

            @SuppressWarnings("rawtypes")
            XLineBreakpoint bp = bpMgr.addLineBreakpoint(
                    (XLineBreakpointType) lineType, vFile.getUrl(), line - 1, null);

            if (bp != null && condition != null) {
                // setConditionExpression expects XExpression; create via implementation
                try {
                    bp.setConditionExpression(
                            com.intellij.xdebugger.impl.breakpoints.XExpressionImpl.fromText(condition));
                } catch (Exception ignored) {
                    // Condition setting is best-effort
                }
            }

            String f = file.contains("/") ? file.substring(file.lastIndexOf('/') + 1) : file;
            if (f.contains("\\")) f = f.substring(f.lastIndexOf('\\') + 1);

            result.put("id", "bp-" + f + ":" + line);
            result.put("file", f);
            result.put("line", line);
            result.put("enabled", bp != null && bp.isEnabled());
            result.put("condition", condition);
        });
        return result;
    }

    private Map<String, Object> removeBreakpoint(String id) {
        Project project = getProject();
        if (project == null) return errorMap("No project");

        int[] parsed = parseId(id);
        if (parsed == null) return errorMap("Bad ID: " + id);
        String fileName = id.startsWith("bp-") ? id.substring(3, id.lastIndexOf(':')) : id;

        boolean[] found = {false};
        runOnEdt(() -> {
            XLineBreakpoint<?> bp = findBp(fileName, parsed[0]);
            if (bp != null) {
                XDebuggerManager.getInstance(project).getBreakpointManager().removeBreakpoint(bp);
                found[0] = true;
            }
        });
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("removed", found[0]);
        r.put("id", id);
        return r;
    }

    private Map<String, Object> toggleBreakpoint(String id, boolean enabled) {
        int[] parsed = parseId(id);
        if (parsed == null) return errorMap("Bad ID: " + id);
        String fileName = id.startsWith("bp-") ? id.substring(3, id.lastIndexOf(':')) : id;

        boolean[] ok = {false};
        runOnEdt(() -> {
            XLineBreakpoint<?> bp = findBp(fileName, parsed[0]);
            if (bp != null) {
                bp.setEnabled(enabled);
                ok[0] = true;
            }
        });
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("id", id);
        r.put("enabled", enabled);
        r.put("found", ok[0]);
        return r;
    }

    // ==================== Debug Control ====================

    private Map<String, Object> startDebug(Map<String, Object> body) {
        Project project = getProject();
        if (project == null) return errorMap("No project");
        String configName = (String) body.get("configuration");

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            RunManager rm = RunManager.getInstance(project);
            RunnerAndConfigurationSettings settings = configName != null
                    ? rm.findConfigurationByName(configName)
                    : rm.getSelectedConfiguration();

            if (settings == null) {
                result.put("error", "No run configuration" + (configName != null ? ": " + configName : ""));
                return;
            }
            ProgramRunnerUtil.executeConfiguration(settings, DefaultDebugExecutor.getDebugExecutorInstance());
            result.put("sessionId", "session-" + System.currentTimeMillis());
            result.put("status", "starting");
            result.put("configuration", settings.getName());
        });
        return result;
    }

    private Map<String, Object> sessionAction(String action) {
        Project project = getProject();
        if (project == null) return errorMap("No project");

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) {
                result.put("error", "No active debug session");
                return;
            }
            switch (action) {
                case "stop" -> session.stop();
                case "pause" -> session.pause();
                case "resume" -> session.resume();
                case "stepOver" -> session.stepOver(false);
                case "stepInto" -> session.stepInto();
                case "stepOut" -> session.stepOut();
            }
            result.put("success", true);
            result.put("action", action);
        });
        return result;
    }

    // ==================== Inspection ====================

    private Map<String, Object> getVariables() {
        Project project = getProject();
        if (project == null) return Map.of("variables", List.of());

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) { result.put("error", "No debug session"); return; }
            XStackFrame frame = session.getCurrentStackFrame();
            if (frame == null) { result.put("error", "No stack frame"); return; }
            XSourcePosition pos = frame.getSourcePosition();
            result.put("variables", List.of());
            if (pos != null) {
                result.put("frame", Map.of("file", pos.getFile().getName(), "line", pos.getLine() + 1));
            }
            result.put("note", "Variable values visible in Rider's Variables panel");
        });
        return result;
    }

    private Map<String, Object> evaluate(Map<String, Object> body) {
        String expr = (String) body.get("expression");
        if (expr == null) return errorMap("Missing 'expression'");
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("expression", expr);
        r.put("status", "submitted");
        r.put("note", "Use Rider's Evaluate Expression (Alt+F8) for full evaluation");
        return r;
    }

    private Map<String, Object> getStackTrace() {
        Project project = getProject();
        if (project == null) return Map.of("frames", List.of());

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) { result.put("error", "No debug session"); return; }
            XStackFrame frame = session.getCurrentStackFrame();
            XSourcePosition pos = frame != null ? frame.getSourcePosition() : null;
            if (pos != null) {
                // Use source position file + line as method identifier
                String method = pos.getFile().getName() + ":" + (pos.getLine() + 1);
                result.put("frames", List.of(Map.of(
                        "method", method, "file", pos.getFile().getName(), "line", pos.getLine() + 1)));
            } else {
                result.put("frames", List.of());
            }
        });
        return result;
    }

    private Map<String, Object> getThreads() {
        Project project = getProject();
        if (project == null) return Map.of("threads", List.of());

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) { result.put("error", "No debug session"); return; }
            XSuspendContext ctx = session.getSuspendContext();
            if (ctx == null) {
                result.put("threads", List.of());
                result.put("note", "Debugger running, not suspended");
                return;
            }
            XExecutionStack stack = ctx.getActiveExecutionStack();
            if (stack != null) {
                result.put("threads", List.of(Map.of(
                        "id", 1, "name", stack.getDisplayName(),
                        "state", "suspended", "isMain", true)));
            } else {
                result.put("threads", List.of());
            }
        });
        return result;
    }

    // ==================== Utilities ====================

    private static Project getProject() {
        Project[] projects = ProjectManager.getInstance().getOpenProjects();
        return projects.length > 0 ? projects[0] : null;
    }

    private static void runOnEdt(Runnable action) {
        ApplicationManager.getApplication().invokeAndWait(action);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> readBody(FullHttpRequest request) {
        try {
            byte[] bytes = new byte[request.content().readableBytes()];
            request.content().readBytes(bytes);
            String json = new String(bytes, StandardCharsets.UTF_8);
            if (json.isBlank()) return Map.of();
            return GSON.fromJson(json, Map.class);
        } catch (Exception e) {
            return Map.of();
        }
    }

    private static void sendJsonResponse(String json, FullHttpRequest request, ChannelHandlerContext context) {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        FullHttpResponse response = new DefaultFullHttpResponse(
                HttpVersion.HTTP_1_1, HttpResponseStatus.OK,
                Unpooled.wrappedBuffer(bytes));
        response.headers().set(HttpHeaderNames.CONTENT_TYPE, "application/json; charset=UTF-8");
        response.headers().set(HttpHeaderNames.CONTENT_LENGTH, bytes.length);
        response.headers().set(HttpHeaderNames.ACCESS_CONTROL_ALLOW_ORIGIN, "*");
        context.writeAndFlush(response);
    }

    private static Map<String, Object> errorMap(String msg) {
        return Map.of("error", msg);
    }

    private static String extractBpId(String path) {
        // /breakpoints/bp-File.cs:42/enable → bp-File.cs:42
        String[] parts = path.split("/");
        // parts: ["", "breakpoints", "bp-File.cs:42", "enable"]
        return parts.length >= 3 ? parts[2] : "";
    }

    private static int[] parseId(String id) {
        String clean = id.startsWith("bp-") ? id.substring(3) : id;
        int idx = clean.lastIndexOf(':');
        if (idx < 0) return null;
        try {
            int line = Integer.parseInt(clean.substring(idx + 1));
            return new int[]{line};
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static XLineBreakpoint<?> findBp(String fileName, int line) {
        Project project = getProject();
        if (project == null) return null;
        XBreakpointManager mgr = XDebuggerManager.getInstance(project).getBreakpointManager();
        for (XBreakpoint<?> bp : mgr.getAllBreakpoints()) {
            if (bp instanceof XLineBreakpoint<?> lbp) {
                if (lbp.getFileUrl().endsWith(fileName) && lbp.getLine() == line - 1) {
                    return lbp;
                }
            }
        }
        return null;
    }

    private static VirtualFile findFile(String path) {
        // Absolute path
        VirtualFile vf = LocalFileSystem.getInstance().findFileByPath(path);
        if (vf != null) return vf;

        // Relative to project
        Project project = getProject();
        if (project != null && project.getBasePath() != null) {
            vf = LocalFileSystem.getInstance().findFileByPath(project.getBasePath() + "/" + path);
            if (vf != null) return vf;
        }

        // Search by filename
        if (project != null) {
            String name = path.contains("/") ? path.substring(path.lastIndexOf('/') + 1) : path;
            if (name.contains("\\")) name = name.substring(name.lastIndexOf('\\') + 1);
            Collection<VirtualFile> files = FilenameIndex.getVirtualFilesByName(
                    name, GlobalSearchScope.projectScope(project));
            if (!files.isEmpty()) return files.iterator().next();
        }
        return null;
    }
}
