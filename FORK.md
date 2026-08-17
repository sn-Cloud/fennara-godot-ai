# sn-Cloud Fennara Fork

This repository is a personal maintenance fork of
[fennaraOfficial/fennara-godot-ai](https://github.com/fennaraOfficial/fennara-godot-ai).
It keeps the complete upstream Fennara feature set and adds built-in chat access
through the official OpenAI Codex CLI and a user's ChatGPT subscription.

The separate [sn-Cloud/godot-ai-manager](https://github.com/sn-Cloud/godot-ai-manager)
project owns the earlier Godot MCP Native and Codex/Kimi dual-backend design.
Those components are not part of this repository.

## ChatGPT Account Provider

The fork supports two independent OpenAI connection methods:

- `openai/<model>` uses an OpenAI API key and is billed through the API account.
- `codex/default` uses the locally installed Codex CLI and its ChatGPT account.

To use the ChatGPT account provider:

1. Install the official Codex CLI and confirm `codex --version` works.
2. Open **Chat Settings > Chat > Open providers**.
3. Choose **Codex (ChatGPT account)**.
4. Complete the browser OAuth flow.
5. Select `codex/default`.

Fennara starts `codex app-server --stdio` locally. The Codex CLI owns OAuth
credentials, refresh tokens, account status, model access, and subscription
enforcement. Fennara does not read or store ChatGPT tokens.

The default Fennara permission mode maps to Codex `workspaceWrite`. Choosing
Fennara **Full access** maps the Codex thread to `dangerFullAccess`.

Codex sessions can use the existing Fennara MCP tools for Godot editor and
runtime operations. This does not install or replace Fennara MCP with Godot MCP
Native.

## Upstream Relationship

The fork follows upstream releases while retaining the Codex account provider.
When merging upstream changes, keep the provider implementation, account UI,
settings migration, and `codex/default` model routing together.

The canonical upstream documentation and its translations remain unchanged so
the upstream documentation consistency gate can run without fork-specific
translation drift. Fork-only behavior is documented in this file.
