use std::{
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
    assert!(fixture.is_file(), "fixture must exist: {}", fixture.display());
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

#[derive(Default)]
struct TurnEvents {
    deltas: usize,
    compaction_started: usize,
    compaction_completed: usize,
    completed: bool,
}

async fn drain_turn(connection: &mut CodexConnection) -> TurnEvents {
    timeout(TEST_TIMEOUT, async {
        let mut events = TurnEvents::default();
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
    let (approval_tx, mut approval_rx) = mpsc::unbounded_channel();
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
async fn invalid_json_is_reported_as_provider_output_error() {
    let (_fixture, mut connection) = spawn_fixture("invalid-json-turn", None).await;
    let thread_id = start_thread(&mut connection).await;
    start_turn(&mut connection, &thread_id).await;
    let error = connection
        .read_message()
        .await
        .expect_err("invalid JSON should fail");
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
    let error = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), None),
    )
    .await
    .expect("crash initialize timed out")
    .expect_err("crash initialize should fail");
    let message = error.user_message();
    assert!(message.contains("fake Codex crash at initialize"), "{message}");
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
