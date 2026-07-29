# Codex Embedded Provider Architecture

Status: draft for maintainer review

Target for the first complete Draft PR: Windows x86_64

## User value

The Codex provider is optional. It exists for users who prefer to remain inside the Godot editor instead of switching between Godot and the Codex App or CLI. It does not attempt to replace the Codex harness. Codex remains the agent runtime; Fennara provides an embedded presentation, Godot connectivity, and a single-window workflow.

Users who prefer the Codex App or CLI connected to Fennara through MCP continue to use that workflow unchanged.

## Non-goals

The first version does not:

- reimplement the Codex harness;
- read, copy, export, or persist ChatGPT OAuth tokens;
- replace Fennara MCP with another Godot MCP implementation;
- emulate Codex context compaction in Fennara;
- silently replay a Fennara transcript into a missing Codex thread;
- change the behavior of any existing API-key or local-model provider.

## Ownership boundaries

| Concern | Codex owns | Fennara owns |
| --- | --- | --- |
| Authentication | OAuth flow, account credentials, refresh tokens, subscription state | Starting the login request, presenting the browser URL and account status, logout action |
| `CODEX_HOME` | Contents, format, credentials, saved Codex threads, Codex configuration | Selecting an explicit home path, passing it to the process, validating that the directory is usable |
| Model runtime | Model catalog, model behavior, native app-server protocol semantics | Provider availability, compatibility checks, model presentation in the existing picker |
| Threads | Thread contents, turn state, thread persistence and resume semantics | Persisting only the binding from a Fennara chat ID to a Codex thread ID |
| Context | Context window accounting and compaction | Rendering compaction status; bypassing Fennara-owned summarization for Codex chats |
| Commands and file changes | Execution, sandbox enforcement, native command/file-change events | Rendering activity and forwarding approval decisions |
| Godot tools | Selecting and invoking tools through the configured Fennara MCP server | MCP server, tool definitions, permission classification, Godot editor/runtime bridge |
| Approvals | Native approval request and decision protocol | Existing approval UI, user decision, correlation and response transport |
| Chat history | Authoritative agent context and resumable thread | A local presentation/audit mirror of user-visible messages and events |
| Process lifecycle | App-server process behavior after spawn | Discovery/install, spawn, I/O, cancellation, crash detection, cleanup and concurrency limits |
| Error recovery | Native retryable/non-retryable protocol errors | Translating errors into stable provider states and user-facing recovery actions |

No secret from `CODEX_HOME` is copied into Fennara settings or the chat database.

## High-level flow

```text
Godot dock
  -> Fennara WebSocket chat protocol
  -> Fennara daemon Codex provider
  -> Codex app-server (JSON-RPC over stdio)
  -> Codex thread

Codex thread
  -> Fennara MCP server
  -> Godot tools and editor/runtime bridge
```

All app-server I/O, decoding, process waits, runtime installation and MCP tool work run outside the Godot main thread. The Godot plugin receives bounded asynchronous messages only.

## Provider modules

The implementation is split into the following boundaries.

### `runtime_locator`

Platform-neutral interface that returns one of:

- a verified Fennara-managed Codex runtime;
- a verified user-supplied runtime override;
- a verified Codex runtime discovered on `PATH`;
- unavailable, corrupted, incompatible, or unsupported-platform state.

Runtime selection order:

1. explicit `FENNARA_CODEX_COMMAND` override;
2. Fennara-managed pinned runtime;
3. compatible runtime on `PATH`.

An override is never silently replaced or modified.

### `runtime_installer`

Platform interface for managed installation. Windows is implemented first. Linux and macOS implementations use the same result and progress types later.

Installation requirements:

- download a pinned Codex release into a unique staging directory;
- verify the published digest before extraction or activation;
- verify `codex --version` and an app-server initialize probe;
- activate with an atomic directory rename;
- keep the previous verified runtime until activation succeeds;
- delete stale staging directories on the next startup;
- allow retry after interruption without treating a partial file as installed.

The managed runtime is stored under Fennara application data, not inside a Godot project and not inside the user's normal `CODEX_HOME`.

### `process_supervisor`

Owns child-process handles, stdin/stdout tasks, stderr capture, request correlation and termination.

The first version uses:

- short-lived processes for compatibility probes and account operations;
- one turn-scoped app-server process per active Codex chat turn;
- a persisted Codex thread ID to resume context between processes and daemon restarts;
- a bounded global semaphore for concurrent Codex processes.

