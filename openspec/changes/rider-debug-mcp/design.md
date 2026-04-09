## Context

本项目是一个全新的 Python MCP 工具，用于将 AI 助手与 JetBrains Rider IDE 的调试器深度集成。当前开发者在 Rider 中调试时，所有操作都是手动的：设置断点、检查变量、分析崩溃日志。通过 MCP 协议，AI 助手可以直接驱动调试器，实现断点自动化管理和崩溃智能分析。

系统采用三层架构：
1. **MCP Server 层**（面向 AI 助手）：提供 `rider_cli` 和 `rider_query` 两个标准 MCP 工具
2. **Middleware 分析层**（核心逻辑）：命令解析、数据转换、状态管理、崩溃分析
3. **Rider Gateway 层**（面向 IDE）：通过 HTTP/WebSocket 与 Rider 通信

## Goals / Non-Goals

**Goals:**
- 提供简洁的 `rider_cli` + `rider_query` 双工具 MCP 接口，降低 AI 调用复杂度
- 构建中间件层处理复杂的指令路由、数据聚合和崩溃分析逻辑
- 支持断点全生命周期管理（添加/删除/启用/禁用/列表/条件断点）
- 实现调试控制（运行/暂停/单步/继续/停止）
- 自动捕获崩溃/异常事件并生成结构化分析报告
- 读取调试时变量、堆栈帧、线程信息
- 完善的单元测试和 GitHub Actions CI 流水线

**Non-Goals:**
- 不实现 Rider IDE 插件（仅通过外部 API 通信）
- 不处理代码编辑/重构（仅聚焦调试）
- 不支持远程调试场景（V1 仅支持本地 Rider 实例）
- 不实现 UI/可视化界面

## Decisions

### Decision 1: 使用 Python MCP SDK 实现 MCP 服务器

**选择**: 使用 `mcp` Python SDK（官方 SDK）构建 MCP 服务器

**理由**:
- Python 生态丰富，HTTP 通信和数据处理库成熟
- 官方 MCP SDK 提供标准协议实现，减少协议层工作量
- 用户明确要求使用 Python
- Python 的异步支持（asyncio）适合处理调试事件流

**替代方案**:
- TypeScript SDK：MCP 生态更成熟，但用户指定 Python
- 自定义协议实现：灵活但工作量大，不符合 MCP 标准

### Decision 2: 双工具接口模式（cli + query）

**选择**: MCP Server 仅暴露 `rider_cli` 和 `rider_query` 两个工具

**理由**:
- 遵循 UE MCP 工具的成功模式，AI 只需学习两个工具的语法
- `rider_cli`：执行操作型命令（设置断点、控制调试）
- `rider_query`：查询信息（断点列表、变量值、堆栈、崩溃报告）
- 命令路由逻辑下沉到中间件层，MCP 层保持简单
- 支持批量命令（多行输入，一次往返）

**替代方案**:
- 每个功能一个工具：工具数量膨胀，AI 选择负担重
- 单一工具：无法区分读写语义

### Decision 3: 中间件分析层架构

**选择**: 独立的中间件层，采用 Command/Handler 模式

**设计**:
```
MCP Tool Input → CommandParser → CommandRouter → Handler → RiderGateway
                                                    ↓
                                              AnalysisEngine
                                                    ↓
                                            Formatted Response
```

**组件**:
- `CommandParser`: 解析 CLI 语法（支持位置参数、命名参数、@ 上下文目标）
- `CommandRouter`: 将命令分发到对应的 Handler
- `Handlers`: 每个命令域一个 Handler（BreakpointHandler, DebugHandler, AnalysisHandler）
- `AnalysisEngine`: 崩溃分析引擎，堆栈解析、变量上下文关联、根因推断
- `SessionManager`: 管理调试会话状态、断点缓存

**理由**:
- 中间件层解耦 MCP 协议与 IDE 通信，各层可独立测试
- Command/Handler 模式便于扩展新命令
- 分析引擎独立可复用

### Decision 4: Rider IDE 通信方式

**选择**: 通过 Rider 内置 REST API + WebSocket 通信

**理由**:
- Rider 基于 IntelliJ 平台，支持 Built-in Server（默认端口 63342+）
- 通过 REST API 可以执行 IDE 操作（设置断点、启动调试等）
- WebSocket 可以监听调试事件（断点命中、异常抛出、进程退出）
- 使用 `httpx` 作为 HTTP 客户端（支持异步）
- 使用 `websockets` 监听调试事件流

**替代方案**:
- JetBrains Gateway 协议：文档有限，主要用于远程开发
- 自定义 Rider 插件暴露 API：开发成本高，维护负担重

### Decision 5: 项目结构

**选择**: 标准 Python 包结构 + src layout

```
cyRiderDebugCli/
├── src/
│   └── rider_debug_mcp/
│       ├── __init__.py
│       ├── server.py           # MCP Server（rider_cli + rider_query）
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── parser.py       # CommandParser
│       │   ├── router.py       # CommandRouter
│       │   └── session.py      # SessionManager
│       ├── handlers/
│       │   ├── __init__.py
│       │   ├── breakpoint.py   # 断点管理命令
│       │   ├── debug.py        # 调试控制命令
│       │   ├── inspect.py      # 变量/堆栈查询
│       │   └── analysis.py     # 崩溃分析命令
│       ├── gateway/
│       │   ├── __init__.py
│       │   ├── client.py       # Rider HTTP/WS 客户端
│       │   ├── models.py       # 数据模型（Pydantic）
│       │   └── events.py       # 调试事件监听
│       └── analysis/
│           ├── __init__.py
│           ├── crash.py        # 崩溃分析引擎
│           └── report.py       # 报告生成
├── tests/
│   ├── conftest.py
│   ├── test_parser.py
│   ├── test_router.py
│   ├── test_handlers.py
│   ├── test_gateway.py
│   └── test_analysis.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml
├── README.md
├── .gitignore
└── LICENSE
```

### Decision 6: CI/CD 配置

**选择**: GitHub Actions + pytest + ruff

- 触发条件：push 到 main、所有 PR
- 测试矩阵：Python 3.11, 3.12
- 步骤：lint (ruff) → test (pytest) → coverage report
- Gateway 层测试使用 mock，不依赖实际 Rider 实例

## Risks / Trade-offs

- **[Rider API 稳定性]** Rider 内置 REST API 非官方公开 API，可能跨版本变更 → 封装 Gateway 层隔离变更影响，添加版本检测
- **[调试事件实时性]** WebSocket 事件推送可能有延迟或断连 → 实现重连机制和心跳检测
- **[Mock 测试覆盖度]** Gateway 层使用 mock 测试，可能遗漏真实交互问题 → 增加集成测试标记，可选连接真实 Rider 运行
- **[命令语法复杂度]** CLI 语法需要足够简单让 AI 使用，但又要足够表达力 → 参考 UE MCP 工具的成熟语法设计
- **[Python 异步复杂度]** 事件监听需要异步处理 → 使用 asyncio + 标准异步模式，保持代码可读性
