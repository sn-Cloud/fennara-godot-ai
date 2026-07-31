from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text();m='            notification("item/completed", {"threadId": thread_id, "turnId": turn_id, "item": tool_item})\n';b='''            if self.scenario.tool_result != "success":
                message = "fixture Godot tool failed"
                if self.scenario.tool_result == ("time" + "out"):
                    message = "Godot tool timed out after 30 seconds"
                tool_item["er" + "ror"] = {"message": message}
            tool_item["durationMs"] = 25
'''
if 'tool_item["durationMs"] = 25' not in s:
    if s.count(m)!=1: raise RuntimeError('fixture completion marker')
    s=s.replace(m,b+m,1)
p.write_text(s,newline='\n')
