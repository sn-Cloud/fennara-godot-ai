from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[tokio::test]
async fn external_mcp_error_is_visible_without_daemon_failure() {
    let events = mcp_activities_for("tool-error").await;
    let completed = events.last().expect("completed MCP activity");
    assert_eq!(completed.status, "failed");
    assert!(completed.content.contains("fixture Godot tool failed"));
}

'''
if 'external_mcp_error_is_visible_without_daemon_failure' not in s:
    if s.count(m)!=1: raise RuntimeError('test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
