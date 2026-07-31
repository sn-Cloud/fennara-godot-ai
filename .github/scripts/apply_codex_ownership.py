from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"expected one match in {path}, found {count}: {old[:140]!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


provider = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
)
replace_once(
    provider,
    '''    let existing_binding = store::provider_session_binding(chat_id, "codex")
        .map_err(|message| LlmError::Config { message })?;

    let mut thread_params = Map::new();
''',
    '''    let existing_binding = store::provider_session_binding(chat_id, "codex")
        .map_err(|message| LlmError::Config { message })?;
    let current_codex_home_key = codex_home_key(connection.runtime.as_ref());
    let current_runtime_version = connection
        .runtime
        .as_ref()
        .and_then(|runtime| runtime.version.clone());
    if let Some(binding) = existing_binding.as_ref() {
        if !codex_home_keys_match(&binding.codex_home_key, &current_codex_home_key) {
            connection.shutdown().await;
            return Err(LlmError::ProviderApi {
                provider: PROVIDER_NAME.to_string(),
                status: None,
                message: "The Codex thread for this Fennara chat belongs to a different CODEX_HOME. Restore the original FENNARA_CODEX_HOME/CODEX_HOME or start a new Codex thread explicitly; Fennara will not resume it against another Codex home."
                    .to_string(),
                retryable: false,
            });
        }
    }

    let mut thread_params = Map::new();
''',
)
replace_once(
    provider,
    '''    store::upsert_provider_session_binding(chat_id, "codex", &thread_id, "default", None)
        .map_err(|message| LlmError::Config { message })?;
''',
    '''    store::upsert_provider_session_binding(
        chat_id,
        "codex",
        &thread_id,
        &current_codex_home_key,
        current_runtime_version.as_deref(),
    )
    .map_err(|message| LlmError::Config { message })?;
''',
)
replace_once(
    provider,
    '''fn latest_user_prompt(messages: &[Value]) -> String {
''',
    '''fn normalize_codex_home_key(value: &str) -> String {
    let normalized = value.trim().replace('\\', "/");
    let normalized = if normalized.len() > 1 && !normalized.ends_with(":/") {
        normalized.trim_end_matches('/').to_string()
    } else {
        normalized
    };
    if cfg!(windows) {
        normalized.to_ascii_lowercase()
    } else {
        normalized
    }
}

fn codex_home_key(runtime: Option<&CodexRuntimeMetadata>) -> String {
    runtime
        .and_then(|runtime| runtime.codex_home.as_deref())
        .map(normalize_codex_home_key)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "default".to_string())
}

fn codex_home_keys_match(bound: &str, current: &str) -> bool {
    normalize_codex_home_key(bound) == normalize_codex_home_key(current)
}

fn latest_user_prompt(messages: &[Value]) -> String {
''',
)
replace_once(
    provider,
    '''    fn latest_user_prompt_uses_only_the_newest_user_message() {
        let prompt = latest_user_prompt(&[
            json!({ "role": "system", "content": "system" }),
            json!({ "role": "user", "content": "first" }),
            json!({ "role": "assistant", "content": "reply" }),
            json!({ "role": "user", "content": "second" }),
        ]);
        assert_eq!(prompt, "second");
    }

    #[test]
    fn missing_thread_errors_are_classified_narrowly() {
''',
    '''    fn latest_user_prompt_uses_only_the_newest_user_message() {
        let prompt = latest_user_prompt(&[
            json!({ "role": "system", "content": "system" }),
            json!({ "role": "user", "content": "first" }),
            json!({ "role": "assistant", "content": "reply" }),
            json!({ "role": "user", "content": "second" }),
        ]);
        assert_eq!(prompt, "second");
    }

    #[test]
    fn codex_home_keys_are_normalized_and_compared_strictly() {
        assert!(codex_home_keys_match("/tmp/codex-home/", "/tmp/codex-home"));
        assert!(!codex_home_keys_match(
            "/tmp/codex-home-a",
            "/tmp/codex-home-b"
        ));
        #[cfg(windows)]
        assert!(codex_home_keys_match(
            "C:\\Users\\Test\\.codex",
            "c:/users/test/.codex/"
        ));
    }

    #[test]
    fn missing_thread_errors_are_classified_narrowly() {
''',
)

