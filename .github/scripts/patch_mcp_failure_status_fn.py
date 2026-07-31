from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8')
m='fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {\n'
b='''fn mcp_failure_status(item: &Value) -> String {
    let message = item.pointer("/error/message")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    if message.contains("timed out") || message.contains("timeout") {
        "timed_out".to_string()
    } else if message.contains("cancel") || message.contains("interrupt") {
        "cancelled".to_string()
    } else {
        "failed".to_string()
    }
}

'''
if 'fn mcp_failure_status(' not in s:
    if s.count(m)!=1: raise RuntimeError('status marker')
    p.write_text(s.replace(m,b+m,1),encoding='utf-8',newline='\n')
