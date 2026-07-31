from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8');m='fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {\n'
b='''fn mcp_content(item: &Value, status: &str) -> String {
    if let Some(message) = item.pointer("/error/message").and_then(Value::as_str) {
        return message.to_string();
    }
    let Some(result) = item.get("result").filter(|value| !value.is_null()) else {
        return if status == "running" {
            "Running through Codex app-server and the configured Fennara MCP server.".to_string()
        } else { String::new() };
    };
    if let Some(value) = result.get("structuredContent").filter(|value| !value.is_null()) {
        return format!("```json\n{}\n```", format_json(value));
    }
    result.get("content").and_then(Value::as_array)
        .map(|parts| parts.iter().filter_map(mcp_content_part).collect::<Vec<_>>().join("\n\n"))
        .unwrap_or_else(|| format_json(result))
}

'''
if 'fn mcp_content(' not in s:
    if s.count(m)!=1: raise RuntimeError('content marker')
    p.write_text(s.replace(m,b+m,1),encoding='utf-8',newline='\n')
