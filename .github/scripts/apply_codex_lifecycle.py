from pathlib import Path
from textwrap import dedent


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"expected one match in {path}, found {count}: {old[:120]!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


fixture = Path(
    "local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py"
)
crash_preset = '            "crash-turn": {"crash_at": "turn"},\n'
replace_once(
    fixture,
    crash_preset,
    crash_preset
    + '            "crash-turn-once": {"crash_at": "turn-once"},\n'
    + '            "interrupt-turn": {"turn_result": "await-interrupt"},\n'
    + '            "tool-burst": {"burst_deltas": 10_000, "tool_progress": True},\n',
)

fixture_text = fixture.read_text(encoding="utf-8")
crash_start = fixture_text.index("    def maybe_crash(self, point: str) -> None:\n")
crash_end = fixture_text.index(
    "\n    def handle(self, message: dict[str, Any]) -> None:", crash_start
)
crash_function = "\n".join(
    [
        "    def maybe_crash(self, point: str) -> None:",
        "        crash_at = self.scenario.crash_at",
        '        if crash_at == f"{point}-once":',
        "            self.codex_home.mkdir(parents=True, exist_ok=True)",
        '            marker = self.codex_home / f"fake-crash-{point}-once"',
        "            if marker.exists():",
        "                return",
        '            marker.write_text("crashed", encoding="utf-8")',
        "        elif crash_at != point:",
        "            return",
        '        sys.stderr.write(f"fake Codex crash at {point}\\n")',
        "        sys.stderr.flush()",
        "        raise SystemExit(70)",
        "",
    ]
)
fixture.write_text(
    fixture_text[:crash_start] + crash_function + fixture_text[crash_end:],
    encoding="utf-8",
)

turn_emit = "            self.emit_turn(thread_id, turn_id)\n"
turn_replacement = "\n".join(
    [
        '            if self.scenario.turn_result == "await-interrupt":',
        '                item_id = f"agent-{uuid.uuid4()}"',
        "                notification(",
        '                    "turn/started",',
        "                    {",
        '                        "threadId": thread_id,',
        '                        "turn": {"id": turn_id, "status": "inProgress"},',
        "                    },",
        "                )",
        "                notification(",
        '                    "item/agentMessage/delta",',
        "                    {",
        '                        "threadId": thread_id,',
        '                        "turnId": turn_id,',
        '                        "itemId": item_id,',
        '                        "delta": "fixture partial response",',
        "                    },",
        "                )",
        "                return",
        "            self.emit_turn(thread_id, turn_id)",
        "",
    ]
)
replace_once(fixture, turn_emit, turn_replacement)

tests = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/"
    "codex_app_server/integration_tests.rs"
)
replace_once(
    tests,
    "    time::Duration,\n",
    "    time::{Duration, Instant},\n",
)

test_marker = """#[tokio::test]
async fn multiple_app_server_sessions_are_isolated() {"""
lifecycle_tests = dedent(
    """\
    #[tokio::test]
    async fn turn_interrupt_finishes_and_reaps_the_app_server() {
        let (fixture, mut connection) = spawn_fixture("interrupt-turn", None).await;
        let thread_id = start_thread(&mut connection).await;
        start_turn(&mut connection, &thread_id).await;
        let delta = wait_for_notification(&mut connection, "item/agentMessage/delta").await;
        assert_eq!(
            delta.get("delta").and_then(Value::as_str),
            Some("fixture partial response")
        );

        connection.interrupt_turn(&thread_id).await;
        let completed = wait_for_notification(&mut connection, "turn/completed").await;
        assert_eq!(
            completed.pointer("/turn/status").and_then(Value::as_str),
            Some("interrupted")
        );
        connection.shutdown().await;
        assert!(
            connection
                .child
                .try_wait()
                .expect("read interrupted child status")
                .is_some(),
            "Codex app-server must be reaped after cancellation"
        );

        let requests = fixture_request_log(&fixture);
        assert!(requests.iter().any(|request| {
            request.get("method").and_then(Value::as_str) == Some("turn/interrupt")
        }));
    }

    #[tokio::test]
    async fn crashed_turn_process_restarts_and_resumes_the_existing_thread() {
        let fixture = fixture_runtime("crash-turn-once");
        let mut crashed = timeout(
            TEST_TIMEOUT,
            CodexConnection::spawn_runtime(fixture.spec.clone(), None),
        )
        .await
        .expect("crash fixture initialize timed out")
        .expect("crash fixture initialize failed");
        let thread_id = start_thread(&mut crashed).await;
        let error = crashed
            .request(
                "turn/start",
                json!({
                    "threadId": thread_id.clone(),
                    "input": [{ "type": "text", "text": "crash this turn once" }]
                }),
                TEST_TIMEOUT,
            )
            .await
            .expect_err("first turn should crash the app-server");
        match error {
            LlmError::ProviderApi {
                message, retryable, ..
            } => {
                assert!(retryable);
                assert!(message.contains("Codex app-server exited"), "{message}");
            }
            other => panic!("unexpected crash error: {other:?}"),
        }
        crashed.shutdown().await;

        let mut restarted = timeout(
            TEST_TIMEOUT,
            CodexConnection::spawn_runtime(fixture.spec.clone(), None),
        )
        .await
        .expect("restart fixture initialize timed out")
        .expect("restart fixture initialize failed");
        let resumed = restarted
            .request(
                "thread/resume",
                json!({ "threadId": thread_id.clone() }),
                TEST_TIMEOUT,
            )
            .await
            .expect("thread/resume after crash failed");
        assert_eq!(
            resumed.pointer("/thread/id").and_then(Value::as_str),
            Some(thread_id.as_str())
        );
        start_turn_with_text(&mut restarted, &thread_id, "continue after crash").await;
        let events = drain_turn(&mut restarted).await;
        assert!(events.completed);
        restarted.shutdown().await;
    }

    #[tokio::test]
    async fn explicit_shutdown_reaps_an_idle_app_server() {
        let (_fixture, mut connection) = spawn_fixture("authenticated", None).await;
        connection.shutdown().await;
        assert!(
            connection
                .child
                .try_wait()
                .expect("read idle child status")
                .is_some(),
            "Codex app-server must not remain orphaned after shutdown"
        );
    }

    #[tokio::test]
    async fn external_tool_event_burst_does_not_block_the_app_server_stream() {
        let (_fixture, mut connection) = spawn_fixture("tool-burst", None).await;
        let thread_id = start_thread(&mut connection).await;
        let started = Instant::now();
        start_turn(&mut connection, &thread_id).await;
        let events = drain_turn(&mut connection).await;
        let elapsed = started.elapsed();
        assert_eq!(events.deltas, 10_000);
        assert_eq!(events.mcp_activities.len(), 3);
        assert!(events.completed);
        assert!(
            elapsed < Duration::from_secs(10),
            "synthetic tool/event burst stalled for {elapsed:?}"
        );
        connection.shutdown().await;
    }

    #[tokio::test]
    async fn multiple_app_server_sessions_are_isolated() {"""
)
replace_once(tests, test_marker, lifecycle_tests)
