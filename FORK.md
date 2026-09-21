# sn-Cloud Fennara Fork

This repository is a personal maintenance fork of
[fennaraOfficial/fennara-godot-ai](https://github.com/fennaraOfficial/fennara-godot-ai).
It keeps the complete upstream Fennara feature set and adds built-in chat access
through the official OpenAI Codex CLI and a user's ChatGPT subscription.

The separate [sn-Cloud/godot-ai-manager](https://github.com/sn-Cloud/godot-ai-manager)
project owns the earlier Godot MCP Native and Codex/Kimi dual-backend design.
Those components are not part of this repository.

## Windows Complete Addon

Copy the packaged `addons/fennara` folder into a Godot 4.5+ project, open
the Fennara dock, and click **Set Up Fennara**. Choose a provider or sign in
to **Codex (ChatGPT account)**. Users do not install Rust, Node.js, or a
separate Fennara/Codex CLI. Windows embedded chat uses Edge WebView2.

The complete addon includes the Windows GDExtension, ripgrep, Fennara CLI,
daemon/MCP launchers and runtimes, and the native Codex distribution with
its sandbox helpers. First setup verifies the bundled hashes and prepares
a build-specific runtime cache under `%LOCALAPPDATA%/Fennara`. Settings,
chat history and logs remain in that user directory. No release download
or self-update occurs during bundled setup. A running different build must
have no connected editors before it can be replaced; close other editors
and retry when prompted. The setup panel reports failures and offers Retry.

Complete addons automatically check the fork's GitHub releases at editor startup.
The existing update panel downloads and verifies a complete addon, then asks to
close Godot before applying it. Its existing backup/recovery flow is retained.
Only `sn-Cloud/fennara-godot-ai` complete Windows assets are accepted, so upstream
releases cannot overwrite Codex support. Ordinary non-bundled installations
continue using the original upstream discovery, installation and update paths.
Older packages without this updater need one manual complete-folder replacement.

The bundled Codex runtime independently checks the official npm stable release
when the model catalog is requested, at most once every six hours. It verifies
the registry's SHA-512 integrity and the extracted runtime before activation.
Updates live in `%LOCALAPPDATA%/Fennara/codex-runtime`; existing conversations keep
their original process and new connections use the updated runtime. Failures
retain the previous runtime and are recorded in `codex-runtime/status.json`.
Refresh the model picker after an update to see the new catalog. No Node.js is
required on users' machines. Global Codex installs, ChatGPT credentials, other
providers and non-bundled installations are untouched. `FENNARA_CODEX_COMMAND`
disables managed updates for an explicit override; setting
`FENNARA_CODEX_AUTO_UPDATE_DISABLED` disables background update checks.

Maintainers build the Windows GDExtension with SCons and the Rust workspace
with `cargo build --release --workspace --locked`, then package the folder:

```powershell
node scripts/package-windows-standalone-addon.mjs --codex-root <native-codex-vendor-directory> --ripgrep <path-to-rg.exe>
```

The Codex directory must contain `bin/codex.exe` and `codex-resources/`
(including the command runner and Windows sandbox setup helper). The full
vendor directory and its metadata are preserved. The script outputs
`dist/fennara-addon-windows-x86_64-standalone-v<version>/addons/fennara`.
It does not publish a release or change upstream release workflows.

The packaging command also produces an adjacent versioned `.zip` and `.sha256`.
To distribute a plugin update, a maintainer must explicitly publish a stable
`v<version>` release on the fork with
`fennara-addon-windows-x86_64-standalone-v<version>.zip`. GitHub's release asset
must include its computed `sha256:` digest. The version must be greater than
the installed addon version. Source-only releases are not offered as updates.
Publishing remains manual; no existing upstream workflow is changed.

Use official Codex **0.155.1 or newer stable** for complete addon builds.
The packager checks `codex-package.json` before replacing an existing output.
Codex 0.145.0 returned a valid catalog without Astra; 0.155.1 returned
`gpt-6-astra` for the same account during verification. Model discovery also
depends on the bundled runtime version, so refresh the runtime when updating
the addon, rather than only refreshing its UI. Maintainers can stage the
verified version without changing a global installation:

```powershell
npm install --prefix temp/codex-runtime-0.155.1 --no-audit --no-fund --ignore-scripts @openai/codex@0.155.1
node scripts/package-windows-standalone-addon.mjs --codex-root temp/codex-runtime-0.155.1/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc --ripgrep <path-to-rg.exe>
```

These are maintainer build steps; addon users still only replace the complete
`addons/fennara` folder and run setup in Godot.

Validate a built package with `node scripts/test-standalone-addon.mjs
<godot.exe> <complete-addon-directory>` using the main Godot executable (not
the Windows console wrapper). The test requires the daemon port to be free,
uses a fresh user-data directory under repository `temp/`, checks real editor
connectivity and damaged-bundle handling, then shuts down its own daemon.

## ChatGPT Account Provider Setup

The fork supports two independent OpenAI connection methods:

- `openai/<model>` uses an OpenAI API key and is billed through the API account.
- `codex/<model>` uses the bundled or locally installed Codex CLI and its ChatGPT account.

To use the ChatGPT account provider:

1. Use the complete Windows addon, or install the official Codex CLI when using a lightweight addon.
2. Open **Chat Settings > Chat > Open providers**.
3. Choose **Codex (ChatGPT account)**.
4. Complete the browser OAuth flow.
5. Open the model picker and select a model returned by your Codex account.

Models and their reasoning-effort options come from the official
[Codex app-server `model/list` protocol](https://developers.openai.com/codex/app-server#list-models-modellist).
Fennara follows all pages, excludes hidden models, and uses the returned names,
supported efforts and defaults. Refresh the model picker to request the current
catalog. Availability follows that Codex runtime and account; it need not match
another ChatGPT or Codex client. Catalog failures are shown without substituting
hardcoded models. A previously selected model that disappears must be reselected.
The legacy `codex/default` selection resolves to the official default model.
Before generation, Fennara checks the selected model and effort against the
official catalog again. Models without reasoning options omit effort entirely.

Fennara starts `codex app-server --stdio` locally. The Codex CLI owns OAuth
credentials, refresh tokens, account status, model access, and subscription
enforcement. Fennara does not read or store ChatGPT tokens.
Codex streamed reply text is retained in the final completion used to save and
refresh chat history.

Codex tool activity renders and records through Fennara's native tool cards.
The official `item/started` and `item/completed` notifications for MCP tool
calls, command executions, file changes, and web searches map onto the same
`function_call` and `tool_result` transcript items used by the other built-in
providers, so tool cards, persisted results, history replay, and traces follow
one pipeline instead of transient status text. A tool approval and its result
share one card id. Command output and diffs are truncated for display. Results
of tools that already executed are persisted even when the turn later fails,
so the transcript keeps a record of completed work. Completed tool groups stay
available to subsequent conversation replay; a later provider failure is stored
as a separate assistant message. If the UI disconnects, already received tool
results (including queued results) are saved without requiring another UI send.

Codex chat starts the matching bundled MCP runtime as `fennara_chat`, with an
explicit `--project-path` binding. This thread-local configuration disables the
legacy `fennara` MCP entry for this chat only; it never changes external clients'
configuration or the global MCP Target.

Fennara tool calls use the same `PermissionPolicy` as the other built-in chat
providers: read-only operations (including `fennara_status`) run directly;
project writes and execution ask in **Ask** mode and run directly in **Full
access**. Argument-dependent operations such as `project_settings` and
`runtime_session` are classified by action. Unsupported tools/actions remain
denied. Automatic decisions require a matching active call on the plugin-owned
MCP server, including its thread, turn, tool name, and arguments.

Native Codex operations use `read-only` / `untrusted` in Ask mode and
`workspace-write` / `on-request` in Full access. Full access does not grant
unrestricted host access. Other providers' permission rules are unchanged.
External MCP services, unmatched requests and additional native permissions
still use the existing session-bound Approve/Deny controls. Generic MCP input
forms and authentication URL flows are not treated as tool approvals.

Codex sessions can use the existing Fennara MCP tools for Godot editor and
runtime operations. This does not install or replace Fennara MCP with Godot MCP
Native.

## Upstream Relationship

The fork follows upstream releases while retaining the Codex account provider.
When merging upstream changes, keep the provider implementation, account UI,
settings migration, and `codex/default` model routing together.

Fork-only behavior is documented in this file; setup, release, and repository
map pages link here for the complete Windows addon workflow.
