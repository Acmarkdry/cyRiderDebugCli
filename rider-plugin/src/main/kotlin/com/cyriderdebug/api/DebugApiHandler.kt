package com.cyriderdebug.api

import com.google.gson.Gson
import com.google.gson.JsonParser
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.ProjectManager
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpMethod
import io.netty.handler.codec.http.HttpResponseStatus
import io.netty.handler.codec.http.QueryStringDecoder
import org.jetbrains.ide.HttpRequestHandler
import org.jetbrains.ide.RestService
import java.io.BufferedReader
import java.io.InputStreamReader
import io.netty.buffer.ByteBufInputStream

/**
 * REST API handler that bridges HTTP requests to Rider's debugger.
 *
 * All endpoints are under /api/debug/* and are registered via the
 * built-in HTTP server's extension point.
 */
class DebugApiHandler : HttpRequestHandler() {

    private val gson = Gson()

    override fun isSupported(request: FullHttpRequest): Boolean {
        return request.uri().startsWith("/api/debug")
    }

    override fun process(
        urlDecoder: QueryStringDecoder,
        request: FullHttpRequest,
        context: ChannelHandlerContext
    ): Boolean {
        val path = urlDecoder.path()
        val method = request.method()

        try {
            val result = when {
                // --- Breakpoint endpoints ---
                path == "/api/debug/breakpoints" && method == HttpMethod.POST -> {
                    val body = readBody(request)
                    handleAddBreakpoint(body)
                }
                path == "/api/debug/breakpoints" && method == HttpMethod.GET -> {
                    handleListBreakpoints()
                }
                path.startsWith("/api/debug/breakpoints/") && path.endsWith("/enable") && method == HttpMethod.POST -> {
                    val id = extractSegment(path, "/api/debug/breakpoints/", "/enable")
                    handleEnableBreakpoint(id, true)
                }
                path.startsWith("/api/debug/breakpoints/") && path.endsWith("/disable") && method == HttpMethod.POST -> {
                    val id = extractSegment(path, "/api/debug/breakpoints/", "/disable")
                    handleEnableBreakpoint(id, false)
                }
                path.startsWith("/api/debug/breakpoints/") && method == HttpMethod.DELETE -> {
                    val id = path.substringAfter("/api/debug/breakpoints/")
                    handleRemoveBreakpoint(id)
                }

                // --- Debug control endpoints ---
                path == "/api/debug/start" && method == HttpMethod.POST -> {
                    val body = readBody(request)
                    handleStartDebug(body)
                }
                path == "/api/debug/stop" && method == HttpMethod.POST -> handleStopDebug()
                path == "/api/debug/pause" && method == HttpMethod.POST -> handlePause()
                path == "/api/debug/resume" && method == HttpMethod.POST -> handleResume()
                path == "/api/debug/stepOver" && method == HttpMethod.POST -> handleStep("over")
                path == "/api/debug/stepInto" && method == HttpMethod.POST -> handleStep("into")
                path == "/api/debug/stepOut" && method == HttpMethod.POST -> handleStep("out")

                // --- Inspection endpoints ---
                path == "/api/debug/variables" && method == HttpMethod.GET -> {
                    val frameIndex = urlDecoder.parameters()["frameIndex"]?.firstOrNull()?.toIntOrNull() ?: 0
                    handleGetVariables(frameIndex)
                }
                path == "/api/debug/evaluate" && method == HttpMethod.POST -> {
                    val body = readBody(request)
                    handleEvaluate(body)
                }
                path == "/api/debug/stackTrace" && method == HttpMethod.GET -> {
                    val threadId = urlDecoder.parameters()["threadId"]?.firstOrNull()?.toIntOrNull()
                    handleGetStackTrace(threadId)
                }
                path == "/api/debug/threads" && method == HttpMethod.GET -> handleGetThreads()

                // --- WebSocket events endpoint (placeholder) ---
                path == "/api/debug/events" -> {
                    mapOf("error" to "WebSocket endpoint – connect via ws:// protocol")
                }

                else -> {
                    RestService.sendStatus(HttpResponseStatus.NOT_FOUND, false, context.channel())
                    return true
                }
            }

            val json = gson.toJson(result)
            RestService.send(json, request, context.channel())

        } catch (e: Exception) {
            val errorJson = gson.toJson(mapOf("error" to (e.message ?: "Internal error")))
            RestService.send(errorJson, request, context.channel())
        }

        return true
    }

