from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs')
s=p.read_text(encoding='utf-8')
a='| StreamItem::FunctionCallError { .. } => true,'
b='| StreamItem::FunctionCallError { .. }\n        | StreamItem::ExternalTool { .. } => true,'
if b not in s:
    if s.count(a)!=1: raise RuntimeError('match arm marker')
    p.write_text(s.replace(a,b,1),encoding='utf-8',newline='\n')
