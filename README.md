# Fennara Godot AI

[![Discord](https://img.shields.io/badge/Discord-加入%20Fennara-5865F2?logo=discord&logoColor=white)](https://discord.com/invite/3fF4ft9PTk)
[![演示](https://img.shields.io/badge/演示-查看全部-red?logo=youtube&logoColor=white)](docs/demos.md)
[![许可证](https://img.shields.io/badge/许可证-MIT-blue.svg)](LICENSE.md)

Fennara 已被多家 Godot 开发团队使用，其中包括 [Somni Game Studios](https://somnigamestudios.com/)。

Fennara 为 AI 助手提供与 Godot 编辑器的实时连接。它既可供 Codex、Claude、Cursor、Gemini、Antigravity 等支持 MCP 的应用使用，也可通过可选的 Godot 编辑器内置聊天面板直接使用。

Agent 可以检查场景、分析脚本、截取画面、读取运行时错误，并在编辑器中验证修改结果，而不是只根据项目文件进行推测。

## Codex 内置对话插件

当前分支还包含一个独立的 Godot 内置对话面板，底层使用官方 `codex app-server`。它复用 Codex／ChatGPT 登录状态，并自动配置 Codex 连接位于 `http://127.0.0.1:9080/mcp` 的 Godot MCP Native。

安装方法、架构、权限和验证说明请参阅 [Godot Codex 内置对话](addons/codex_native_chat/README.md)。

<table>
  <tr>
    <td width="46%">
      <a href="https://www.youtube.com/watch?v=2vSYP7GyA5U">
        <img src="https://i.ytimg.com/vi/2vSYP7GyA5U/hqdefault.jpg" alt="Fennara 与其他 Godot MCP 的对比" width="100%" />
      </a>
    </td>
    <td>
      <strong>查看精选演示</strong><br />
      Fennara 与其他 Godot MCP 的对比。<br />
      <a href="https://www.youtube.com/watch?v=2vSYP7GyA5U">播放视频</a><br />
      <a href="docs/demos.md">浏览全部演示视频</a>
    </td>
  </tr>
</table>

## 功能说明

- 通过 MCP 向外部 AI 应用提供理解 Godot 的工具。
- 在 Godot 编辑器内部提供可选的本地聊天面板。
- 返回真实的 Godot 反馈，包括场景树、诊断信息、截图、运行时日志和验证结果。
- 让 Agent 以当前已打开的编辑器为依据，而不是只依赖文件系统。

外部 MCP 应用和内置聊天使用各自独立的模型配置。参阅 [MCP 应用与内置聊天](docs/chat-vs-mcp.md) 和 [内置聊天模型提供方](docs/providers.md)。

## 环境要求

- Godot 4.5 或更高版本。
- 支持的桌面系统：Windows x86_64、Linux x86_64 或 macOS arm64。
- 只有在需要通过 Claude、Codex、Cursor、Gemini、Antigravity 或其他外部 AI 应用使用 Fennara 时，才需要支持 MCP 的编程应用。
- 只有在需要使用 Fennara 内置聊天面板时，才需要配置聊天模型提供方。可以使用云端模型密钥，也可以使用 Ollama／LM Studio 等本地模型服务。

完整安装流程请参阅 [安装与配置](docs/setup.md)。

## 安装后包含的组件

- 位于 `res://addons/fennara/` 的 Fennara 插件。
- 安装在 Fennara 应用数据目录中的轻量 `fennara` CLI。
- 供 AI 编程应用使用的本地 MCP Server。
- 在 MCP／聊天请求与当前 Godot 编辑器之间进行桥接的本地守护进程。
- 为 AI Agent 自动生成的项目指导文件。

内置聊天面板使用平台 WebView：Windows 使用 Microsoft Edge WebView2，macOS 使用 WKWebView／WebKit，Linux 使用由 Fennara 管理的共享 CEF 运行时。即使可选聊天面板无法启动，MCP 工具仍可正常工作。

## 安装

在 Windows 和 Linux 上，可以选择插件安装或 CLI 安装。macOS 建议使用下面的 CLI 安装方式，以避免手动下载和解压插件 ZIP 后可能出现的系统安全提示。

### 将插件添加到项目

- 打开 [最新版本](https://github.com/fennaraOfficial/fennara-godot-ai/releases/latest)，下载 `fennara-addon-latest.zip`，将其中的 `addons/fennara/` 解压到项目中。

打开项目，选择 Fennara 面板，然后点击 **Set Up Fennara**。

> **macOS：** 当前版本插件中包含尚未经过 Apple 公证的原生库。通过浏览器下载并手动解压插件 ZIP 时，macOS 可能提示无法验证 `libfennara.macos.editor` 是否安全。为避免该提示，请使用下面的 CLI 安装方式。已经出现提示时，关闭 Godot，删除手动复制的 `addons/fennara/`，然后通过 CLI 安装。

### 使用 CLI 安装（macOS 推荐）

CLI 安装的是同一个 Fennara 插件。macOS 推荐使用这种方式，因为它可以绕过浏览器和 Finder 的隔离属性，避免上述安全提示。

Windows 安装命令：

```powershell
irm https://raw.githubusercontent.com/fennaraOfficial/fennara-godot-ai/main/install.ps1 | iex
```

macOS 和 Linux 安装命令：

```bash
curl -fsSL https://raw.githubusercontent.com/fennaraOfficial/fennara-godot-ai/main/install.sh | sh
```

然后进入 Godot 项目目录运行：

```bash
cd path/to/your-godot-project
fennara install
```

故障排查请参阅 [安装与配置](docs/setup.md)，完整命令说明请参阅 [Fennara CLI](docs/cli.md)。

## 配置模型提供方或连接 MCP 应用

### 内置聊天

打开 **Chat Settings > Chat**，选择 **Open providers**，然后连接模型提供方。

Fennara 对云端模型采用用户自备密钥模式，也支持本地 Ollama 或 LM Studio 服务。参阅 [支持的模型提供方](docs/providers.md)。

### MCP 应用

打开 **Chat Settings > MCP Apps**，找到需要使用的应用并点击 **Set Up**。

也可以在终端中连接：

```bash
fennara mcp-setup --codex
fennara mcp-setup --help
```

Chat Settings 中未列出目标 MCP 应用时，请参阅 [MCP 配置](docs/mcp-setup.md)，其中包含完整应用列表和手动配置说明。

## 更新

Fennara 面板显示 **Update** 时，点击并按照提示操作。

> **从 Fennara v0.3.8 或更早版本升级：** 请先使用对应平台的安装命令重新安装一次 CLI，然后再运行 `fennara update`。旧版 CLI 使用的发布标签已经停用，无法发现当前版本。重新安装 CLI 只会切换后续更新来源，不会删除现有项目插件或配置。

> **macOS 用户从 Fennara v0.3.11 升级：** 更新前请先使用 macOS 安装命令重新安装一次 CLI。v0.3.11 CLI 会在自更新前拒绝现有的 macOS framework bundle。重新安装只会替换 CLI，不会删除现有项目插件或配置。

通过终端更新时，先关闭 Godot，然后运行：

```bash
cd path/to/your-godot-project
fennara update
```

恢复和诊断方法请参阅 [更新 Fennara](docs/setup.md#update-fennara)。

## 工具能力

Fennara 提供少量面向 Godot 的专用工具：

- 写入或更新项目文件并返回诊断结果。
- 执行一次性的场景编辑脚本。
- 检查场景树、节点、资源和 Godot 类。
- 验证场景。
- 截取画面。
- 启动运行时会话并读取运行日志。
- 对正在运行的场景执行小型运行时脚本。

Fennara 的目标不是替代 Agent 自带的文件工具，而是补充缺失的 Godot 反馈闭环。

## 演示

观看 Fennara 实际操作演示：

[![该 Godot 插件全面改变 AI 游戏开发](https://i.ytimg.com/vi/pijlHyiOnz4/hqdefault.jpg)](https://www.youtube.com/watch?v=pijlHyiOnz4&t=22s)

更多视频：

- [我给 Codex 一张游戏概念图，它在 Godot 中完成了这个项目](https://www.youtube.com/watch?v=ztbH6zBhxMc)
- [Fennara MCP 在 Godot 中制作 Katamari 风格游戏](https://www.youtube.com/watch?v=8y2Ub8pgNSs)
- [这个 Godot 插件改变了 AI 游戏开发方式](https://www.youtube.com/watch?v=wKln8248y2M)

更多内容请参阅 Fennara 频道的 [演示列表](docs/demos.md)。

## Star 历史

<a href="https://www.star-history.com/?repos=fennaraOfficial%2Ffennara-godot-ai&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=fennaraOfficial/fennara-godot-ai&type=date&theme=dark&legend=top-left&sealed_token=fezQNXcS0bAmXpZnoyG8FLlAkcnajD5wnBrugJG7WDJRaoSAqXHjV010Bm1XJN9cWChDHTsk1MaWr3jWkh8KF-Hqp1fxnJfmPlvjUc8vtS_kao5tXHGBGQyL5IHhgzDdaoMqjRdH5B8pdo2Z-Pm511AXJxdwOYbXFCqcKNkpgS6WgxVUNjOTrKc5_ZkO" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=fennaraOfficial/fennara-godot-ai&type=date&legend=top-left&sealed_token=fezQNXcS0bAmXpZnoyG8FLlAkcnajD5wnBrugJG7WDJRaoSAqXHjV010Bm1XJN9cWChDHTsk1MaWr3jWkh8KF-Hqp1fxnJfmPlvjUc8vtS_kao5tXHGBGQyL5IHhgzDdaoMqjRdH5B8pdo2Z-Pm511AXJxdwOYbXFCqcKNkpgS6WgxVUNjOTrKc5_ZkO" />
   <img alt="Star 历史图表" src="https://api.star-history.com/chart?repos=fennaraOfficial/fennara-godot-ai&type=date&legend=top-left&sealed_token=fezQNXcS0bAmXpZnoyG8FLlAkcnajD5wnBrugJG7WDJRaoSAqXHjV010Bm1XJN9cWChDHTsk1MaWr3jWkh8KF-Hqp1fxnJfmPlvjUc8vtS_kao5tXHGBGQyL5IHhgzDdaoMqjRdH5B8pdo2Z-Pm511AXJxdwOYbXFCqcKNkpgS6WgxVUNjOTrKc5_ZkO" />
 </picture>
</a>

## 文档

| 建议入口 | 适用场景 |
| --- | --- |
| [文档首页](docs/README.md) | 查看全部指南和参考资料 |
| [安装与配置](docs/setup.md) | 安装、更新和故障排查 |
| [聊天模型提供方](docs/providers.md) | 内置聊天模型和密钥配置 |
| [MCP 配置](docs/mcp-setup.md) | Codex、Claude、Cursor 和其他 MCP 应用 |
| [工具说明](docs/tools.md) | Agent 可获得的 Godot 反馈能力 |
| [参与贡献](CONTRIBUTING.md) | 开发和 Pull Request 指南 |

## 社区

欢迎在 Discord 中咨询安装问题、交流使用经验或提供早期反馈：

https://discord.com/invite/3fF4ft9PTk

## 许可证

参阅 [LICENSE.md](LICENSE.md)。
