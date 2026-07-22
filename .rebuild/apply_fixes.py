#!/usr/bin/env python3
from pathlib import Path
import shutil
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

# GitHub Actions 的 GITHUB_TOKEN 不能通过 git push 创建或更新工作流文件。
# 测试仍使用源码包中的工作流定义，但发布提交先移除它们；
# 通过验证后，再由 GitHub Contents API 添加最终的仅手动运行工作流。
workflows_dir = root / ".github" / "workflows"
if workflows_dir.exists():
    shutil.rmtree(workflows_dir)
