from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "ui/chat/app.js").read_text(encoding="utf-8")
distributed = (ROOT / "godot_demo/addons/fennara/dist/app.js").read_text(encoding="utf-8")

if source != distributed:
    raise RuntimeError("source and distributed chat UI differ")

required = [
    "CODEX_RUNTIME_POLL_MS",
    "codexRuntimeInstallRequested",
    "requestCodexRuntimeStatus",
    "codexRuntimeProgressLabel",
    "codex_runtime_install_start",
    "codex_runtime_install_cancel",
    "codex_runtime_status",
    "automatic installation is not supported on this platform yet",
    "Codex runtime installed. Starting ChatGPT login",
]
for marker in required:
    if marker not in source:
        raise RuntimeError(f"missing managed Codex runtime UI marker: {marker}")

assets = (ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/assets.rs").read_text(
    encoding="utf-8"
)
for marker in [
    "codex_account_ui_exposes_cancel_and_runtime_compatibility",
    "codex_runtime_install_start",
    "codex_runtime_install_cancel",
]:
    if marker not in assets:
        raise RuntimeError(f"missing embedded asset test marker: {marker}")

print("phase nine UI is already applied and verified")
