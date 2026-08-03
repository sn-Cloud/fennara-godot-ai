# Codex app-server ownership boundaries and acceptance matrix

This document defines the ownership contract for the optional Codex experience embedded in the Fennara Godot panel. The central invariant is that Fennara owns its local UI, chat records, project scope and provider binding, while the official Codex runtime owns authentication, remote thread state, context compaction and execution of Codex-selected commands or MCP tools.

## Ownership boundaries

| Concern | Authoritative owner | Fennara responsibility | Failure behavior |
| --- | --- | --- | --- |
| Command and Godot tool routing | Codex selects the command or MCP tool. The configured Fennara MCP server owns Godot-aware routing and execution. | Pass the project working directory and permissions to Codex; render command and MCP lifecycle events. A Codex-executed MCP call is never inserted into Fennara's internal tool loop, so it cannot execute twice. | Command, file-change and MCP failures remain visible provider events. The daemon does not retry an already executed tool implicitly. |
| app-server event rendering | Codex app-server is authoritative for event identifiers, status, arguments and results. | Convert streaming text, reasoning, plan, usage, command, file-change and MCP events into Fennara stream events and native tool cards. MCP arguments are limited to 8 KiB and displayed content to 32 KiB; image bytes are replaced by metadata. | Unknown events are ignored. Invalid JSON or an unexpected process exit becomes a provider error with bounded stderr diagnostics. |
| Approvals and sandbox permissions | The user decision is authoritative. Codex enforces the selected approval policy and sandbox. | Map normal mode to `approvalPolicy=on-request` plus `sandbox=workspaceWrite`; map Full access to `approvalPolicy=never` plus `sandbox=dangerFullAccess`. Deliver command and file approvals to the Fennara UI and return `accept`, `decline` or `cancel`. | Missing UI approval channels default to decline. Approval timeout or closed response channels also deny. |
| Codex thread and Fennara history | Codex owns the remote thread. Fennara owns local chat messages and a binding from `(chat_id, provider_id)` to the Codex thread. | Use `thread/start` once, persist the returned thread ID, then use `thread/resume`. A resumed turn sends only the newest user input. | If Codex reports that the thread does not exist, the binding is marked broken and Fennara refuses silent reconstruction or local-history replay. Other errors are not reclassified as missing threads. |
| Codex-owned context compaction | Codex owns when and how its thread is compacted. | Observe compaction events without producing a second Fennara summary or replacing the Codex thread. | The same thread ID is resumed after compaction and after app-server/daemon restart. |
| Authentication and `CODEX_HOME` | Official Codex CLI/app-server owns OAuth tokens, refresh tokens, account state and subscription entitlement. | Start official `account/*` RPCs, expose non-secret status, and pass the selected home to the process. Home precedence is `FENNARA_CODEX_HOME`, then `CODEX_HOME`, then Codex's default. Persist the normalized actual `codexHome` and runtime version with each chat binding. | Fennara never reads or stores ChatGPT tokens. A binding is not resumed when its saved Codex home differs from the current runtime; the user must restore the original home or explicitly start a new thread. |
| Process lifecycle, cancellation, crashes and concurrency | The operating system owns process termination; Codex owns durable thread files in its home. | Start a separate app-server process for each status/login/stream operation, set `kill_on_drop`, send `turn/interrupt` on cancellation, reap children on shutdown, capture bounded stderr and reconnect by thread ID after a crash. Keep chat bindings isolated in SQLite. | A crash is retryable but never causes automatic history replay. Multiple chats and concurrent app-server sessions do not share mutable Fennara turn state. |
| Pinned runtime and compatibility | The tested runtime contract is Codex `0.144.4`; the minimum accepted external runtime is `0.144.0`. | Prefer `FENNARA_CODEX_COMMAND`, then a verified Fennara-managed runtime, then `PATH`. Validate `userAgent`, `codexHome`, `platformFamily` and `platformOs` from `initialize`. | Older, malformed or platform-mismatched runtimes are rejected before a turn begins. Newer runtimes at or above the minimum run as compatible but unverified. |

## Runtime and authentication details

- The managed runtime is currently available only for Windows x86_64.
- The managed binary URL, filename and SHA-256 are pinned to the tested version.
- Downloads use a temporary `.download` file, verify SHA-256 before activation, preserve the previous runtime during replacement and recover interrupted activation on the next attempt.
- Cancelling or failing a download removes the partial file.
- Public account status exposes installation, connection, plan and email metadata, but never serializes credentials.
- Login is single-flight per Fennara daemon. Chat streams remain independent and each receives its own app-server process.

## Thread and history lifecycle

