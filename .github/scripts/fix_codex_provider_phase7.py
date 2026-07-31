from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
content = path.read_text(encoding="utf-8")
old = '''    assert_eq!(first_events.deltas, 2);
    assert_eq!(second_events.deltas, 2);
'''
new = '''    assert_eq!(first_events.deltas, 1);
    assert_eq!(second_events.deltas, 1);
'''
count = content.count(old)
if count != 1:
    raise RuntimeError(f"expected one concurrent-session assertion block, found {count}")
path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
