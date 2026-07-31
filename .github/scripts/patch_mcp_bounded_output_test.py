from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn wait_for_notification(connection: &mut CodexConnection, expected_method: &str) -> Value {\n';b='''#[test]
fn external_mcp_payload_is_bounded_and_omits_image_bytes() {
    let item = json!({
        "id": "mcp-large",
        "type": "mcpToolCall",
        "server": "fennara",
        "tool": "capture_runtime_screenshot",
        "status": "completed",
        "arguments": { "note": "x".repeat(20_000) },
        "result": {
            "content": [
                { "type": "text", "text": "y".repeat(80_000) },
                { "type": "image", "mimeType": "image/png", "data": "z".repeat(100_000) }
            ],
            "structuredContent": null,
            "_meta": null
        },
        "error": null
    });
    let mut states = HashMap::new();
    let event = mcp_lifecycle_event(Some(&item), true, &mut states).unwrap();
    let StreamEvent::ExternalToolActivity { arguments, content, .. } = event else {
        panic!("expected external MCP activity");
    };
    assert!(arguments.chars().count() <= MCP_ARGUMENT_LIMIT + 40);
    assert!(content.chars().count() <= MCP_CONTENT_LIMIT + 40);
    assert!(content.contains("Output truncated by Fennara"));
    assert!(!content.contains(&"z".repeat(256)));
}

'''
if 'external_mcp_payload_is_bounded_and_omits_image_bytes' not in s:
    if s.count(m)!=1: raise RuntimeError('test marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