Turn-scoped processes avoid a hidden long-lived process per historical chat while preserving Codex-owned thread state. Multiple chats and multiple Godot editors can run concurrently up to the configured process limit. Fennara already prevents two simultaneous turns in the same chat.

Shutdown sequence:

1. send `turn/interrupt` when a turn exists;
2. wait for a bounded grace period;
3. close stdin;
4. terminate the child;
5. force-kill the process tree after the final timeout.

A process exit is converted into a provider error with captured, size-bounded stderr. The persisted thread binding is retained so the next turn can attempt `thread/resume`.

### `protocol_client`

Typed JSON-RPC boundary responsible for:

- initialize/initialized handshake;
- request IDs and response correlation;
- server notifications;
- server-to-client approval requests;
- protocol timeouts;
- unknown-event tolerance;
- version and capability extraction.

Raw app-server values do not escape this module. Unknown notifications are logged at debug level and ignored unless they are required to complete an active request.

### `session_store`

Adds a provider-session table keyed by Fennara chat ID. It stores only non-secret metadata:

- `chat_id`;
- `provider_id`;
- `provider_thread_id`;
- a non-secret `codex_home_key` identifying the selected home configuration;
- runtime version used when the binding was last confirmed;
- creation and update timestamps;
- last resume status.

The table never stores OAuth tokens, account cookies, Codex configuration contents or a copy of the Codex thread.

## Command and Godot tool routing

Codex native command execution and file changes remain inside the Codex harness and sandbox.

Godot-specific operations are exposed to Codex through the existing Fennara MCP server. Fennara does not convert Codex command events into Fennara tool calls and does not execute a command twice.

Routing rules:

- `commandExecution` and `fileChange` events are rendered as Codex activity;
- `mcpToolCall` events identify the Fennara tool and are rendered using existing tool-result presentation when possible;
- the actual Godot request continues through Fennara MCP and the existing Godot bridge;
- MCP success, failure, timeout and cancellation are returned to Codex through MCP, not fabricated by the embedded chat adapter.

## App-server event rendering

The adapter normalizes Codex events into stable Fennara chat events.

| Codex event | Fennara presentation |
| --- | --- |
| agent message delta | assistant text delta |
| reasoning delta/summary | reasoning delta |
| command/file/MCP item started | activity item in running state |
| command/file/MCP item completed | activity item in completed/failed state |
| token usage update | usage update |
| context compaction started/completed | context status item; no Fennara summary is created |
| warning/config warning | non-fatal status or diagnostic |
| turn completed | finish state and usage |
| turn interrupted | cancelled finish state |
| process exit/protocol failure | failed generation with recovery guidance |

Event rendering is idempotent by provider item ID. Duplicate events after reconnect must not create duplicate visible items.

## Approvals and sandbox permissions

Fennara currently exposes two user modes.

### Ask for approval

- Codex approval policy: `on-request`;
- sandbox: `workspaceWrite`;
- command and file approval requests are shown in the existing Fennara approval UI;
- allow and deny are sent back to the exact app-server request ID;
- timeout, chat cancellation or editor disconnect resolve as deny/cancel, never allow.

### Full access

- Codex approval policy: `never`;
- sandbox: `dangerFullAccess`;
- Fennara does not display approval prompts that Codex should not request in this mode;
- an unexpected approval request is denied and recorded as a compatibility diagnostic.

Godot MCP tools continue to use Fennara's existing permission classification. Selecting Full access affects both the Codex sandbox mapping and Fennara tool policy; it does not bypass tools that Fennara classifies as unsupported or denied.

## Codex thread and Fennara history ownership

A Fennara chat has at most one active Codex thread binding.

First turn:

1. create the Fennara chat and user message;
2. start a Codex thread;
3. persist the returned Codex thread ID before streaming the turn;
4. start the turn with only the new user input and attachments.

Later turns:

1. load the persisted binding;
2. spawn and initialize app-server;
3. resume the Codex thread;
4. start a new turn with only the new user input and attachments.

Fennara history is a UI/audit mirror. It is not replayed on every Codex turn.

If resume reports that the thread is missing or unreadable, Fennara marks the binding broken and presents an explicit action to start a new Codex thread. It does not silently rebuild context from the local transcript.

