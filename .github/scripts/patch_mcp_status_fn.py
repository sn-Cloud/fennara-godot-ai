from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8')
m='fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {\n'
b='''fn mcp_status(item: &Value, completed: bool) -> String {
    match item.get("status").and_then(Value::as_str).unwrap_or_default() {
        "inProgress" => "running".to_string(),
        "completed" => "completed".to_string(),
        "failed" => mcp_failure_status(item),
        _ if completed => "completed".to_string(),
        _ => "running".to_string(),
    }
}

'''
if 'fn mcp_status(item:' not in s:
    if s.count(m)!=1: raise RuntimeError('status marker')
    p.write_text(s.replace(m,b+m,1),encoding='utf-8',newline='\n')
