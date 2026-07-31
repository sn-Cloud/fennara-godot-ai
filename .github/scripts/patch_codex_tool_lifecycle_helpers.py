from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8')
marker='fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {\n'
block='''fn mcp_lifecycle_event(
    item: Option<&Value>,
    completed: bool,
    states: &mut HashMap<String, McpItemState>,
) -> Option<StreamEvent> {
    let item = item?;
    if item.get("type").and_then(Value::as_str) != Some("mcpToolCall") {
        return None;
    }
    let id = clean_json_string(item.get("id"))?;
    let previous = states.get(&id).cloned();
    let server = clean_json_string(item.get("server"));
    let tool = clean_json_string(item.get("tool"))
        .or_else(|| clean_json_string(item.get("name")));
    let name = match (server, tool) {
        (Some(server), Some(tool)) => format!("{server} · {tool}"),
        (_, Some(tool)) => tool,
        _ => previous.as_ref().map(|state| state.name.clone())
            .unwrap_or_else(|| "MCP tool".to_string()),
    };
    let arguments = item.get("arguments").map(format_json)
        .or_else(|| previous.as_ref().map(|state| state.arguments.clone()))
        .unwrap_or_else(|| "{}".to_string());
    let arguments = truncate_text(&arguments, MCP_ARGUMENT_LIMIT);
    let status = mcp_status(item, completed);
    let content = truncate_text(&mcp_content(item, &status), MCP_CONTENT_LIMIT);
    if mcp_status_is_terminal(&status) {
        states.remove(&id);
    } else {
        states.insert(id.clone(), McpItemState {
            name: name.clone(),
            arguments: arguments.clone(),
        });
    }
    Some(StreamEvent::ExternalToolActivity {
        id,
        name,
        arguments,
        content,
        status,
    })
}

fn mcp_progress_event(
    params: &Value,
    states: &HashMap<String, McpItemState>,
) -> Option<StreamEvent> {
    let id = clean_json_string(params.get("itemId"))?;
    let state = states.get(&id)?;
    let content = clean_json_string(params.get("message"))?;
    Some(StreamEvent::ExternalToolActivity {
        id,
        name: state.name.clone(),
        arguments: state.arguments.clone(),
        content: truncate_text(&content, MCP_CONTENT_LIMIT),
        status: "running".to_string(),
    })
}

'''
if 'fn mcp_lifecycle_event(' not in s:
    if s.count(marker)!=1: raise RuntimeError('item status helper marker')
    s=s.replace(marker,block+marker,1)
p.write_text(s,encoding='utf-8',newline='\n')
