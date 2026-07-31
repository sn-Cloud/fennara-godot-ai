from pathlib import Path


def fix(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    start_marker = "function updateToolCall(item) {\n"
    end_marker = "\n    function isTerminalToolStatus(status) {"
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    block = text[start:end]
    indented = "\n".join(("    " + line) if line else "" for line in block.splitlines())
    path.write_text(text[:start] + indented + text[end:], encoding="utf-8")


source = Path("ui/chat/transcript-renderer.js")
packaged = Path("godot_demo/addons/fennara/dist/transcript-renderer.js")
fix(source)
fix(packaged)
if source.read_bytes() != packaged.read_bytes():
    raise SystemExit("source and packaged transcript renderers diverged")
