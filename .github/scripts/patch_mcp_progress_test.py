from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[tokio::test]
async fn external_mcp_progress_reuses_the_same_tool_card() {
    let events = mcp_activities_for("tool-progress").await;
    assert_eq!(events.len(), 3);
    assert_eq!(events[0].id, events[1].id);
    assert_eq!(events[1].id, events[2].id);
    assert_eq!(events[1].status, "running");
    assert!(events[1].content.contains("fixture Godot tool progress"));
    assert_eq!(events[2].status, "completed");
}

'''
if 'external_mcp_progress_reuses_the_same_tool_card' not in s:
    if s.count(m)!=1: raise RuntimeError('test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
