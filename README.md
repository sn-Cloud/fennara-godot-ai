# Fennara Godot AI

> 基于 [fennaraOfficial/fennara-godot-ai](https://github.com/fennaraOfficial/fennara-godot-ai) 的个人维护分支。

[![Upstream](https://img.shields.io/badge/upstream-Fennara-5865F2)](https://github.com/fennaraOfficial/fennara-godot-ai)
[![Version](https://img.shields.io/badge/version-0.4.0-blue)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)

## 当前状态

> [!IMPORTANT]
> 本仓库基于完整的 Fennara `0.4.0`，并恢复 Codex `app-server` 与 ChatGPT 会员账号登录。Fennara 原有 MCP、daemon、CLI、Godot 工具及全部 API Provider 均继续保留。

Codex 会员登录使用本机安装的 OpenAI Codex CLI。OAuth 凭据由 Codex CLI 保存和刷新，本插件不读取或保存 ChatGPT Token。

此前基于 Godot MCP Native 重构的 Codex／Kimi 双后端方案，已经独立拆分到：

- [sn-Cloud/godot-ai-manager](https://github.com/sn-Cloud/godot-ai-manager)

因此，本仓库不再包含以下内容：

- Godot MCP Native 集成；
- Codex `app-server` 管理层；
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
| ChatGPT／Codex Plus、Pro 等会员账号通过 Codex CLI 登录内置聊天 | 已恢复 |
| Kimi 会员账号登录 | 不属于本仓库 |
| Godot MCP Native | 不属于本仓库 |

### OpenAI 登录方式说明

当前 Fennara 内置聊天连接 OpenAI 时使用 OpenAI API Key：

```text
OPENAI_API_KEY
```

OpenAI API Key Provider 与 Codex 会员账号 Provider 相互独立：

- `openai/<model>` 使用 `OPENAI_API_KEY`；
- `codex/default` 使用 Codex CLI 保存的 ChatGPT 账号；
- 外部 Codex 应用仍使用自己的账号和模型配置。

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
- 使用内置聊天时，需要配置云端 Provider API Key，或启动 Ollama／LM Studio 本地服务。

## 安装

当前 `main` 与上游 Fennara 0.4.0 保持一致，因此可以使用上游官方发行版。

### 方式一：安装插件

打开 [Fennara 最新发行版](https://github.com/fennaraOfficial/fennara-godot-ai/releases/latest)，下载 `fennara-addon-latest.zip`，将其中的：

```text
addons/fennara/
```

复制到 Godot 项目中。

启动项目后，在 Fennara 面板中点击 **Set Up Fennara**。

### 方式二：使用 CLI

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

> [!NOTE]
> 上述安装命令下载的是上游 Fennara 官方发行版，不包含本仓库新增的 Codex 会员登录。使用本功能需要从本仓库构建或等待本仓库独立发行版。

## 配置内置聊天

在 Godot 的 Fennara 面板中打开：

```text
Chat Settings > Chat > Open providers
```

可选择：

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

完整说明见 [Provider 文档](docs/providers.md)。

## 配置外部 MCP 应用

在 Fennara 面板中打开：

```text
Chat Settings > MCP Apps
```

选择对应应用并点击 **Set Up**。

也可以使用命令行：

```bash
fennara mcp-setup --codex
fennara mcp-setup --help
```

完整说明见 [MCP 配置文档](docs/mcp-setup.md)。

## 更新

关闭 Godot 后，在项目目录运行：

```bash
fennara update
```

也可以在 Fennara 面板显示 **Update** 时直接执行更新。

## 隐私与遥测

上游 Fennara 默认每天最多发送一次匿名活跃安装事件，内容包括随机安装 UUID、Fennara 和 Godot 版本、操作系统及 CPU 架构，不包含项目数据、路径、提示词、工具活动、日志、截图或账号信息。

可通过以下任一方式关闭：

```text
Chat Settings > Chat > Anonymous telemetry
FENNARA_DISABLE_TELEMETRY=true
DO_NOT_TRACK=1
```

完整说明见 [匿名遥测文档](docs/telemetry.md)。

## 与上游的关系

- 上游项目：[fennaraOfficial/fennara-godot-ai](https://github.com/fennaraOfficial/fennara-godot-ai)
- 本仓库当前基于并同步上游 Fennara 0.4.0；
- Fennara 原始代码、品牌和社区资源归上游项目及其贡献者；
- 本仓库未来新增的扩展会在 README 和提交记录中单独标明；
- 不会将 Godot MCP Native 或其他第三方项目声明为本仓库自有实现。

## 文档

| 文档 | 内容 |
| --- | --- |
| [文档索引](docs/README.md) | 全部使用和开发文档 |
| [安装与故障排除](docs/setup.md) | 安装、更新和常见问题 |
| [Provider](docs/providers.md) | 内置聊天模型与 API Key |
| [MCP 配置](docs/mcp-setup.md) | 外部 AI 应用连接方式 |
| [工具说明](docs/tools.md) | Godot 编辑器反馈能力 |
| [匿名遥测](docs/telemetry.md) | 收集内容和关闭方式 |
| [贡献指南](CONTRIBUTING.md) | 开发和 Pull Request 规范 |

## 许可证

本项目沿用 MIT License，详见 [LICENSE.md](LICENSE.md)。
