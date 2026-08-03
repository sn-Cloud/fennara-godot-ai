# Fennara Godot AI

> 基于 [fennaraOfficial/fennara-godot-ai](https://github.com/fennaraOfficial/fennara-godot-ai) 的个人维护分支。

[![Upstream](https://img.shields.io/badge/upstream-Fennara-5865F2)](https://github.com/fennaraOfficial/fennara-godot-ai)
[![Version](https://img.shields.io/badge/version-0.4.0-blue)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)

## 当前状态

> [!IMPORTANT]
> 本仓库以完整的 Fennara `0.4.0` 为基础，并在内置聊天中恢复了通过官方 Codex CLI 使用 ChatGPT 会员账号登录的能力。Fennara 原有 MCP、daemon、CLI、Godot 工具及全部 API Provider 均继续保留。

Codex 会员登录通过本机安装的 OpenAI Codex CLI 和 `codex app-server --stdio` 实现。OAuth 凭据、刷新令牌、账号状态及订阅权限均由 Codex CLI 管理；Fennara 不读取或保存 ChatGPT Token。

此前基于 Godot MCP Native 重构的 Codex／Kimi 双后端方案，已独立拆分到：

- [sn-Cloud/godot-ai-manager](https://github.com/sn-Cloud/godot-ai-manager)

两个项目的定位不同：

- 本仓库保留完整 Fennara，并增加 Codex ChatGPT 会员账号 Provider；
- `godot-ai-manager` 使用独立的 Codex／Kimi 官方后端，并以 Godot MCP Native 作为 Godot MCP。

因此，本仓库仍然不包含以下内容：

- Godot MCP Native 集成；
- Kimi ACP 管理层；
- Kimi 会员设备码登录；
- 以 Godot MCP Native 替换 Fennara MCP 的架构。

## 功能边界

| 功能 | 当前 `main` 状态 |
| --- | --- |
| Fennara MCP、daemon、CLI 和 Godot 工具 | 已保留 |
| Godot 编辑器内置聊天 | 已支持 |
| OpenAI API Key | 已支持 |
| Anthropic、DeepSeek、OpenRouter、Moonshot AI、Kimi For Coding、MiniMax、NVIDIA 等 API Provider | 已支持 |
| Ollama、LM Studio 本地模型 | 已支持 |
| Codex、Claude、Cursor、Gemini、Antigravity 等外部 MCP 应用 | 已支持 |
| ChatGPT／Codex Plus、Pro 等会员账号通过官方 Codex CLI 登录内置聊天 | 已恢复 |
| Kimi 会员账号登录 | 不属于本仓库 |
| Godot MCP Native | 不属于本仓库 |

### Codex app-server 架构与验收

Codex 内置聊天的命令路由、事件渲染、审批与沙箱、线程与历史、上下文压缩、认证与 `CODEX_HOME`、进程生命周期、版本兼容策略及自动化验收矩阵，见：

- [Codex app-server ownership boundaries and acceptance matrix](docs/codex-app-server-ownership.md)

### OpenAI 登录方式说明

本仓库同时支持两种彼此独立的 OpenAI 使用方式。

#### OpenAI API Key

```text
OPENAI_API_KEY
```

对应模型格式：

```text
openai/<model>
```

API 调用产生的费用由 OpenAI API 账户单独结算，与 ChatGPT Plus、Pro 等会员订阅无关。

#### ChatGPT 会员账号

对应模型格式：

```text
codex/default
```

该方式使用 Codex CLI 保存的 ChatGPT 账号，不需要把 OAuth Token 或 ChatGPT 凭据写入 Fennara。

外部 Codex 应用仍使用其自身的账号、模型和权限配置，不会自动继承 Fennara 内置聊天的 Provider 设置。

## 项目定位

Fennara 为 AI 编程助手提供与 Godot 编辑器的实时连接，使 AI 不只读取项目文件，还能获得 Godot 编辑器和运行时的实际反馈。

主要能力包括：

- 通过 MCP 连接 Codex、Claude、Cursor、Gemini、Antigravity 等外部 AI 应用；
- 在 Godot 编辑器内使用可选的本地聊天面板；
- 检查场景树、节点、资源和脚本诊断；
- 修改项目文件并返回 Godot 校验结果；
- 捕获编辑器或运行时截图；
- 启动运行时会话并读取日志；
- 在实时场景中执行受控脚本；
- 管理对话、模型、权限审批、Diff、日志和上下文压缩。

外部 MCP 应用与 Fennara 内置聊天使用彼此独立的模型和账号配置。

## 环境要求

- Godot 4.5 或更高版本；
- Windows x86_64、Linux x86_64 或 macOS arm64；
- 使用外部 AI 应用时，需要支持 MCP 的客户端；
- 使用云端 API Provider 时，需要配置对应 API Key；
- 使用 Ollama／LM Studio 时，需要启动本地模型服务；
- 使用 ChatGPT 会员账号登录时，需要安装官方 Codex CLI，并确保 `codex --version` 可以正常执行。

## 安装

当前 `main` 基于上游 Fennara `0.4.0`，但已经加入本仓库自定义的 Codex ChatGPT 会员登录代码，因此不再与上游官方发行版完全一致。

### 使用本仓库版本

要使用 ChatGPT 会员账号登录功能，需要使用本仓库 `main` 分支源码进行构建和安装。

> [!NOTE]
> 本仓库目前没有声明上游官方安装脚本会生成或下载包含该功能的构建产物。在本仓库发布独立发行版前，不应把上游发行包视为包含 Codex 会员登录的版本。

### 使用上游官方版本

不需要 ChatGPT 会员登录时，可以使用上游 Fennara 官方发行版。

打开 [Fennara 最新发行版](https://github.com/fennaraOfficial/fennara-godot-ai/releases/latest)，下载 `fennara-addon-latest.zip`，将其中的：

```text
addons/fennara/
```

复制到 Godot 项目中。

启动项目后，在 Fennara 面板中点击 **Set Up Fennara**。

也可以使用上游 CLI 安装脚本。

Windows：

```powershell
irm https://raw.githubusercontent.com/fennaraOfficial/fennara-godot-ai/main/install.ps1 | iex
```

macOS 或 Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/fennaraOfficial/fennara-godot-ai/main/install.sh | sh
```

然后进入 Godot 项目目录：

```bash
fennara install
```

> [!WARNING]
> 上述发行版和安装脚本来自上游仓库，不包含本仓库新增的 Codex ChatGPT 会员登录功能。

## 配置内置聊天

在 Godot 的 Fennara 面板中打开：

```text
Chat Settings > Chat > Open providers
```

可选择：

- Codex (ChatGPT account)；
- OpenAI；
- Anthropic；
- OpenRouter；
- DeepSeek；
- Z.AI；
- Moonshot AI；
- Kimi For Coding；
- MiniMax；
- NVIDIA；
- 自定义 OpenAI 兼容接口；
- Ollama；
- LM Studio。

### 使用 ChatGPT 会员账号

1. 安装官方 Codex CLI。
2. 在终端执行 `codex --version`，确认命令可用。
3. 打开 `Chat Settings > Chat > Open providers`。
4. 选择 **Codex (ChatGPT account)**。
5. 在浏览器中完成 ChatGPT OAuth 登录。
6. 选择模型 `codex/default`。

Fennara 会在本机启动 `codex app-server --stdio`，并读取账号状态和流式会话事件。OAuth Token 仍由 Codex CLI 保存和刷新。

默认权限模式映射为 Codex `workspaceWrite`；在 Fennara 中选择 **Full access** 时，会映射为 Codex `dangerFullAccess`。

Codex 会话仍可通过现有 Fennara MCP 使用 Godot 编辑器和运行时工具，无需安装 Godot MCP Native。
