from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[tokio::test]
async fn newer_runtime_is_allowed_but_marked_unverified() {
    let (_fixture, mut connection) = spawn_fixture("newer-runtime", None).await;
    let runtime = connection.runtime.as_ref().expect("runtime metadata");
    assert_eq!(runtime.version.as_deref(), Some("0.145.0"));
    assert_eq!(
        runtime.compatibility,
        codex_runtime::CodexCompatibility::CompatibleUnverified
    );
    assert!(runtime.compatibility_error.is_none());
    connection.shutdown().await;
}

'''
if 'newer_runtime_is_allowed_but_marked_unverified' not in s:
    if s.count(m)!=1: raise RuntimeError('integration test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
