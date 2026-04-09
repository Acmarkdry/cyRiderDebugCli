## 1. Project Scaffolding & Git Setup

- [x] 1.1 Initialize Git repository with `git init`
- [x] 1.2 Create `.gitignore` (Python template: __pycache__, .venv, .pytest_cache, dist/, *.egg-info, .ruff_cache)
- [x] 1.3 Create `pyproject.toml` with project metadata, dependencies (mcp, httpx, websockets, pydantic), dev dependencies (pytest, pytest-asyncio, pytest-cov, ruff), and src layout configuration
- [x] 1.4 Create `README.md` with project overview, architecture diagram, setup instructions, usage examples, and CLI command reference
- [x] 1.5 Create `LICENSE` file (MIT)
- [x] 1.6 Create directory structure: `src/rider_debug_mcp/`, `src/rider_debug_mcp/middleware/`, `src/rider_debug_mcp/handlers/`, `src/rider_debug_mcp/gateway/`, `src/rider_debug_mcp/analysis/`, `tests/`
- [x] 1.7 Create all `__init__.py` files for the package

## 2. Data Models (Pydantic)

- [x] 2.1 Create `src/rider_debug_mcp/gateway/models.py` with Pydantic models: `Breakpoint`, `DebugSession`, `Variable`, `StackFrame`, `ThreadInfo`
- [x] 2.2 Create `src/rider_debug_mcp/gateway/events.py` with event models: `BreakpointHitEvent`, `ExceptionEvent`, `ProcessExitEvent`, `DebugEvent` (union type)
- [x] 2.3 Create `src/rider_debug_mcp/middleware/models.py` with `ParsedCommand`, `CommandResult`, `ErrorResult` response models
- [x] 2.4 Create `src/rider_debug_mcp/analysis/models.py` with `CrashContext`, `CrashReport`, `AnnotatedStackFrame` models
- [x] 2.5 Write unit tests for all Pydantic models validation in `tests/test_models.py`

## 3. Middleware - Command Parser

- [x] 3.1 Create `src/rider_debug_mcp/middleware/parser.py` with `CommandParser` class supporting: positional args, named args (`--key value`), context targets (`@target`), comments (`# comment`), multi-line batch parsing
- [x] 3.2 Implement `ParseError` exception class with descriptive error messages
- [x] 3.3 Write unit tests for CommandParser in `tests/test_parser.py`: single command, named args, context target, batch, comments, error cases

## 4. Middleware - Command Router

- [x] 4.1 Create `src/rider_debug_mcp/middleware/router.py` with `CommandRouter` class: handler registry, command dispatch, unknown command handling with suggestions (fuzzy match)
- [x] 4.2 Define `BaseHandler` abstract class with `handle(command: ParsedCommand) -> CommandResult` interface
- [x] 4.3 Write unit tests for CommandRouter in `tests/test_router.py`: routing to correct handler, unknown command error, suggestion matching

## 5. Middleware - Session Manager

- [x] 5.1 Create `src/rider_debug_mcp/middleware/session.py` with `SessionManager` class: debug session tracking, breakpoint cache, operation history (last N operations)
- [x] 5.2 Write unit tests for SessionManager in `tests/test_session.py`: session lifecycle, breakpoint caching, context query output

## 6. Rider Gateway Client

- [x] 6.1 Create `src/rider_debug_mcp/gateway/client.py` with `RiderClient` class: port auto-discovery (63342-63352), HTTP connection via httpx (async)
- [x] 6.2 Implement breakpoint management methods: `add_breakpoint`, `remove_breakpoint`, `enable_breakpoint`, `disable_breakpoint`, `list_breakpoints`
- [x] 6.3 Implement debug control methods: `start_debug`, `stop_debug`, `pause`, `resume`, `step_over`, `step_into`, `step_out`
- [x] 6.4 Implement inspection methods: `get_variables`, `evaluate_expression`, `get_stack_trace`, `get_threads`
- [x] 6.5 Implement connection health check and error handling (connection refused, timeout, invalid response)
- [x] 6.6 Create `src/rider_debug_mcp/gateway/events.py` EventListener with WebSocket connection, event parsing, reconnection with exponential backoff
- [x] 6.7 Write unit tests for RiderClient (mocked HTTP responses) in `tests/test_gateway.py`
- [x] 6.8 Write unit tests for EventListener (mocked WebSocket) in `tests/test_events.py`

