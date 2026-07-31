from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();m='#[derive(Default)]\nstruct TurnEvents {';b='''#[derive(Clone, Debug)]
struct ObservedMcpActivity {
    id: String,
    name: String,
    arguments: String,
    content: String,
    status: String,
}

'''
if 'struct ObservedMcpActivity' not in s:
    if s.count(m)!=1: raise RuntimeError('TurnEvents marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
