#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: apply_fixes.py <clean-tree>")

root = Path(sys.argv[1])
paths = [
    root / "addons/godot_ai_manager/agent_backend.gd",
    root / "addons/godot_ai_manager/codex_backend.gd",
    root / "addons/godot_ai_manager/kimi_backend.gd",
    root / "tests/godot_ai_manager/backend_smoke_test.gd",
]

for path in paths:
    text = path.read_text(encoding="utf-8")
    updated = text.replace("is_connected()", "is_backend_connected()")
    if updated == text and "is_backend_connected()" not in text:
        raise RuntimeError(f"expected backend connection method not found: {path}")
    path.write_text(updated, encoding="utf-8")
