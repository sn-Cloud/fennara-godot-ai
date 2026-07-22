#!/usr/bin/env python3
import json
import sys


def emit(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()

pending_approval = False
for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    message = json.loads(raw)
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        emit({"id": request_id, "result": {"userAgent": "mock-codex"}})
    elif method == "account/read":
        emit({"id": request_id, "result": {"account": {"type": "chatgpt", "planType": "plus"}, "requiresOpenaiAuth": True}})
    elif method == "account/login/start":
        emit({"id": request_id, "result": {"authUrl": "https://example.invalid/codex-login"}})
    elif method == "account/logout":
        emit({"id": request_id, "result": {}})
        emit({"method": "account/updated", "params": {"authMode": None, "planType": None}})
    elif method == "config/mcpServer/reload":
        emit({"id": request_id, "result": {}})
    elif method == "mcpServerStatus/list":
        emit({"id": request_id, "result": {"data": [{"name": "godot-mcp", "status": "ready"}]}})
    elif method == "thread/start":
        thread = {"id": "codex-thread-1"}
        emit({"id": request_id, "result": {"thread": thread}})
        emit({"method": "thread/started", "params": {"thread": thread}})
    elif method == "thread/resume":
        thread = {"id": params.get("threadId", "codex-thread-1")}
        emit({"id": request_id, "result": {"thread": thread}})
    elif method == "turn/start":
        turn = {"id": "codex-turn-1", "status": "inProgress"}
        emit({"id": request_id, "result": {"turn": turn}})
        emit({"method": "turn/started", "params": {"turn": turn}})
        emit({"method": "item/started", "params": {"item": {"type": "mcpToolCall", "server": "godot-mcp", "tool": "get-scene-tree"}}})
        emit({"method": "turn/diff/updated", "params": {"diff": "diff --git a/player.gd b/player.gd\n@@ -1 +1 @@\n-old\n+new\n"}})
        pending_approval = True
        emit({"id": "codex-approval-1", "method": "item/commandExecution/requestApproval", "params": {"command": "godot --headless --path . --quit", "cwd": params.get("cwd", "."), "reason": "验证项目"}})
    elif request_id == "codex-approval-1" and pending_approval:
        decision = (message.get("result") or {}).get("decision")
        if decision not in ("accept", "acceptForSession"):
            emit({"method": "error", "params": {"message": "approval rejected in test"}})
        pending_approval = False
        emit({"method": "item/agentMessage/delta", "params": {"delta": "Codex 已通过 Godot MCP Native 完成验证。"}})
        emit({"method": "turn/completed", "params": {"turn": {"id": "codex-turn-1", "status": "completed"}}})
    elif method == "turn/interrupt":
        emit({"id": request_id, "result": {}})
        emit({"method": "turn/completed", "params": {"turn": {"id": params.get("turnId"), "status": "interrupted"}}})
