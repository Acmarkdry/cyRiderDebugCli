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
import com.intellij.xdebugger.XDebugSessionListener;
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
import java.time.Instant;
import java.util.*;
import java.util.Collections;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * REST API handler bridging MCP server to Rider's XDebugger.
 * Registers under /api/rider-debug-mcp/* via built-in HTTP server.
 *
 * Features:
 *   - Breakpoint CRUD
 *   - Debug session control (start/stop/step)
 *   - Variable/stack inspection
 *   - Event queue: captures breakpoint hits, pauses (assert), exceptions, exits
 *   - Auto-resume policy: optionally auto-resume on assert/exception
 */
public class DebugBridgeHandler extends HttpRequestHandler {

    private static final String PREFIX = "/api/rider-debug-mcp";
    private static final Gson GSON = new GsonBuilder().serializeNulls().create();
    private static final int MAX_EVENTS = 200;

    // --- Event queue (thread-safe, bounded) ---
    private static final ConcurrentLinkedDeque<Map<String, Object>> EVENT_QUEUE = new ConcurrentLinkedDeque<>();

    // --- Auto-resume policy ---
    private static final AtomicBoolean AUTO_RESUME_ON_EXCEPTION = new AtomicBoolean(false);
    private static final AtomicBoolean AUTO_COLLECT_ON_PAUSE = new AtomicBoolean(true);

    // --- Track whether we've attached listener to current session ---
    private static volatile XDebugSession lastTrackedSession = null;

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

        // Events & policy
        if ("/events".equals(path) && method == HttpMethod.GET) return pollEvents();
        if ("/events/clear".equals(path) && method == HttpMethod.POST) return clearEvents();
        if ("/debug/exceptionPolicy".equals(path) && method == HttpMethod.GET) return getExceptionPolicy();
        if ("/debug/exceptionPolicy".equals(path) && method == HttpMethod.POST) return setExceptionPolicy(readBody(request));
        if ("/debug/autoResume".equals(path) && method == HttpMethod.POST) return autoResume(readBody(request));

