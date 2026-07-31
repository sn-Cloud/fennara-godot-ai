from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''async fn mcp_activities_for(scenario: &str) -> Vec<ObservedMcpActivity> {
    let (_fixture, mut connection) = spawn_fixture(scenario, None).await;
    let thread_id = start_thread(&mut connection).await;
    start_turn(&mut connection, &thread_id).await;
    let events = drain_turn(&mut connection).await;
    assert!(events.completed);
    connection.shutdown().await;
    events.mcp_activities
}

'''
if 'async fn mcp_activities_for(' not in s:
    if s.count(m)!=1: raise RuntimeError('auth helper marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
