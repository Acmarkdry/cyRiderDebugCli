package com.cyriderdebug.mcp

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.intellij.execution.ProgramRunnerUtil
import com.intellij.execution.RunManager
import com.intellij.execution.executors.DefaultDebugExecutor
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.ProjectManager
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.psi.search.FilenameIndex
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.xdebugger.XDebuggerManager
import com.intellij.xdebugger.XExpression
import com.intellij.xdebugger.breakpoints.XBreakpointType
import com.intellij.xdebugger.breakpoints.XLineBreakpoint
import com.intellij.xdebugger.breakpoints.XLineBreakpointType
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpMethod
import io.netty.handler.codec.http.QueryStringDecoder
import io.netty.channel.ChannelHandlerContext
import org.jetbrains.ide.HttpRequestHandler
import org.jetbrains.ide.RestService

/**
 * Single-file REST handler that bridges MCP ↔ Rider Debugger.
 * All endpoints under /api/rider-debug-mcp/
 */
class DebugBridgeHandler : HttpRequestHandler() {

    private val gson: Gson = GsonBuilder().serializeNulls().create()
    private val prefix = "/api/rider-debug-mcp"

    override fun isSupported(request: FullHttpRequest): Boolean =
        request.uri().startsWith(prefix)

    override fun process(
        urlDecoder: QueryStringDecoder,
        request: FullHttpRequest,
        context: ChannelHandlerContext
    ): Boolean {
        val path = urlDecoder.path().removePrefix(prefix)
        val method = request.method()
        val result: Any = try {
            route(path, method, urlDecoder, request)
        } catch (e: Exception) {
            mapOf("error" to (e.message ?: "Internal error"))
        }
        RestService.send(gson.toJson(result), request, context.channel())
        return true
    }

    private fun route(
        path: String, method: HttpMethod,
        decoder: QueryStringDecoder, request: FullHttpRequest
    ): Any = when {
        // --- Status ---
        path == "/status" -> status()

        // --- Breakpoints ---
        path == "/breakpoints" && method == HttpMethod.GET -> listBreakpoints()
        path == "/breakpoints" && method == HttpMethod.POST -> addBreakpoint(body(request))
        path.matches(Regex("/breakpoints/[^/]+/enable")) && method == HttpMethod.POST ->
            toggleBreakpoint(seg(path, 2), true)
        path.matches(Regex("/breakpoints/[^/]+/disable")) && method == HttpMethod.POST ->
            toggleBreakpoint(seg(path, 2), false)
        path.matches(Regex("/breakpoints/[^/]+")) && method == HttpMethod.DELETE ->
            removeBreakpoint(seg(path, 2))

        // --- Debug control ---
        path == "/debug/start" && method == HttpMethod.POST -> startDebug(body(request))
        path == "/debug/stop" && method == HttpMethod.POST -> stopDebug()
        path == "/debug/pause" && method == HttpMethod.POST -> pauseDebug()
        path == "/debug/resume" && method == HttpMethod.POST -> resumeDebug()
        path == "/debug/stepOver" && method == HttpMethod.POST -> step("over")
        path == "/debug/stepInto" && method == HttpMethod.POST -> step("into")
        path == "/debug/stepOut" && method == HttpMethod.POST -> step("out")

        // --- Inspection ---
        path == "/debug/variables" && method == HttpMethod.GET -> getVariables()
        path == "/debug/evaluate" && method == HttpMethod.POST -> evaluate(body(request))
        path == "/debug/stackTrace" && method == HttpMethod.GET -> getStackTrace()
        path == "/debug/threads" && method == HttpMethod.GET -> getThreads()

        else -> mapOf("error" to "Unknown endpoint: $path")
    }

    // ===== Status =====

    private fun status(): Map<String, Any?> {
        val project = project() ?: return mapOf("active" to false, "plugin" to "rider-debug-mcp", "version" to "0.1.0")
        val session = XDebuggerManager.getInstance(project).currentSession
        return mapOf(
            "plugin" to "rider-debug-mcp",
            "version" to "0.1.0",
            "active" to (session != null),
            "paused" to (session?.isPaused ?: false),
            "stopped" to (session?.isStopped ?: true),
            "project" to project.name
        )
    }

    // ===== Breakpoints =====

