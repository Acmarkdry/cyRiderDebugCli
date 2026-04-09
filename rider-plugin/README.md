# Rider Debug API Bridge Plugin

JetBrains Rider 插件，将调试器操作通过内置 HTTP Server 暴露为 REST API，供 `rider-debug-mcp` MCP 服务器调用。

## 为什么需要这个插件？

JetBrains Rider 的内置 HTTP Server（端口 63342-63352）默认只暴露少量端点（如 `/api/about`），**不提供调试相关的 REST API**。

本插件注册了 `HttpRequestHandler` 扩展点，在 `/api/debug/*` 路径下暴露完整的调试操作接口，桥接 HTTP 请求到 Rider 的 `XDebuggerManager` / `RunManager` 等 IntelliJ Platform API。

## 暴露的端点

### 断点管理
| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/debug/breakpoints` | 添加断点 |
| GET | `/api/debug/breakpoints` | 列出所有断点 |
| DELETE | `/api/debug/breakpoints/{id}` | 删除断点 |
| POST | `/api/debug/breakpoints/{id}/enable` | 启用断点 |
| POST | `/api/debug/breakpoints/{id}/disable` | 禁用断点 |

### 调试控制
| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/debug/start` | 启动调试会话 |
| POST | `/api/debug/stop` | 停止调试 |
| POST | `/api/debug/pause` | 暂停执行 |
| POST | `/api/debug/resume` | 恢复执行 |
| POST | `/api/debug/stepOver` | Step Over |
| POST | `/api/debug/stepInto` | Step Into |
| POST | `/api/debug/stepOut` | Step Out |

### 运行时检查
| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/debug/variables?frameIndex=0` | 获取变量 |
| POST | `/api/debug/evaluate` | 表达式求值 |
| GET | `/api/debug/stackTrace?threadId=1` | 获取调用栈 |
| GET | `/api/debug/threads` | 获取线程列表 |

## 构建

```bash
cd rider-plugin
./gradlew buildPlugin
```

构建产物在 `build/distributions/rider-debug-api-*.zip`。

## 安装

1. 在 Rider 中打开 `Settings → Plugins → ⚙ → Install Plugin from Disk...`
2. 选择构建出的 `.zip` 文件
3. 重启 Rider

## 开发

```bash
# 在 Rider 沙箱中运行插件
./gradlew runIde
```

## 兼容性

- JetBrains Rider 2024.1 ~ 2025.1.*
- IntelliJ Platform SDK (XDebugger API)

## 架构说明

```
HTTP Request → DebugApiHandler.process()
                    ↓
              路由到具体 handler
                    ↓
         ApplicationManager.invokeAndWait { ... }
                    ↓
         XDebuggerManager / RunManager / XBreakpointManager
                    ↓
              JSON Response
```

所有 IDE API 调用都在 EDT（Event Dispatch Thread）上执行，通过 `invokeAndWait` 确保线程安全。
