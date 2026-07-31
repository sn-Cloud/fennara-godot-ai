from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='async fn drain_turn(connection: &mut CodexConnection) -> TurnEvents {\n';b='''fn record_mcp_activity(events: &mut TurnEvents, event: StreamEvent) {
    let StreamEvent::ExternalToolActivity {
        id,
        name,
        arguments,
        content,
        status,
    } = event
    else {
        return;
    };
    events.mcp_activities.push(ObservedMcpActivity {
        id,
        name,
        arguments,
        content,
        status,
    });
}

'''
if 'fn record_mcp_activity(' not in s:
    if s.count(m)!=1: raise RuntimeError('drain_turn marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
