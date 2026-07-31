from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8');m='fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {\n'
b='''fn mcp_content_part(part: &Value) -> Option<String> {
    if let Some(text) = part.get("text").and_then(Value::as_str) {
        return Some(text.to_string());
    }
    if part.get("type").and_then(Value::as_str) == Some("image") {
        let mime = part.get("mimeType").or_else(|| part.get("mime_type"))
            .and_then(Value::as_str).unwrap_or("image");
        return Some(format!("Image result ({mime})"));
    }
    (!part.is_null()).then(|| format!("```json\n{}\n```", format_json(part)))
}

'''
if 'fn mcp_content_part(' not in s:
    if s.count(m)!=1: raise RuntimeError('content marker')
    p.write_text(s.replace(m,b+m,1),encoding='utf-8',newline='\n')
