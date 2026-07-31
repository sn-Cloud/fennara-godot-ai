from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
content = TARGET.read_text(encoding="utf-8")

replacements = [
    (
        "                    error: None,\n                    runtime: None,\n                };",
        "                    error: None,\n                    runtime: None,\n                    mcp: codex_mcp::inspect(),\n                };",
        "login account update status",
    ),
    (
        "        error,\n        runtime: None,\n    }\n}\n\nfn attach_runtime",
        "        error,\n        runtime: None,\n        mcp: codex_mcp::inspect(),\n    }\n}\n\nfn attach_runtime",
        "account status result",
    ),
]

for old, new, label in replacements:
    if new in content:
        continue
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {label}, found {count}")
    content = content.replace(old, new, 1)

TARGET.write_text(content, encoding="utf-8", newline="\n")
print("Codex MCP account status initialization completed")
