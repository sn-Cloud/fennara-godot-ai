# Fennara Godot AI

## Embedded Codex Native Chat (Experimental)

This branch adds the initial architecture for an in-editor Codex client.

The goal is to provide a Godot dock similar to IDE Codex integrations:

```
Godot Editor Dock
        |
        | JSON-RPC
        v
codex app-server
        |
        | MCP
        v
Godot MCP Native
        |
        v
Godot Editor
```

### Godot MCP Native integration

The embedded Codex client is designed to automatically connect to Godot MCP Native.

Default MCP endpoint:

```
http://127.0.0.1:9080/mcp
```

Required Codex MCP configuration:

```toml
[mcp_servers.godot-mcp]
type = "streamableHttp"
url = "http://127.0.0.1:9080/mcp"
```

### Planned features

- Embedded Godot chat dock
- Codex app-server login flow
- ChatGPT subscription authentication through Codex
- Streaming responses
- Tool call visualization
- Approval UI
- Diff review
- Automatic Godot MCP Native discovery

The current implementation is an experimental foundation.

## Existing Fennara Documentation

Fennara gives AI assistants a live connection to Godot. Use it from MCP-capable apps like Codex, Claude, Cursor, Gemini, and Antigravity, or from the optional in-editor chat dock.
