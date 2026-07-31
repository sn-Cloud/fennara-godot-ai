from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8')
old='''        connection.runtime = Some(codex_runtime::metadata_from_initialize(
            &runtime_spec,
            &initialize,
        ));
'''
new='''        connection.runtime = Some(codex_runtime::metadata_from_initialize(
            &runtime_spec,
            &initialize,
        )?);
'''
if new not in s:
    if s.count(old)!=1: raise RuntimeError('runtime metadata assignment')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
