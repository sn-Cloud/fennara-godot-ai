# Codex embedded provider — Windows manual acceptance

Status: **pending execution before ready-for-review**

Automated CI covers lifecycle, event throughput, renderer coalescing, tool terminal states and provider regressions. This sheet supplies the remaining evidence from a real Windows x86_64 Godot editor; synthetic results must not be entered as real measurements.

## Environment

- Date:
- Windows version:
- CPU / RAM / GPU:
- Godot version:
- Representative project and revision:
- Fennara revision:
- Codex runtime version and source:
- `CODEX_HOME`: default / isolated

## Baseline

Record at least 60 seconds with the embedded Codex panel idle.

- Editor frame-time median / p95 / maximum:
- Visible input latency:
- Daemon CPU / memory:
- Codex process count:

## Scenarios

| Scenario | Measurements | Result |
| --- | --- | --- |
| Long text and reasoning stream | | Pending |
| Repeated read-only Godot tools | | Pending |
| Mutating tools with allow and deny | | Pending |
| Tool failure, timeout and cancellation | | Pending |
| Screenshot/runtime-session operations | | Pending |
| Two Godot editors with active Codex chats | | Pending |
| App-server crash and thread resume | | Pending |
| Daemon restart and thread resume | | Pending |

## Acceptance criteria

- No sustained editor-frame stall attributable to provider event rendering.
- No UI freeze requiring Godot restart.
- Tool progress remains cancellable and does not block editor input.
- Closing one editor or chat does not affect another editor's process, approval or thread.
- Child processes are reaped after completion, cancellation, crash and shutdown.
- Any measurable regression is recorded with reproduction steps and resolved or explicitly accepted before ready-for-review.

## Sign-off

- Tester:
- Overall result: Pending
- Blocking findings:
- Evidence attachments or logs:
