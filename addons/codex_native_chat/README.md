# Godot Codex 内置对话

Godot Codex 内置对话插件在 Godot 编辑器中嵌入一个 Codex 客户端。插件会在后台启动官方 `codex app-server` 进程，使用用户现有的 Codex／ChatGPT 登录状态，并自动配置 Codex 连接 Godot MCP Native。

## 架构

```text
Godot 编辑器 Dock
      |
      | 通过 stdio 进行双向 JSON-RPC 通信
      v
codex app-server
      |
      | Codex MCP 客户端
      v
Godot MCP Native
http://127.0.0.1:9080/mcp
      |
      v
当前 Godot 编辑器和正在运行的项目
```

插件本身不包含 AI 模型，也不会读取或保存 ChatGPT OAuth 令牌。身份认证、令牌刷新、会话存储、模型执行、文件系统工具、Shell 工具、Git 工具和 MCP 调用，均由官方 Codex 进程负责。

## 环境要求

- Godot 4.6 或更高版本。
- 本机已安装官方 Codex CLI。
- ChatGPT 套餐包含 Codex 使用权限，或使用其他受 Codex 支持的模型提供方。
- 需要让 AI 操作 Godot 编辑器时，必须安装并启用 Godot MCP Native。

## 安装

### 使用已验证的 ZIP 安装

1. 从最近一次成功的 **Codex 内置对话 CI** 运行产物中下载 `codex-native-chat-addon-1.0.0.zip`。
2. 将 ZIP 解压到 Godot 项目根目录，其中包含 `addons/codex_native_chat/`。
3. 将 Godot MCP Native 安装到 `addons/godot_mcp/` 并启用。
4. 打开 **项目 > 项目设置 > 插件**。
5. 启用 **Codex 内置对话**。
6. 打开 **CodexNativeChatDock** 面板。

### 从源代码安装

将 `addons/codex_native_chat/` 复制到 Godot 项目中，然后在 **项目 > 项目设置 > 插件** 中启用该插件。

插件会自动查找 Codex。自动检测失败时，打开 **设置**，填写 `codex.exe`、`codex.cmd` 或 Unix `codex` 可执行文件的完整路径。

## ChatGPT 登录

点击 **登录**。插件会调用：

```text
account/login/start { type = "chatgpt" }
```

Codex 会打开官方浏览器登录流程。登录凭据由 Codex 自行保存和刷新，插件只能接收认证方式、套餐类型等账户状态信息。

## Godot MCP Native 集成

默认地址：

```text
http://127.0.0.1:9080/mcp
```

插件会创建或更新以下项目级 Codex 配置，同时保留其他无关配置：

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
enabled = true
startup_timeout_sec = 20
```

配置文件路径：

```text
<Godot 项目目录>/.codex/config.toml
```

修改地址后，插件会调用 `config/mcpServer/reload` 重新加载配置，并通过 `mcpServerStatus/list` 查询连接状态。Godot MCP Native 通常会在编辑器内部启动 HTTP 服务，默认端口为 `9080`。

Godot MCP Native 使用 Bearer Token 时，不要把令牌提交到项目仓库。应在用户级 Codex 配置中通过环境变量设置，例如：

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
bearer_token_env_var = "GODOT_MCP_TOKEN"
```

## 已实现功能

- 启动和停止使用重定向 stdio 的 `codex app-server`。
- 完成必需的 `initialize`／`initialized` 握手。
- 读取当前 Codex 账户状态，并启动 ChatGPT 登录或退出。
- 创建新的 Codex 会话，并按 Godot 项目恢复最近一次会话。
- 启动和中断任务轮次。
- 将 Agent 的流式消息显示在 Godot Dock 中。
- 显示命令、文件修改、MCP 工具和网页搜索活动。
- 显示当前轮次汇总后的 Diff。
- 处理命令执行和文件修改审批。
- 处理额外权限请求。
- 处理 Codex `request_user_input` 和 MCP elicitation 请求。
- 配置并重新加载 Godot MCP Native。
- 提供模型、沙箱、审批策略、MCP 地址、Codex 可执行文件和自动连接设置。

## 自动化验证

CI 使用 Godot 4.6.3 在 Windows 和 Linux 上验证插件，覆盖：

- 编辑器插件加载和 GDScript 解析。
- 通过重定向 stdio 进行双向 JSON-RPC 通信。
- 原生可执行文件及 Windows `codex.cmd` 启动路径。
- 官方 `@openai/codex` app-server 握手。
- `account/read`、MCP 配置重载和 MCP 状态查询。
- 会话创建和恢复。
- 任务启动、流式输出、Diff 渲染、中断和完成。
- 命令与文件修改审批。
- 权限审批、用户输入请求和 MCP elicitation。
- 登录／退出状态、设置持久化和请求上下文清理。
- 在不覆盖其他内容的情况下更新项目 `.codex/config.toml`。

只有 Windows 和 Linux 的全部任务通过后，CI 才会生成可安装归档及对应的 SHA-256 校验文件。

## 默认安全设置

```text
沙箱：workspace-write
审批策略：on-request
```

该配置允许 Codex 修改当前项目，但在请求更高权限操作时需要用户审批。设置面板还提供 `read-only`、`danger-full-access`、`untrusted` 和 `never` 等选项。无限制模式会授予 Codex 相应的本机权限，只应在可信项目和仓库中使用。

## 典型使用流程

1. 启用 Godot MCP Native。
2. 启用 Codex 内置对话插件。
3. 确认 Codex 和 Godot MCP Native 的状态均显示已连接或就绪。
4. 需要时完成登录。
5. 输入开发任务，例如：

```text
检查当前场景，实现缺失的玩家受伤反馈，运行项目，并通过 Godot MCP Native 验证结果。
```

6. 在 Dock 中审查命令执行和文件修改请求。
7. 在接受最终结果前检查 **Diff** 和 **日志** 页面。

## 当前限制

- 插件依赖本机已安装 Codex 的 app-server 协议版本。当前使用稳定的 v2 会话／任务接口，并启用了用户输入和权限流程所需的实验性请求。
- Windows 的 npm 安装通常提供 `codex.cmd`；插件可通过 `cmd.exe` 启动它，但使用原生 `codex.exe` 的 stdio 行为更直接。
- Dock 提供实用的富文本流式显示，但没有完整复制官方 Codex 客户端的渲染系统。
- 实际 ChatGPT 浏览器 OAuth、用户代理配置、真实 Godot MCP Native 实例以及用户自己的项目，仍需在本机进行一次最终验收。