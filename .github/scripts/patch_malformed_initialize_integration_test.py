from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[tokio::test]
async fn missing_required_initialize_field_is_rejected() {
    let fixture = fixture_runtime("malformed-initialize");
    let result = timeout(
        TEST_TIMEOUT,
        CodexConnection::spawn_runtime(fixture.spec.clone(), None),
    )
    .await
    .expect("initialize structure validation timed out");
    let error = match result {
        Ok(mut connection) => {
            connection.shutdown().await;
            panic!("incomplete initialize response should be rejected");
        }
        Err(error) => error,
    };
    let message = error.user_message();
    assert!(message.contains("platformOs"));
    assert!(message.contains(codex_runtime::PINNED_CODEX_VERSION));
}

'''
if 'missing_required_initialize_field_is_rejected' not in s:
    if s.count(m)!=1: raise RuntimeError('integration test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
