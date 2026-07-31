from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "local/crates/fennara-daemon/src"

patterns = [
    (
        re.compile(
            r"(?m)^(?P<indent>\s*)max_output_tokens: (?P<value>[^\n]+),\n(?P=indent)cwd:"
        ),
        4,
        "chat request initializers",
        lambda match: (
            f"{match.group('indent')}max_output_tokens: {match.group('value')},\n"
            f"{match.group('indent')}chat_id: None,\n"
            f"{match.group('indent')}cwd:"
        ),
    ),
    (
        re.compile(r"(?m)^(?P<indent>\s*)tools: (?P<value>[^\n]+),\n(?P=indent)cwd:"),
        7,
        "LLM request initializers",
        lambda match: (
            f"{match.group('indent')}tools: {match.group('value')},\n"
            f"{match.group('indent')}chat_id: None,\n"
            f"{match.group('indent')}cwd:"
        ),
    ),
]

counts = [0, 0]
for path in SOURCE_ROOT.rglob("*.rs"):
    content = path.read_text(encoding="utf-8")
    updated = content
    for index, (pattern, _, _, replacement) in enumerate(patterns):
        updated, count = pattern.subn(replacement, updated)
        counts[index] += count
    if updated != content:
        path.write_text(updated, encoding="utf-8", newline="\n")

for count, (_, expected, label, _) in zip(counts, patterns):
    if count != expected:
        raise RuntimeError(f"expected {expected} {label}, updated {count}")

print(f"updated {counts[0]} ChatRequest and {counts[1]} LlmRequest initializers")
