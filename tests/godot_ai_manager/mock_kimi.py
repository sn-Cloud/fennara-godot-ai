#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == "login":
    sys.stderr.write("Open https://example.invalid/kimi-device and enter code TEST-CODE\n")
    sys.stderr.flush()
    raise SystemExit(0)


def emit(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()

state = "idle"
errors = []
prompt_request_id = None
for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    message = json.loads(raw)
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        emit({"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": 1,
            "agentInfo": {"name": "Kimi Code CLI", "version": "mock"},
            "agentCapabilities": {"loadSession": True, "mcpCapabilities": {"http": True}},
            "authMethods": [{"id": "login", "name": "Kimi Code"}],
        }})
    elif method == "authenticate":
        if params.get("methodId") != "login":
            emit({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "invalid method"}})
        else:
            emit({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "session/new":
        servers = params.get("mcpServers") or []
        if not servers or servers[0].get("name") != "godot-mcp" or servers[0].get("type") != "http":
            errors.append("invalid mcpServers")
        emit({"jsonrpc": "2.0", "id": request_id, "result": {
            "sessionId": "kimi-session-1",
            "configOptions": [{"id": "model", "name": "Model", "currentValue": "k3"}],
        }})
    elif method in ("session/load", "session/resume"):
        emit({"jsonrpc": "2.0", "id": request_id, "result": {"sessionId": params.get("sessionId", "kimi-session-1"), "configOptions": []}})
    elif method == "session/set_config_option":
        emit({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "session/prompt":
        prompt_request_id = request_id
        state = "await_write"
        emit({"jsonrpc": "2.0", "id": "kimi-write-1", "method": "fs/write_text_file", "params": {"sessionId": params.get("sessionId"), "path": "generated_by_kimi.txt", "content": "Kimi ACP file bridge works."}})
    elif request_id == "kimi-write-1" and state == "await_write":
        if message.get("error"):
            errors.append("write failed")
        state = "await_read"
        emit({"jsonrpc": "2.0", "id": "kimi-read-1", "method": "fs/read_text_file", "params": {"sessionId": "kimi-session-1", "path": "generated_by_kimi.txt"}})
    elif request_id == "kimi-read-1" and state == "await_read":
        content = (message.get("result") or {}).get("content", "")
        if content != "Kimi ACP file bridge works.":
            errors.append("read content mismatch")
        state = "await_escape"
        emit({"jsonrpc": "2.0", "id": "kimi-escape-1", "method": "fs/write_text_file", "params": {"sessionId": "kimi-session-1", "path": "../escape.txt", "content": "forbidden"}})
    elif request_id == "kimi-escape-1" and state == "await_escape":
        if not message.get("error"):
            errors.append("path escape was not rejected")
        state = "await_permission"
        emit({"jsonrpc": "2.0", "id": "kimi-permission-1", "method": "session/request_permission", "params": {
            "sessionId": "kimi-session-1",
            "toolCall": {"toolCallId": "tool-1", "title": "运行 Godot 验证", "kind": "execute", "rawInput": {"command": "godot --headless"}},
            "options": [
                {"optionId": "allow_once", "name": "允许一次", "kind": "allow_once"},
                {"optionId": "reject_once", "name": "拒绝", "kind": "reject_once"},
            ],
        }})
    elif request_id == "kimi-permission-1" and state == "await_permission":
        outcome = (message.get("result") or {}).get("outcome", {})
        if outcome.get("outcome") != "selected" or outcome.get("optionId") != "allow_once":
            errors.append("permission mismatch")
        state = "done"
        emit({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "kimi-session-1", "update": {"sessionUpdate": "tool_call", "toolCallId": "tool-1", "title": "Godot MCP Native", "status": "completed", "rawOutput": {"diff": "diff --git a/kimi.gd b/kimi.gd\n@@ -1 +1 @@\n-old\n+new\n"}}}})
        emit({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": "kimi-session-1", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Kimi 已通过 Godot MCP Native 完成验证。"}}}})
        if errors:
            emit({"jsonrpc": "2.0", "id": 99999, "error": {"code": -32099, "message": "; ".join(errors)}})
        emit({"jsonrpc": "2.0", "id": prompt_request_id, "result": {"stopReason": "end_turn"}})
    elif method == "session/cancel":
        emit({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": params.get("sessionId"), "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "已取消"}}}})
