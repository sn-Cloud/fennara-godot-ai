# Godot Codex 内置对话

Godot Codex 内置对话插件在 Godot 编辑器中嵌入一个 Codex 客户端。插件会在后台启动官方 `codex app-server` 进程，使用用户现有的 Codex／ChatGPT 登录状态，并自动配置 Codex 连接 Godot MCP Native。

> **重要：Godot MCP Native 是一个独立的第三方开源项目，不属于本仓库，也不会随本插件一起安装。**
>
> 官方仓库：<https://github.com/yurineko73/Godot-MCP-Native>
>
> 要让 Codex 直接读取和操作 Godot 的场景、节点、脚本、资源、调试器和运行时状态，必须另外安装并启用 Godot MCP Native。

## 三个组件的职责

| 组件 | 职责 |
| --- | --- |
| **Godot Codex 内置对话** | 提供 Godot 内部聊天界面，启动和管理 `codex app-server`，显示流式回答、工具调用、审批、Diff 和日志，并自动写入 MCP 配置。 |
| **官方 Codex CLI / app-server** | 负责 ChatGPT 登录、模型推理、会话、文件系统、Shell、Git 和 MCP 客户端能力。 |
| **Godot MCP Native** | 在 Godot 编辑器内部提供原生 MCP Server，使 Codex 能操作场景、节点、脚本、资源、调试器、Profiler、运行时对象和截图等 Godot 专用能力。 |

本插件不复制 Godot MCP Native 的代码，也不替代它。两者需要分别安装、分别启用、分别更新。

## Godot MCP Native

### 官方项目

- GitHub：<https://github.com/yurineko73/Godot-MCP-Native>
- Godot 插件目录：`addons/godot_mcp/`
- 默认 HTTP MCP 地址：`http://127.0.0.1:9080/mcp`
- 许可证：MIT

Godot MCP Native 使用 Godot 原生实现，不要求额外运行 Node.js MCP Server。其官方说明目前提供约 155 个工具，覆盖节点、脚本、场景、编辑器、调试器、性能分析、运行时对象、输入、动画、材质、音频、TileMap、资源和项目设置等能力。

### 为什么本插件需要它

Codex 自带文件、Shell 和 Git 工具，因此即使没有 Godot MCP Native，它仍然可以修改项目文件。但是它无法可靠获得以下 Godot 编辑器内部信息：

- 当前打开的场景和实际场景树；
- 节点属性、信号、资源和 Inspector 状态；
- Godot 解析和导入后的真实结果；
- Debugger、调用栈、运行时变量和 Profiler 数据；
- 正在运行的场景树、节点状态和游戏画面；
- 通过 Godot 编辑器执行节点修改、运行项目和截图验证。

Godot MCP Native 提供这部分能力。本插件负责把它自动接入 Codex，并在 Godot 内提供完整交互界面。

### 安装 Godot MCP Native

#### 方式一：Godot Asset Library

1. 在 Godot 编辑器中打开 **AssetLib**。
2. 搜索 **Godot MCP Native**。
3. 下载并安装。
4. 打开 **项目 > 项目设置 > 插件**。
5. 启用 **Godot MCP Native**。

#### 方式二：从官方仓库手动安装

1. 打开 <https://github.com/yurineko73/Godot-MCP-Native>。
2. 下载或克隆该仓库。
3. 将其中的 `addons/godot_mcp/` 复制到当前 Godot 项目的 `addons/` 目录。
4. 在 **项目 > 项目设置 > 插件** 中启用 **Godot MCP Native**。

安装完成后，项目中应同时存在：

```text
addons/
├── codex_native_chat/
└── godot_mcp/
```

### 独立更新与兼容性

Godot MCP Native 由其原作者独立维护，本仓库不会固定、复制或自动更新它。Godot MCP Native 发布新版本后，应从其官方仓库或 Godot Asset Library 更新。

本插件只依赖以下公开行为：

- Godot MCP Native 在 Godot 编辑器内运行；
- 使用 Streamable HTTP MCP；
- 默认地址为 `http://127.0.0.1:9080/mcp`，或使用用户在设置中指定的其他地址；
- Codex 能通过标准 MCP 客户端连接该服务。

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
Godot MCP Native（独立仓库，需单独安装）
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
- 已从独立仓库安装并启用 Godot MCP Native。

