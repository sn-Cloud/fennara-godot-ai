# 发布检查

发布前确认：

1. Godot 4.6.3 在 Windows 与 Linux 能加载插件；
2. Codex 模拟协议与官方 app-server 握手通过；
3. Kimi 模拟 ACP 与官方 `kimi acp` 初始化通过；
4. Godot MCP Native 配置只包含 `godot-mcp`；
5. Kimi 文件反向 RPC 无法越过项目根目录；
6. 发布树不存在 Fennara MCP、daemon、CLI、Bridge 或旧工具定义；
7. README 中仍明确 Godot MCP Native 为独立依赖；
8. 不生成 ZIP。
