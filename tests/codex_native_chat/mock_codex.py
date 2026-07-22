#!/usr/bin/env python3
import json
import os
import sys


def emit(message):
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


emit({"method": "mock/started", "params": {"pid": os.getpid(), "argv": sys.argv}})

for raw_line in sys.stdin:
    raw_line = raw_line.strip()
    if not raw_line:
        continue
    message = json.loads(raw_line)
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        emit({
            "id": request_id,
            "result": {
                "userAgent": "mock-codex",
                "codexHome": "/tmp/mock-codex",
                "platformFamily": "unix",
                "platformOs": "linux",
            },
        })
        emit({"method": "mock/notification", "params": {"ok": True}})
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
    elif request_id == "approval-1" and "result" in message:
        emit({
            "method": "mock/approvalReceived",
            "params": {"decision": message.get("result", {}).get("decision")},
        })
