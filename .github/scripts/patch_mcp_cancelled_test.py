from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[test]
fn interrupted_external_mcp_activity_is_cancelled() {
    let item = json!({
        "id": "mcp-cancelled",
        "type": "mcpToolCall",
        "server": "fennara",
        "tool": "get_scene_tree",
        "status": "failed",
        "arguments": {},
        "result": null,
        "error": { "message": "Godot tool interrupted by user" }
    });
    let mut states = HashMap::new();
    let event = mcp_lifecycle_event(Some(&item), true, &mut states).unwrap();
    let StreamEvent::ExternalToolActivity { status, content, .. } = event else {
        panic!("expected external MCP activity");
    };
    assert_eq!(status, "cancelled");
    assert!(content.contains("interrupted"));
}

'''
if 'interrupted_external_mcp_activity_is_cancelled' not in s:
    if s.count(m)!=1: raise RuntimeError('test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