    // ===== Breakpoint handlers =====

    private fun handleAddBreakpoint(body: Map<String, Any?>): Map<String, Any?> {
        val file = body["file"] as? String ?: return mapOf("error" to "Missing 'file' field")
        val line = (body["line"] as? Number)?.toInt() ?: return mapOf("error" to "Missing 'line' field")
        val condition = body["condition"] as? String

        // Use XDebuggerManager to toggle breakpoint via IntelliJ Platform API
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        val bpId = "bp-${file.substringAfterLast("/")}:$line"

        // Schedule on EDT to interact with IDE APIs
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            try {
                val xDebuggerManager = com.intellij.xdebugger.XDebuggerManager.getInstance(project)
                val breakpointManager = xDebuggerManager.breakpointManager

                // Find the virtual file
                val vFile = findVirtualFile(project, file)
                if (vFile == null) {
                    result = mapOf("error" to "File not found: $file")
                    return@invokeAndWait
                }

                // Add a line breakpoint via the breakpoint manager
                val lineType = com.intellij.xdebugger.breakpoints.XBreakpointType.EXTENSION_POINT_NAME
                    .extensionList
                    .filterIsInstance<com.intellij.xdebugger.breakpoints.XLineBreakpointType<*>>()
                    .firstOrNull()

                if (lineType != null) {
                    @Suppress("UNCHECKED_CAST")
                    val bp = breakpointManager.addLineBreakpoint(
                        lineType as com.intellij.xdebugger.breakpoints.XLineBreakpointType<com.intellij.xdebugger.breakpoints.XBreakpointProperties<*>>,
                        vFile.url,
                        line - 1,  // 0-indexed
                        null
                    )
                    if (bp != null && condition != null) {
                        bp.conditionExpression = com.intellij.xdebugger.XExpression.fromText(condition)
                    }
                    result = mapOf(
                        "id" to bpId,
                        "file" to file,
                        "line" to line,
                        "enabled" to (bp?.isEnabled ?: true),
                        "condition" to condition
                    )
                } else {
                    result = mapOf("error" to "No line breakpoint type available")
                }
            } catch (e: Exception) {
                result = mapOf("error" to "Failed to add breakpoint: ${e.message}")
            }
        }
        return result
    }

    private fun handleRemoveBreakpoint(id: String): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val xDebuggerManager = com.intellij.xdebugger.XDebuggerManager.getInstance(project)
            val breakpointManager = xDebuggerManager.breakpointManager
            // Parse id to find matching breakpoint (format: bp-File.cs:42)
            val parts = id.removePrefix("bp-").split(":")
            if (parts.size == 2) {
                val fileName = parts[0]
                val line = parts[1].toIntOrNull()
                val allBps = breakpointManager.allBreakpoints
                val matchedBp = allBps.find { bp ->
                    bp is com.intellij.xdebugger.breakpoints.XLineBreakpoint<*> &&
                    bp.fileUrl.endsWith(fileName) &&
                    bp.line == (line?.minus(1) ?: -1)
                }
                if (matchedBp != null) {
                    breakpointManager.removeBreakpoint(matchedBp)
                    result = mapOf("removed" to true, "id" to id)
                } else {
                    result = mapOf("error" to "Breakpoint not found: $id")
                }
            } else {
                result = mapOf("error" to "Invalid breakpoint ID format: $id")
            }
        }
        return result
    }

    private fun handleEnableBreakpoint(id: String, enabled: Boolean): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val xDebuggerManager = com.intellij.xdebugger.XDebuggerManager.getInstance(project)
            val bpMgr = xDebuggerManager.breakpointManager
            val parts = id.removePrefix("bp-").split(":")
            if (parts.size == 2) {
                val allBps = bpMgr.allBreakpoints
                val matchedBp = allBps.find { bp ->
                    bp is com.intellij.xdebugger.breakpoints.XLineBreakpoint<*> &&
                    bp.fileUrl.endsWith(parts[0]) &&
                    bp.line == (parts[1].toIntOrNull()?.minus(1) ?: -1)
                }
                if (matchedBp != null) {
                    matchedBp.isEnabled = enabled
                    result = mapOf("id" to id, "enabled" to enabled)
                } else {
                    result = mapOf("error" to "Breakpoint not found: $id")
                }
            } else {
                result = mapOf("error" to "Invalid breakpoint ID: $id")
            }
        }
        return result
    }

    private fun handleListBreakpoints(): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("breakpoints" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val xDebuggerManager = com.intellij.xdebugger.XDebuggerManager.getInstance(project)
            val bps = xDebuggerManager.breakpointManager.allBreakpoints
                .filterIsInstance<com.intellij.xdebugger.breakpoints.XLineBreakpoint<*>>()
                .map { bp ->
                    val fileName = bp.fileUrl.substringAfterLast("/")
                    mapOf(
                        "id" to "bp-$fileName:${bp.line + 1}",
                        "file" to fileName,
                        "line" to bp.line + 1,
                        "enabled" to bp.isEnabled,
                        "condition" to bp.conditionExpression?.expression
                    )
                }
            result = mapOf("breakpoints" to bps)
        }
        return result
    }

    // ===== Debug control handlers =====

    private fun handleStartDebug(body: Map<String, Any?>): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        val configName = body["configuration"] as? String

        // Use ExecutionManager to start debug
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            try {
                val runManager = com.intellij.execution.RunManager.getInstance(project)
                val settings = if (configName != null) {
                    runManager.findConfigurationByName(configName)
                } else {
                    runManager.selectedConfiguration
                }

                if (settings == null) {
                    result = mapOf("error" to "No run configuration found" +
                        (if (configName != null) ": $configName" else ". Select a configuration in Rider first."))
                    return@invokeAndWait
                }

                val executor = com.intellij.execution.executors.DefaultDebugExecutor.getDebugExecutorInstance()
                com.intellij.execution.ProgramRunnerUtil.executeConfiguration(settings, executor)

                result = mapOf(
                    "sessionId" to "session-${System.currentTimeMillis()}",
                    "status" to "starting",
                    "configuration" to settings.name
                )
            } catch (e: Exception) {
                result = mapOf("error" to "Failed to start debug: ${e.message}")
            }
        }
        return result
    }

    private fun handleStopDebug(): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session != null) {
                session.stop()
                result = mapOf("stopped" to true)
            } else {
                result = mapOf("error" to "No active debug session")
            }
        }
        return result
    }

    private fun handlePause(): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session != null) {
                session.pause()
                result = mapOf("paused" to true)
            } else {
                result = mapOf("error" to "No active debug session")
            }
        }
        return result
    }

    private fun handleResume(): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session != null) {
                session.resume()
                result = mapOf("resumed" to true)
            } else {
                result = mapOf("error" to "No active debug session")
            }
        }
        return result
    }

    private fun handleStep(type: String): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session != null) {
                when (type) {
                    "over" -> session.stepOver(false)
                    "into" -> session.stepInto()
                    "out" -> session.stepOut()
                }
                result = mapOf("step" to type, "success" to true)
            } else {
                result = mapOf("error" to "No active debug session")
            }
        }
        return result
    }

    // ===== Inspection handlers =====

    private fun handleGetVariables(frameIndex: Int): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("variables" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session == null) {
                result = mapOf("error" to "No active debug session")
                return@invokeAndWait
            }
            val currentFrame = session.currentStackFrame
            if (currentFrame == null) {
                result = mapOf("error" to "No current stack frame (is the debugger paused?)")
                return@invokeAndWait
            }
            // Note: Full variable tree extraction requires async callbacks.
            // For MVP, return frame info and basic data.
            result = mapOf(
                "variables" to emptyList<Any>(),
                "frame" to mapOf(
                    "name" to (currentFrame.evaluationExpression ?: "unknown"),
                    "sourcePosition" to currentFrame.sourcePosition?.let {
                        mapOf("file" to it.file.name, "line" to it.line + 1)
                    }
                ),
                "note" to "Variable tree extraction requires async XValue enumeration. See plugin docs."
            )
        }
        return result
    }

    private fun handleEvaluate(body: Map<String, Any?>): Map<String, Any?> {
        val expression = body["expression"] as? String ?: return mapOf("error" to "Missing 'expression'")
        val project = getActiveProject() ?: return mapOf("error" to "No project open")
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session == null) {
                result = mapOf("error" to "No active debug session")
                return@invokeAndWait
            }
            // Expression evaluation in XDebugger is async.
            // For MVP, we acknowledge the request.
            result = mapOf(
                "expression" to expression,
                "status" to "submitted",
                "note" to "Expression evaluation is async. Full result requires XValue callback integration."
            )
        }
        return result
    }

    private fun handleGetStackTrace(threadId: Int?): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("frames" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session == null) {
                result = mapOf("error" to "No active debug session")
                return@invokeAndWait
            }
            val currentFrame = session.currentStackFrame
            val frameInfo = currentFrame?.sourcePosition?.let {
                mapOf(
                    "method" to (currentFrame.evaluationExpression ?: "unknown"),
                    "file" to it.file.name,
                    "line" to it.line + 1
                )
            }
            result = mapOf(
                "frames" to listOfNotNull(frameInfo),
                "note" to "Full stack enumeration requires XExecutionStack traversal."
            )
        }
        return result
    }

    private fun handleGetThreads(): Map<String, Any?> {
        val project = getActiveProject() ?: return mapOf("threads" to emptyList<Any>())
        var result: Map<String, Any?> = emptyMap()
        ApplicationManager.getApplication().invokeAndWait {
            val session = com.intellij.xdebugger.XDebuggerManager.getInstance(project).currentSession
            if (session == null) {
                result = mapOf("error" to "No active debug session")
                return@invokeAndWait
            }
            val suspendContext = session.suspendContext
            if (suspendContext == null) {
                result = mapOf("threads" to emptyList<Any>(), "note" to "Debugger is running, not suspended.")
                return@invokeAndWait
            }
            // Thread info from execution stacks
            val activeStack = suspendContext.activeExecutionStack
            val threads = mutableListOf<Map<String, Any?>>()
            if (activeStack != null) {
                threads.add(mapOf(
                    "id" to 1,
                    "name" to activeStack.displayName,
                    "state" to "suspended",
                    "isMain" to true
                ))
            }
            result = mapOf("threads" to threads)
        }
        return result
    }

    // ===== Utility =====

    private fun getActiveProject(): com.intellij.openapi.project.Project? {
        return ProjectManager.getInstance().openProjects.firstOrNull()
    }

    private fun findVirtualFile(
        project: com.intellij.openapi.project.Project,
        filePath: String
    ): com.intellij.openapi.vfs.VirtualFile? {
        // Try absolute path first
        val vfs = com.intellij.openapi.vfs.LocalFileSystem.getInstance()
        vfs.findFileByPath(filePath)?.let { return it }

        // Try relative to project base path
        val basePath = project.basePath ?: return null
        vfs.findFileByPath("$basePath/$filePath")?.let { return it }

        // Search by filename in project
        val fileName = filePath.substringAfterLast("/").substringAfterLast("\\")
        val scope = com.intellij.psi.search.GlobalSearchScope.projectScope(project)
        val files = com.intellij.openapi.fileTypes.FileTypeManager.getInstance()
            .let { com.intellij.psi.search.FilenameIndex.getVirtualFilesByName(fileName, scope) }
        return files.firstOrNull()
    }

    private fun readBody(request: FullHttpRequest): Map<String, Any?> {
        return try {
            val content = request.content()
            if (content.readableBytes() == 0) return emptyMap()
            val bytes = ByteArray(content.readableBytes())
            content.readBytes(bytes)
            @Suppress("UNCHECKED_CAST")
            gson.fromJson(String(bytes, Charsets.UTF_8), Map::class.java) as Map<String, Any?>
        } catch (e: Exception) {
            emptyMap()
        }
    }

    private fun extractSegment(path: String, prefix: String, suffix: String): String {
        return path.removePrefix(prefix).removeSuffix(suffix)
    }
}
