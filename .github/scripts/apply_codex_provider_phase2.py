from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def path(relative: str) -> Path:
    return ROOT / relative


def replace_once(relative: str, old: str, new: str) -> None:
    target = path(relative)
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected 1 match, found {count}: {old[:120]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


PROVIDERS_MOD = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
replace_once(PROVIDERS_MOD, "mod context;\n", "mod context;\nmod control;\n")
replace_once(
    PROVIDERS_MOD,
    "pub(crate) use error::LlmError;\n",
    "pub(crate) use control::{\n    ProviderApprovalDecision, ProviderApprovalKind, ProviderApprovalRequest,\n    ProviderApprovalSender,\n};\npub(crate) use error::LlmError;\n",
)
replace_once(
    PROVIDERS_MOD,
    "    trace: Option<TraceRecorder>,\n    on_item: F,\n",
    "    trace: Option<TraceRecorder>,\n    approval_tx: Option<ProviderApprovalSender>,\n    on_item: F,\n",
)
replace_once(
    PROVIDERS_MOD,
    "            codex_app_server::stream_chat(&llm_request, {\n",
    "            codex_app_server::stream_chat(&llm_request, approval_tx, {\n",
)

CODEX = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
replace_once(
    CODEX,
    "    process::{Child, ChildStdin, ChildStdout, Command},\n    time::timeout,\n",
    "    process::{Child, ChildStdin, ChildStdout, Command},\n    sync::oneshot,\n    time::timeout,\n",
)
replace_once(
    CODEX,
    "    error::LlmError,\n",
    "    control::{\n        ProviderApprovalDecision, ProviderApprovalKind, ProviderApprovalRequest,\n        ProviderApprovalSender,\n    },\n    error::LlmError,\n",
)
replace_once(
    CODEX,
    "const LOGIN_TIMEOUT: Duration = Duration::from_secs(15 * 60);\n",
    "const LOGIN_TIMEOUT: Duration = Duration::from_secs(15 * 60);\nconst APPROVAL_TIMEOUT: Duration = Duration::from_secs(15 * 60);\n",
)
replace_once(
    CODEX,
    "pub(crate) async fn stream_chat<F, Fut>(\n    request: &LlmRequest,\n    mut on_event: F,\n",
    "pub(crate) async fn stream_chat<F, Fut>(\n    request: &LlmRequest,\n    approval_tx: Option<ProviderApprovalSender>,\n    mut on_event: F,\n",
)
replace_once(
    CODEX,
    "    let mut connection = CodexConnection::spawn().await?;\n    let account = connection\n",
    "    let mut connection = CodexConnection::spawn_with_approvals(approval_tx).await?;\n    let account = connection\n",
)
replace_once(
    CODEX,
    "    thread_params.insert(\n        \"sandbox\".to_string(),\n",
    "    thread_params.insert(\n        \"approvalsReviewer\".to_string(),\n        Value::String(\"user\".to_string()),\n    );\n    thread_params.insert(\n        \"sandbox\".to_string(),\n",
)
replace_once(
    CODEX,
    "struct CodexConnection {\n    child: Child,\n    stdin: ChildStdin,\n    lines: Lines<BufReader<ChildStdout>>,\n    next_id: u64,\n}\n\nimpl CodexConnection {\n    async fn spawn() -> Result<Self, LlmError> {\n",
    "struct CodexConnection {\n    child: Child,\n    stdin: ChildStdin,\n    lines: Lines<BufReader<ChildStdout>>,\n    next_id: u64,\n    approval_tx: Option<ProviderApprovalSender>,\n}\n\nimpl CodexConnection {\n    async fn spawn() -> Result<Self, LlmError> {\n        Self::spawn_with_approvals(None).await\n    }\n\n    async fn spawn_with_approvals(\n        approval_tx: Option<ProviderApprovalSender>,\n    ) -> Result<Self, LlmError> {\n",
)
replace_once(
    CODEX,
    "            lines: BufReader::new(stdout).lines(),\n            next_id: 1,\n",
    "            lines: BufReader::new(stdout).lines(),\n            next_id: 1,\n            approval_tx,\n",
)
replace_once(
    CODEX,
    "                    \"capabilities\": {}\n",
    "                    \"capabilities\": { \"experimentalApi\": true }\n",
)
replace_once(
    CODEX,
    '''        let result = match method {
            "item/commandExecution/requestApproval" | "item/fileChange/requestApproval" => {
                json!({ "decision": "decline" })
            }
            "tool/requestUserInput" => json!({ "answers": {} }),
            "mcpServer/elicitation/request" => json!({ "action": "decline" }),
            _ => json!({}),
        };
''',
    '''        let params = message.get("params").cloned().unwrap_or_else(|| json!({}));
        let result = match method {
            "item/commandExecution/requestApproval" | "item/fileChange/requestApproval" => {
                self.request_approval(method, params).await?
            }
            "tool/requestUserInput" => json!({ "answers": {} }),
            "mcpServer/elicitation/request" => json!({ "action": "decline" }),
            _ => json!({}),
        };
''',
)
replace_once(
    CODEX,
    "    async fn interrupt_turn(&mut self, thread_id: &str) {\n",
    '''    async fn request_approval(&mut self, method: &str, params: Value) -> Result<Value, LlmError> {
        let kind = match method {
            "item/commandExecution/requestApproval" => ProviderApprovalKind::CommandExecution,
            "item/fileChange/requestApproval" => ProviderApprovalKind::FileChange,
            _ => return Ok(json!({ "decision": "decline" })),
        };
        let Some(approval_tx) = self.approval_tx.clone() else {
            return Ok(json!({ "decision": "decline" }));
        };
        let (decision_tx, decision_rx) = oneshot::channel();
        let request = ProviderApprovalRequest {
            kind,
            item_id: approval_item_id(&params),
            thread_id: optional_string(&params, "threadId"),
            turn_id: optional_string(&params, "turnId"),
            summary: approval_summary(kind, &params),
            details: params,
            responder: decision_tx,
        };
        approval_tx.send(request).map_err(|_| LlmError::ProviderApi {
            provider: PROVIDER_NAME.to_string(),
            status: None,
            message: "Codex approval could not be delivered to the Fennara UI.".to_string(),
            retryable: false,
        })?;
        let decision = match timeout(APPROVAL_TIMEOUT, decision_rx).await {
            Ok(Ok(decision)) => decision,
            Ok(Err(_)) | Err(_) => ProviderApprovalDecision::Denied,
        };
        Ok(approval_result(decision))
    }

    async fn interrupt_turn(&mut self, thread_id: &str) {
''',
)
replace_once(
    CODEX,
    "fn rpc_error(error: &Value) -> LlmError {\n",
    '''fn optional_string(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn approval_item_id(params: &Value) -> String {
    optional_string(params, "itemId")
        .or_else(|| optional_string(params, "approvalId"))
        .unwrap_or_else(|| "codex-approval-item".to_string())
}

fn approval_summary(kind: ProviderApprovalKind, params: &Value) -> String {
    if let Some(reason) = optional_string(params, "reason") {
        return reason;
    }
    match kind {
        ProviderApprovalKind::CommandExecution => params
            .get("command")
            .map(display_json_value)
            .filter(|value| !value.is_empty())
            .map(|command| format!("Run command: {command}"))
            .unwrap_or_else(|| "Allow Codex to run this command?".to_string()),
        ProviderApprovalKind::FileChange => params
            .get("grantRoot")
            .and_then(Value::as_str)
            .map(|root| format!("Allow Codex to modify files under {root}?"))
            .unwrap_or_else(|| "Allow Codex to apply these file changes?".to_string()),
    }
}

fn display_json_value(value: &Value) -> String {
    match value {
        Value::String(value) => value.clone(),
        Value::Array(values) => values
            .iter()
            .map(display_json_value)
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>()
            .join(" "),
        Value::Null => String::new(),
        other => other.to_string(),
    }
}

fn approval_result(decision: ProviderApprovalDecision) -> Value {
    json!({
        "decision": match decision {
            ProviderApprovalDecision::Approved => "accept",
            ProviderApprovalDecision::Denied => "decline",
            ProviderApprovalDecision::Cancelled => "cancel",
        }
    })
}

fn rpc_error(error: &Value) -> LlmError {
''',
)
replace_once(
    CODEX,
    "    fn reads_chatgpt_account_status() {\n",
    '''    fn approval_results_use_codex_v2_decisions() {
        assert_eq!(approval_result(ProviderApprovalDecision::Approved), json!({ "decision": "accept" }));
        assert_eq!(approval_result(ProviderApprovalDecision::Denied), json!({ "decision": "decline" }));
        assert_eq!(approval_result(ProviderApprovalDecision::Cancelled), json!({ "decision": "cancel" }));
    }

    #[test]
    fn command_approval_summary_prefers_reason_then_command() {
        assert_eq!(
            approval_summary(
                ProviderApprovalKind::CommandExecution,
                &json!({ "command": ["cargo", "test"] })
            ),
            "Run command: cargo test"
        );
        assert_eq!(
            approval_summary(
                ProviderApprovalKind::CommandExecution,
                &json!({ "reason": "Run the test suite", "command": "cargo test" })
            ),
            "Run the test suite"
        );
    }

    #[test]
    fn reads_chatgpt_account_status() {
''',
)

PUBLISHER = "local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs"
replace_once(
    PUBLISHER,
    "use std::collections::{HashMap, HashSet};\n",
    "use std::{\n    collections::{HashMap, HashSet},\n    sync::atomic::Ordering,\n};\n",
)
replace_once(
    PUBLISHER,
    "use crate::runtime_daemon::state::AppState;\n",
    '''use crate::runtime_daemon::{
    permissions::{
        ApprovalMode, PendingToolApproval, ToolApprovalRequest, ToolApprovalReview,
        ToolApprovalStatus, ToolPermissionKind, approval_request_payload,
    },
    state::AppState,
};
''',
)
replace_once(
    PUBLISHER,
    "        ChatCompletion, ChatRequest, FinishReason, LlmError, ProviderSettings, StreamItem,\n        stream_chat,\n",
    "        ChatCompletion, ChatRequest, FinishReason, LlmError, ProviderApprovalDecision,\n        ProviderApprovalKind, ProviderApprovalRequest, ProviderSettings, StreamItem, stream_chat,\n",
)
replace_once(
    PUBLISHER,
    "    chat_id: &str,\n    project_path: Option<String>,\n",
    "    chat_id: &str,\n    session_id: String,\n    project_path: Option<String>,\n",
)
replace_once(
    PUBLISHER,
    "    let (item_tx, mut item_rx) = mpsc::unbounded_channel::<StreamItem>();\n",
    "    let (item_tx, mut item_rx) = mpsc::unbounded_channel::<StreamItem>();\n    let (approval_tx, mut approval_rx) = mpsc::unbounded_channel::<ProviderApprovalRequest>();\n",
)
replace_once(
    PUBLISHER,
    "            Some(trace_for_task),\n            |item| {\n",
    "            Some(trace_for_task),\n            Some(approval_tx),\n            |item| {\n",
)
replace_once(
    PUBLISHER,
    "    let mut done_rx = done_rx;\n    let completion = loop {\n",
    "    let mut done_rx = done_rx;\n    let mut approval_channel_open = true;\n    let completion = loop {\n",
)
replace_once(
    PUBLISHER,
    "        tokio::select! {\n            item = item_rx.recv() => {\n",
    '''        tokio::select! {
            approval = approval_rx.recv(), if approval_channel_open => {
                match approval {
                    Some(approval) => {
                        handle_provider_approval(
                            sender,
                            request_id.clone(),
                            state,
                            chat_id,
                            &session_id,
                            approval,
                            &trace,
                        )
                        .await?;
                    }
                    None => approval_channel_open = false,
                }
            }
            item = item_rx.recv() => {
''',
)
replace_once(
    PUBLISHER,
    "fn stream_item_has_assistant_output(item: &StreamItem) -> bool {\n",
    '''async fn handle_provider_approval<S>(
    sender: &mut S,
    request_id: Option<String>,
    state: &AppState,
    chat_id: &str,
    session_id: &str,
    approval: ProviderApprovalRequest,
    trace: &trace::TraceRecorder,
) -> Result<(), S::Error>
where
    S: Sink<Message> + Unpin,
    S::Error: std::fmt::Debug,
{
    let approval_id = format!(
        "provider-approval-{}",
        state.request_counter.fetch_add(1, Ordering::Relaxed) + 1
    );
    let tool_kind = match approval.kind {
        ProviderApprovalKind::CommandExecution => ToolPermissionKind::ExecutesProject,
        ProviderApprovalKind::FileChange => ToolPermissionKind::MutatesProject,
    };
    let (review_tx, review_rx) = oneshot::channel();
    let request = ToolApprovalRequest {
        id: approval_id.clone(),
        chat_id: chat_id.to_string(),
        session_id: session_id.to_string(),
        tool_call_id: approval.item_id.clone(),
        tool_name: approval.kind.tool_name().to_string(),
        tool_kind,
        tool_kind_label: tool_kind.label(),
        approval_mode: ApprovalMode::Ask,
        status: ToolApprovalStatus::PendingApproval,
        reason: approval.summary.clone(),
        summary: approval.summary.clone(),
    };
    state.pending_tool_approvals.write().await.insert(
        approval_id.clone(),
        PendingToolApproval {
            request: request.clone(),
            responder: review_tx,
        },
    );
    trace.with_approval(approval_id.clone()).event_status(
        "provider.approval.requested",
        "pending",
        json!({
            "kind": approval.kind.label(),
            "item_id": approval.item_id,
            "thread_id": approval.thread_id,
            "turn_id": approval.turn_id
        }),
    );
    send_provider_approval_update(
        sender,
        request_id.clone(),
        &approval,
        &request,
        ToolApprovalStatus::PendingApproval.as_str(),
    )
    .await?;

    let review = super::tool_loop::wait_for_tool_approval(
        state,
        chat_id,
        &approval_id,
        review_rx,
    )
    .await;
    let (provider_decision, status, ui_status) = match review {
        ToolApprovalReview::Approved => (
            ProviderApprovalDecision::Approved,
            ToolApprovalStatus::Approved,
            "approved",
        ),
        ToolApprovalReview::Denied => (
            ProviderApprovalDecision::Denied,
            ToolApprovalStatus::Denied,
            "denied",
        ),
        ToolApprovalReview::TimedOut => (
            ProviderApprovalDecision::Denied,
            ToolApprovalStatus::Denied,
            "timed_out",
        ),
        ToolApprovalReview::Cancelled => (
            ProviderApprovalDecision::Cancelled,
            ToolApprovalStatus::Cancelled,
            "cancelled",
        ),
    };
    let resolved = ToolApprovalRequest {
        status,
        ..request
    };
    trace.with_approval(approval_id).event_status(
        "provider.approval.resolved",
        ui_status,
        json!({ "kind": approval.kind.label() }),
    );
    send_provider_approval_update(sender, request_id, &approval, &resolved, ui_status).await?;
    let _ = approval.responder.send(provider_decision);
    Ok(())
}

async fn send_provider_approval_update<S>(
    sender: &mut S,
    request_id: Option<String>,
    approval: &ProviderApprovalRequest,
    request: &ToolApprovalRequest,
    status: &str,
) -> Result<(), S::Error>
where
    S: Sink<Message> + Unpin,
{
    send_json(
        sender,
        json!({
            "type": "chat_item_update",
            "request_id": request_id,
            "item": {
                "id": approval.item_id,
                "type": "function_call",
                "name": approval.kind.tool_name(),
                "arguments": approval.details.to_string(),
                "content": approval.summary,
                "status": status,
                "approval": approval_request_payload(request)
            }
        }),
    )
    .await
}

fn stream_item_has_assistant_output(item: &StreamItem) -> bool {
''',
)

RUNNER = "local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs"
replace_once(
    RUNNER,
    "            state,\n            &chat_id,\n            scope.project_path.clone(),\n",
    "            state,\n            &chat_id,\n            bound_project.session_id.clone(),\n            scope.project_path.clone(),\n",
)

TOOL_LOOP = "local/crates/fennara-daemon/src/runtime_daemon/chat/generation/tool_loop.rs"
replace_once(
    TOOL_LOOP,
    "async fn wait_for_tool_approval(\n    state: &AppState,\n    chat_id: &str,\n    approval_id: &str,\n    mut approval_rx: oneshot::Receiver<ToolApprovalReview>,\n",
    "pub(super) async fn wait_for_tool_approval(\n    state: &AppState,\n    chat_id: &str,\n    approval_id: &str,\n    mut approval_rx: oneshot::Receiver<ToolApprovalReview>,\n",
)

CHAT_MOD = "local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs"
replace_once(
    CHAT_MOD,
    "use futures_util::{Sink, SinkExt, StreamExt};\n",
    "use futures_util::{Sink, SinkExt, StreamExt};\n",
)
replace_once(
    CHAT_MOD,
    "use std::collections::BTreeMap;\nuse tokio::sync::broadcast;\n",
    '''use std::{
    collections::BTreeMap,
    fmt,
    pin::Pin,
    task::{Context as TaskContext, Poll},
};
use tokio::sync::{broadcast, mpsc};
''',
)
replace_once(
    CHAT_MOD,
    "#[derive(Clone)]\nstruct BoundChatProject {\n",
    '''#[derive(Clone)]
struct ChatOutbound {
    sender: mpsc::UnboundedSender<Message>,
}

#[derive(Debug)]
struct ChatOutboundError;

impl fmt::Display for ChatOutboundError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("chat websocket writer is unavailable")
    }
}

impl std::error::Error for ChatOutboundError {}

impl Sink<Message> for ChatOutbound {
    type Error = ChatOutboundError;

    fn poll_ready(
        self: Pin<&mut Self>,
        _context: &mut TaskContext<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        if self.get_mut().sender.is_closed() {
            Poll::Ready(Err(ChatOutboundError))
        } else {
            Poll::Ready(Ok(()))
        }
    }

    fn start_send(self: Pin<&mut Self>, item: Message) -> Result<(), Self::Error> {
        self.get_mut().sender.send(item).map_err(|_| ChatOutboundError)
    }

    fn poll_flush(
        self: Pin<&mut Self>,
        _context: &mut TaskContext<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }

    fn poll_close(
        self: Pin<&mut Self>,
        _context: &mut TaskContext<'_>,
    ) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }
}

#[derive(Clone)]
struct BoundChatProject {
''',
)
replace_once(
    CHAT_MOD,
    '''async fn handle_chat_socket(socket: WebSocket, state: AppState, bound_project: BoundChatProject) {
    let (mut sender, mut receiver) = socket.split();
    let mut active_chat_id: Option<String> = None;
    let mut context_receiver = state.chat_context_sender.subscribe();
''',
    '''async fn handle_chat_socket(socket: WebSocket, state: AppState, bound_project: BoundChatProject) {
    let (mut socket_sender, mut receiver) = socket.split();
    let (outbound_tx, mut outbound_rx) = mpsc::unbounded_channel::<Message>();
    let writer_task = tokio::spawn(async move {
        while let Some(message) = outbound_rx.recv().await {
            if socket_sender.send(message).await.is_err() {
                break;
            }
        }
    });
    let mut sender = ChatOutbound { sender: outbound_tx };
    let mut active_chat_id: Option<String> = None;
    let mut context_receiver = state.chat_context_sender.subscribe();
''',
)
replace_once(
    CHAT_MOD,
    '''                        if handle_request(
                            &mut sender,
                            &mut active_chat_id,
                            &state,
                            &bound_project,
                            request,
                        )
                        .await
                        .is_err()
                        {
                            break;
                        }
''',
    '''                        if request.request_type == "send_chat" {
                            let mut task_sender = sender.clone();
                            let mut task_active_chat_id = request
                                .chat_id
                                .clone()
                                .or_else(|| active_chat_id.clone());
                            let task_state = state.clone();
                            let task_project = bound_project.clone();
                            tokio::spawn(async move {
                                let _ = generation::runner::run_chat(
                                    &mut task_sender,
                                    &mut task_active_chat_id,
                                    &task_state,
                                    &task_project,
                                    request,
                                )
                                .await;
                            });
                            continue;
                        }
                        if handle_request(
                            &mut sender,
                            &mut active_chat_id,
                            &state,
                            &bound_project,
                            request,
                        )
                        .await
                        .is_err()
                        {
                            break;
                        }
''',
)
replace_once(
    CHAT_MOD,
    "    }\n}\n\nasync fn send_initial_state<S>(\n",
    "    }\n    writer_task.abort();\n}\n\nasync fn send_initial_state<S>(\n",
)

print("phase two migration applied")
