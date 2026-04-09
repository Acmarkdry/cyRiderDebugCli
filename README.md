<p align="center">
  <h1 align="center">🛠️ Rider Debug MCP</h1>
  <p align="center">
    <strong>MCP Server for JetBrains Rider Debugger Integration</strong>
  </p>
  <p align="center">
    <a href="https://github.com/Acmarkdry/cyRiderDebugCli/actions"><img src="https://github.com/Acmarkdry/cyRiderDebugCli/workflows/CI/badge.svg" alt="CI Status"></a>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
    <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatible-purple.svg" alt="MCP Compatible"></a>
  </p>
</p>

---

> 让 AI 助手直接驱动 JetBrains Rider 调试器 — 自动设置断点、控制调试流程、读取运行时变量、智能分析崩溃。

## ✨ Features

| 功能域 | 能力 |
|--------|------|
| **断点管理** | 添加 / 删除 / 启用 / 禁用 / 列表 / 条件断点 / 一键清除 |
| **调试控制** | 启动 / 停止 / 暂停 / 恢复 / Step Over / Step Into / Step Out |
| **运行时检查** | 读取变量、表达式求值、调用栈查看、线程列表 |
| **崩溃分析** | 自动捕获异常、.NET 堆栈解析、用户代码标注、结构化报告生成 |
| **CLI 语法** | 批量命令、`@context` 文件上下文、`--named` 参数、`# 注释` |

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────────┐     ┌──────────────┐
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

## 📁 Project Structure

```
cyRiderDebugCli/
├── src/rider_debug_mcp/
│   ├── server.py              # MCP Server (rider_cli + rider_query)
│   ├── __main__.py            # Entry point: python -m rider_debug_mcp
│   ├── middleware/
│   │   ├── parser.py          # CLI command parser
│   │   ├── router.py          # Command router + BaseHandler
│   │   ├── session.py         # Debug session state manager
│   │   └── help.py            # Help system
│   ├── handlers/
│   │   ├── breakpoint.py      # Breakpoint CRUD commands
│   │   ├── debug.py           # Debug control commands
│   │   ├── inspect.py         # Variable/stack inspection
│   │   └── analysis.py        # Crash analysis commands
│   ├── gateway/
│   │   ├── client.py          # Rider HTTP client (async, auto-discovery)
│   │   ├── models.py          # Pydantic data models
│   │   └── events.py          # WebSocket event listener
│   └── analysis/
│       ├── crash.py           # Crash analyzer engine
│       ├── report.py          # Report generator
│       └── models.py          # Analysis data models
├── tests/                     # 137 unit tests
├── .github/workflows/ci.yml   # GitHub Actions CI
├── pyproject.toml             # Project config & dependencies
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **JetBrains Rider** (running with built-in server enabled)
> 💡 **无需安装任何 Rider 插件！** 本项目使用 JetBrains 内置 HTTP Server 的原生端点（`/api/internal/executeAction`、`/api/internal/runScript`），直接与 Rider 调试器交互。只需在 Rider 中启用 **Allow unsigned requests**（Settings → Build → Debugger）。

### Installation

```bash
# Clone
git clone https://github.com/Acmarkdry/cyRiderDebugCli.git
cd cyRiderDebugCli

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# Install (with dev dependencies)
pip install -e ".[dev]"
```

### Run the MCP Server

```bash
python -m rider_debug_mcp
```

## 🔌 MCP Client Configuration

### Claude Desktop

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "rider-debug": {
      "command": "python",
      "args": ["-m", "rider_debug_mcp"],
      "cwd": "D:/path/to/cyRiderDebugCli"
    }
  }
}
```

### Cursor / Windsurf / CodeMaker

在 MCP 设置中添加：

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

### VS Code (Copilot MCP)

在 `.vscode/mcp.json` 中：

```json
{
  "servers": {
    "rider-debug": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "rider_debug_mcp"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

## 📖 Command Reference

### MCP Tools

本服务器提供 **两个 MCP 工具**，遵循双接口模式：

| Tool | 用途 |
|------|------|
| `rider_cli` | 执行操作型命令（设置断点、控制调试等） |
| `rider_query` | 查询信息（帮助、状态、崩溃报告等） |

### rider_cli Commands

#### Breakpoint Management

```bash
add_breakpoint <file> <line> [--condition "<expr>"]   # 添加断点
remove_breakpoint <id>                                 # 删除断点
enable_breakpoint <id>                                 # 启用断点
disable_breakpoint <id>                                # 禁用断点
list_breakpoints                                       # 列出所有断点
clear_breakpoints                                      # 清除所有断点
```

#### Debug Control

```bash
start_debug [config_name]    # 启动调试会话
stop_debug                   # 停止调试
pause                        # 暂停执行
resume                       # 恢复执行
step_over                    # 单步跳过
step_into                    # 单步进入
step_out                     # 单步跳出
```

#### Runtime Inspection

```bash
get_variables [frame_index]  # 获取局部变量
evaluate <expression>        # 表达式求值
get_stack_trace [thread_id]  # 获取调用栈
get_threads                  # 获取线程列表
```

#### Crash Analysis

```bash
analyze_crash                # 分析最近崩溃
crash_report                 # 获取崩溃报告
crash_history                # 崩溃历史记录
```

### rider_query Queries

```bash
help                  # 列出所有命令
help <command>        # 命令详细帮助
context               # 当前调试会话状态
crash_report          # 最新崩溃报告
crash_history         # 会话崩溃历史
breakpoints           # 当前断点列表
health                # 连接健康状态
```

### CLI Syntax Features

```bash
# 批量命令（多行，一次往返）
@PlayerController.cs          # 设置文件上下文
add_breakpoint 42             # 使用上下文中的文件
add_breakpoint 55 --condition "health <= 0"  # 条件断点

# 注释
# 这是注释，会被忽略
add_breakpoint Enemy.cs 10

# 命名参数
start_debug --config MyApp
```

## 🧪 Testing

```bash
# 运行所有测试
pytest

# 带覆盖率
pytest --cov=rider_debug_mcp --cov-report=term-missing

# 只运行特定测试
pytest tests/test_parser.py -v

# Lint 检查
ruff check src/ tests/

# 代码格式化
ruff format src/ tests/
```

**测试覆盖：** 137 个单元测试，覆盖所有核心模块。

## 🔧 Tech Stack

| 技术 | 用途 |
|------|------|
| [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) | MCP 协议实现 |
| [httpx](https://www.python-httpx.org/) | 异步 HTTP 客户端 |
| [websockets](https://websockets.readthedocs.io/) | 调试事件流监听 |
| [Pydantic](https://docs.pydantic.dev/) | 数据模型验证 |
| [pytest](https://docs.pytest.org/) | 单元测试框架 |
| [ruff](https://docs.astral.sh/ruff/) | Lint & 格式化 |

## 📋 How It Works

1. **AI 助手**通过 MCP 协议调用 `rider_cli` / `rider_query`
2. **CommandParser** 解析 CLI 语法为结构化命令
3. **CommandRouter** 将命令分发到对应的 Handler
4. **Handlers** 调用 **RiderClient** 与 Rider IDE 交互
5. **EventListener** 通过 WebSocket 监听调试事件（断点命中、异常等）
6. **CrashAnalyzer** 自动捕获异常，解析 .NET 堆栈，生成结构化报告
7. **SessionManager** 维护调试会话状态、断点缓存和操作历史

## 🤝 Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ for the AI-assisted debugging workflow
</p>