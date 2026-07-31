from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
content = path.read_text(encoding="utf-8")
old = "                    email: None,\n                    error: None,\n                };\n"
new = "                    email: None,\n                    error: None,\n                    runtime: None,\n                };\n"
count = content.count(old)
if count != 1:
    raise RuntimeError(f"expected one login status initializer, found {count}")
path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
