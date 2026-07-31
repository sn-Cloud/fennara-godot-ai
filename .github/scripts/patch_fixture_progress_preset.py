from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text()
m='            "unknown-events": {"unknown_events": True},\n'
line='            "tool-progress": {"tool_progress": True},\n'
if '"tool-progress"' not in s: s=s.replace(m,m+line,1)
p.write_text(s,newline='\n')
