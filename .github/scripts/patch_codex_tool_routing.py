from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8')
old='''            "item/started" => {
                if let Some(status) = item_status_message(params.get("item"), false) {
                    if !on_event(StreamEvent::Status { message: status }).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/completed" => {
                if let Some(status) = item_status_message(params.get("item"), true) {
                    if !on_event(StreamEvent::Status { message: status }).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
'''
new='''            "item/started" => {
                let event = mcp_lifecycle_event(params.get("item"), false, &mut mcp_items)
                    .or_else(|| item_status_message(params.get("item"), false)
                        .map(|message| StreamEvent::Status { message }));
                if let Some(event) = event {
                    if !on_event(event).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/completed" => {
                let event = mcp_lifecycle_event(params.get("item"), true, &mut mcp_items)
                    .or_else(|| item_status_message(params.get("item"), true)
                        .map(|message| StreamEvent::Status { message }));
                if let Some(event) = event {
                    if !on_event(event).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/mcpToolCall/progress" => {
                if let Some(event) = mcp_progress_event(&params, &mcp_items) {
                    if !on_event(event).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
'''
if '"item/mcpToolCall/progress" =>' not in s:
    if s.count(old)!=1: raise RuntimeError('item lifecycle block')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
