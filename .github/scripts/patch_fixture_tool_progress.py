from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text(encoding='utf-8')
marker='''            notification("item/started", {"threadId": thread_id, "turnId": turn_id, "item": tool_item})
'''
block=marker+'''            if self.scenario.tool_progress:
                notification(
                    "item/mcpToolCall/progress",
                    {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "itemId": tool_item["id"],
                        "message": "fixture Godot tool progress",
                    },
                )
'''
if 'fixture Godot tool progress' not in s:
    if s.count(marker)!=1: raise RuntimeError('fixture started notification')
    s=s.replace(marker,block,1)
p.write_text(s,encoding='utf-8',newline='\n')
