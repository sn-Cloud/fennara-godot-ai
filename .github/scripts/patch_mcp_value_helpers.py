from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8');m='fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {\n'
b='''fn clean_json_string(value: Option<&Value>) -> Option<String> {
    value.and_then(Value::as_str).map(str::trim)
        .filter(|value| !value.is_empty()).map(ToString::to_string)
}

fn format_json(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        _ => serde_json::to_string_pretty(value).unwrap_or_else(|_| value.to_string()),
    }
}

fn truncate_text(value: &str, limit: usize) -> String {
    if value.chars().count() <= limit { return value.to_string(); }
    let mut output = value.chars().take(limit).collect::<String>();
    output.push_str("\n\n[Output truncated by Fennara]");
    output
}

'''
if 'fn clean_json_string(' not in s:
    if s.count(m)!=1: raise RuntimeError('value helper marker')
    p.write_text(s.replace(m,b+m,1),encoding='utf-8',newline='\n')
