# AGENTS.md

## 项目目标

维护一个 Godot 编辑器内 AI 管理插件。Codex 和 Kimi 必须分别使用各自官方本地协议；Godot 专用能力只能来自独立安装的 Godot MCP Native。

## 约束

- 不得添加 Fennara MCP、daemon、CLI、WebSocket Bridge 或旧工具 Schema。
- 不得打包 Godot MCP Native。
- 不得读取或保存第三方 OAuth Token。
- Kimi ACP 文件访问必须限制在项目根目录。
- 面向用户的说明和 UI 使用中文；协议字段、类名和命令保持官方形式。
- CI 默认只允许手动触发。
- 不生成 ZIP。
