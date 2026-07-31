from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text();m='            tool_item["status"] = "completed" if self.scenario.tool_result == "success" else "failed"\n';a=m+'            if self.scenario.tool_result == "success":\n                tool_item["result"] = {"content": [{"type": "text", "text": "fixture scene tree"}], "structuredContent": {"ok": True, "nodes": 3}, "_meta": None}\n'
if '"structuredContent": {"ok": True' not in s:
    if s.count(m)!=1: raise RuntimeError('fixture status marker')
    s=s.replace(m,a,1)
p.write_text(s,newline='\n')
