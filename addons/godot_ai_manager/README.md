# Godot AI 管理器插件

该 Godot 4.6+ EditorPlugin 在一个 Dock 内管理 Codex 与 Kimi Code 两个官方后端。

## 依赖关系

| 组件 | 来源 | 职责 |
| --- | --- | --- |
| Godot AI 管理器 | 本仓库 | UI、后端切换、会话、审批、Diff、日志和设置。 |
| Codex CLI | OpenAI 官方 | ChatGPT 登录、模型、工具、会话和 MCP 客户端。 |
| Kimi Code CLI | Moonshot AI 官方 | Kimi 会员登录、ACP Agent、工具、会话和 MCP 客户端。 |
| Godot MCP Native | 独立第三方仓库 | 唯一的 Godot MCP Server 与 Godot 专用工具。 |

Godot MCP Native 官方仓库：<https://github.com/yurineko73/Godot-MCP-Native>

本插件不包含 Godot MCP Native，也不包含 Fennara MCP。

## 目录

```text
addons/godot_ai_manager/
├── agent_backend.gd
├── codex_backend.gd
├── kimi_backend.gd
├── jsonrpc_process_client.gd
├── raw_process_runner.gd
├── command_resolver.gd
├── codex_config_manager.gd
├── godot_ai_manager.gd
├── godot_ai_manager_dock.gd
├── godot_ai_manager_dock.tscn
└── plugin.cfg
```

## Codex 配置

插件只维护以下表：

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
enabled = true
startup_timeout_sec = 20
```

其他 Codex 配置会保留。检测到 Fennara MCP 条目时仅提示。

## Kimi MCP 转发

创建或加载 ACP 会话时传入：

```json
{
  "name": "godot-mcp",
  "type": "http",
  "url": "http://127.0.0.1:9080/mcp",
  "headers": []
}
```

## 文件安全

Kimi ACP 可能向客户端发出 `fs/read_text_file` 和 `fs/write_text_file`。本插件会规范化路径，并拒绝当前 Godot 项目目录之外的访问。

## 会员登录

- Codex：通过 `account/login/start { type = "chatgpt" }` 打开官方登录页面。
- Kimi：运行官方 `kimi login`，捕获设备码说明并打开验证页面。

插件不保存 OAuth Token。