    private fun listBreakpoints(): Map<String, Any> {
        val project = project() ?: return mapOf("breakpoints" to emptyList<Any>())
        var bps = emptyList<Map<String, Any?>>()
        edt {
            bps = XDebuggerManager.getInstance(project).breakpointManager.allBreakpoints
                .filterIsInstance<XLineBreakpoint<*>>()
                .map { bp ->
                    val f = bp.fileUrl.substringAfterLast("/")
                    mapOf("id" to "bp-$f:${bp.line + 1}", "file" to f, "line" to bp.line + 1,
                        "enabled" to bp.isEnabled, "condition" to bp.conditionExpression?.expression)
                }
        }
        return mapOf("breakpoints" to bps)
    }

    @Suppress("UNCHECKED_CAST")
    private fun addBreakpoint(body: Map<String, Any?>): Map<String, Any?> {
        val file = body["file"] as? String ?: return mapOf("error" to "Missing 'file'")
        val line = (body["line"] as? Number)?.toInt() ?: return mapOf("error" to "Missing 'line'")
        val condition = body["condition"] as? String
        val project = project() ?: return mapOf("error" to "No project open")

        var result: Map<String, Any?> = emptyMap()
        edt {
            val vFile = findFile(file) ?: run {
                result = mapOf("error" to "File not found: $file"); return@edt
            }
            val bpMgr = XDebuggerManager.getInstance(project).breakpointManager
            val lineType = XBreakpointType.EXTENSION_POINT_NAME.extensionList
                .filterIsInstance<XLineBreakpointType<*>>().firstOrNull()
            if (lineType == null) { result = mapOf("error" to "No line breakpoint type"); return@edt }

            val bp = bpMgr.addLineBreakpoint(
                lineType as XLineBreakpointType<Nothing>, vFile.url, line - 1, null
            )
            if (bp != null && condition != null) {
                bp.conditionExpression = XExpression.fromText(condition)
            }
            val f = file.substringAfterLast("/").substringAfterLast("\\")
            result = mapOf("id" to "bp-$f:$line", "file" to f, "line" to line,
                "enabled" to (bp?.isEnabled ?: true), "condition" to condition)
        }
        return result
    }

    private fun removeBreakpoint(id: String): Map<String, Any?> {
        val project = project() ?: return mapOf("error" to "No project")
        val (fileName, line) = parseId(id) ?: return mapOf("error" to "Bad ID: $id")
        var found = false
        edt {
            val bp = findBp(fileName, line)
            if (bp != null) {
                XDebuggerManager.getInstance(project).breakpointManager.removeBreakpoint(bp)
                found = true
            }
        }
        return mapOf("removed" to found, "id" to id)
    }

    private fun toggleBreakpoint(id: String, enabled: Boolean): Map<String, Any?> {
        val (fileName, line) = parseId(id) ?: return mapOf("error" to "Bad ID: $id")
        var ok = false
        edt {
            findBp(fileName, line)?.let { it.isEnabled = enabled; ok = true }
        }
        return mapOf("id" to id, "enabled" to enabled, "found" to ok)
    }

    // ===== Debug Control =====

    private fun startDebug(body: Map<String, Any?>): Map<String, Any?> {
        val project = project() ?: return mapOf("error" to "No project")
        val configName = body["configuration"] as? String
        var result: Map<String, Any?> = emptyMap()
        edt {
            val rm = RunManager.getInstance(project)
            val settings = if (configName != null) rm.findConfigurationByName(configName) else rm.selectedConfiguration
            if (settings == null) {
                result = mapOf("error" to "No run configuration" + if (configName != null) ": $configName" else "")
                return@edt
            }
            ProgramRunnerUtil.executeConfiguration(settings, DefaultDebugExecutor.getDebugExecutorInstance())
            result = mapOf("sessionId" to "session-${System.currentTimeMillis()}", "status" to "starting",
                "configuration" to settings.name)
        }
        return result
    }

    private fun stopDebug() = sessionAction("stop") { it.stop() }
    private fun pauseDebug() = sessionAction("pause") { it.pause() }
    private fun resumeDebug() = sessionAction("resume") { it.resume() }
    private fun step(type: String) = sessionAction(type) { s ->
        when (type) { "over" -> s.stepOver(false); "into" -> s.stepInto(); "out" -> s.stepOut() }
    }

    private fun sessionAction(name: String, action: (com.intellij.xdebugger.XDebugSession) -> Unit): Map<String, Any?> {
        val project = project() ?: return mapOf("error" to "No project")
        var result: Map<String, Any?> = emptyMap()
        edt {
            val session = XDebuggerManager.getInstance(project).currentSession
            if (session == null) { result = mapOf("error" to "No active debug session"); return@edt }
            action(session)
            result = mapOf("success" to true, "action" to name)
        }
        return result
    }

