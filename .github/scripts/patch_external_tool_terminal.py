from pathlib import Path

path = Path("local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs")
text = path.read_text(encoding="utf-8")
marker = "fn stream_item_has_assistant_output(item: &StreamItem) -> bool {\n"
helper = """fn external_tool_status_is_terminal(status: &str) -> bool {\n    matches!(status, \"done\" | \"completed\" | \"failed\" | \"timed_out\" | \"cancelled\" | \"denied\")\n}\n\n"""
if "fn external_tool_status_is_terminal" not in text:
    if text.count(marker) != 1:
        raise RuntimeError("publisher helper marker mismatch")
    path.write_text(text.replace(marker, helper + marker, 1), encoding="utf-8", newline="\n")
