from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text();m='            "tool-error": {"tool_result": "error"},\n';key='tool-'+'time'+'out';value='time'+'out';line=f'            "{key}": {{"tool_result": "{value}"}},\n'
if f'"{key}"' not in s: s=s.replace(m,m+line,1)
p.write_text(s,newline='\n')
