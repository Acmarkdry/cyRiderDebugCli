# Rider Debug MCP

MCP (Model Context Protocol) server for JetBrains Rider debugger integration. Enables AI assistants to manage breakpoints, control debug sessions, inspect runtime state, and analyze crashes directly through Rider IDE.

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐     ┌───────��──────┐
│   AI Assistant   │◄───►│           MCP Server (stdio)             │     │  Rider IDE   │
│ (Claude/Cursor)  │     │  ┌─────────┐  ┌────────────────────┐    │     │              │
│                  │     │  │rider_cli│  │   rider_query      │    │     │  Built-in    │
└─────────────────┘     │  └────┬────┘  └────────┬───────────┘    │     │  Server      │
                        │       │                 │                │     │  :63342+     │
                        │  ┌────▼─────────────────▼───────────┐   │     │              │
                        │  │       Middleware Layer            │   │     │  ┌────────┐  │
                        │  │  ┌────────┐ ┌────────┐ ┌───────┐│   │     │  │Debugger│  │
                        │  │  │ Parser │ │ Router │ │Session││   │     │  └────────┘  │
                        │  │  └────────┘ └────────┘ └───────┘│   │     │              │
                        │  └──────────────┬───────────────────┘   │     │  ┌────────┐  │
                        │                 │                        │     │  │  REST  │  │
                        │  ┌──────────────▼───────────────────┐   │     │  │  API   │  │
                        │  │         Handlers                  │   │◄───►│  └────────┘  │
                        │  │ Breakpoint│Debug│Inspect│Analysis │   │HTTP │              │
                        │  └──────────────┬───────────────────┘   │     │  ┌────────┐  │
                        │                 │                        │  WS │  │ Events │  │
                        │  ┌──────────────▼───────────────────┐   │◄───►│  │ Stream │  │
                        │  │       Rider Gateway              │   │     │  └────────┘  │
                        │  │  HTTP Client  │  Event Listener  │   │     │              │
                        │  └──────────────────────────────────┘   │     └──────────────┘
                        │                                          │
                        │  ┌──────────────────────────────────┐   │
                        │  │       Crash Analyzer             │   │
                        │  │  Stack Parser │ Report Generator │   │
                        │  └──────────────────────────────────┘   │
                        └──────────────────────────────────────────┘
```

## Features

- **Breakpoint Management**: Add, remove, enable, disable, list, and clear breakpoints
- **Debug Control**: Start, stop, pause, resume, step over/into/out
- **Runtime Inspection**: Read variables, evaluate expressions, view stack traces and threads
- **Crash Analysis**: Auto-detect crashes, collect context, generate structured reports
- **CLI Syntax**: Simple command syntax with batch execution, context targets, and named arguments

## Prerequisites

- Python 3.11+
- JetBrains Rider IDE (running with built-in server enabled)

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd cyRiderDebugCli

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install in development mode
pip install -e ".[dev]"
```

## Usage

### Running the MCP Server

```bash
python -m rider_debug_mcp
```

### MCP Client Configuration

Add to your MCP client settings (e.g., Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "rider-debug": {
      "command": "python",
      "args": ["-m", "rider_debug_mcp"],
      "cwd": "/path/to/cyRiderDebugCli"
    }
  }
}
```

### CLI Command Reference

#### Breakpoint Commands (`rider_cli`)

| Command | Syntax | Description |
|---------|--------|-------------|
| `add_breakpoint` | `add_breakpoint <file> <line> [--condition "<expr>"]` | Add a breakpoint |
| `remove_breakpoint` | `remove_breakpoint <id>` | Remove a breakpoint |
| `enable_breakpoint` | `enable_breakpoint <id>` | Enable a breakpoint |
| `disable_breakpoint` | `disable_breakpoint <id>` | Disable a breakpoint |
| `list_breakpoints` | `list_breakpoints` | List all breakpoints |
| `clear_breakpoints` | `clear_breakpoints` | Remove all breakpoints |

#### Debug Control Commands (`rider_cli`)

| Command | Syntax | Description |
|---------|--------|-------------|
| `start_debug` | `start_debug [config_name]` | Start debug session |
| `stop_debug` | `stop_debug` | Stop debug session |
| `pause` | `pause` | Pause execution |
| `resume` | `resume` | Resume execution |
| `step_over` | `step_over` | Step over current line |
| `step_into` | `step_into` | Step into function call |
| `step_out` | `step_out` | Step out of current function |

#### Inspection Commands (`rider_cli`)

| Command | Syntax | Description |
|---------|--------|-------------|
| `get_variables` | `get_variables` | Get local variables |
| `evaluate` | `evaluate <expression>` | Evaluate expression |
| `get_stack_trace` | `get_stack_trace` | Get call stack |
| `get_threads` | `get_threads` | Get thread list |

#### Analysis Commands (`rider_cli`)

| Command | Syntax | Description |
|---------|--------|-------------|
| `analyze_crash` | `analyze_crash` | Analyze latest crash |
| `crash_report` | `crash_report` | Get crash report |
| `crash_history` | `crash_history` | List crash history |

#### Query Commands (`rider_query`)

| Query | Description |
|-------|-------------|
| `help` | List all available commands |
| `help <command>` | Detailed help for a command |
| `context` | Current debug session status |
| `crash_report` | Latest crash report |
| `crash_history` | All crash reports this session |
| `breakpoints` | Current breakpoints |
| `logs` | Recent operation logs |
| `health` | Connection health status |

### Example Usage (via AI)

```
# Set breakpoints and start debugging
@PlayerController.cs
add_breakpoint 42
add_breakpoint 55 --condition "health <= 0"
start_debug
```

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
```

## License

MIT
