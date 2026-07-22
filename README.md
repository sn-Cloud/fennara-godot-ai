# Godot Codex 内置对话

在 Godot 编辑器内部直接使用官方 Codex 的开发插件。

本插件会在后台启动官方 `codex app-server`，复用用户现有的 Codex／ChatGPT 登录状态，并在 Godot 中提供聊天、流式输出、工具调用、审批、Diff、日志和会话管理界面。

## 核心外部依赖：Godot MCP Native

> **Godot MCP Native 是一个完全独立的第三方开源仓库，不属于本项目，也不会随本插件一起安装。**
>
> 官方仓库：<https://github.com/yurineko73/Godot-MCP-Native>

Godot MCP Native 是本项目实现“让 Codex 直接控制 Godot 编辑器”的关键组件。它在 Godot 内部运行原生 MCP Server，并向 Codex 提供场景、节点、脚本、资源、调试器、Profiler、运行时对象、动画、材质、音频、输入和截图等 Godot 专用工具。

没有安装 Godot MCP Native 时，Codex 仍可使用自身的文件、Shell 和 Git 工具修改项目文件，但无法可靠读取和操作 Godot 编辑器内部状态。

### Godot MCP Native 官方信息

- 官方仓库：<https://github.com/yurineko73/Godot-MCP-Native>
- 插件目录：`addons/godot_mcp/`
- 默认 MCP 地址：`http://127.0.0.1:9080/mcp`
- 实现方式：Godot 原生实现，不需要额外运行 Node.js MCP Server
- 许可证：MIT
- 安装方式：Godot Asset Library 或从官方仓库手动安装

Godot MCP Native 由其原作者独立开发和维护。本项目不会复制、打包、固定版本或自动更新它。两个插件需要分别安装、分别启用和分别更新。

## 组件职责

| 组件 | 主要职责 |
| --- | --- |
| **Godot Codex 内置对话** | Godot 内部聊天界面、Codex 进程管理、流式显示、审批、Diff、日志、会话和 MCP 自动配置。 |
| **官方 Codex CLI / app-server** | ChatGPT 登录、模型推理、会话存储、文件、Shell、Git 和 MCP 客户端。 |
| **Godot MCP Native** | 在 Godot 编辑器内部提供 MCP Server 和 Godot 专用操作工具。 |

## 系统架构

```text
Godot 编辑器
└── Codex 内置对话 Dock
        |
        | JSON-RPC / JSONL over stdio
        v
    codex app-server
        |
        | 标准 MCP 客户端
        v
    Godot MCP Native（独立仓库，需单独安装）
    http://127.0.0.1:9080/mcp
        |
        v
    当前 Godot 编辑器和正在运行的项目
```

## 环境要求

- Godot 4.6 或更高版本；
- 本机已安装官方 Codex CLI；
- ChatGPT 套餐包含 Codex 使用权限，或使用其他 Codex 支持的模型提供方；
- 已从独立仓库安装并启用 Godot MCP Native。

## 安装顺序

### 第一步：安装 Godot MCP Native

官方仓库：<https://github.com/yurineko73/Godot-MCP-Native>

#### 通过 Godot Asset Library 安装

1. 在 Godot 中打开 **AssetLib**；
2. 搜索 **Godot MCP Native**；
3. 下载并安装；
4. 打开 **项目 > 项目设置 > 插件**；
5. 启用 **Godot MCP Native**。

#### 从官方仓库手动安装

1. 下载或克隆 Godot MCP Native 官方仓库；
2. 将其中的 `addons/godot_mcp/` 复制到当前项目的 `addons/` 目录；
3. 在 **项目 > 项目设置 > 插件** 中启用 **Godot MCP Native**。

### 第二步：安装 Codex 内置对话

1. 将本仓库中的 `addons/codex_native_chat/` 复制到 Godot 项目的 `addons/` 目录；
2. 打开 **项目 > 项目设置 > 插件**；
3. 启用 **Codex 内置对话**；
4. 打开 **CodexNativeChatDock** 面板。

安装后项目目录应至少包含：

```text
addons/
├── codex_native_chat/
└── godot_mcp/
```

## Godot MCP Native 自动配置

本插件默认将 Codex 连接到：

