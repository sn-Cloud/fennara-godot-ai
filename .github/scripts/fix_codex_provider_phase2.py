from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs"
content = path.read_text(encoding="utf-8")
old = "        None,\n        move |item| {\n"
new = "        None,\n        None,\n        move |item| {\n"
count = content.count(old)
if count != 1:
    raise RuntimeError(f"expected one summary stream call, found {count}")
path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
