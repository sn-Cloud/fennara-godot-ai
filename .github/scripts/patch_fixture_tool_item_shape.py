from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text(encoding='utf-8')
old='''            tool_item = {
                "id": f"tool-{uuid.uuid4()}",
                "type": "mcpToolCall",
                "tool": "get_scene_tree",
                "status": "inProgress",
            }
'''
new='''            tool_item = {
                "id": f"tool-{uuid.uuid4()}",
                "type": "mcpToolCall",
                "server": "fennara",
                "tool": "get_scene_tree",
                "status": "inProgress",
                "arguments": {"depth": 2},
                "result": None,
                "error": None,
                "durationMs": None,
            }
'''
if '"server": "fennara"' not in s:
    if s.count(old)!=1: raise RuntimeError('fixture MCP item shape')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