    // ===== Inspection =====

    private fun getVariables(): Map<String, Any?> {
        val project = project() ?: return mapOf("variables" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        edt {
            val session = XDebuggerManager.getInstance(project).currentSession
            if (session == null) { result = mapOf("error" to "No debug session"); return@edt }
            val frame = session.currentStackFrame
            if (frame == null) { result = mapOf("error" to "No stack frame"); return@edt }
            val pos = frame.sourcePosition
            result = mapOf("variables" to emptyList<Any>(),
                "frame" to mapOf("file" to (pos?.file?.name ?: "?"), "line" to ((pos?.line ?: 0) + 1)),
                "note" to "Full variable extraction requires async XValue callbacks - use Rider's Variables panel")
        }
        return result
    }

    private fun evaluate(body: Map<String, Any?>): Map<String, Any?> {
        val expr = body["expression"] as? String ?: return mapOf("error" to "Missing 'expression'")
        return mapOf("expression" to expr, "status" to "submitted",
            "note" to "Use Rider's Evaluate Expression dialog (Alt+F8) for full evaluation")
    }

    private fun getStackTrace(): Map<String, Any?> {
        val project = project() ?: return mapOf("frames" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        edt {
            val session = XDebuggerManager.getInstance(project).currentSession
            if (session == null) { result = mapOf("error" to "No debug session"); return@edt }
            val frame = session.currentStackFrame
            val pos = frame?.sourcePosition
            val frames = if (pos != null) listOf(mapOf(
                "method" to (frame?.evaluationExpression ?: "unknown"),
                "file" to pos.file.name, "line" to pos.line + 1
            )) else emptyList()
            result = mapOf("frames" to frames)
        }
        return result
    }

    private fun getThreads(): Map<String, Any?> {
        val project = project() ?: return mapOf("threads" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        edt {
            val session = XDebuggerManager.getInstance(project).currentSession
            if (session == null) { result = mapOf("error" to "No debug session"); return@edt }
            val ctx = session.suspendContext
            val stack = ctx?.activeExecutionStack
            val threads = if (stack != null) listOf(mapOf(
                "id" to 1, "name" to stack.displayName, "state" to "suspended", "isMain" to true
            )) else emptyList()
            result = mapOf("threads" to threads)
        }
        return result
    }

    // ===== Utilities =====

    private fun project() = ProjectManager.getInstance().openProjects.firstOrNull()

    private fun edt(block: () -> Unit) = ApplicationManager.getApplication().invokeAndWait(block)

    private fun body(request: FullHttpRequest): Map<String, Any?> = try {
        val bytes = ByteArray(request.content().readableBytes())
        request.content().readBytes(bytes)
        @Suppress("UNCHECKED_CAST")
        gson.fromJson(String(bytes, Charsets.UTF_8), Map::class.java) as Map<String, Any?>
    } catch (_: Exception) { emptyMap() }

    private fun seg(path: String, index: Int): String = path.split("/").filter { it.isNotEmpty() }[index - 1]

    private fun parseId(id: String): Pair<String, Int>? {
        val clean = id.removePrefix("bp-")
        val idx = clean.lastIndexOf(':')
        if (idx < 0) return null
        val line = clean.substring(idx + 1).toIntOrNull() ?: return null
        return clean.substring(0, idx) to line
    }

    private fun findBp(fileName: String, line: Int): XLineBreakpoint<*>? {
        val project = project() ?: return null
        return XDebuggerManager.getInstance(project).breakpointManager.allBreakpoints
            .filterIsInstance<XLineBreakpoint<*>>()
            .find { it.fileUrl.endsWith(fileName) && it.line == line - 1 }
    }

    private fun findFile(path: String): com.intellij.openapi.vfs.VirtualFile? {
        LocalFileSystem.getInstance().findFileByPath(path)?.let { return it }
        val project = project() ?: return null
        val basePath = project.basePath
        if (basePath != null) LocalFileSystem.getInstance().findFileByPath("$basePath/$path")?.let { return it }
        val name = path.substringAfterLast("/").substringAfterLast("\\")
        return FilenameIndex.getVirtualFilesByName(name, GlobalSearchScope.projectScope(project)).firstOrNull()
    }
}
