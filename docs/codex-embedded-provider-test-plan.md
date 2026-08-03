# Codex Embedded Provider Test Plan

Status: draft for maintainer review

This document defines the acceptance matrix for the complete Draft PR. Tests use a deterministic fake app-server by default. Real Codex and real OAuth tests are opt-in and never run with repository secrets.

## Test layers

### Unit tests

Pure tests cover:

- runtime version parsing and compatibility policy;
- platform runtime selection order;
- JSON-RPC request/response correlation;
- event normalization;
- approval-mode mapping;
- account status decoding;
- thread binding persistence;
- recoverable and non-recoverable error classification;
- process-exit diagnostic truncation;
- renderer delta coalescing.

### Fake app-server integration tests

A small test executable speaks JSON-RPC over stdio and can be scripted to:

- emit responses, notifications and approval requests;
- delay or omit messages;
- produce invalid JSON or incompatible shapes;
- compact a thread;
- exit normally or crash;
- record every request from Fennara;
- simulate multiple simultaneous processes.

These tests run in CI without network access or an OpenAI account.

### Daemon integration tests

Tests start the Fennara daemon with a temporary application directory, temporary SQLite database, fake Codex runtime and fake Godot bridge. They exercise the same WebSocket messages used by the embedded chat.

### Godot responsiveness tests

Automated tests verify that the daemon and renderer boundary remains asynchronous. A manual Windows acceptance profile measures editor responsiveness with a real Godot project.

### Real-runtime smoke tests

Opt-in tests run against the pinned Codex runtime on a developer machine. OAuth smoke tests require the developer to complete browser login and are not part of unattended CI.

## Runtime fixture requirements

The fake app-server supports these scenarios through command-line flags or a JSON script:

- authenticated and unauthenticated account states;
- login success, failure, cancellation and timeout;
- logout success and failure;
- thread start, resume, missing thread and corrupt thread;
- text, reasoning, usage, activity and warning events;
- compaction start/completion followed by another turn;
- command and file approval requests;
- MCP tool activity and completion;
- delayed events and high-frequency event bursts;
- crash before initialize, during a request and during streaming;
- malformed JSON and unknown events;
- configurable version and capability responses.

Every integration test asserts both the user-visible result and the exact protocol requests sent to the fake runtime.

## Authentication

| Case | Setup | Expected result |
| --- | --- | --- |
| Login success | account requires auth; login completes successfully | browser URL returned; status becomes connected; no credential is written to Fennara storage |
| Login failure | login completion reports failure | provider remains disconnected; error is visible and retryable |
| Login cancellation | cancel while login process is waiting | child process terminated; signing-in state cleared; no stale login lock |
| Login timeout | no completion event | timeout state; child terminated; retry allowed |
| Duplicate login | second request for same home while login is active | second request rejected as already in progress |
| Independent homes | login active for two different home keys | both may proceed independently within process limit |
| Logout success | connected account | Codex logout called; public status becomes disconnected |
| Logout failure | app-server returns error | existing public status retained with non-destructive error |
| Status probe unavailable | runtime missing or process cannot start | provider reports unavailable, daemon remains healthy |
| Secret persistence audit | complete login/logout sequence | SQLite/settings/log snapshots contain no token, cookie or auth payload |

## Streaming turns

| Case | Expected result |
| --- | --- |
| Basic text stream | ordered assistant deltas, final text and finish state |
| Reasoning stream | reasoning events rendered separately and in order |
| Usage updates | latest usage is stored and displayed without duplicate accounting |
| Duplicate item event | one visible item per provider item ID |
| Unknown event | ignored with diagnostic; turn continues |
| Warning event | non-fatal status shown; turn continues |
| Invalid JSON | generation fails cleanly; daemon remains available |
| App-server response timeout | stable timeout error; process cleaned up |
| User cancellation | `turn/interrupt` sent; partial text retained; final state cancelled |
| Cancellation during startup | child terminated; no thread binding written unless thread creation was confirmed |
| Cancellation during approval | approval resolved as cancelled/denied; turn interrupted |

## Thread start and resume

