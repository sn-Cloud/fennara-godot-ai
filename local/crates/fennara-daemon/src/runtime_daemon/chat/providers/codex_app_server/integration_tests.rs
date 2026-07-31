use std::{
    collections::HashMap,
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::Duration,
};

use serde_json::{Value, json};
use tokio::{sync::mpsc, time::timeout};

use super::*;

static FIXTURE_COUNTER: AtomicU64 = AtomicU64::new(0);
const TEST_TIMEOUT: Duration = Duration::from_secs(20);

struct FixtureRuntime {
    root: PathBuf,
    spec: codex_runtime::CodexRuntimeSpec,
}

impl Drop for FixtureRuntime {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn fixture_runtime(scenario: &str) -> FixtureRuntime {
    let root = std::env::temp_dir().join(format!(
        "fennara-fake-codex-{}-{}",
        std::process::id(),
        FIXTURE_COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).expect("create fixture directory");
    let fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("fake_codex_app_server.py");
    assert!(
        fixture.is_file(),
        "fixture must exist: {}",
        fixture.display()
    );
    let executable = write_fixture_launcher(&root, scenario, &fixture);
    FixtureRuntime {
        root,
        spec: codex_runtime::CodexRuntimeSpec {
            executable,
            source: codex_runtime::CodexRuntimeSource::Configured,
            platform: test_platform(),
            codex_home: None,
        },
    }
}

#[cfg(windows)]
fn write_fixture_launcher(root: &Path, scenario: &str, fixture: &Path) -> PathBuf {
    let launcher = root.join("fake-codex.cmd");
    fs::write(
        &launcher,
        format!(
            "@echo off\r\nset \"FAKE_CODEX_SCENARIO={}\"\r\npython \"{}\" %*\r\n",
            scenario,
            fixture.display()
        ),
    )
    .expect("write Windows fixture launcher");
    launcher
}

#[cfg(not(windows))]
fn write_fixture_launcher(root: &Path, scenario: &str, fixture: &Path) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let launcher = root.join("fake-codex");
    fs::write(
        &launcher,
        format!(
            "#!/bin/sh\nexport FAKE_CODEX_SCENARIO={}\nexec python3 {} \"$@\"\n",
            shell_quote(scenario),
            shell_quote(&fixture.display().to_string())
        ),
    )
    .expect("write Unix fixture launcher");
    let mut permissions = fs::metadata(&launcher)
        .expect("read fixture launcher metadata")
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&launcher, permissions).expect("make fixture launcher executable");
    launcher
}

#[cfg(not(windows))]
fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn test_platform() -> codex_runtime::CodexRuntimePlatform {
    if cfg!(windows) {
        codex_runtime::CodexRuntimePlatform::Windows
    } else if cfg!(target_os = "macos") {
        codex_runtime::CodexRuntimePlatform::Macos
    } else {
        codex_runtime::CodexRuntimePlatform::Linux
    }
}

async fn spawn_fixture(
    scenario: &str,
    approval_tx: Option<ProviderApprovalSender>,
) -> (FixtureRuntime, CodexConnection) {
    let fixture = fixture_runtime(scenario);
    let connection = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), approval_tx),
    )
    .await
    .expect("fixture initialize timed out")
    .expect("fixture initialize failed");
    (fixture, connection)
}

async fn start_thread(connection: &mut CodexConnection) -> String {
    let result = connection
        .request(
            "thread/start",
            json!({
                "cwd": ".",
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandbox": "workspaceWrite",
                "ephemeral": false
            }),
            TEST_TIMEOUT,
        )
        .await
        .expect("thread/start failed");
    result
        .pointer("/thread/id")
        .and_then(Value::as_str)
        .expect("fixture thread id")
        .to_string()
}

async fn start_turn(connection: &mut CodexConnection, thread_id: &str) {
    connection
        .request(
            "turn/start",
            json!({
                "threadId": thread_id,
                "input": [{ "type": "text", "text": "test turn" }]
            }),
            TEST_TIMEOUT,
        )
        .await
        .expect("turn/start failed");
}

#[derive(Clone, Debug)]
struct ObservedMcpActivity {
    id: String,
    name: String,
    arguments: String,
    content: String,
    status: String,
}

#[derive(Default)]
struct TurnEvents {
    deltas: usize,
    compaction_started: usize,
    compaction_completed: usize,
    mcp_activities: Vec<ObservedMcpActivity>,
    completed: bool,
}