Fennara's existing “revert last turn” cannot rewind a Codex thread. The first version disables that action for Codex chats and explains why. A future implementation may use an official Codex fork/rollback primitive if one becomes available and can be tested.

## Codex-owned context compaction

For Codex chats, Fennara's provider-message summarization and context-overflow retry path are bypassed. Codex receives the current turn against its resumed thread and owns all compaction decisions.

Fennara may render compaction lifecycle events and store a non-authoritative marker for diagnostics, but it does not store or inject a replacement summary.

After compaction, the same thread ID remains authoritative. A daemon restart resumes that thread normally.

## Authentication and `CODEX_HOME`

Login and logout run through app-server account methods.

- Browser OAuth is initiated by Codex.
- Fennara stores only public account status needed by the UI.
- Credentials remain under `CODEX_HOME` and are never returned to the renderer.
- Account status is probed on daemon startup, provider selection and explicit refresh.
- Only one login attempt per `codex_home_key` can be active.
- Cancelling login terminates the login process and returns the UI to a disconnected state.

The default uses the user's normal Codex home so the official Codex App/CLI and Fennara can share the same authenticated account and threads. An advanced setting can select an isolated home, represented only by a non-secret key in the database.

## Version pinning and compatibility

The complete Draft PR defines:

- one pinned managed Codex version;
- a tested compatibility range for externally installed runtimes;
- the app-server capabilities required by this provider;
- a denylist for known-broken versions when necessary.

Compatibility is checked with `codex --version` and an initialize probe. A runtime outside the tested range is not started automatically. The UI shows the detected and required versions and offers installation of the pinned runtime on supported platforms.

Protocol fields are decoded defensively. Optional additions are tolerated; missing required methods or incompatible response shapes produce an “incompatible runtime” state rather than a daemon crash.

## Platform boundaries

Platform-specific code is limited to runtime discovery, installation and process-tree termination.

```text
CodexPlatform
  locate_runtime()
  managed_runtime_path()
  install_pinned_runtime(progress, cancel)
  build_spawn_command(runtime, args, env)
  terminate_process_tree(process)
```

Provider sessions, authentication protocol, event normalization, approvals, persistence and UI behavior are platform-neutral.

### Windows first version

Windows x86_64 implements all platform operations and is the only supported managed-runtime target in the first Draft PR.

### Linux and macOS later

Linux and macOS add implementations of the same interface. No provider or UI protocol changes should be required.

### Unsupported platforms

The Codex provider remains visible but unavailable, with a clear message stating that embedded Codex is not supported on that platform yet. Existing providers and external MCP usage remain fully functional.

## Responsiveness requirements

The implementation must not block Godot's main thread.

Acceptance requirements:

- no synchronous process spawn, filesystem scan, download, extraction or app-server read loop in GDScript callbacks;
- renderer updates are batched and size-bounded;
- high-frequency deltas are coalesced before crossing the WebSocket/UI boundary;
- tool calls run through existing asynchronous daemon/Godot bridge paths;
- a stress turn with continuous streaming and repeated Godot tools does not introduce a measurable sustained editor-frame stall attributable to the Codex provider.

Manual profiling records editor frame-time samples and daemon CPU/memory while the automated fake app-server emits worst-case event bursts.

## Failure behavior

| Failure | User-visible behavior | Recovery |
| --- | --- | --- |
| runtime missing | provider unavailable | install pinned runtime or select external executable |
| partial/corrupt install | install marked incomplete | remove staging data and retry |
| incompatible version | provider unavailable with detected version | install pinned runtime |
| authentication failed | disconnected with error | retry login |
| login cancelled | disconnected | start login again |
| thread missing | chat requires new Codex thread | explicit start-new-thread action |
| app-server crash | active generation fails, partial text retained | next turn retries resume with a new process |
| daemon restart | no active process remains | reload binding and resume thread |
| approval timeout/disconnect | request denied/cancelled | retry the turn or action |
| concurrency limit reached | queued or busy status | starts when a slot is available or user cancels |

## Regression boundary

Codex-specific behavior is selected only when the resolved provider adapter is `CodexAppServer`. Existing provider request construction, tool loop, context summarization and authentication remain unchanged for all other adapters.

The test suite must prove that existing providers still resolve, authenticate and stream through their original paths when Codex is unavailable, disabled, incompatible or failing.