| Case | Expected result |
| --- | --- |
| First turn | `thread/start`; returned thread ID persisted before `turn/start` |
| Second turn | `thread/resume` using persisted ID; only new user input sent |
| Daemon restart | persisted binding loaded; thread resumed successfully |
| Runtime process restart | new process resumes same thread |
| Missing thread | binding marked broken; explicit new-thread action shown; no silent transcript replay |
| Non-recoverable resume failure | generation fails with original error and recovery guidance |
| Multiple chats | each Fennara chat uses its own Codex thread binding |
| Model change within chat | behavior follows documented compatibility policy; no accidental cross-chat binding |
| Archive chat | process stopped; binding retained or removed according to archive policy without affecting other chats |
| Revert action | disabled for Codex chat with clear explanation |

## Context compaction

| Case | Expected result |
| --- | --- |
| Compaction event rendering | status shown without creating a Fennara-generated summary |
| Turn after compaction | same Codex thread resumed; only new user input sent |
| Daemon restart after compaction | same thread resumes successfully |
| Fennara local summary threshold reached | Fennara summarization is bypassed for Codex provider |
| Context overflow from Codex | Codex error rendered; Fennara does not invoke its non-Codex overflow replay path |
| Compaction event burst | events coalesced without UI starvation |

## Approvals and sandbox permissions

### Ask mode

| Case | Expected result |
| --- | --- |
| Command approval allow | covered by `command_approval_accepts_through_provider_control_channel`; allow returned to exact RPC request |
| Command approval deny | covered by `command_approval_declines_through_provider_control_channel`; command not reported as successful |
| File approval allow | covered by `file_approval_accepts_through_provider_control_channel`; item continues |
| File approval deny | covered by `file_approval_declines_through_provider_control_channel`; item ends denied/failed |
| Approval timeout | deny/cancel returned; never implicitly allowed |
| Editor disconnect | pending approval cancelled/denied |
| Chat cancellation | pending approval cancelled/denied and turn interrupted |
| Two simultaneous approvals | decisions correlated to correct request IDs |

### Full access mode

| Case | Expected result |
| --- | --- |
| Turn start mapping | approval policy `never`, sandbox `dangerFullAccess` |
| Unexpected approval request | denied and compatibility warning recorded |
| Fennara-denied Godot tool | remains denied; Full access does not override unsupported tool policy |

## Godot MCP tools

Tests use a fake Godot bridge and the existing Fennara MCP route.

| Case | Expected result |
| --- | --- |
| Read-only tool success | result returned to Codex and rendered once |
| Mutating tool approved | approval flow completes, tool result returned |
| Mutating tool denied | denied result returned without execution |
| Tool failure | structured failure returned and rendered; turn may continue |
| Tool timeout | timeout returned; no stuck pending request |
| Tool cancellation | bridge request cancelled and Codex turn can stop |
| Godot editor disconnect | stable unavailable result; no daemon crash |
| Late tool result after cancellation | ignored or marked late; not attached to another turn |
| Duplicate MCP event | one visible activity item |
| Large tool output | bounded/truncated according to existing Fennara tool policy |

## Godot lag and responsiveness

### Automated assertions

- app-server reads and writes run on Tokio tasks, never on a GDScript callback;
- runtime discovery and installation are asynchronous;
- event batches crossing to the UI have a bounded item count and payload size;
- a fake app-server emitting at least 10,000 small deltas completes without unbounded queue growth;
- repeated MCP calls do not block the WebSocket receive loop;
- cancellation remains responsive during a high-frequency event stream;
- daemon CPU and memory remain bounded in the burst fixture.

### Manual Windows profile

Run a representative Godot project with editor frame timing visible.

Scenarios:

1. idle embedded Codex chat;
2. long text/reasoning stream;
3. repeated scene-tree and diagnostics tools;
4. repeated screenshots and runtime-session operations;
5. command/file approval prompts;
6. cancellation during each scenario;
7. two Godot editors with active Codex chats.

Record:

- editor frame-time baseline and test range;
- visible input latency while typing and manipulating the scene;
- daemon CPU and memory;
- process count;
- event queue high-water mark.

