from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text()
m='                Some("item/agentMessage/delta") => events.deltas += 1,\n'
b=m+'''                Some("item/started") => {
                    if let Some(event) = mcp_lifecycle_event(
                        message.pointer("/params/item"),
                        false,
                        &mut mcp_items,
                    ) {
                        record_mcp_activity(&mut events, event);
                    }
                }
                Some("item/mcpToolCall/progress") => {
                    if let Some(event) = mcp_progress_event(
                        message.get("params").unwrap_or(&Value::Null),
                        &mcp_items,
                    ) {
                        record_mcp_activity(&mut events, event);
                    }
                }
                Some("item/completed") => {
                    if let Some(event) = mcp_lifecycle_event(
                        message.pointer("/params/item"),
                        true,
                        &mut mcp_items,
                    ) {
                        record_mcp_activity(&mut events, event);
                    }
                }
'''
if 'Some("item/mcpToolCall/progress")' not in s:
    if s.count(m)!=1: raise RuntimeError('agent delta marker')
    s=s.replace(m,b,1)
p.write_text(s,newline='\n')
