from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py');s=p.read_text();a='    tool_result: str = "success"\n';b=a+'    tool_progress: bool = False\n';p.write_text(s if 'tool_progress: bool' in s else s.replace(a,b,1),newline='\n')