## 安装本插件

1. 将 `addons/codex_native_chat/` 复制到 Godot 项目中。
2. 按上文说明单独安装 Godot MCP Native。
3. 打开 **项目 > 项目设置 > 插件**。
4. 启用 **Godot MCP Native**。
5. 启用 **Codex 内置对话**。
6. 打开 **CodexNativeChatDock** 面板。

插件会自动查找 Codex。自动检测失败时，打开 **设置**，填写 `codex.exe`、`codex.cmd` 或 Unix `codex` 可执行文件的完整路径。

## ChatGPT 登录

点击 **登录**。插件会调用：

```text
account/login/start { type = "chatgpt" }
```

Codex 会打开官方浏览器登录流程。登录凭据由 Codex 自行保存和刷新，插件只能接收认证方式、套餐类型等账户状态信息。

## 自动连接 Godot MCP Native

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

修改地址后，插件会调用 `config/mcpServer/reload` 重新加载配置，并通过 `mcpServerStatus/list` 查询连接状态。

需要注意：本插件只负责配置和查询连接，不能替代 Godot MCP Native 的安装和启动。如果状态显示未连接，应检查：

1. `addons/godot_mcp/` 是否存在；
2. Godot MCP Native 是否已在插件管理中启用；
3. Godot MCP Native 的 HTTP 模式和端口是否正确；
4. `9080` 端口是否被其他程序占用；
5. 启用认证时，Codex 是否配置了正确的 Bearer Token。

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
- 自动配置、重新加载并查询 Godot MCP Native 状态。
- 提供模型、沙箱、审批策略、MCP 地址、Codex 可执行文件和自动连接设置。

## 自动化验证

CI 使用 Godot 4.6.3 在 Windows 和 Linux 上验证插件，覆盖：

- 编辑器插件加载和 GDScript 解析；
- 通过重定向 stdio 进行双向 JSON-RPC 通信；
- 原生可执行文件及 Windows `codex.cmd` 启动路径；
- 官方 `@openai/codex` app-server 握手；
- `account/read`、MCP 配置重载和 MCP 状态查询；
- 会话创建和恢复；
- 任务启动、流式输出、Diff 渲染、中断和完成；
- 命令与文件修改审批；
- 权限审批、用户输入请求和 MCP elicitation；
- 登录／退出状态、设置持久化和请求上下文清理；
- 在不覆盖其他内容的情况下更新项目 `.codex/config.toml`。

自动化测试可以验证 Codex 协议和 MCP 配置流程，但无法在云端替代真实 Godot MCP Native 编辑器实例。最终仍需在本机验证真实连接和工具调用。

## 默认安全设置

```text
沙箱：workspace-write
审批策略：on-request
```

该配置允许 Codex 修改当前项目，但在请求更高权限操作时需要用户审批。设置面板还提供 `read-only`、`danger-full-access`、`untrusted` 和 `never` 等选项。无限制模式会授予 Codex 相应的本机权限，只应在可信项目和仓库中使用。

## 典型使用流程

1. 从官方独立仓库安装并启用 Godot MCP Native。
2. 安装并启用 Codex 内置对话插件。
3. 确认 Codex 和 Godot MCP Native 的状态均显示已连接或就绪。
4. 需要时完成 ChatGPT 登录。
5. 输入开发任务，例如：

```text
检查当前场景，实现缺失的玩家受伤反馈，运行项目，并通过 Godot MCP Native 验证结果。
```

6. 在 Dock 中审查命令执行和文件修改请求。
7. 在接受最终结果前检查 **Diff** 和 **日志** 页面。

## 当前限制

- Godot MCP Native 是独立项目，其版本、工具数量和兼容性由原仓库维护。
- 本插件依赖本机已安装 Codex 的 app-server 协议版本。当前使用稳定的 v2 会话／任务接口，并启用了用户输入和权限流程所需的实验性请求。
- Windows 的 npm 安装通常提供 `codex.cmd`；插件可通过 `cmd.exe` 启动它，但使用原生 `codex.exe` 的 stdio 行为更直接。
- Dock 提供实用的富文本流式显示，但没有完整复制官方 Codex 客户端的渲染系统。
- 实际 ChatGPT 浏览器 OAuth、用户代理配置、真实 Godot MCP Native 实例以及用户自己的项目，仍需在本机进行一次最终验收。
