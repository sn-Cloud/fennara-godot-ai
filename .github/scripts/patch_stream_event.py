from pathlib import Path

path = Path("local/crates/fennara-daemon/src/runtime_daemon/chat/providers/stream.rs")
text = path.read_text(encoding="utf-8")
old = """    Status {\n        message: String,\n    },\n"""
new = """    ExternalToolActivity {\n        id: String,\n        name: String,\n        arguments: String,\n        content: String,\n        status: String,\n    },\n    Status {\n        message: String,\n    },\n"""
if "ExternalToolActivity" not in text:
    if text.count(old) != 1:
        raise RuntimeError("StreamEvent status marker mismatch")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
