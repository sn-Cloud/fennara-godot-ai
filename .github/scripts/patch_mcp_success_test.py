from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[tokio::test]
async fn external_mcp_success_updates_one_fennara_tool_card() {
    let events = mcp_activities_for("authenticated").await;
    assert_eq!(events.len(), 2);
    assert_eq!(events[0].id, events[1].id);
    assert_eq!(events[0].status, "running");
    assert_eq!(events[1].status, "completed");
    assert_eq!(events[1].name, "fennara · get_scene_tree");
    assert!(events[1].arguments.contains("depth"));
    assert!(events[1].content.contains("\\\"ok\\\": true"));
}

'''
if 'external_mcp_success_updates_one_fennara_tool_card' not in s:
    if s.count(m)!=1: raise RuntimeError('test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