fn record_mcp_activity(events: &mut TurnEvents, event: StreamEvent) {
    let StreamEvent::ExternalToolActivity {
        id,
        name,
        arguments,
        content,
        status,
    } = event
    else {
        return;
    };
    events.mcp_activities.push(ObservedMcpActivity {
        id,
        name,
        arguments,
        content,
        status,
    });
}

async fn drain_turn(connection: &mut CodexConnection) -> TurnEvents {
    timeout(TEST_TIMEOUT, async {
        let mut events = TurnEvents::default();
        let mut mcp_items: HashMap<String, McpItemState> = HashMap::new();
        while !events.completed {
            let message = connection.read_message().await.expect("read turn event");
            if connection
                .respond_to_server_request(&message)
                .await
                .expect("respond to fixture request")
            {
                continue;
            }
            match message.get("method").and_then(Value::as_str) {
                Some("item/agentMessage/delta") => events.deltas += 1,
                Some("item/started") => {
                    if let Some(event) =
                        mcp_lifecycle_event(message.pointer("/params/item"), false, &mut mcp_items)
                    {
                        record_mcp_activity(&mut events, event);
                    }
                }
                Some("item/mcpToolCall/progress") => {
                    if let Some(event) = mcp_progress_event(
                        message.get("params").unwrap_or(&Value::Null),
                        &mcp_items,
                    ) {
                        record_mcp_activity(&mut events, event);
                    }
                }
                Some("item/completed") => {
                    if let Some(event) =
                        mcp_lifecycle_event(message.pointer("/params/item"), true, &mut mcp_items)
                    {
                        record_mcp_activity(&mut events, event);
                    }
                }
                Some("thread/compaction/started") => events.compaction_started += 1,
                Some("thread/compaction/completed") => events.compaction_completed += 1,
                Some("turn/completed") => events.completed = true,
                _ => {}
            }
        }
        events
    })
    .await
    .expect("turn event drain timed out")
}

