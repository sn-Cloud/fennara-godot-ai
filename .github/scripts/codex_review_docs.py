from pathlib import Path

root = Path(__file__).resolve().parents[2]

def replace_once(path, old, new):
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"anchor mismatch: {path}: {old[:60]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

architecture = root / "docs/codex-embedded-provider-architecture.md"
section = '''## T3 Code reference assessment

T3 Code was reviewed as a mature Codex app-server client rather than copied as a dependency. Its separation between app-server process management, provider/session coordination, WebSocket routing and browser event projection supports the same boundary used here: the renderer consumes structured events while a server-side component owns JSON-RPC and child-process lifecycle.

Fennara adopts the following lessons:

- keep app-server process ownership outside the renderer;
- correlate approvals, thread IDs and turn events at the daemon boundary;
- resume Codex-owned threads instead of rebuilding them from UI history;
- normalize provider events before rendering;
- isolate concurrent sessions and explicitly clean up child processes.

Fennara differs where its host requires it: the daemon is Rust rather than Node.js; Godot operations stay behind Fennara MCP and the Godot bridge; runtime pinning and installation are Fennara responsibilities; and turn-scoped processes preserve durable Codex thread bindings across process and daemon restarts. The official Codex app-server protocol remains authoritative if a reference implementation differs from the pinned protocol.

'''
replace_once(architecture, "## Platform boundaries\n", section + "## Platform boundaries\n")

ownership = root / "docs/codex-app-server-ownership.md"
replace_once(ownership,
    "| Approvals | `command_approval_accepts_through_provider_control_channel`, `file_approval_declines_through_provider_control_channel` |",
    "| Approvals | `command_approval_accepts_through_provider_control_channel`, `command_approval_declines_through_provider_control_channel`, `file_approval_accepts_through_provider_control_channel`, `file_approval_declines_through_provider_control_channel` |")
replace_once(ownership,
    "| Compatibility | `older_runtime_is_rejected_before_initialized_notification`, `newer_runtime_is_allowed_but_marked_unverified`, `missing_required_initialize_field_is_rejected` and the unit tests in `codex_runtime.rs` |",
    "| Existing-provider regression | `codex_registration_preserves_existing_provider_registry_and_routing` verifies that Codex remains a separate account-backed adapter and does not capture existing provider prefixes. The full Rust workspace remains the functional regression gate. |\n| Compatibility | `older_runtime_is_rejected_before_initialized_notification`, `newer_runtime_is_allowed_but_marked_unverified`, `missing_required_initialize_field_is_rejected` and the unit tests in `codex_runtime.rs` |")
replace_once(ownership,
    "These automated checks demonstrate that tool progress traffic does not synchronously block the provider stream or force one UI render per event. They are not a full Godot frame-time benchmark.",
    "These automated checks demonstrate that tool progress traffic does not synchronously block the provider stream or force one UI render per event. They are not a full Godot frame-time benchmark. The Draft PR therefore keeps the Windows editor profile as an explicit manual acceptance gate rather than presenting synthetic throughput as real editor frame-time proof.")

test_plan = root / "docs/codex-embedded-provider-test-plan.md"
replace_once(test_plan,
    "| Command approval allow | existing approval UI shown; allow returned to exact RPC request |\n| Command approval deny | deny returned; command not reported as successful |\n| File approval allow | allow returned and item continues |\n| File approval deny | deny returned and item ends denied/failed |",
    "| Command approval allow | covered by `command_approval_accepts_through_provider_control_channel`; allow returned to exact RPC request |\n| Command approval deny | covered by `command_approval_declines_through_provider_control_channel`; command not reported as successful |\n| File approval allow | covered by `file_approval_accepts_through_provider_control_channel`; item continues |\n| File approval deny | covered by `file_approval_declines_through_provider_control_channel`; item ends denied/failed |")
replace_once(test_plan,
    "## Existing-provider regression tests\n\nThese tests run with Codex unavailable, available and intentionally failing.\n",
    "## Existing-provider regression tests\n\n`codex_registration_preserves_existing_provider_registry_and_routing` is the explicit registry and routing guard. The full workspace run remains the functional regression gate for request construction, model resolution, authentication and streaming. These tests run with Codex unavailable, available and intentionally failing.\n")
replace_once(test_plan,
    "8. A documented manual Windows OAuth and Godot responsiveness result.\n\nReal network downloads and real OAuth are never required for ordinary pull-request CI.",
    "8. A documented manual Windows OAuth and Godot responsiveness result before the Draft PR is promoted to ready-for-review. Use `docs/codex-windows-manual-acceptance.md`.\n\nReal network downloads and real OAuth are never required for ordinary pull-request CI. The Draft PR may be opened while the Windows sheet is pending so architecture and implementation can be reviewed together; it must not be marked ready until real measurements are recorded.")

(root / "docs/codex-windows-manual-acceptance.md").write_text('''# Codex embedded provider — Windows manual acceptance

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
''', encoding="utf-8")
