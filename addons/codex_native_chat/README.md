# Godot Codex Native Chat

Godot Codex Native Chat embeds a Codex client in the Godot editor. It starts the official `codex app-server` process in the background, uses the user's existing Codex/ChatGPT authentication, and configures Codex to connect to Godot MCP Native.

## Architecture

```text
Godot editor dock
      |
      | bidirectional JSON-RPC over stdio
      v
codex app-server
      |
      | Codex MCP client
      v
Godot MCP Native
http://127.0.0.1:9080/mcp
      |
      v
Current Godot editor and running project
```

The addon does not contain an AI model and does not read or store ChatGPT OAuth tokens. Authentication, token refresh, thread storage, model execution, filesystem tools, shell tools, Git tools, and MCP calls remain owned by the official Codex process.

## Requirements

- Godot 4.6 or newer.
- The official Codex CLI installed locally.
- A ChatGPT plan with Codex access, or another Codex-supported provider.
- Godot MCP Native installed and enabled when Godot editor control is required.

## Installation

1. Copy `addons/codex_native_chat/` into the Godot project.
2. Install Godot MCP Native into `addons/godot_mcp/` and enable it.
3. Open **Project > Project Settings > Plugins**.
4. Enable **Codex Native Chat**.
5. Open the **CodexNativeChatDock** dock.

The addon attempts to find Codex automatically. When auto-detection fails, open **Settings** and set the full path to `codex.exe`, `codex.cmd`, or the Unix `codex` executable.

## ChatGPT login

Press **Login**. The dock calls:

```text
account/login/start { type = "chatgpt" }
```

Codex opens its official browser-based login flow. Codex stores and refreshes the resulting credentials. The addon receives only account status notifications such as the authentication mode and plan type.

## Godot MCP Native integration

The default endpoint is:

```text
http://127.0.0.1:9080/mcp
```

The addon creates or updates the following project-level Codex configuration without replacing unrelated configuration:

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
enabled = true
startup_timeout_sec = 20
```

The file is written to:

```text
<godot-project>/.codex/config.toml
```

After changing the endpoint, the addon calls `config/mcpServer/reload` and checks `mcpServerStatus/list`. Godot MCP Native normally starts its HTTP server from inside the editor on port `9080`.

If Godot MCP Native uses a bearer token, configure it in Codex manually rather than committing the token to the project repository. For example, use an environment variable in the user-level Codex configuration:

```toml
[mcp_servers.godot-mcp]
url = "http://127.0.0.1:9080/mcp"
bearer_token_env_var = "GODOT_MCP_TOKEN"
```

## Implemented features

- Starts and stops `codex app-server` with redirected stdio.
- Performs the required `initialize` / `initialized` handshake.
- Reads the current Codex account and starts ChatGPT login/logout.
- Creates new Codex threads and resumes the most recent thread for each Godot project.
- Starts and interrupts turns.
- Streams agent messages into the Godot dock.
- Displays command, file-change, MCP-tool, and web-search activity.
- Displays the aggregated turn diff.
- Handles command and file-change approvals.
- Handles additional permission requests.
- Handles Codex `request_user_input` and MCP elicitation requests.
- Configures and reloads Godot MCP Native.
- Exposes model, sandbox, approval policy, endpoint, executable, and auto-connect settings.

## Default safety settings

```text
sandbox: workspace-write
approval policy: on-request
```

This allows Codex to modify the current project while requiring approval when it requests elevated operations. The settings panel also exposes `read-only`, `danger-full-access`, `untrusted`, and `never`. Selecting unrestricted modes gives Codex the corresponding local machine privileges; use them only in a trusted project and repository.

## Typical workflow

1. Enable Godot MCP Native.
2. Enable Codex Native Chat.
3. Confirm both status lines become connected/ready.
4. Log in when required.
5. Enter a task such as:

```text
Inspect the current scene, implement the missing player damage feedback, run the project, and verify the result through Godot MCP Native.
```

6. Review command and file approvals in the dock.
7. Inspect the **Diff** and **Logs** tabs before accepting the final result.

## Limitations

- The addon depends on the installed Codex app-server protocol version. It uses the stable v2 thread/turn API and opts into experimental requests required for user-input and permission workflows.
- Windows npm installations may expose `codex.cmd`; the addon supports it through `cmd.exe`, but a native `codex.exe` is preferred for the cleanest stdio behavior.
- The dock provides practical rich-text streaming, not the full rendering system used by the official Codex applications.
- Real ChatGPT OAuth, proxy behavior, and Godot MCP Native runtime behavior must be validated on the user's machine because CI cannot access the user's account or editor session.
