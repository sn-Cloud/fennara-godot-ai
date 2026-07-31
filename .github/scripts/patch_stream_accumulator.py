from pathlib import Path

path = Path("local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs")
text = path.read_text(encoding="utf-8")
marker = """            StreamEvent::Status { message } => {\n"""
block = """            StreamEvent::ExternalToolActivity {\n                id,\n                name,\n                arguments,\n                content,\n                status,\n            } => {\n                items.push(StreamItem::ExternalTool {\n                    id,\n                    name,\n                    arguments,\n                    content,\n                    status,\n                });\n            }\n"""
if "StreamEvent::ExternalToolActivity" not in text:
    if text.count(marker) != 1:
        raise RuntimeError("StreamAccumulator status marker mismatch")
    path.write_text(text.replace(marker, block + marker, 1), encoding="utf-8", newline="\n")