## 7. Command Handlers

- [x] 7.1 Create `src/rider_debug_mcp/handlers/breakpoint.py` with `BreakpointHandler`: commands `add_breakpoint`, `remove_breakpoint`, `enable_breakpoint`, `disable_breakpoint`, `list_breakpoints`, `clear_breakpoints`
- [x] 7.2 Create `src/rider_debug_mcp/handlers/debug.py` with `DebugHandler`: commands `start_debug`, `stop_debug`, `pause`, `resume`, `step_over`, `step_into`, `step_out`
- [x] 7.3 Create `src/rider_debug_mcp/handlers/inspect.py` with `InspectHandler`: commands `get_variables`, `evaluate`, `get_stack_trace`, `get_threads`
- [x] 7.4 Create `src/rider_debug_mcp/handlers/analysis.py` with `AnalysisHandler`: commands `analyze_crash`, `crash_report`, `crash_history`
- [x] 7.5 Register all handlers in the CommandRouter
- [x] 7.6 Write unit tests for all handlers (mocked gateway) in `tests/test_handlers.py`

## 8. Crash Analysis Engine

- [x] 8.1 Create `src/rider_debug_mcp/analysis/crash.py` with `CrashAnalyzer`: auto-subscribe to exception/exit events, collect crash context (stack, variables, threads, breakpoint history)
- [x] 8.2 Implement .NET stack trace parser: parse raw text into `AnnotatedStackFrame` list, tag user code vs framework code
- [x] 8.3 Create `src/rider_debug_mcp/analysis/report.py` with `ReportGenerator`: generate structured CrashReport from CrashContext (summary, exception chain, annotated stack, variable snapshot, investigation suggestions)
- [x] 8.4 Implement crash history storage (in-memory, per session)
- [x] 8.5 Write unit tests for CrashAnalyzer and ReportGenerator in `tests/test_analysis.py`

## 9. MCP Server

- [x] 9.1 Create `src/rider_debug_mcp/server.py` with MCP server using `mcp` Python SDK: register `rider_cli` tool with comprehensive description (syntax, examples, available commands), register `rider_query` tool with description
- [x] 9.2 Implement `rider_cli` handler: receive command string → CommandParser → CommandRouter → return formatted result, support multi-line batch execution
- [x] 9.3 Implement `rider_query` handler: support `help`, `help <command>`, `context`, `crash_report`, `crash_history`, `breakpoints`, `logs`, `health`
- [x] 9.4 Configure stdio transport for MCP communication
- [x] 9.5 Create `src/rider_debug_mcp/__main__.py` entry point for `python -m rider_debug_mcp`
- [x] 9.6 Write unit tests for MCP server tool registration and routing in `tests/test_server.py`

## 10. Integration & Help System

- [x] 10.1 Implement help system: command registry with descriptions, syntax, parameter info, examples; `help` lists all commands grouped by domain; `help <command>` shows detailed help
- [x] 10.2 Create `tests/conftest.py` with shared fixtures: mock RiderClient, mock session, sample data factories
- [x] 10.3 Run full test suite and verify all tests pass

## 11. CI/CD & GitHub Actions

- [x] 11.1 Create `.github/workflows/ci.yml`: trigger on push to main + PRs, matrix (Python 3.11, 3.12), steps: checkout → setup-python → install deps → ruff check → pytest --cov → coverage report
- [x] 11.2 Add ruff configuration in `pyproject.toml` (line length, target Python version, select rules)
- [x] 11.3 Verify CI workflow passes locally with `ruff check` and `pytest`

## 12. Documentation & Finalization

- [x] 12.1 Update `README.md` with complete CLI command reference table, MCP configuration example (for Claude/Cursor), and architecture diagram
- [x] 12.2 Add MCP client configuration example (JSON snippet for adding this server to MCP settings)
- [x] 12.3 Create initial git commit with conventional commit message
