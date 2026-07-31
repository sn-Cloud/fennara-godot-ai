from pathlib import Path

path = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
)
lines = path.read_text(encoding="utf-8").splitlines()
normalization_matches = 0
windows_fixture_matches = 0
for index, line in enumerate(lines):
    if line.strip().startswith("let normalized = value.trim().replace("):
        lines[index] = (
            "    let normalized = value.trim().replace("
            + "'"
            + chr(92) * 2
            + "'"
            + ', "/");'
        )
        normalization_matches += 1
    if "C:" in line and "Users" in line and "Test" in line and ".codex" in line:
        lines[index] = (
            '            r"C:'
            + chr(92)
            + "Users"
            + chr(92)
            + "Test"
            + chr(92)
            + '.codex",'
        )
        windows_fixture_matches += 1
if normalization_matches != 1:
    raise SystemExit(
        f"expected one path-normalization line, found {normalization_matches}"
    )
if windows_fixture_matches != 1:
    raise SystemExit(
        f"expected one Windows path fixture, found {windows_fixture_matches}"
    )
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
