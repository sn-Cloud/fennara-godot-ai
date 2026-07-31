from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
content = path.read_text(encoding="utf-8")
old = "    let (approval_tx, mut approval_rx) = mpsc::unbounded_channel();\n"
new = "    let (approval_tx, mut approval_rx) =\n        mpsc::unbounded_channel::<ProviderApprovalRequest>();\n"
count = content.count(old)
if count != 1:
    raise RuntimeError(f"expected one approval test channel, found {count}")
path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
