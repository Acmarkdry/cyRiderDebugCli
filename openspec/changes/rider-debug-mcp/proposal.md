## Why

当前在 JetBrains Rider IDE 中进行 C#/Unity 项目调试时，开发者需要手动设置断点、手动分析崩溃日志、手动定位问题根因。这些重复性的调试操作占用了大量时间。通过构建一个 MCP (Model Context Protocol) 工具，AI 助手可以直接与 Rider 调试器交互——设置断点、读取运行时变量、自动分析崩溃信息——从而将 AI 深度集成到调试工作流中。

## What Changes

- **新建 MCP Server**：基于 Python 实现完整的 MCP 服务器，提供 `rider_cli` 和 `rider_query` 两个工具接口，遵循与 UE MCP 工具相同的双接口模式
- **新建中间件分析层（Middleware）**：在 MCP 工具和 Rider IDE 之间建立智能中间层，负责：
  - 指令解析与路由（将 CLI 命令映射到 Rider Gateway API 调用）
  - 断点数据采集与格式化
  - 崩溃信息自动捕获与结构化分析
  - 调试会话状态管理
- **Rider Gateway 通信层**：通过 JetBrains Gateway API / Rider 内置 REST API 与 IDE 交互
- **自动崩溃分析**：监听调试会话中的异常/崩溃事件，自动采集堆栈、变量、上下文并生成结构化分析报告
- **Git 仓库初始化**：项目使用 Git 版本控制，配置 `.gitignore`、README 等
- **GitHub Actions CI**：配置自动化单元测试流水线，每次 push/PR 触发 pytest

## Capabilities

### New Capabilities
- `mcp-server`: MCP 服务器核心，包含 `rider_cli` 和 `rider_query` 双工具接口定义、MCP 协议处理、命令解析与分发
- `middleware-analysis`: 中间件分析层，负责指令路由、数据转换、断点信息聚合、崩溃数据结构化分析、调试会话状态管理
- `rider-gateway`: Rider IDE 通信层，封装 JetBrains Gateway API 调用，处理断点 CRUD、调试控制（step/continue/pause）、变量读取、崩溃事件监听
- `crash-analyzer`: 崩溃自动分析引擎，监听异常事件、采集堆栈与上下文、生成结构化分析报告
- `ci-pipeline`: GitHub Actions CI/CD 配置，pytest 单元测试流水线

### Modified Capabilities
<!-- 这是全新项目，没有已有 capability 需要修改 -->

## Impact

- **代码**：全新 Python 项目，包含 MCP server、middleware、gateway client、crash analyzer 四个核心模块
- **依赖**：`mcp` SDK、`httpx`/`aiohttp`（HTTP 通信）、`pytest`（测试）、`pydantic`（数据模型）
- **API**：依赖 JetBrains Rider Gateway REST API（断点管理、调试控制、变量查询）
- **系统**：需要 Rider IDE 运行并开启 Gateway/REST 端口；Python 3.11+ 运行环境
- **CI/CD**：新增 GitHub Actions workflow 文件
