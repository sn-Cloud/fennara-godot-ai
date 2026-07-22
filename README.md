# Godot AI 管理器

在 Godot 编辑器内统一管理 **Codex** 与 **Kimi Code** 两个官方 AI Agent 后端，并将 Godot 编辑器能力统一交给独立项目 **Godot MCP Native**。

本项目保留了 Fennara 在对话、会话、状态、审批、Diff 和日志方面的 AI 管理思路，但已经彻底移除 Fennara 自带的 MCP Server、daemon、CLI、WebSocket Bridge、Godot 工具定义和模型提供方运行时。运行期间不会启动任何 Fennara 服务，也不会生成 Fennara MCP 配置。

## 核心原则

```text
Godot AI 管理器
├── Codex 官方后端
│   ├── codex app-server
│   └── ChatGPT／Codex 会员登录
├── Kimi 官方后端
│   ├── kimi acp
│   └── kimi login 会员设备码登录
└── 唯一 Godot MCP：Godot MCP Native
```

- Codex 只使用 OpenAI 官方 `codex app-server`。
- Kimi 只使用 Moonshot AI 官方 `kimi acp` 和 `kimi login`。
- 不使用第三方协议转换器，不让一个后端伪装成另一个后端。
- 不包含第二套 Godot MCP，不与 Godot MCP Native 竞争端口、工具名或编辑器状态。

## 必须单独安装：Godot MCP Native

> **Godot MCP Native 是独立第三方开源项目，不属于本仓库，也不会随本插件自动安装。**

官方仓库：<https://github.com/yurineko73/Godot-MCP-Native>

它在 Godot 编辑器内部提供原生 MCP Server，使 AI 能读取和操作场景、节点、脚本、资源、调试器、Profiler、运行时对象、输入、动画、材质、音频和截图等 Godot 专用能力。

默认地址：

```text
http://127.0.0.1:9080/mcp
```

没有安装 Godot MCP Native 时，Codex 和 Kimi 仍能使用各自的文件、Shell 与 Git 工具，但不能可靠访问 Godot 编辑器内部状态。

## 两个官方后端

### Codex

运行链路：

```text
Godot Dock → codex app-server → ChatGPT／Codex 会员 → Godot MCP Native
```

已实现：

- 自动查找 `codex.exe`、`codex.cmd` 或 Unix `codex`；
- `initialize`／`initialized`；
- `account/read`、ChatGPT 登录和退出；
- 新建、恢复会话；
- 启动、中断任务；
- 流式回答、工具活动、Diff；
- 命令、文件和额外权限审批；
- 用户提问与 MCP elicitation；
- 自动维护项目 `.codex/config.toml` 中唯一的 `godot-mcp` 配置；
- MCP 配置重载和状态查询。

### Kimi Code

运行链路：

```text
Godot Dock → kimi acp → Kimi Code 会员 → Godot MCP Native
```

已实现：

- 自动查找 `kimi.exe`、`kimi.cmd` 或 Unix `kimi`；
- ACP JSON-RPC 初始化与能力协商；
- 官方 `authenticate(methodId = "login")`；
- 点击登录后运行官方 `kimi login` 设备码流程；
- 自动捕获验证地址并打开浏览器；
- 新建、加载和恢复会话；
- 通过 `mcpServers` 将 Godot MCP Native 的 HTTP 服务传入 Kimi 会话；
- prompt、流式消息、思考摘要、工具活动、计划、取消任务；
- ACP 权限请求；
- ACP `fs/read_text_file` 与 `fs/write_text_file`，并强制限制在当前 Godot 项目目录；
- 模型配置选项。

Kimi ACP 没有官方 `logout` 方法，因此插件不会私自删除凭据。需要退出时，在 Kimi Code CLI 交互界面执行 `/logout`。

## Fennara 已移除的部分

最终发布树中不包含：

- `addons/fennara/`；
- `fennara-mcp`；
- Fennara daemon；
- Fennara CLI；
- Fennara WebSocket Bridge；
- Fennara 自带 Godot 工具及 Schema；
- Fennara MCP 配置向导；
- Fennara 的 OpenRouter、Ollama、LM Studio 等模型后端；
- Fennara 使用的本地服务和端口。

只保留重新实现后的通用 AI 管理能力：后端选择、对话、会话、状态、审批、Diff、日志和设置持久化。

## 安装

### 1. 安装 Godot MCP Native

通过 Godot Asset Library 搜索 **Godot MCP Native**，或从其官方仓库下载，将：

```text
addons/godot_mcp/
```

复制到项目并在 **项目 > 项目设置 > 插件** 中启用。

### 2. 安装本插件

将本仓库中的：

```text
addons/godot_ai_manager/
```

复制到项目，然后启用 **Godot AI 管理器**。

项目目录应至少包含：

```text
addons/
├── godot_ai_manager/
└── godot_mcp/
```

### 3. 安装官方 CLI

Codex：安装官方 OpenAI Codex CLI，并确保 `codex --version` 可运行。

Kimi：使用 Kimi Code 官方安装脚本或：

```bash
npm install -g @moonshot-ai/kimi-code@latest
```

确认：

```bash
kimi --version
```

## 使用

1. 打开 Godot 右侧的 **GodotAiManagerDock**；
2. 选择 **Codex** 或 **Kimi Code**；
3. 点击 **连接**；
4. 点击 **登录**并完成对应官方会员授权；
5. 确认 Godot MCP Native 状态；
6. 输入开发任务；
7. 审查审批、Diff 和日志。

## 安全边界

- 默认 Codex 沙箱为 `workspace-write`，审批策略为 `on-request`。
- Kimi ACP 文件反向 RPC 只允许当前 Godot 项目目录内的路径。
- 本插件不读取或保存 ChatGPT、Codex、Kimi 的 OAuth Token。
- 登录凭据由各自官方 CLI 保存和刷新。
- 检测到用户配置中残留的 Fennara MCP 时只显示警告，不擅自修改用户私人配置。
- Godot MCP Native 启用 Bearer Token 时，应通过环境变量或各后端官方安全配置传递，不要提交到 Git。

## 自动化验证

仓库包含两类 CI：

- 普通仓库检查：验证必需文件以及发布树中不存在 Fennara MCP/runtime；
- 手动 Godot 测试：Windows 和 Linux 上加载 Godot 4.6.3，测试 Codex、Kimi ACP、审批、会话、文件边界和官方 CLI 握手。

Godot 专项 CI 只允许手动触发，避免每次提交重复运行和发送大量邮件。项目不再生成安装 ZIP。

## 文档

- [架构](docs/architecture.md)
- [手动安装](docs/manual-install.md)
- [仓库结构](docs/repo-map.md)
- [发布检查](docs/release.md)
- [插件详细说明](addons/godot_ai_manager/README.md)

## 许可证与归属

代码使用 MIT License。Fennara 与 Godot MCP Native 均为独立项目，详情见 [NOTICE.md](NOTICE.md) 和 [LICENSE.md](LICENSE.md)。