1. Fennara creates or opens a local chat scoped to the current Godot project.
2. The first Codex turn calls `thread/start`, then saves the returned thread ID, normalized `codexHome` and runtime version.
3. Later turns verify the saved home against the active runtime and call `thread/resume`.
4. Only the latest user message is sent for a resumed turn. Fennara history remains local display/history data and is not replayed into the Codex thread.
5. Codex may compact its own context. Fennara observes the lifecycle event and keeps the same binding.
6. If the app-server exits, the next explicit request starts a new process and resumes the existing Codex thread.
7. If the thread is genuinely missing, Fennara marks the binding broken and requires an explicit new thread.

## Automated acceptance matrix

The following tests are part of the Rust workspace and use the fake app-server where isolation from real accounts is required.

| Area | Acceptance coverage |
| --- | --- |
| Login and logout | `fixture_login_success_updates_account_state`, `fixture_login_failure_remains_disconnected_and_retryable`, `fixture_login_cancellation_clears_pending_authentication`, `fixture_logout_removes_connected_account`, `public_account_status_surface_never_serializes_credentials` |
| Streaming and resume | `fixture_starts_and_resumes_threads`, `resumed_turn_protocol_uses_only_latest_user_input`, `empty_latest_user_input_never_replays_local_history` |
| Compaction | `compaction_events_do_not_break_thread_completion`, `compacted_thread_resumes_after_app_server_restart` |
| Missing-thread classification | `missing_thread_resume_is_classified_without_history_replay`, `non_missing_resume_error_is_not_reclassified` |
| Approvals | `command_approval_accepts_through_provider_control_channel`, `command_approval_declines_through_provider_control_channel`, `file_approval_accepts_through_provider_control_channel`, `file_approval_declines_through_provider_control_channel` |
| Godot/MCP tool lifecycle | `external_mcp_success_updates_one_fennara_tool_card`, `external_mcp_error_is_visible_without_daemon_failure`, `external_mcp_timeout_has_distinct_terminal_state`, `interrupted_external_mcp_activity_is_cancelled`, `external_mcp_progress_reuses_the_same_tool_card`, `external_mcp_payload_is_bounded_and_omits_image_bytes` |
| Cancellation and cleanup | `turn_interrupt_finishes_and_reaps_the_app_server`, `explicit_shutdown_reaps_an_idle_app_server` |
| Crashes and restart | `crash_diagnostics_include_stderr_and_exit_status`, `crashed_turn_process_restarts_and_resumes_the_existing_thread` |
| Multiple chats/editors | `provider_session_bindings_survive_reopened_store_connections`, `multiple_godot_project_scopes_keep_codex_bindings_isolated`, `multiple_app_server_sessions_are_isolated` |
| Existing-provider regression | `codex_registration_preserves_existing_provider_registry_and_routing` verifies that Codex remains a separate account-backed adapter and does not capture existing provider prefixes. The full Rust workspace remains the functional regression gate. |
| Compatibility | `older_runtime_is_rejected_before_initialized_notification`, `newer_runtime_is_allowed_but_marked_unverified`, `missing_required_initialize_field_is_rejected` and the unit tests in `codex_runtime.rs` |
| Missing/corrupt/interrupted runtime | Managed-runtime tests cover checksum success, checksum mismatch cleanup, download cancellation cleanup, interrupted activation recovery, safe replacement and the pinned official asset contract. |
| Event throughput | `burst_events_are_drained_without_blocking_the_runtime` and `external_tool_event_burst_does_not_block_the_app_server_stream` drain 10,000 synthetic events; the latter also includes MCP lifecycle events and enforces a 10-second CI budget. |
| Embedded UI scheduling | `transcript-renderer-coalescing.test.js` submits 10,000 updates for one tool before an animation frame and verifies that only the newest state is rendered once. It also verifies independent tool IDs, synchronous terminal flush and cancellation cleanup. |

## Performance interpretation

The daemon-side 10,000-event tests are regression guards for app-server backpressure and event-card processing. The embedded transcript renderer additionally coalesces repeated updates for the same tool ID and renders only the newest state once per animation frame; stream completion, cancellation and reset synchronously flush or discard pending state. This removes event-rate-proportional Markdown parsing, DOM replacement and layout work from the Godot WebView path.

These automated checks demonstrate that tool progress traffic does not synchronously block the provider stream or force one UI render per event. They are not a full Godot frame-time benchmark. The Draft PR therefore keeps the Windows editor profile as an explicit manual acceptance gate rather than presenting synthetic throughput as real editor frame-time proof. Real editor lag can still be caused by the selected Godot tool, project size, filesystem activity, asset imports and scene refresh work, so release testing should additionally profile Godot frame time and editor responsiveness on representative projects.

## Non-goals

- Fennara does not duplicate Codex thread storage or implement its own Codex context compactor.
- Fennara does not extract, copy or migrate OAuth credentials between Codex homes.
- Fennara does not silently recreate missing threads from local chat history.
- Fennara does not treat newer unverified Codex versions as tested merely because initialization succeeds.