Acceptance: no sustained editor-frame stall attributable to the provider and no UI freeze requiring Godot restart. Any measurable regression must be documented and resolved before the PR is marked ready for review.

## Process lifecycle and crashes

| Case | Expected result |
| --- | --- |
| Initialize failure | process terminated; provider unavailable/error state |
| Crash before thread start | no binding written; generation fails cleanly |
| Crash after thread start | binding retained; next turn attempts resume |
| Crash during stream | partial content retained; generation failed; process cleaned up |
| Graceful completion | stdin closed and process reaped |
| Cancellation ignores interrupt | force-kill after timeout |
| Descendant process remains | platform process-tree termination removes it |
| Daemon restart | previous child processes are not assumed alive; bindings remain usable |
| Concurrency cap reached | later request queued or rejected with stable busy state; no over-spawn |
| Queued request cancelled | removed before process spawn |
| Multiple editors close | only their processes and approvals are cancelled |

## Runtime discovery, installation and compatibility

| Case | Expected result |
| --- | --- |
| Explicit valid override | selected without modification |
| Explicit missing override | clear configuration error; no fallback that hides the mistake |
| Managed pinned runtime | preferred over PATH runtime |
| Compatible PATH runtime | used when no managed runtime exists |
| Incompatible PATH runtime | provider unavailable; pinned install offered |
| Missing runtime | install action available on Windows |
| Corrupted executable | verification fails; runtime not activated |
| Missing required capability | incompatible state, not daemon crash |
| New optional protocol fields | tolerated |
| Missing required response field | stable incompatible-runtime error |
| Download interrupted | partial staging data never activated; retry succeeds |
| Digest mismatch | download rejected; previous runtime remains active |
| Extraction interrupted | staging directory cleaned on next startup |
| Activation interrupted | previous verified runtime remains active |
| Runtime update | new version verified then atomically activated |
| Unsupported OS | provider visible but unavailable with platform message |

## Existing-provider regression tests

`codex_registration_preserves_existing_provider_registry_and_routing` is the explicit registry and routing guard. The full workspace run remains the functional regression gate for request construction, model resolution, authentication and streaming. These tests run with Codex unavailable, available and intentionally failing.

- OpenAI-compatible providers build the same requests as before.
- Anthropic-compatible providers build the same requests as before.
- OpenRouter and custom providers retain API-key/header behavior.
- Ollama and LM Studio continue to use their existing endpoints and model discovery.
- Existing Fennara tool loop and context compaction remain active for non-Codex providers.
- Selecting or failing Codex does not modify saved API keys or custom-provider settings.
- Provider catalog serialization remains backward compatible.
- Existing chat databases migrate without losing chats or messages.
- A Codex migration failure leaves the previous database usable or fails startup without partial schema state.

## Multi-chat and multi-editor matrix

- two Codex chats in one editor;
- one Codex chat and one non-Codex chat in one editor;
- two Godot editors connected to one daemon with different projects;
- two editors using the same `CODEX_HOME`;
- two editors using different home keys;
- cancellation in one chat while another streams;
- approval in one editor while another editor closes;
- daemon restart with several persisted thread bindings.

Each case verifies isolation of thread IDs, request IDs, approval decisions, process handles, project cwd and Godot session IDs.

## CI gates

The Draft PR is not ready for maintainer review until these gates pass:

1. Rust formatting and lint checks.
2. Existing daemon test suite.
3. Fake app-server unit and integration suite.
4. Database migration tests from the previous schema.
5. JavaScript syntax/tests for new UI states.
6. Existing-provider regression suite.
7. Windows runtime-manager tests using local fixture archives, not live downloads.
8. A documented manual Windows OAuth and Godot responsiveness result before the Draft PR is promoted to ready-for-review. Use `docs/codex-windows-manual-acceptance.md`.

Real network downloads and real OAuth are never required for ordinary pull-request CI. The Draft PR may be opened while the Windows sheet is pending so architecture and implementation can be reviewed together; it must not be marked ready until real measurements are recorded.
