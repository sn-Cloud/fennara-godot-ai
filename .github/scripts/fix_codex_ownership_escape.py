from pathlib import Path

path = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
)
lines = path.read_text(encoding="utf-8").splitlines()
matches = 0
for index, line in enumerate(lines):
    if line.strip().startswith("let normalized = value.trim().replace("):
        lines[index] = (
            "    let normalized = value.trim().replace("
            + "'"
            + chr(92) * 2
            + "'"
            + ', "/");'
        )
        matches += 1
if matches != 1:
    raise SystemExit(f"expected one path-normalization line, found {matches}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