```text
http://127.0.0.1:9080/mcp
```

插件会在项目中创建或更新：

```text
<Godot 项目目录>/.codex/config.toml
```

写入以下配置，同时保留其他 Codex 配置：

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
enabled = true
startup_timeout_sec = 20
```

配置变化后，插件会调用：

```text
config/mcpServer/reload
mcpServerStatus/list
```

用于重新加载 MCP 配置并查询 Godot MCP Native 状态。

需要注意：**自动配置不等于自动安装。** 本插件无法替代 Godot MCP Native，也无法在它未安装或未启用时提供 Godot 编辑器控制能力。

## 主要功能

- 在 Godot 内部启动和关闭官方 `codex app-server`；
- 使用 ChatGPT／Codex 会员登录状态；
- 新建和恢复 Codex 会话；
- 流式显示 Agent 回答；
- 中断当前任务；
- 显示命令、文件修改、MCP 工具和网页搜索活动；
- 显示汇总 Diff 和运行日志；
- 处理命令执行、文件修改和额外权限审批；
- 处理 Codex `request_user_input` 和 MCP elicitation；
- 自动维护 Godot MCP Native 的 Codex 配置；
- 查询并显示 Godot MCP Native 连接状态；
- 配置模型、沙箱、审批策略、MCP 地址和 Codex 可执行文件。

## ChatGPT 登录

点击插件中的 **登录** 后，插件会请求官方 Codex 启动浏览器登录流程：

```text
account/login/start { type = "chatgpt" }
```

OAuth 凭据由官方 Codex 保存和刷新。本插件不会读取或保存 ChatGPT OAuth Token。

## 安全设置

默认配置：

```text
沙箱：workspace-write
审批策略：on-request
```

该配置允许 Codex 修改当前项目，但在请求更高权限操作时需要用户确认。

设置中也可选择 `read-only`、`danger-full-access`、`untrusted` 和 `never` 等模式。无限制模式会授予 Codex 相应的本机权限，只应在可信项目和仓库中使用。

Godot MCP Native 启用 Bearer Token 时，建议通过环境变量传递，不要把令牌提交到项目仓库：

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
bearer_token_env_var = "GODOT_MCP_TOKEN"
```

## 自动化验证

项目使用 Godot 4.6.3 在 Windows 和 Linux 上验证：

- Godot 编辑器插件加载和 GDScript 解析；
- 双向 JSON-RPC／JSONL stdio 通信；
- Windows `codex.exe`、`codex.cmd` 和 `cmd.exe` 启动路径；
- 官方 `@openai/codex` app-server 握手；
- 账户状态读取；
- MCP 配置重载和状态查询；
- 会话创建、恢复、任务启动、中断和完成；
- 流式消息、Diff 和日志；
- 命令、文件、权限和用户输入审批；
- MCP elicitation；
- 请求上下文释放和设置持久化。

云端测试无法代替真实的 ChatGPT OAuth、用户代理环境、Godot MCP Native 编辑器实例和实际项目，因此仍需进行本机最终验收。

## 故障排查

Godot MCP Native 状态显示未连接时，依次检查：

1. `addons/godot_mcp/` 是否存在；
2. Godot MCP Native 是否在插件管理中启用；
3. Godot MCP Native 是否使用 HTTP 模式；
4. 端口是否为 `9080`，或插件设置中的地址是否与实际一致；
5. `9080` 端口是否被占用；
6. 启用认证时，Codex 是否获得正确的 Bearer Token；
7. 修改配置后是否重新连接 Codex。

## 详细文档

完整安装、架构、权限和兼容性说明：

[addons/codex_native_chat/README.md](addons/codex_native_chat/README.md)

Godot MCP Native 官方文档：

<https://github.com/yurineko73/Godot-MCP-Native>

## 当前限制

- Godot MCP Native 是独立项目，其版本、工具和兼容性由原仓库维护；
- 本插件依赖本机安装的 Codex app-server 协议版本；
- Godot 内部 Dock 没有完整复制官方 Codex 客户端的全部渲染功能；
- 真实 OAuth、代理和 Godot MCP Native 工具调用仍需在用户电脑上验证。

## 许可证

参阅 [LICENSE.md](LICENSE.md)。
