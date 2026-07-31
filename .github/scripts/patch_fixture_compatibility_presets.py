from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text();m='            "unknown-events": {"unknown_events": True},\n';b=m+'            "older-runtime": {"version": "0.100.0"},\n            "newer-runtime": {"version": "0.145.0"},\n            "malformed-initialize": {"initialize_shape": "missing-platform"},\n'
if '"older-runtime"' not in s:
    if s.count(m)!=1: raise RuntimeError('fixture preset marker')
    s=s.replace(m,b,1)
p.write_text(s,newline='\n')
