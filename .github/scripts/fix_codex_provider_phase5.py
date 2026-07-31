from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
content = path.read_text(encoding="utf-8")

old_channel = "    let (approval_tx, mut approval_rx) = mpsc::unbounded_channel();\n"
new_channel = "    let (approval_tx, mut approval_rx) =\n        mpsc::unbounded_channel::<ProviderApprovalRequest>();\n"
count = content.count(old_channel)
if count != 1:
    raise RuntimeError(f"expected one approval test channel, found {count}")
content = content.replace(old_channel, new_channel, 1)

old_invalid_json = '''#[tokio::test]
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
'''
new_invalid_json = '''#[tokio::test]
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
'''
count = content.count(old_invalid_json)
if count != 1:
    raise RuntimeError(f"expected one invalid JSON integration test, found {count}")
content = content.replace(old_invalid_json, new_invalid_json, 1)

path.write_text(content, encoding="utf-8", newline="\n")