#[tokio::test]
async fn fixture_initializes_and_reads_chatgpt_account() {
    let (_fixture, mut connection) = spawn_fixture("authenticated", None).await;
    let runtime = connection.runtime.as_ref().expect("runtime metadata");
    assert_eq!(runtime.version.as_deref(), Some("0.0.0-fake"));
    assert_eq!(
        runtime.compatibility,
        codex_runtime::CodexCompatibility::CompatibleUnverified
    );

    let account = connection
        .request(
            "account/read",
            json!({ "refreshToken": false }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/read failed");
    assert_eq!(account.pointer("/account/type"), Some(&json!("chatgpt")));
    assert_eq!(account.pointer("/account/planType"), Some(&json!("plus")));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_starts_and_resumes_threads() {
    let (_fixture, mut connection) = spawn_fixture("authenticated", None).await;
    let thread_id = start_thread(&mut connection).await;
    let resumed = connection
        .request(
            "thread/resume",
            json!({ "threadId": thread_id }),
            TEST_TIMEOUT,
        )
        .await
        .expect("thread/resume failed");
    assert_eq!(
        resumed.pointer("/thread/id").and_then(Value::as_str),
        Some(thread_id.as_str())
    );
    connection.shutdown().await;
}

#[tokio::test]
async fn missing_thread_resume_is_classified_without_history_replay() {
    let (_fixture, mut connection) = spawn_fixture("resume-missing", None).await;
    let error = connection
        .request(
            "thread/resume",
            json!({ "threadId": "missing-thread" }),
            TEST_TIMEOUT,
        )
        .await
        .expect_err("missing thread should fail");
    assert!(is_missing_thread_error(&error));
    connection.shutdown().await;
}

async fn assert_approval_round_trip(
    scenario: &str,
    expected_kind: ProviderApprovalKind,
    decision: ProviderApprovalDecision,
) {
    let (approval_tx, mut approval_rx) = mpsc::unbounded_channel::<ProviderApprovalRequest>();
    let approval_task = tokio::spawn(async move {
        let request = timeout(TEST_TIMEOUT, approval_rx.recv())
            .await
            .expect("approval receive timed out")
            .expect("approval channel closed");
        assert_eq!(request.kind, expected_kind);
        assert_eq!(request.summary, "fixture approval request");
        request
            .responder
            .send(decision)
            .expect("send approval decision");
    });
    let (_fixture, mut connection) = spawn_fixture(scenario, Some(approval_tx)).await;
    let thread_id = start_thread(&mut connection).await;
    start_turn(&mut connection, &thread_id).await;
    let events = drain_turn(&mut connection).await;
    assert!(events.completed);
    approval_task.await.expect("approval task failed");
    connection.shutdown().await;
}

#[tokio::test]
async fn command_approval_accepts_through_provider_control_channel() {
    assert_approval_round_trip(
        "command-approval",
        ProviderApprovalKind::CommandExecution,
        ProviderApprovalDecision::Approved,
    )
    .await;
}

#[tokio::test]
async fn file_approval_declines_through_provider_control_channel() {
    assert_approval_round_trip(
        "file-approval",
        ProviderApprovalKind::FileChange,
        ProviderApprovalDecision::Denied,
    )
    .await;
}

#[tokio::test]
async fn compaction_events_do_not_break_thread_completion() {
    let (_fixture, mut connection) = spawn_fixture("compaction", None).await;
    let thread_id = start_thread(&mut connection).await;
    start_turn(&mut connection, &thread_id).await;
    let events = drain_turn(&mut connection).await;
    assert_eq!(events.compaction_started, 1);
    assert_eq!(events.compaction_completed, 1);
    assert!(events.completed);
    connection.shutdown().await;
}

#[tokio::test]
async fn multiple_app_server_sessions_are_isolated() {
    let (_first_fixture, mut first) = spawn_fixture("authenticated", None).await;
    let (_second_fixture, mut second) = spawn_fixture("authenticated", None).await;
    let first_thread = start_thread(&mut first).await;
    let second_thread = start_thread(&mut second).await;
    assert_ne!(first_thread, second_thread);
    start_turn(&mut first, &first_thread).await;
    start_turn(&mut second, &second_thread).await;
    let (first_events, second_events) =
        tokio::join!(drain_turn(&mut first), drain_turn(&mut second));
    assert!(first_events.completed);
    assert!(second_events.completed);
    assert_eq!(first_events.deltas, 1);
    assert_eq!(second_events.deltas, 1);
    first.shutdown().await;
    second.shutdown().await;
}

#[tokio::test]
async fn invalid_json_is_reported_as_provider_output_error() {
    let (_fixture, mut connection) = spawn_fixture("invalid-json-turn", None).await;
    let thread_id = start_thread(&mut connection).await;
    let error = connection
        .request(
            "turn/start",
            json!({
                "threadId": thread_id,
                "input": [{ "type": "text", "text": "test turn" }]
            }),
            TEST_TIMEOUT,
        )
        .await
        .expect_err("invalid JSON should fail the active request");
    match error {
        LlmError::InvalidProviderOutput { raw, .. } => {
            assert_eq!(raw.as_deref(), Some("{not valid json}"));
        }
        other => panic!("unexpected error: {other:?}"),
    }
    connection.shutdown().await;
}

#[tokio::test]
async fn crash_diagnostics_include_stderr_and_exit_status() {
    let fixture = fixture_runtime("crash-initialize");
    let result = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), None),
    )
    .await
    .expect("crash initialize timed out");
    let error = match result {
        Ok(mut connection) => {
            connection.shutdown().await;
            panic!("crash initialize should fail");
        }
        Err(error) => error,
    };
    let message = error.user_message();
    assert!(
        message.contains("fake Codex crash at initialize"),
        "{message}"
    );
    assert!(message.contains("status"), "{message}");
}

#[tokio::test]
async fn burst_events_are_drained_without_blocking_the_runtime() {
    let (_fixture, mut connection) = spawn_fixture("burst", None).await;
    let thread_id = start_thread(&mut connection).await;
    start_turn(&mut connection, &thread_id).await;
    let events = drain_turn(&mut connection).await;
    assert_eq!(events.deltas, 10_000);
    assert!(events.completed);
    connection.shutdown().await;
}

async fn mcp_activities_for(scenario: &str) -> Vec<ObservedMcpActivity> {
    let (_fixture, mut connection) = spawn_fixture(scenario, None).await;
    let thread_id = start_thread(&mut connection).await;
    start_turn(&mut connection, &thread_id).await;
    let events = drain_turn(&mut connection).await;
    assert!(events.completed);
    connection.shutdown().await;
    events.mcp_activities
}

#[tokio::test]
async fn external_mcp_success_updates_one_fennara_tool_card() {
    let events = mcp_activities_for("authenticated").await;
    assert_eq!(events.len(), 2);
    assert_eq!(events[0].id, events[1].id);
    assert_eq!(events[0].status, "running");
    assert_eq!(events[1].status, "completed");
    assert_eq!(events[1].name, "fennara · get_scene_tree");
    assert!(events[1].arguments.contains("depth"));
    assert!(events[1].content.contains("\"ok\": true"));
}

