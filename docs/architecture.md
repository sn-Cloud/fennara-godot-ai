# 架构

## 管理层

`GodotAiManagerDock` 只负责用户界面与公共状态。`AiAgentBackend` 定义统一事件，两个实现分别适配官方协议：

```text
GodotAiManagerDock
└── AiAgentBackend
    ├── CodexAgentBackend → codex app-server
    └── KimiAgentBackend  → kimi acp
```

## Godot 能力层

Godot MCP Native 是唯一 Godot MCP：

```text
Codex app-server ─┐
                  ├─ MCP HTTP → Godot MCP Native → Godot 编辑器
Kimi ACP ─────────┘
```

Codex 通过项目 `.codex/config.toml` 连接；Kimi 通过 ACP `session/new`／`session/load` 的 `mcpServers` 参数连接。

## 不存在的运行时

仓库不包含也不启动 Fennara MCP、daemon、CLI、WebSocket Bridge 或旧工具 Schema。Fennara 仅作为 AI 管理交互设计的来源之一记录在 NOTICE 中。
