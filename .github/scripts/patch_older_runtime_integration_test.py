from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[tokio::test]
async fn older_runtime_is_rejected_before_initialized_notification() {
    let fixture = fixture_runtime("older-runtime");
    let result = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), None),
    )
    .await
    .expect("older runtime validation timed out");
    let error = match result {
        Ok(mut connection) => {
            connection.shutdown().await;
            panic!("older runtime should be rejected");
        }
        Err(error) => error,
    };
    let message = error.user_message();
    assert!(message.contains(codex_runtime::MINIMUM_CODEX_VERSION));
    assert!(message.contains(codex_runtime::PINNED_CODEX_VERSION));
}

'''
if 'older_runtime_is_rejected_before_initialized_notification' not in s:
    if s.count(m)!=1: raise RuntimeError('integration test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