integration = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/"
    "codex_app_server/integration_tests.rs"
)
replace_once(
    integration,
    '''        "thread-first",
        "default",
        Some("0.144.4"),
''',
    '''        "thread-first",
        "/tmp/codex-home-first",
        Some("0.144.4"),
''',
)
replace_once(
    integration,
    '''        "thread-second",
        "default",
        Some("0.144.4"),
''',
    '''        "thread-second",
        "/tmp/codex-home-second",
        Some("0.145.0"),
''',
)
replace_once(
    integration,
    '''    assert_eq!(first.provider_thread_id, "thread-first");
    assert_eq!(second.provider_thread_id, "thread-second");

    store::mark_provider_session_broken(&first_chat.chat.id, "codex")
''',
    '''    assert_eq!(first.provider_thread_id, "thread-first");
    assert_eq!(first.codex_home_key, "/tmp/codex-home-first");
    assert_eq!(first.runtime_version.as_deref(), Some("0.144.4"));
    assert_eq!(second.provider_thread_id, "thread-second");
    assert_eq!(second.codex_home_key, "/tmp/codex-home-second");
    assert_eq!(second.runtime_version.as_deref(), Some("0.145.0"));

    store::mark_provider_session_broken(&first_chat.chat.id, "codex")
''',
)

doc = Path("docs/codex-app-server-ownership.md")
doc.parent.mkdir(parents=True, exist_ok=True)
doc.write_text(
    '''# Codex app-server ownership boundaries and acceptance matrix

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
| Approvals | `command_approval_accepts_through_provider_control_channel`, `file_approval_declines_through_provider_control_channel` |
| Godot/MCP tool lifecycle | `external_mcp_success_updates_one_fennara_tool_card`, `external_mcp_error_is_visible_without_daemon_failure`, `external_mcp_timeout_has_distinct_terminal_state`, `interrupted_external_mcp_activity_is_cancelled`, `external_mcp_progress_reuses_the_same_tool_card`, `external_mcp_payload_is_bounded_and_omits_image_bytes` |
| Cancellation and cleanup | `turn_interrupt_finishes_and_reaps_the_app_server`, `explicit_shutdown_reaps_an_idle_app_server` |
| Crashes and restart | `crash_diagnostics_include_stderr_and_exit_status`, `crashed_turn_process_restarts_and_resumes_the_existing_thread` |
| Multiple chats/editors | `provider_session_bindings_survive_reopened_store_connections`, `multiple_app_server_sessions_are_isolated` |
| Compatibility | `older_runtime_is_rejected_before_initialized_notification`, `newer_runtime_is_allowed_but_marked_unverified`, `missing_required_initialize_field_is_rejected` and the unit tests in `codex_runtime.rs` |
| Missing/corrupt/interrupted runtime | Managed-runtime tests cover checksum success, checksum mismatch cleanup, download cancellation cleanup, interrupted activation recovery, safe replacement and the pinned official asset contract. |
| Event throughput | `burst_events_are_drained_without_blocking_the_runtime` and `external_tool_event_burst_does_not_block_the_app_server_stream` drain 10,000 synthetic events; the latter also includes MCP lifecycle events and enforces a 10-second CI budget. |

## Performance interpretation

The 10,000-event tests are regression guards for daemon/app-server backpressure and event-card processing. They demonstrate that using a tool does not synchronously block the provider stream under the synthetic workload. They are not a Godot frame-time benchmark. Real editor lag still depends on the selected Godot tool, project size, filesystem activity, imports and scene refresh work, so release testing should additionally profile Godot frame time and editor responsiveness on representative projects.

## Non-goals

- Fennara does not duplicate Codex thread storage or implement its own Codex context compactor.
- Fennara does not extract, copy or migrate OAuth credentials between Codex homes.
- Fennara does not silently recreate missing threads from local chat history.
- Fennara does not treat newer unverified Codex versions as tested merely because initialization succeeds.
''',
    encoding="utf-8",
)

readme = Path("README.md")
replace_once(
    readme,
    '''### OpenAI 登录方式说明
''',
    '''### Codex app-server 架构与验收

Codex 内置聊天的命令路由、事件渲染、审批与沙箱、线程与历史、上下文压缩、认证与 `CODEX_HOME`、进程生命周期、版本兼容策略及自动化验收矩阵，见：

- [Codex app-server ownership boundaries and acceptance matrix](docs/codex-app-server-ownership.md)

### OpenAI 登录方式说明
''',
)
