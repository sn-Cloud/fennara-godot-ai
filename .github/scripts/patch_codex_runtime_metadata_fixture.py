from pathlib import Path

path = Path("local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs")
text = path.read_text(encoding="utf-8")
old = '''            pinned_version: codex_runtime::PINNED_CODEX_VERSION,
            source: codex_runtime::CodexRuntimeSource::Path,
'''
new = '''            pinned_version: codex_runtime::PINNED_CODEX_VERSION,
            minimum_version: codex_runtime::MINIMUM_CODEX_VERSION,
            compatibility_error: None,
            source: codex_runtime::CodexRuntimeSource::Path,
'''
if new not in text:
    if text.count(old) != 1:
        raise RuntimeError("runtime metadata fixture marker mismatch")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