        return errorMap("Unknown endpoint: " + path);
    }

    // ==================== Status ====================

    private Map<String, Object> status() {
        ensureSessionTracked();

        Map<String, Object> map = new LinkedHashMap<>();
        map.put("plugin", "rider-debug-mcp");
        map.put("version", "0.2.0");

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

        // Schedule listener attachment after a short delay (session needs time to start)
        new Thread(() -> {
            try { Thread.sleep(2000); } catch (InterruptedException ignored) {}
            ensureSessionTracked();
        }).start();

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

    // ==================== Inspection (deep XDebugger API access) ====================

    private static final long ASYNC_TIMEOUT_MS = 5000;

    /**
     * GET /debug/variables — enumerate XValue children from the current stack frame.
     *
     * IMPORTANT: computeChildren/computePresentation callbacks fire on a pooled thread,
     * NOT on EDT. We must NOT call latch.await() on EDT (deadlock). So we grab the
     * frame reference on EDT, then do the async work + await on the caller (Netty) thread.
     */
    private Map<String, Object> getVariables() {
        Project project = getProject();
        if (project == null) return Map.of("variables", List.of());

        Map<String, Object> result = new LinkedHashMap<>();

        // Step 1: grab frame reference on EDT
        final XStackFrame[] frameRef = {null};
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) { result.put("error", "No debug session"); return; }
            XStackFrame frame = session.getCurrentStackFrame();
            if (frame == null) { result.put("error", "No stack frame"); return; }
            frameRef[0] = frame;

            XSourcePosition pos = frame.getSourcePosition();
            if (pos != null) {
                result.put("frame", Map.of("file", pos.getFile().getName(), "line", pos.getLine() + 1));
            }
        });

        if (frameRef[0] == null) return result.isEmpty() ? Map.of("error", "No stack frame") : result;

        // Step 2: compute children on the current (Netty) thread — callbacks come on a pooled thread
        List<Map<String, Object>> vars = Collections.synchronizedList(new ArrayList<>());
        var latch = new java.util.concurrent.CountDownLatch(1);

        frameRef[0].computeChildren(new com.intellij.xdebugger.frame.XCompositeNode() {
            @Override
            public void addChildren(@NotNull com.intellij.xdebugger.frame.XValueChildrenList children, boolean last) {
                for (int i = 0; i < children.size(); i++) {
                    String name = children.getName(i);
                    com.intellij.xdebugger.frame.XValue xval = children.getValue(i);
                    Map<String, Object> varInfo = new LinkedHashMap<>();
                    varInfo.put("name", name);
                    collectXValuePresentation(xval, varInfo);
                    vars.add(varInfo);
                }
                if (last) latch.countDown();
            }

            @Override
            public void tooManyChildren(int remaining) {
                vars.add(Map.of("name", "...", "value", remaining + " more children", "type", "overflow"));
                latch.countDown();
            }

            @Override public void setAlreadySorted(boolean alreadySorted) {}

            @Override
            public void setErrorMessage(@NotNull String errorMessage) {
                vars.add(Map.of("name", "__error__", "value", errorMessage, "type", "error"));
                latch.countDown();
            }

            @Override
            public void setErrorMessage(@NotNull String errorMessage, @org.jetbrains.annotations.Nullable com.intellij.xdebugger.frame.XDebuggerTreeNodeHyperlink link) {
                setErrorMessage(errorMessage);
            }

            @Override
            public void setMessage(@NotNull String message, @org.jetbrains.annotations.Nullable javax.swing.Icon icon,
                                   @NotNull com.intellij.ui.SimpleTextAttributes attributes,
                                   @org.jetbrains.annotations.Nullable com.intellij.xdebugger.frame.XDebuggerTreeNodeHyperlink link) {}

            @Override public boolean isObsolete() { return false; }
        });

        try { latch.await(ASYNC_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS); }
        catch (InterruptedException ignored) {}

        result.put("variables", vars);
        return result;
    }

    /**
     * Collect value + type from XValue's presentation callback.
     * This uses computePresentation() with a sync latch.
     */
    private static void collectXValuePresentation(com.intellij.xdebugger.frame.XValue xval, Map<String, Object> target) {
        var latch = new java.util.concurrent.CountDownLatch(1);
        final String[] collected = {"", "", "false"};

        xval.computePresentation(new com.intellij.xdebugger.frame.XValueNode() {
            @Override
            public void setPresentation(@org.jetbrains.annotations.Nullable javax.swing.Icon icon,
                                        @org.jetbrains.annotations.Nullable String type,
                                        @NotNull String value, boolean hasChildren) {
                collected[0] = value;
                collected[1] = type != null ? type : "";
                collected[2] = String.valueOf(hasChildren);
                latch.countDown();
            }

            @Override
            public void setPresentation(@org.jetbrains.annotations.Nullable javax.swing.Icon icon,
                                        @NotNull com.intellij.xdebugger.frame.presentation.XValuePresentation presentation,
                                        boolean hasChildren) {
                collected[0] = presentation.getSeparator() != null ? presentation.getSeparator() : "";
                collected[1] = presentation.getType() != null ? presentation.getType() : "";
                collected[2] = String.valueOf(hasChildren);
                // Try to get the rendered text
                var sb = new StringBuilder();
                presentation.renderValue(new com.intellij.xdebugger.frame.presentation.XValuePresentation.XValueTextRenderer() {
                    @Override
                    public void renderValue(@NotNull String value) { sb.append(value); }
                    @Override
                    public void renderStringValue(@NotNull String value) { sb.append('"').append(value).append('"'); }
                    @Override
                    public void renderStringValue(@NotNull String value, @org.jetbrains.annotations.Nullable String additionalSpecialCharsToHighlight, int maxLength) {
                        sb.append('"').append(value).append('"');
                    }
                    @Override
                    public void renderNumericValue(@NotNull String value) { sb.append(value); }
                    @Override
                    public void renderKeywordValue(@NotNull String value) { sb.append(value); }
                    @Override
                    public void renderComment(@NotNull String comment) { sb.append(" /* ").append(comment).append(" */"); }
                    @Override
                    public void renderSpecialSymbol(@NotNull String symbol) { sb.append(symbol); }
                    @Override
                    public void renderError(@NotNull String error) { sb.append("[error: ").append(error).append("]"); }
                    @Override
                    public void renderValue(@NotNull String value, @NotNull com.intellij.openapi.editor.colors.TextAttributesKey key) { sb.append(value); }
                });
                if (!sb.isEmpty()) collected[0] = sb.toString();
                latch.countDown();
            }

            @Override
            public void setFullValueEvaluator(@NotNull com.intellij.xdebugger.frame.XFullValueEvaluator fullValueEvaluator) {}

            @Override
            public boolean isObsolete() { return false; }
        }, com.intellij.xdebugger.frame.XValuePlace.TREE);

        try { latch.await(ASYNC_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS); }
        catch (InterruptedException ignored) {}

        target.put("value", collected[0]);
        target.put("type", collected[1]);
        target.put("hasChildren", Boolean.parseBoolean(collected[2]));
    }

    /**
     * POST /debug/evaluate — evaluate expression in the current debug session.
     * Uses XDebuggerEvaluator.evaluate() with a sync callback.
     */
    private Map<String, Object> evaluate(Map<String, Object> body) {
        String expr = (String) body.get("expression");
        if (expr == null) return errorMap("Missing 'expression'");

        Project project = getProject();
        if (project == null) return errorMap("No project");

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("expression", expr);

        // Step 1: grab evaluator on EDT
        final com.intellij.xdebugger.evaluation.XDebuggerEvaluator[] evalRef = {null};
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) { result.put("error", "No debug session"); return; }
            XStackFrame frame = session.getCurrentStackFrame();
            if (frame == null) { result.put("error", "No stack frame"); return; }
            evalRef[0] = frame.getEvaluator();
            if (evalRef[0] == null) { result.put("error", "No evaluator available"); }
        });

        if (evalRef[0] == null) return result;

        // Step 2: evaluate on Netty thread, await callback
        var latch = new java.util.concurrent.CountDownLatch(1);
        try {
            com.intellij.xdebugger.impl.breakpoints.XExpressionImpl expression =
                com.intellij.xdebugger.impl.breakpoints.XExpressionImpl.fromText(expr);

            evalRef[0].evaluate(expression, new com.intellij.xdebugger.evaluation.XDebuggerEvaluator.XEvaluationCallback() {
                @Override
                public void evaluated(@NotNull com.intellij.xdebugger.frame.XValue xval) {
                    collectXValuePresentation(xval, result);
                    result.put("status", "evaluated");
                    latch.countDown();
                }

                @Override
                public void errorOccurred(@NotNull String errorMessage) {
                    result.put("error", errorMessage);
                    result.put("status", "error");
                    latch.countDown();
                }
            }, null);
        } catch (Exception e) {
            result.put("error", "Evaluation failed: " + e.getMessage());
            result.put("status", "error");
            return result;
        }

        try { latch.await(ASYNC_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS); }
        catch (InterruptedException ignored) {}

        if (!result.containsKey("status")) {
            result.put("status", "timeout");
            result.put("note", "Evaluation timed out after " + ASYNC_TIMEOUT_MS + "ms");
        }
        return result;
    }

    /**
     * GET /debug/stackTrace — enumerate ALL frames from XExecutionStack.
     * Uses computeStackFrames() with a sync callback.
     */
    private Map<String, Object> getStackTrace() {
        Project project = getProject();
        if (project == null) return Map.of("frames", List.of());

        Map<String, Object> result = new LinkedHashMap<>();

        // Step 1: grab execution stack on EDT
        final XExecutionStack[] stackRef = {null};
        final XStackFrame[] topFrameRef = {null};
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) { result.put("error", "No debug session"); return; }

            XSuspendContext ctx = session.getSuspendContext();
            if (ctx == null) { result.put("error", "Not suspended"); return; }

            stackRef[0] = ctx.getActiveExecutionStack();
            if (stackRef[0] == null) { result.put("error", "No active execution stack"); return; }

            topFrameRef[0] = stackRef[0].getTopFrame();
            result.put("threadName", stackRef[0].getDisplayName());
        });

        if (stackRef[0] == null) return result;

        // Step 2: compute all frames on Netty thread
        List<Map<String, Object>> frames = Collections.synchronizedList(new ArrayList<>());
        var latch = new java.util.concurrent.CountDownLatch(1);

        stackRef[0].computeStackFrames(0, new XExecutionStack.XStackFrameContainer() {
            @Override
            public void addStackFrames(@NotNull List<? extends XStackFrame> stackFrames, boolean last) {
                for (XStackFrame sf : stackFrames) {
                    Map<String, Object> frameInfo = new LinkedHashMap<>();
                    XSourcePosition sfPos = sf.getSourcePosition();
                    if (sfPos != null) {
                        frameInfo.put("file", sfPos.getFile().getName());
                        frameInfo.put("line", sfPos.getLine() + 1);
                        frameInfo.put("filePath", sfPos.getFile().getPath());
                    }
                    frameInfo.put("method", extractFrameDisplayName(sf));
                    frameInfo.put("index", frames.size());
                    frames.add(frameInfo);
                }
                if (last) latch.countDown();
            }

            @Override
            public void errorOccurred(@NotNull String errorMessage) {
                frames.add(Map.of("error", errorMessage));
                latch.countDown();
            }
        });

        try { latch.await(ASYNC_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS); }
        catch (InterruptedException ignored) {}

        // Fallback if computeStackFrames returned nothing
        if (frames.isEmpty() && topFrameRef[0] != null) {
            XSourcePosition topPos = topFrameRef[0].getSourcePosition();
            Map<String, Object> fallback = new LinkedHashMap<>();
            if (topPos != null) {
                fallback.put("file", topPos.getFile().getName());
                fallback.put("line", topPos.getLine() + 1);
            }
            fallback.put("method", extractFrameDisplayName(topFrameRef[0]));
            fallback.put("index", 0);
            frames.add(fallback);
        }

        result.put("frames", frames);
        return result;
    }

    /**
     * Extract a human-readable function name from a stack frame.
     * Tries customizePresentation, then toString, then source position.
     */
    private static String extractFrameDisplayName(XStackFrame frame) {
        // Try customizePresentation to get the text the UI shows
        try {
            var component = new com.intellij.ui.ColoredTextContainer() {
                final StringBuilder sb = new StringBuilder();
                @Override public void append(@NotNull String fragment, @NotNull com.intellij.ui.SimpleTextAttributes attributes) { sb.append(fragment); }
                @Override public void setIcon(@org.jetbrains.annotations.Nullable javax.swing.Icon icon) {}
                @Override public void setToolTipText(@org.jetbrains.annotations.Nullable String text) {}
            };
            frame.customizePresentation(component);
            String name = component.sb.toString().trim();
            if (!name.isEmpty()) return name;
        } catch (Exception ignored) {}

        // Fallback: toString
        try {
            String s = frame.toString();
            if (s != null && !s.contains("@") && !s.isEmpty()) return s;
        } catch (Exception ignored) {}

        // Final fallback: file:line
        XSourcePosition pos = frame.getSourcePosition();
        if (pos != null) return pos.getFile().getName() + ":" + (pos.getLine() + 1);
        return "unknown";
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

    // ==================== Events & Session Tracking ====================

    /**
     * Ensure we have a session listener attached to the current debug session.
     * Called from status() and other entry points to lazily attach.
     */
    private void ensureSessionTracked() {
        Project project = getProject();
        if (project == null) return;

        XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
        if (session == null || session == lastTrackedSession) return;

        lastTrackedSession = session;
        session.addSessionListener(new XDebugSessionListener() {
            @Override
            public void sessionPaused() {
                // This fires on breakpoint hit, assert, exception — any pause
                Map<String, Object> event = new LinkedHashMap<>();
                event.put("eventType", "paused");
                event.put("timestamp", Instant.now().toString());

                // Collect context
                XStackFrame frame = session.getCurrentStackFrame();
                XSourcePosition pos = frame != null ? frame.getSourcePosition() : null;
                if (pos != null) {
                    event.put("file", pos.getFile().getName());
                    event.put("line", pos.getLine() + 1);
                    event.put("filePath", pos.getFile().getPath());
                }

                // Check if this pause is at a known breakpoint location
                boolean isAtBreakpoint = false;
                if (pos != null) {
                    Project proj = getProject();
                    if (proj != null) {
                        XBreakpointManager bpMgr = XDebuggerManager.getInstance(proj).getBreakpointManager();
                        for (XBreakpoint<?> b : bpMgr.getAllBreakpoints()) {
                            if (b instanceof XLineBreakpoint<?> lbp) {
                                if (lbp.getFileUrl().endsWith(pos.getFile().getName())
                                        && lbp.getLine() == pos.getLine()) {
                                    isAtBreakpoint = true;
                                    String fName = pos.getFile().getName();
                                    event.put("reason", "breakpoint");
                                    event.put("breakpointId", "bp-" + fName + ":" + (pos.getLine() + 1));
                                    break;
                                }
                            }
                        }
                    }
                }
                if (!isAtBreakpoint) {
                    event.put("reason", "exception_or_assert");
                    event.put("note", "Program paused (assert/exception/signal). Use /debug/stackTrace and /debug/resume or /debug/autoResume.");
                }

                pushEvent(event);

                // Auto-resume if policy says so and it's an exception/assert
                if (!isAtBreakpoint && AUTO_RESUME_ON_EXCEPTION.get()) {
                    // Collect info first, then auto-resume
                    Map<String, Object> autoEvent = new LinkedHashMap<>();
                    autoEvent.put("eventType", "auto_resumed");
                    autoEvent.put("timestamp", Instant.now().toString());
                    autoEvent.put("reason", "auto_resume_policy");
                    if (pos != null) {
                        autoEvent.put("file", pos.getFile().getName());
                        autoEvent.put("line", pos.getLine() + 1);
                    }
                    pushEvent(autoEvent);
                    // Resume on a separate thread to not deadlock
                    ApplicationManager.getApplication().invokeLater(session::resume);
                }
            }

            @Override
            public void sessionResumed() {
                Map<String, Object> event = new LinkedHashMap<>();
                event.put("eventType", "resumed");
                event.put("timestamp", Instant.now().toString());
                pushEvent(event);
            }

            @Override
            public void sessionStopped() {
                Map<String, Object> event = new LinkedHashMap<>();
                event.put("eventType", "stopped");
                event.put("timestamp", Instant.now().toString());
                pushEvent(event);
                lastTrackedSession = null;
            }
        });

        // Record that we started tracking
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventType", "session_tracked");
        event.put("timestamp", Instant.now().toString());
        event.put("note", "Debug session listener attached. Events will be captured automatically.");
        pushEvent(event);
    }

    private static void pushEvent(Map<String, Object> event) {
        EVENT_QUEUE.addLast(event);
        while (EVENT_QUEUE.size() > MAX_EVENTS) {
            EVENT_QUEUE.pollFirst();
        }
    }

    private Map<String, Object> pollEvents() {
        ensureSessionTracked();
        List<Map<String, Object>> events = new ArrayList<>();
        Map<String, Object> event;
        while ((event = EVENT_QUEUE.pollFirst()) != null) {
            events.add(event);
        }
        return Map.of("events", events, "count", events.size());
    }

    private Map<String, Object> clearEvents() {
        EVENT_QUEUE.clear();
        return Map.of("cleared", true);
    }

    private Map<String, Object> getExceptionPolicy() {
        Map<String, Object> r = new LinkedHashMap<>();
        r.put("autoResumeOnException", AUTO_RESUME_ON_EXCEPTION.get());
        r.put("autoCollectOnPause", AUTO_COLLECT_ON_PAUSE.get());
        r.put("description", "autoResumeOnException=true: program auto-resumes on assert/exception after collecting info. " +
                "autoCollectOnPause=true: pause events include file/line info.");
        return r;
    }

    private Map<String, Object> setExceptionPolicy(Map<String, Object> body) {
        if (body.containsKey("autoResumeOnException")) {
            AUTO_RESUME_ON_EXCEPTION.set(Boolean.TRUE.equals(body.get("autoResumeOnException")));
        }
        if (body.containsKey("autoCollectOnPause")) {
            AUTO_COLLECT_ON_PAUSE.set(Boolean.TRUE.equals(body.get("autoCollectOnPause")));
        }
        return getExceptionPolicy();
    }

    private Map<String, Object> autoResume(Map<String, Object> body) {
        // Convenience endpoint: resume current session + collect crash info
        Project project = getProject();
        if (project == null) return errorMap("No project");

        Map<String, Object> result = new LinkedHashMap<>();
        runOnEdt(() -> {
            XDebugSession session = XDebuggerManager.getInstance(project).getCurrentSession();
            if (session == null) {
                result.put("error", "No active debug session");
                return;
            }
            // Collect info before resuming
            XStackFrame frame = session.getCurrentStackFrame();
            XSourcePosition pos = frame != null ? frame.getSourcePosition() : null;
            if (pos != null) {
                result.put("pausedAt", Map.of("file", pos.getFile().getName(), "line", pos.getLine() + 1));
            }
            result.put("wasPaused", session.isPaused());

            // Resume
            if (session.isPaused()) {
                session.resume();
                result.put("resumed", true);
            } else {
                result.put("resumed", false);
                result.put("note", "Session was not paused");
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
