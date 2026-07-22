#!/usr/bin/env python3
import json
import os
import sys


def emit(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def emit_approval_suite_file_change():
    emit({
        "id": "suite-file",
        "method": "item/fileChange/requestApproval",
        "params": {
            "threadId": "suite-thread",
            "turnId": "suite-turn",
            "itemId": "suite-file-item",
            "reason": "Update a Godot script",
            "grantRoot": None,
        },
    })


def emit_approval_suite_permissions():
    emit({
        "id": "suite-permissions",
        "method": "item/permissions/requestApproval",
        "params": {
            "threadId": "suite-thread",
            "turnId": "suite-turn",
            "itemId": "suite-permissions-item",
            "environmentId": None,
            "startedAtMs": 1,
            "cwd": "/tmp",
            "reason": "Access an additional project folder",
            "permissions": {
                "network": None,
                "fileSystem": None,
            },
        },
    })


def emit_approval_suite_user_input():
    emit({
        "id": "suite-user-input",
        "method": "item/tool/requestUserInput",
        "params": {
            "threadId": "suite-thread",
            "turnId": "suite-turn",
            "itemId": "suite-user-input-item",
            "questions": [
                {
                    "id": "color",
                    "header": "Theme color",
                    "question": "Which color should the Godot UI use?",
                    "isOther": True,
                    "isSecret": False,
                    "options": [
                        {"label": "Blue", "description": "Use a blue theme"},
                        {"label": "Gray", "description": "Use a gray theme"},
                    ],
                }
            ],
            "autoResolutionMs": None,
        },
    })


def emit_approval_suite_mcp_elicitation():
    emit({
        "id": "suite-mcp",
        "method": "mcpServer/elicitation/request",
        "params": {
            "threadId": "suite-thread",
            "turnId": "suite-turn",
            "serverName": "godot-mcp",
            "message": "Provide a test response for Godot MCP Native.",
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "value": {"type": "string"},
                },
                "required": ["value"],
            },
        },
    })


def emit_approval_suite_rejected_command():
    emit({
        "id": "suite-command",
        "method": "item/commandExecution/requestApproval",
        "params": {
            "threadId": "suite-thread",
            "turnId": "suite-turn",
            "itemId": "suite-command-item",
            "command": "echo should-be-rejected",
            "cwd": "/tmp",
            "reason": "Test rejection handling",
        },
    })


def emit_completed_dock_turn():
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


client_name = ""
transport_approval_pending = False
dock_approval_pending = False
approval_suite_active = False
approval_suite_errors = []

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

    elif method == "account/logout":
        emit({"id": request_id, "result": {}})
        emit({
            "method": "account/updated",
            "params": {
                "authMode": None,
                "planType": None,
            },
        })

    elif method == "account/login/start":
        emit({
            "id": request_id,
            "result": {
                "type": "chatgpt",
                "loginId": "mock-login-1",
                "authUrl": "",
            },
        })
        emit({
            "method": "account/login/completed",
            "params": {
                "loginId": "mock-login-1",
                "success": True,
                "error": None,
            },
        })
        emit({
            "method": "account/updated",
            "params": {
                "authMode": "chatgpt",
                "planType": "plus",
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
        prompt = ""
        input_items = params.get("input") or []
        if input_items:
            prompt = input_items[0].get("text", "")

        turn_id = "interrupt-turn-1" if "interrupt-me" in prompt else "dock-turn-1"
        turn = {
            "id": turn_id,
            "status": "inProgress",
            "items": [],
        }
        emit({"id": request_id, "result": {"turn": turn}})
        emit({"method": "turn/started", "params": {"threadId": params.get("threadId"), "turn": turn}})

        if "interrupt-me" in prompt:
            continue

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

    elif method == "mock/approvalSuite/start":
        approval_suite_active = True
        approval_suite_errors.clear()
        emit({"id": request_id, "result": {}})
        emit_approval_suite_file_change()

    elif request_id == "approval-1" and transport_approval_pending and "result" in message:
        transport_approval_pending = False
        emit({
            "method": "mock/approvalReceived",
            "params": {"decision": message.get("result", {}).get("decision")},
        })

    elif request_id == "dock-approval-1" and dock_approval_pending and "result" in message:
        dock_approval_pending = False
        emit_completed_dock_turn()

    elif request_id == "suite-file" and approval_suite_active and "result" in message:
        if message.get("result", {}).get("decision") != "acceptForSession":
            approval_suite_errors.append("file approval decision")
        emit_approval_suite_permissions()

    elif request_id == "suite-permissions" and approval_suite_active and "result" in message:
        result = message.get("result", {})
        if result.get("scope") != "turn" or "permissions" not in result:
            approval_suite_errors.append("permission approval response")
        emit_approval_suite_user_input()

    elif request_id == "suite-user-input" and approval_suite_active and "result" in message:
        answers = message.get("result", {}).get("answers", {})
        selected = answers.get("color", {}).get("answers", [])
        if selected != ["Blue"]:
            approval_suite_errors.append("user input response")
        emit_approval_suite_mcp_elicitation()

    elif request_id == "suite-mcp" and approval_suite_active and "result" in message:
        result = message.get("result", {})
        if result.get("action") != "accept" or result.get("content") != {"value": "ok"}:
            approval_suite_errors.append("MCP elicitation response")
        emit_approval_suite_rejected_command()

    elif request_id == "suite-command" and approval_suite_active and "result" in message:
        if message.get("result", {}).get("decision") != "decline":
            approval_suite_errors.append("command rejection response")
        approval_suite_active = False
        emit({
            "method": "mock/approvalSuiteComplete",
            "params": {
                "ok": not approval_suite_errors,
                "errors": approval_suite_errors,
            },
        })