#[tokio::test]
async fn external_mcp_error_is_visible_without_daemon_failure() {
    let events = mcp_activities_for("tool-error").await;
    let completed = events.last().expect("completed MCP activity");
    assert_eq!(completed.status, "failed");
    assert!(completed.content.contains("fixture Godot tool failed"));
}

#[tokio::test]
async fn external_mcp_timeout_has_distinct_terminal_state() {
    let scenario = format!("tool-{}{}", "time", "out");
    let events = mcp_activities_for(&scenario).await;
    let completed = events.last().expect("completed MCP activity");
    assert_eq!(completed.status, "timed_out");
    assert!(completed.content.contains("timed out"));
}

#[tokio::test]
async fn external_mcp_progress_reuses_the_same_tool_card() {
    let events = mcp_activities_for("tool-progress").await;
    assert_eq!(events.len(), 3);
    assert_eq!(events[0].id, events[1].id);
    assert_eq!(events[1].id, events[2].id);
    assert_eq!(events[1].status, "running");
    assert!(events[1].content.contains("fixture Godot tool progress"));
    assert_eq!(events[2].status, "completed");
}

#[test]
fn interrupted_external_mcp_activity_is_cancelled() {
    let item = json!({
        "id": "mcp-cancelled",
        "type": "mcpToolCall",
        "server": "fennara",
        "tool": "get_scene_tree",
        "status": "failed",
        "arguments": {},
        "result": null,
        "error": { "message": "Godot tool interrupted by user" }
    });
    let mut states = HashMap::new();
    let event = mcp_lifecycle_event(Some(&item), true, &mut states).unwrap();
    let StreamEvent::ExternalToolActivity {
        status, content, ..
    } = event
    else {
        panic!("expected external MCP activity");
    };
    assert_eq!(status, "cancelled");
    assert!(content.contains("interrupted"));
}

#[test]
fn external_mcp_payload_is_bounded_and_omits_image_bytes() {
    let item = json!({
        "id": "mcp-large",
        "type": "mcpToolCall",
        "server": "fennara",
        "tool": "capture_runtime_screenshot",
        "status": "completed",
        "arguments": { "note": "x".repeat(20_000) },
        "result": {
            "content": [
                { "type": "text", "text": "y".repeat(80_000) },
                { "type": "image", "mimeType": "image/png", "data": "z".repeat(100_000) }
            ],
            "structuredContent": null,
            "_meta": null
        },
        "error": null
    });
    let mut states = HashMap::new();
    let event = mcp_lifecycle_event(Some(&item), true, &mut states).unwrap();
    let StreamEvent::ExternalToolActivity {
        arguments, content, ..
    } = event
    else {
        panic!("expected external MCP activity");
    };
    assert!(arguments.chars().count() <= MCP_ARGUMENT_LIMIT + 40);
    assert!(content.chars().count() <= MCP_CONTENT_LIMIT + 40);
    assert!(content.contains("Output truncated by Fennara"));
    assert!(!content.contains(&"z".repeat(256)));
}

async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {
    timeout(TEST_TIMEOUT, async {
        loop {
            let message = connection
                .read_message()
                .await
                .expect("read authentication notification");
            if connection
                .respond_to_server_request(&message)
                .await
                .expect("respond to authentication server request")
            {
                continue;
            }
            if message.get("method").and_then(Value::as_str) == Some(expected_method) {
                return message.get("params").cloned().unwrap_or_else(|| json!({}));
            }
        }
    })
    .await
    .unwrap_or_else(|_| panic!("notification timed out: {expected_method}"))
}

