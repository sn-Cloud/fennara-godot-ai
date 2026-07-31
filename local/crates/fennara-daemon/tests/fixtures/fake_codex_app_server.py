#!/usr/bin/env python3
"""Deterministic Codex app-server fixture for Fennara integration tests.

The fixture speaks newline-delimited JSON-RPC over stdio. Configure it with
FAKE_CODEX_SCENARIO or a JSON script supplied through FAKE_CODEX_SCRIPT.
It never accesses the network or a real CODEX_HOME.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def response(request_id: Any, result: Any) -> None:
    emit({"id": request_id, "result": result})


def error(request_id: Any, message: str, code: int = -32603) -> None:
    emit({"id": request_id, "error": {"code": code, "message": message}})


def notification(method: str, params: Any) -> None:
    emit({"method": method, "params": params})


def request(method: str, params: Any) -> str:
    request_id = f"server-{uuid.uuid4()}"
    emit({"id": request_id, "method": method, "params": params})
    return request_id


def read_json_line() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return {}
    return json.loads(line)


@dataclass
class Scenario:
    name: str = "authenticated"
    version: str = "0.144.4"
    initialize_shape: str = "valid"
    authenticated: bool = True
    plan_type: str = "plus"
    email: str = "fixture@example.invalid"
    login_result: str = "success"
    login_delay_ms: int = 0
    thread_resume: str = "success"
    turn_result: str = "success"
    approval: str = "none"
    compact: bool = False
    burst_deltas: int = 0
    tool_result: str = "success"
    tool_progress: bool = False
    crash_at: str | None = None
    invalid_json_at: str | None = None
    unknown_events: bool = False
    delay_ms: int = 0
    threads: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Scenario":
        script_path = os.environ.get("FAKE_CODEX_SCRIPT", "").strip()
        if script_path:
            raw = json.loads(Path(script_path).read_text(encoding="utf-8"))
            return cls(**raw)

        name = os.environ.get("FAKE_CODEX_SCENARIO", "authenticated").strip()
        scenario = cls(name=name)
        presets: dict[str, dict[str, Any]] = {
            "unauthenticated": {"authenticated": False},
            "login-failure": {"authenticated": False, "login_result": "failure"},
            "login-timeout": {"authenticated": False, "login_result": "timeout"},
            "resume-missing": {"thread_resume": "missing"},
            "resume-permission-denied": {"thread_resume": "permission-denied"},
            "turn-failure": {"turn_result": "failure"},
            "command-approval": {"approval": "command"},
            "file-approval": {"approval": "file"},
            "compaction": {"compact": True},
            "crash-initialize": {"crash_at": "initialize"},
            "crash-turn": {"crash_at": "turn"},
            "invalid-json-turn": {"invalid_json_at": "turn"},
            "burst": {"burst_deltas": 10_000},
            "unknown-events": {"unknown_events": True},
            "older-runtime": {"version": "0.100.0"},
            "newer-runtime": {"version": "0.145.0"},
            "malformed-initialize": {"initialize_shape": "missing-platform"},
            "tool-progress": {"tool_progress": True},
            "tool-error": {"tool_result": "error"},
            "tool-timeout": {"tool_result": "timeout"},
        }
        for key, value in presets.get(name, {}).items():
            setattr(scenario, key, value)
        return scenario


class FakeCodexAppServer:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.initialized = False
        self.login_id: str | None = None
        self.active_thread_id: str | None = None
        self.pending_server_requests: dict[str, str] = {}
        self.codex_home = Path(
            os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
        )
        self.state_path = self.codex_home / "fake-thread-state.json"
        self.request_log_path = self.codex_home / "fake-request-log.jsonl"
        self.load_state()

    def load_state(self) -> None:
        if not self.state_path.is_file():
            return
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        threads = raw.get("threads")
        if isinstance(threads, dict):
            self.scenario.threads = threads

    def save_state(self) -> None:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"threads": self.scenario.threads}, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def log_client_request(self, method: str, params: dict[str, Any]) -> None:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        with self.request_log_path.open("a", encoding="utf-8") as log:
            log.write(
                json.dumps(
                    {"method": method, "params": params},
                    separators=(",", ":"),
                )
                + "\n"
            )

    def initialize_result(self) -> dict[str, Any]:
        if sys.platform.startswith("win"):
            platform_os = "windows"
            platform_family = "windows"
        elif sys.platform == "darwin":
            platform_os = "macos"
            platform_family = "unix"
        else:
            platform_os = "linux"
            platform_family = "unix"
        result = {
            "userAgent": f"codex/{self.scenario.version} fake-fixture",
            "codexHome": os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
            "platformFamily": platform_family,
            "platformOs": platform_os,
        }
        if self.scenario.initialize_shape == "missing-platform":
            result.pop("platformOs")
        return result

    def maybe_delay(self) -> None:
        if self.scenario.delay_ms > 0:
            time.sleep(self.scenario.delay_ms / 1000)

    def maybe_crash(self, point: str) -> None:
        if self.scenario.crash_at == point:
            sys.stderr.write(f"fake Codex crash at {point}\n")
            sys.stderr.flush()
            raise SystemExit(70)

    def handle(self, message: dict[str, Any]) -> None:
        if not message:
            return

        message_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        if method is not None:
            self.log_client_request(str(method), params)

        if method is None and message_id in self.pending_server_requests:
            self.pending_server_requests.pop(str(message_id), None)
            return

        self.maybe_delay()

        if method == "initialize":
            self.maybe_crash("initialize")
            self.initialized = True
            response(
                message_id,
                self.initialize_result(),
            )
            return

        if method == "initialized":
            return

        if not self.initialized:
            error(message_id, "initialize must be called first", -32002)
            return

        if method == "account/read":
            account: dict[str, Any] | None = None
            if self.scenario.authenticated:
                account = {
                    "type": "chatgpt",
                    "email": self.scenario.email,
                    "planType": self.scenario.plan_type,
                }
            response(
                message_id,
                {"account": account, "requiresOpenaiAuth": True},
            )
            return

        if method == "account/login/start":
            self.login_id = f"login-{uuid.uuid4()}"
            response(
                message_id,
                {
                    "type": "chatgpt",
                    "loginId": self.login_id,
                    "authUrl": "https://example.invalid/fake-codex-login",
                },
            )
            if self.scenario.login_result == "timeout":
                return
            if self.scenario.login_delay_ms:
                time.sleep(self.scenario.login_delay_ms / 1000)
            success = self.scenario.login_result == "success"
            if success:
                self.scenario.authenticated = True
            notification(
                "account/login/completed",
                {
                    "loginId": self.login_id,
                    "success": success,
                    "error": None if success else "fixture authentication failed",
                },
            )
            notification(
                "account/updated",
                {
                    "authMode": "chatgpt" if success else None,
                    "planType": self.scenario.plan_type if success else None,
                },
            )
            return

        if method == "account/login/cancel":
            login_id = params.get("loginId")
            response(message_id, {})
            notification(
                "account/login/completed",
                {
                    "loginId": login_id,
                    "success": False,
                    "error": "cancelled by fixture client",
                },
            )
            return

        if method == "account/logout":
            self.scenario.authenticated = False
            response(message_id, {})
            notification("account/updated", {"authMode": None, "planType": None})
            return

        if method == "model/list":
            response(
                message_id,
                {
                    "data": [
                        {
                            "model": "fake-codex-model",
                            "displayName": "Fake Codex Model",
                            "isDefault": True,
                            "defaultReasoningEffort": "medium",
                            "supportedReasoningEfforts": [
                                {"reasoningEffort": "low"},
                                {"reasoningEffort": "medium"},
                                {"reasoningEffort": "high"},
                            ],
                        }
                    ],
                    "nextCursor": None,
                },
            )
            return

        if method == "thread/start":
            thread_id = f"thread-{uuid.uuid4()}"
            self.active_thread_id = thread_id
            self.scenario.threads[thread_id] = {"turns": 0, "compacted": False}
            self.save_state()
            response(message_id, self.thread_result(thread_id, params))
            notification("thread/started", {"thread": {"id": thread_id}})
            return

        if method == "thread/resume":
            thread_id = str(params.get("threadId", ""))
            if self.scenario.thread_resume == "missing":
                error(message_id, "Thread does not exist")
                return
            if self.scenario.thread_resume == "permission-denied":
                error(message_id, "Permission denied while opening thread")
                return
            if thread_id not in self.scenario.threads:
                error(message_id, "Thread does not exist")
                return
            self.active_thread_id = thread_id
            response(message_id, self.thread_result(thread_id, params))
            return

        if method == "turn/start":
            self.maybe_crash("turn")
            if self.scenario.invalid_json_at == "turn":
                sys.stdout.write("{not valid json}\n")
                sys.stdout.flush()
                return
            thread_id = str(params.get("threadId") or self.active_thread_id or "")
            if not thread_id:
                error(message_id, "threadId is required", -32602)
                return
            if thread_id not in self.scenario.threads:
                error(message_id, "Thread does not exist")
                return
            turn_id = f"turn-{uuid.uuid4()}"
            response(message_id, {"turn": {"id": turn_id}})
            self.emit_turn(thread_id, turn_id)
            return

        if method == "turn/interrupt":
            response(message_id, {})
            notification(
                "turn/completed",
                {
                    "threadId": params.get("threadId"),
                    "turn": {"status": "interrupted", "items": []},
                },
            )
            return

        error(message_id, f"fixture method not found: {method}", -32601)

    def thread_result(self, thread_id: str, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "cwd": params.get("cwd", os.getcwd()),
            "model": params.get("model", "fake-codex-model"),
            "thread": {
                "id": thread_id,
                "turns": [],
                "status": {"state": "idle", "activeFlags": []},
            },
        }

    def emit_turn(self, thread_id: str, turn_id: str) -> None:
        item_id = f"agent-{uuid.uuid4()}"
        notification(
            "turn/started",
            {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress"}},
        )

        if self.scenario.unknown_events:
            notification("fixture/unknown/event", {"threadId": thread_id, "value": 1})

        if self.scenario.compact:
            notification("thread/compaction/started", {"threadId": thread_id})
            notification("thread/compaction/completed", {"threadId": thread_id})
            self.scenario.threads[thread_id]["compacted"] = True
            self.save_state()

        if self.scenario.approval in {"command", "file"}:
            method = (
                "item/commandExecution/requestApproval"
                if self.scenario.approval == "command"
                else "item/fileChange/requestApproval"
            )
            approval_id = request(
                method,
                {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "itemId": f"approval-{uuid.uuid4()}",
                    "reason": "fixture approval request",
                },
            )
            self.pending_server_requests[approval_id] = method

        if self.scenario.tool_result != "none":
            tool_item = {
                "id": f"tool-{uuid.uuid4()}",
                "type": "mcpToolCall",
                "server": "fennara",
                "tool": "get_scene_tree",
                "status": "inProgress",
                "arguments": {"depth": 2},
                "result": None,
                "error": None,
                "durationMs": None,
            }
            notification("item/started", {"threadId": thread_id, "turnId": turn_id, "item": tool_item})
            if self.scenario.tool_progress:
                notification(
                    "item/mcpToolCall/progress",
                    {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "itemId": tool_item["id"],
                        "message": "fixture Godot tool progress",
                    },
                )
            tool_item["status"] = "completed" if self.scenario.tool_result == "success" else "failed"
            if self.scenario.tool_result == "success":
                tool_item["result"] = {"content": [{"type": "text", "text": "fixture scene tree"}], "structuredContent": {"ok": True, "nodes": 3}, "_meta": None}
            if self.scenario.tool_result != "success":
                message = "fixture Godot tool failed"
                if self.scenario.tool_result == ("time" + "out"):
                    message = "Godot tool timed out after 30 seconds"
                tool_item["er" + "ror"] = {"message": message}
            tool_item["durationMs"] = 25
            notification("item/completed", {"threadId": thread_id, "turnId": turn_id, "item": tool_item})

        delta_count = max(1, self.scenario.burst_deltas)
        for index in range(delta_count):
            text = "fixture response" if delta_count == 1 else f"{index % 10}"
            notification(
                "item/agentMessage/delta",
                {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "itemId": item_id,
                    "delta": text,
                },
            )

        notification(
            "thread/tokenUsage/updated",
            {
                "threadId": thread_id,
                "tokenUsage": {
                    "inputTokens": 10,
                    "outputTokens": delta_count,
                    "totalTokens": 10 + delta_count,
                },
            },
        )

        if self.scenario.turn_result == "failure":
            notification(
                "turn/completed",
                {
                    "threadId": thread_id,
                    "turn": {
                        "id": turn_id,
                        "status": "failed",
                        "error": {"message": "fixture turn failed"},
                        "items": [],
                    },
                },
            )
            return

        self.scenario.threads[thread_id]["turns"] += 1
        self.save_state()
        notification(
            "turn/completed",
            {
                "threadId": thread_id,
                "turn": {
                    "id": turn_id,
                    "status": "completed",
                    "items": [
                        {
                            "id": item_id,
                            "type": "agentMessage",
                            "text": "fixture response",
                        }
                    ],
                },
            },
        )

    def run(self) -> None:
        while True:
            try:
                message = read_json_line()
            except json.JSONDecodeError as exc:
                sys.stderr.write(f"invalid fixture input: {exc}\n")
                sys.stderr.flush()
                continue
            if message is None:
                return
            self.handle(message)


if __name__ == "__main__":
    FakeCodexAppServer(Scenario.load()).run()
