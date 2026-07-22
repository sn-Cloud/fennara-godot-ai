#!/usr/bin/env python3
import json
import os
import sys


def emit(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


client_name = ""
transport_approval_pending = False
dock_approval_pending = False

emit({"method": "mock/started", "params": {"pid": os.getpid(), "argv": sys.argv}})

for raw_line in sys.stdin:
    raw_line = raw_line.strip()
    if not raw_line:
        continue

    message = json.loads(raw_line)
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        client_name = params.get("clientInfo", {}).get("name", "")
        emit({
            "id": request_id,
            "result": {
                "userAgent": "mock-codex",
                "codexHome": "/tmp/mock-codex",
                "platformFamily": "windows" if os.name == "nt" else "unix",
                "platformOs": "windows" if os.name == "nt" else "linux",
            },
        })

        if client_name == "godot_codex_native_chat_test":
            emit({"method": "mock/notification", "params": {"ok": True}})
            transport_approval_pending = True
            emit({
                "id": "approval-1",
                "method": "item/commandExecution/requestApproval",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "item-1",
                    "command": "echo smoke-test",
                    "cwd": "/tmp",
                    "reason": "transport smoke test",
                },
            })

    elif method == "account/read":
        emit({
            "id": request_id,
            "result": {
                "account": {
                    "type": "chatgpt",
                    "email": "codex-native-chat-ci@example.com",
                    "planType": "plus",
                },
                "requiresOpenaiAuth": True,
            },
        })

    elif method == "config/mcpServer/reload":
        emit({"id": request_id, "result": {}})

    elif method == "mcpServerStatus/list":
        emit({
            "id": request_id,
            "result": {
                "data": [
                    {
                        "name": "godot-mcp",
                        "status": "ready",
                    }
                ]
            },
        })

    elif method == "thread/start":
        thread = {
            "id": "dock-thread-1",
            "status": {"type": "idle"},
            "cwd": params.get("cwd"),
            "model": params.get("model"),
        }
        emit({"id": request_id, "result": {"thread": thread}})
        emit({"method": "thread/started", "params": {"thread": thread}})

    elif method == "thread/resume":
        thread = {
            "id": params.get("threadId", "dock-thread-1"),
            "status": {"type": "idle"},
        }
        emit({"id": request_id, "result": {"thread": thread}})
        emit({"method": "thread/started", "params": {"thread": thread}})

    elif method == "turn/start":
        turn = {
            "id": "dock-turn-1",
            "status": "inProgress",
            "items": [],
        }
        emit({"id": request_id, "result": {"turn": turn}})
        emit({"method": "turn/started", "params": {"threadId": params.get("threadId"), "turn": turn}})
        emit({
            "method": "item/started",
            "params": {
                "threadId": params.get("threadId"),
                "turnId": "dock-turn-1",
                "item": {
                    "id": "dock-command-1",
                    "type": "commandExecution",
                    "command": "godot --headless --path . --quit",
                    "status": "inProgress",
                },
            },
        })
        emit({
            "method": "turn/diff/updated",
            "params": {
                "threadId": params.get("threadId"),
                "turnId": "dock-turn-1",
                "diff": "diff --git a/player.gd b/player.gd\n+print(\"Codex Native Chat\")\n",
            },
        })
        dock_approval_pending = True
        emit({
            "id": "dock-approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": params.get("threadId"),
                "turnId": "dock-turn-1",
                "itemId": "dock-command-1",
                "command": "godot --headless --path . --quit",
                "cwd": params.get("cwd"),
                "reason": "Verify the Godot project",
            },
        })

    elif method == "turn/interrupt":
        emit({"id": request_id, "result": {}})
        emit({
            "method": "turn/completed",
            "params": {
                "threadId": params.get("threadId"),
                "turn": {
                    "id": params.get("turnId"),
                    "status": "interrupted",
                    "items": [],
                },
            },
        })

    elif request_id == "approval-1" and transport_approval_pending and "result" in message:
        transport_approval_pending = False
        emit({
            "method": "mock/approvalReceived",
            "params": {"decision": message.get("result", {}).get("decision")},
        })

    elif request_id == "dock-approval-1" and dock_approval_pending and "result" in message:
        dock_approval_pending = False
        emit({
            "method": "item/commandExecution/outputDelta",
            "params": {
                "threadId": "dock-thread-1",
                "turnId": "dock-turn-1",
                "itemId": "dock-command-1",
                "delta": "Godot verification passed.\n",
            },
        })
        emit({
            "method": "item/completed",
            "params": {
                "threadId": "dock-thread-1",
                "turnId": "dock-turn-1",
                "item": {
                    "id": "dock-command-1",
                    "type": "commandExecution",
                    "command": "godot --headless --path . --quit",
                    "status": "completed",
                    "exitCode": 0,
                },
            },
        })
        emit({
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": "dock-thread-1",
                "turnId": "dock-turn-1",
                "itemId": "dock-agent-1",
                "delta": "The Godot task was completed and verified through Godot MCP Native.",
            },
        })
        emit({
            "method": "item/completed",
            "params": {
                "threadId": "dock-thread-1",
                "turnId": "dock-turn-1",
                "item": {
                    "id": "dock-agent-1",
                    "type": "agentMessage",
                    "text": "The Godot task was completed and verified through Godot MCP Native.",
                },
            },
        })
        emit({
            "method": "turn/completed",
            "params": {
                "threadId": "dock-thread-1",
                "turn": {
                    "id": "dock-turn-1",
                    "status": "completed",
                    "items": [],
                },
            },
        })