async fn read_fixture_account(connection: &mut CodexConnection) -> Value {
    connection
        .request(
            "account/read",
            json!({ "refreshToken": false }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/read failed")
}

#[tokio::test]
async fn fixture_unauthenticated_status_has_no_account() {
    let (_fixture, mut connection) = spawn_fixture("unauthenticated", None).await;
    let account = read_fixture_account(&mut connection).await;
    assert!(account.get("account").is_some_and(Value::is_null));
    assert_eq!(account.get("requiresOpenaiAuth"), Some(&json!(true)));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_login_success_updates_account_state() {
    let (_fixture, mut connection) = spawn_fixture("unauthenticated", None).await;
    let login = connection
        .request(
            "account/login/start",
            json!({
                "type": "chatgpt",
                "useHostedLoginSuccessPage": true,
                "appBrand": "codex"
            }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/start failed");
    let login_id = login
        .get("loginId")
        .and_then(Value::as_str)
        .expect("fixture login id")
        .to_string();
    assert_eq!(
        login.get("authUrl").and_then(Value::as_str),
        Some("https://example.invalid/fake-codex-login")
    );

    let completed = wait_for_notification(&mut connection, "account/login/completed").await;
    assert_eq!(
        completed.get("loginId").and_then(Value::as_str),
        Some(login_id.as_str())
    );
    assert_eq!(completed.get("success"), Some(&json!(true)));
    let updated = wait_for_notification(&mut connection, "account/updated").await;
    assert_eq!(updated.get("authMode"), Some(&json!("chatgpt")));
    assert_eq!(updated.get("planType"), Some(&json!("plus")));

    let account = read_fixture_account(&mut connection).await;
    assert_eq!(account.pointer("/account/type"), Some(&json!("chatgpt")));
    assert_eq!(account.pointer("/account/planType"), Some(&json!("plus")));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_login_failure_remains_disconnected_and_retryable() {
    let (_fixture, mut connection) = spawn_fixture("login-failure", None).await;
    connection
        .request(
            "account/login/start",
            json!({ "type": "chatgpt" }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/start failed");
    let completed = wait_for_notification(&mut connection, "account/login/completed").await;
    assert_eq!(completed.get("success"), Some(&json!(false)));
    assert!(
        completed
            .get("error")
            .and_then(Value::as_str)
            .is_some_and(|error| error.contains("authentication failed"))
    );
    let account = read_fixture_account(&mut connection).await;
    assert!(account.get("account").is_some_and(Value::is_null));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_login_cancellation_clears_pending_authentication() {
    let (_fixture, mut connection) = spawn_fixture("login-timeout", None).await;
    let login = connection
        .request(
            "account/login/start",
            json!({ "type": "chatgpt" }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/start failed");
    let login_id = login
        .get("loginId")
        .and_then(Value::as_str)
        .expect("fixture login id")
        .to_string();
    connection
        .request(
            "account/login/cancel",
            json!({ "loginId": login_id.clone() }),
            TEST_TIMEOUT,
        )
        .await
        .expect("account/login/cancel failed");
    let completed = wait_for_notification(&mut connection, "account/login/completed").await;
    assert_eq!(
        completed.get("loginId").and_then(Value::as_str),
        Some(login_id.as_str())
    );
    assert_eq!(completed.get("success"), Some(&json!(false)));
    assert!(
        completed
            .get("error")
            .and_then(Value::as_str)
            .is_some_and(|error| error.contains("cancelled"))
    );
    let account = read_fixture_account(&mut connection).await;
    assert!(account.get("account").is_some_and(Value::is_null));
    connection.shutdown().await;
}

#[tokio::test]
async fn fixture_logout_removes_connected_account() {
    let (_fixture, mut connection) = spawn_fixture("authenticated", None).await;
    let before = read_fixture_account(&mut connection).await;
    assert_eq!(before.pointer("/account/type"), Some(&json!("chatgpt")));
    connection
        .request("account/logout", json!({}), TEST_TIMEOUT)
        .await
        .expect("account/logout failed");
    let updated = wait_for_notification(&mut connection, "account/updated").await;
    assert!(updated.get("authMode").is_some_and(Value::is_null));
    let after = read_fixture_account(&mut connection).await;
    assert!(after.get("account").is_some_and(Value::is_null));
    connection.shutdown().await;
}

#[tokio::test]
async fn public_account_status_surface_never_serializes_credentials() {
    let account = json!({
        "account": {
            "type": "chatgpt",
            "email": "fixture@example.invalid",
            "planType": "plus",
            "accessToken": "must-not-escape",
            "refreshToken": "must-not-escape",
            "cookie": "must-not-escape"
        },
        "requiresOpenaiAuth": true
    });
    let status = account_status_from_result(&account, true, false, None);
    let serialized = serde_json::to_string(&status).expect("serialize public account status");
    assert!(serialized.contains("fixture@example.invalid"));
    for forbidden in ["accessToken", "refreshToken", "cookie", "must-not-escape"] {
        assert!(
            !serialized.contains(forbidden),
            "credential leaked through status: {forbidden}"
        );
    }
}
