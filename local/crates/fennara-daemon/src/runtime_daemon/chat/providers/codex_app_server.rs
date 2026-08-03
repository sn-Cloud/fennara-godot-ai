use std::{
    collections::{HashMap, VecDeque},
    process::Stdio,
    sync::{Arc, Mutex, OnceLock},
    time::Duration,
};

use serde::Serialize;
use serde_json::{Map, Value, json};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Lines},
    process::{Child, ChildStderr, ChildStdin, ChildStdout},
    sync::{Mutex as AsyncMutex, oneshot},
    task::JoinHandle,
    time::timeout,
};

use super::super::store;
use super::{
    codex_mcp,
    codex_runtime::{self, CodexRuntimeMetadata},
    control::{
        ProviderApprovalDecision, ProviderApprovalKind, ProviderApprovalRequest,
        ProviderApprovalSender,
    },
    error::LlmError,
    request::LlmRequest,
    stream::{FinishReason, StreamEvent, Usage},
};

const PROVIDER_NAME: &str = "Codex";
const INIT_TIMEOUT: Duration = Duration::from_secs(20);
const RPC_TIMEOUT: Duration = Duration::from_secs(30);
const LOGIN_TIMEOUT: Duration = Duration::from_secs(15 * 60);
const APPROVAL_TIMEOUT: Duration = Duration::from_secs(15 * 60);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(3);
const STDERR_LINE_LIMIT: usize = 40;
const MCP_ARGUMENT_LIMIT: usize = 8 * 1024;
const MCP_CONTENT_LIMIT: usize = 32 * 1024;

#[derive(Clone, Debug, Default, Serialize)]
pub(crate) struct CodexAccountStatus {
    pub(crate) installed: bool,
    pub(crate) connected: bool,
    pub(crate) signing_in: bool,
    pub(crate) auth_mode: Option<String>,
    pub(crate) plan_type: Option<String>,
    pub(crate) email: Option<String>,
    pub(crate) error: Option<String>,
    pub(crate) runtime: Option<CodexRuntimeMetadata>,
    pub(crate) mcp: codex_mcp::CodexMcpStatus,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct CodexLoginStart {
    pub(crate) login_id: String,
    pub(crate) auth_url: String,
}

static ACCOUNT_STATUS: OnceLock<Mutex<CodexAccountStatus>> = OnceLock::new();
static ACTIVE_LOGIN: OnceLock<Mutex<Option<ActiveCodexLogin>>> = OnceLock::new();

struct ActiveCodexLogin {
    login_id: String,
    cancel: oneshot::Sender<()>,
}

#[derive(Clone, Debug)]
struct McpItemState {
    name: String,
    arguments: String,
}

fn account_status_cache() -> &'static Mutex<CodexAccountStatus> {
    ACCOUNT_STATUS.get_or_init(|| Mutex::new(CodexAccountStatus::default()))
}

fn active_login() -> &'static Mutex<Option<ActiveCodexLogin>> {
    ACTIVE_LOGIN.get_or_init(|| Mutex::new(None))
}

pub(crate) fn cached_account_status() -> CodexAccountStatus {
    account_status_cache()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clone()
}

fn store_account_status(status: CodexAccountStatus) {
    *account_status_cache()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner()) = status;
}

pub(crate) fn is_installed() -> bool {
    codex_runtime::resolve_runtime().is_ok()
}

pub(crate) async fn account_status() -> Result<CodexAccountStatus, String> {
    let mut connection = match CodexConnection::spawn().await {
        Ok(connection) => connection,
        Err(error) => {
            let status = CodexAccountStatus {
                installed: false,
                error: Some(error.user_message()),
                ..CodexAccountStatus::default()
            };
            store_account_status(status.clone());
            return Ok(status);
        }
    };
    let result = connection
        .request(
            "account/read",
            json!({ "refreshToken": false }),
            RPC_TIMEOUT,
        )
        .await
        .map_err(|error| error.user_message())?;
    let status = attach_runtime(
        account_status_from_result(&result, true, false, None),
        connection.runtime.as_ref(),
    );
    store_account_status(status.clone());
    connection.shutdown().await;
    Ok(status)
}

pub(crate) async fn start_login() -> Result<CodexLoginStart, String> {
    if active_login()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .is_some()
    {
        return Err("A Codex ChatGPT login is already in progress.".to_string());
    }

    let mut connection = CodexConnection::spawn()
        .await
        .map_err(|error| error.user_message())?;
    let result = connection
        .request(
            "account/login/start",
            json!({
                "type": "chatgpt",
                "useHostedLoginSuccessPage": true,
                "appBrand": "codex"
            }),
            RPC_TIMEOUT,
        )
        .await
        .map_err(|error| error.user_message())?;
    let login_id = result
        .get("loginId")
        .and_then(Value::as_str)
        .ok_or_else(|| "Codex did not return a login id.".to_string())?
        .to_string();
    let auth_url = result
        .get("authUrl")
        .and_then(Value::as_str)
        .ok_or_else(|| "Codex did not return a browser login URL.".to_string())?
        .to_string();

    let previous = cached_account_status();
    let runtime = connection.runtime.clone();
    let (cancel_tx, cancel_rx) = oneshot::channel();
    let login_reserved = {
        let mut active = active_login()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if active.is_none() {
            *active = Some(ActiveCodexLogin {
                login_id: login_id.clone(),
                cancel: cancel_tx,
            });
            true
        } else {
            false
        }
    };
    if !login_reserved {
        connection.shutdown().await;
        return Err("A Codex ChatGPT login is already in progress.".to_string());
    }
    store_account_status(CodexAccountStatus {
        installed: true,
        connected: previous.connected,
        signing_in: true,
        auth_mode: previous.auth_mode,
        plan_type: previous.plan_type,
        email: previous.email,
        error: None,
        runtime: runtime.clone(),
        mcp: codex_mcp::inspect(),
    });

    let task_login_id = login_id.clone();
    tokio::spawn(async move {
        let status = tokio::select! {
            outcome = timeout(LOGIN_TIMEOUT, wait_for_login_completion(&mut connection)) => {
                match outcome {
                    Ok(Ok(status)) => status,
                    Ok(Err(error)) => CodexAccountStatus {
                        installed: true,
                        error: Some(error.user_message()),
                        ..CodexAccountStatus::default()
                    },
                    Err(_) => CodexAccountStatus {
                        installed: true,
                        error: Some("Codex ChatGPT login timed out.".to_string()),
                        ..CodexAccountStatus::default()
                    },
                }
            }
            _ = cancel_rx => {
                let _ = connection
                    .request(
                        "account/login/cancel",
                        json!({ "loginId": task_login_id }),
                        RPC_TIMEOUT,
                    )
                    .await;
                CodexAccountStatus {
                    installed: true,
                    error: Some("Codex ChatGPT login cancelled.".to_string()),
                    ..CodexAccountStatus::default()
                }
            }
        };
        {
            let mut active = active_login()
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            if active
                .as_ref()
                .is_some_and(|active| active.login_id == task_login_id)
            {
                *active = None;
            }
        }
        store_account_status(attach_runtime(status, runtime.as_ref()));
        connection.shutdown().await;
    });

    Ok(CodexLoginStart { login_id, auth_url })
}

pub(crate) fn cancel_login() -> Result<CodexAccountStatus, String> {
    let active = active_login()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .take()
        .ok_or_else(|| "No Codex ChatGPT login is in progress.".to_string())?;
    let _ = active.cancel.send(());
    let mut status = cached_account_status();
    status.signing_in = false;
    status.error = Some("Codex ChatGPT login cancelled.".to_string());
    store_account_status(status.clone());
    Ok(status)
}

pub(crate) async fn logout() -> Result<CodexAccountStatus, String> {
    let mut connection = CodexConnection::spawn()
        .await
        .map_err(|error| error.user_message())?;
    connection
        .request("account/logout", json!({}), RPC_TIMEOUT)
        .await
        .map_err(|error| error.user_message())?;
    connection.shutdown().await;
    let status = CodexAccountStatus {
        installed: true,
        runtime: connection.runtime.clone(),
        mcp: codex_mcp::inspect(),
        ..CodexAccountStatus::default()
    };
    store_account_status(status.clone());
    Ok(status)
}

pub(crate) async fn stream_chat<F, Fut>(
    request: &LlmRequest,
    approval_tx: Option<ProviderApprovalSender>,
    mut on_event: F,
) -> Result<(), LlmError>
where
    F: FnMut(StreamEvent) -> Fut + Send,
    Fut: std::future::Future<Output = Result<bool, LlmError>> + Send,
{
    let mut connection = CodexConnection::spawn_with_approvals(approval_tx).await?;
    let account = connection
        .request(
            "account/read",
            json!({ "refreshToken": false }),
            RPC_TIMEOUT,
        )
        .await?;
    let account_status = attach_runtime(
        account_status_from_result(&account, true, false, None),
        connection.runtime.as_ref(),
    );
    store_account_status(account_status.clone());
    if !account_status.connected {
        connection.shutdown().await;
        return Err(LlmError::Auth {
            provider: "codex".to_string(),
            message: "Sign in to Codex with your ChatGPT account first.".to_string(),
        });
    }

    let chat_id = request.chat_id.as_deref().ok_or_else(|| LlmError::Config {
        message: "Codex requests require a Fennara chat id.".to_string(),
    })?;
    let existing_binding = store::provider_session_binding(chat_id, "codex")
        .map_err(|message| LlmError::Config { message })?;
    let current_codex_home_key = codex_home_key(connection.runtime.as_ref());
    let current_runtime_version = connection
        .runtime
        .as_ref()
        .and_then(|runtime| runtime.version.clone());
    if let Some(binding) = existing_binding.as_ref() {
        if !codex_home_keys_match(&binding.codex_home_key, &current_codex_home_key) {
            connection.shutdown().await;
            return Err(LlmError::ProviderApi {
                provider: PROVIDER_NAME.to_string(),
                status: None,
                message: "The Codex thread for this Fennara chat belongs to a different CODEX_HOME. Restore the original FENNARA_CODEX_HOME/CODEX_HOME or start a new Codex thread explicitly; Fennara will not resume it against another Codex home."
                    .to_string(),
                retryable: false,
            });
        }
    }

    let mut thread_params = Map::new();
    if let Some(cwd) = request
        .cwd
        .as_deref()
        .filter(|value| !value.trim().is_empty())
    {
        thread_params.insert("cwd".to_string(), Value::String(cwd.to_string()));
    }
    thread_params.insert(
        "approvalPolicy".to_string(),
        Value::String(
            if request.approval_mode == "full_access" {
                "never"
            } else {
                "on-request"
            }
            .to_string(),
        ),
    );
    thread_params.insert(
        "approvalsReviewer".to_string(),
        Value::String("user".to_string()),
    );
    thread_params.insert(
        "sandbox".to_string(),
        Value::String(
            if request.approval_mode == "full_access" {
                "dangerFullAccess"
            } else {
                "workspaceWrite"
            }
            .to_string(),
        ),
    );
    thread_params.insert(
        "serviceName".to_string(),
        Value::String("fennara_godot_ai".to_string()),
    );
    let model_id = request.model.model.adapter_model_id.trim();
    if !model_id.is_empty() && model_id != super::codex::DEFAULT_MODEL_ID {
        thread_params.insert("model".to_string(), Value::String(model_id.to_string()));
    }

    let resumed = existing_binding.is_some();
    let thread_result = if let Some(binding) = existing_binding.as_ref() {
        let mut resume_params = thread_params.clone();
        resume_params.insert(
            "threadId".to_string(),
            Value::String(binding.provider_thread_id.clone()),
        );
        match connection
            .request("thread/resume", Value::Object(resume_params), RPC_TIMEOUT)
            .await
        {
            Ok(result) => result,
            Err(error) if is_missing_thread_error(&error) => {
                let _ = store::mark_provider_session_broken(chat_id, "codex");
                connection.shutdown().await;
                return Err(LlmError::ProviderApi {
                    provider: PROVIDER_NAME.to_string(),
                    status: None,
                    message: "The Codex thread for this Fennara chat is no longer available. Start a new Codex thread explicitly; Fennara will not silently rebuild it from local history.".to_string(),
                    retryable: false,
                });
            }
            Err(error) => return Err(error),
        }
    } else {
        connection
            .request("thread/start", Value::Object(thread_params), RPC_TIMEOUT)
            .await?
    };
    let thread_id = thread_result
        .pointer("/thread/id")
        .and_then(Value::as_str)
        .or_else(|| {
            existing_binding
                .as_ref()
                .map(|binding| binding.provider_thread_id.as_str())
        })
        .ok_or_else(|| LlmError::InvalidProviderOutput {
            provider: PROVIDER_NAME.to_string(),
            message: "Codex did not return a thread id.".to_string(),
            raw: Some(thread_result.to_string()),
        })?
        .to_string();
    store::upsert_provider_session_binding(
        chat_id,
        "codex",
        &thread_id,
        &current_codex_home_key,
        current_runtime_version.as_deref(),
    )
    .map_err(|message| LlmError::Config { message })?;

    let prompt = if resumed {
        latest_user_prompt(&request.messages)
    } else {
        prompt_from_messages(&request.messages)
    };
    let turn_params = json!({
        "threadId": thread_id.clone(),
        "input": [{ "type": "text", "text": prompt }],
        "effort": request.model.request.generation.reasoning_effort.clone(),
    });
    connection
        .request("turn/start", turn_params, RPC_TIMEOUT)
        .await?;

    let mut emitted_text = false;
    let mut latest_usage: Option<Usage> = None;
    let mut mcp_items: HashMap<String, McpItemState> = HashMap::new();
    loop {
        let message = connection.read_message().await?;
        if connection.respond_to_server_request(&message).await? {
            continue;
        }
        let Some(method) = message.get("method").and_then(Value::as_str) else {
            continue;
        };
        let params = message.get("params").cloned().unwrap_or_else(|| json!({}));
        match method {
            "item/agentMessage/delta" => {
                if let Some(delta) = params.get("delta").and_then(Value::as_str) {
                    emitted_text = true;
                    if !on_event(StreamEvent::TextDelta {
                        id: params
                            .get("itemId")
                            .and_then(Value::as_str)
                            .unwrap_or("codex-agent")
                            .to_string(),
                        text: delta.to_string(),
                    })
                    .await?
                    {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/reasoning/summaryTextDelta" | "item/reasoning/textDelta" => {
                if let Some(delta) = params.get("delta").and_then(Value::as_str) {
                    if !on_event(StreamEvent::ReasoningDelta {
                        id: params
                            .get("itemId")
                            .and_then(Value::as_str)
                            .unwrap_or("codex-reasoning")
                            .to_string(),
                        text: delta.to_string(),
                    })
                    .await?
                    {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/started" => {
                let event =
                    mcp_lifecycle_event(params.get("item"), false, &mut mcp_items).or_else(|| {
                        item_status_message(params.get("item"), false)
                            .map(|message| StreamEvent::Status { message })
                    });
                if let Some(event) = event {
                    if !on_event(event).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/completed" => {
                let event =
                    mcp_lifecycle_event(params.get("item"), true, &mut mcp_items).or_else(|| {
                        item_status_message(params.get("item"), true)
                            .map(|message| StreamEvent::Status { message })
                    });
                if let Some(event) = event {
                    if !on_event(event).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/mcpToolCall/progress" => {
                if let Some(event) = mcp_progress_event(&params, &mcp_items) {
                    if !on_event(event).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "turn/plan/updated" => {
                if let Some(status) = plan_status_message(&params) {
                    if !on_event(StreamEvent::Status { message: status }).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "thread/tokenUsage/updated" => {
                let usage_value = params
                    .get("tokenUsage")
                    .or_else(|| params.get("usage"))
                    .cloned()
                    .unwrap_or(params);
                let usage = Usage::from_provider_value(&usage_value);
                latest_usage = Some(usage.clone());
                if !on_event(StreamEvent::Usage(usage)).await? {
                    connection.interrupt_turn(&thread_id).await;
                    connection.shutdown().await;
                    return Ok(());
                }
            }
            "turn/completed" => {
                let turn = params.get("turn").unwrap_or(&params);
                let status = turn
                    .get("status")
                    .and_then(Value::as_str)
                    .unwrap_or("completed");
                if status == "failed" {
                    let message = turn
                        .pointer("/error/message")
                        .and_then(Value::as_str)
                        .unwrap_or("Codex turn failed.")
                        .to_string();
                    connection.shutdown().await;
                    return Err(LlmError::ProviderApi {
                        provider: PROVIDER_NAME.to_string(),
                        status: None,
                        message,
                        retryable: false,
                    });
                }
                if !emitted_text {
                    if let Some(text) = final_agent_text(turn) {
                        on_event(StreamEvent::TextDelta {
                            id: "codex-agent-final".to_string(),
                            text,
                        })
                        .await?;
                    }
                }
                let reason = if status == "interrupted" {
                    FinishReason::Cancelled
                } else {
                    FinishReason::Stop
                };
                on_event(StreamEvent::Finish {
                    reason,
                    usage: latest_usage,
                })
                .await?;
                connection.shutdown().await;
                return Ok(());
            }
            "warning" | "configWarning" => {
                if let Some(message) = params
                    .get("message")
                    .or_else(|| params.get("summary"))
                    .and_then(Value::as_str)
                {
                    on_event(StreamEvent::Status {
                        message: message.to_string(),
                    })
                    .await?;
                }
            }
            _ => {}
        }
    }
}

async fn wait_for_login_completion(
    connection: &mut CodexConnection,
) -> Result<CodexAccountStatus, LlmError> {
    let mut successful = false;
    let mut last_status = CodexAccountStatus {
        installed: true,
        signing_in: true,
        ..CodexAccountStatus::default()
    };
    loop {
        let message = connection.read_message().await?;
        if connection.respond_to_server_request(&message).await? {
            continue;
        }
        match message.get("method").and_then(Value::as_str) {
            Some("account/login/completed") => {
                let params = message.get("params").cloned().unwrap_or_else(|| json!({}));
                successful = params
                    .get("success")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                if !successful {
                    return Ok(CodexAccountStatus {
                        installed: true,
                        error: Some(
                            params
                                .get("error")
                                .and_then(Value::as_str)
                                .unwrap_or("Codex ChatGPT login failed.")
                                .to_string(),
                        ),
                        ..CodexAccountStatus::default()
                    });
                }
                last_status.connected = true;
                last_status.signing_in = false;
                last_status.auth_mode = Some("chatgpt".to_string());
            }
            Some("account/updated") => {
                let params = message.get("params").cloned().unwrap_or_else(|| json!({}));
                let auth_mode = params
                    .get("authMode")
                    .and_then(Value::as_str)
                    .map(ToString::to_string);
                last_status = CodexAccountStatus {
                    installed: true,
                    connected: auth_mode.is_some(),
                    signing_in: false,
                    auth_mode,
                    plan_type: params
                        .get("planType")
                        .and_then(Value::as_str)
                        .map(ToString::to_string),
                    email: None,
                    error: None,
                    runtime: None,
                    mcp: codex_mcp::inspect(),
                };
                if successful || last_status.connected {
                    return Ok(last_status);
                }
            }
            _ => {
                if successful {
                    return Ok(last_status);
                }
            }
        }
    }
}

fn account_status_from_result(
    result: &Value,
    installed: bool,
    signing_in: bool,
    error: Option<String>,
) -> CodexAccountStatus {
    let account = result.get("account").filter(|value| !value.is_null());
    let requires_auth = result
        .get("requiresOpenaiAuth")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    CodexAccountStatus {
        installed,
        connected: account.is_some() || !requires_auth,
        signing_in,
        auth_mode: account
            .and_then(|value| value.get("type"))
            .and_then(Value::as_str)
            .map(ToString::to_string),
        plan_type: account
            .and_then(|value| value.get("planType"))
            .and_then(Value::as_str)
            .map(ToString::to_string),
        email: account
            .and_then(|value| value.get("email"))
            .and_then(Value::as_str)
            .map(ToString::to_string),
        error,
        runtime: None,
        mcp: codex_mcp::inspect(),
    }
}

fn attach_runtime(
    mut status: CodexAccountStatus,
    runtime: Option<&CodexRuntimeMetadata>,
) -> CodexAccountStatus {
    status.runtime = runtime.cloned();
    status.mcp = codex_mcp::inspect();
    status
}

fn normalize_codex_home_key(value: &str) -> String {
    let normalized = value.trim().replace('\\', "/");
    let normalized = if normalized.len() > 1 && !normalized.ends_with(":/") {
        normalized.trim_end_matches('/').to_string()
    } else {
        normalized
    };
    if cfg!(windows) {
        normalized.to_ascii_lowercase()
    } else {
        normalized
    }
}

fn codex_home_key(runtime: Option<&CodexRuntimeMetadata>) -> String {
    runtime
        .and_then(|runtime| runtime.codex_home.as_deref())
        .map(normalize_codex_home_key)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "default".to_string())
}

fn codex_home_keys_match(bound: &str, current: &str) -> bool {
    normalize_codex_home_key(bound) == normalize_codex_home_key(current)
}

fn latest_user_prompt(messages: &[Value]) -> String {
    messages
        .iter()
        .rev()
        .find(|message| message.get("role").and_then(Value::as_str) == Some("user"))
        .map(|message| message_content(message.get("content")))
        .filter(|content| !content.trim().is_empty())
        .unwrap_or_default()
}

fn is_missing_thread_error(error: &LlmError) -> bool {
    let message = error.user_message().to_ascii_lowercase();
    [
        "thread not found",
        "thread does not exist",
        "thread no longer exists",
        "no thread found",
        "unknown thread",
    ]
    .iter()
    .any(|pattern| message.contains(pattern))
}

fn prompt_from_messages(messages: &[Value]) -> String {
    let mut output = String::from(
        "You are operating through Fennara inside a Godot project. Use the configured Fennara MCP server for Godot-aware editor and runtime operations when available. Respect the current project boundary.\n\nConversation context:\n",
    );
    for message in messages {
        let role = message
            .get("role")
            .and_then(Value::as_str)
            .unwrap_or("message");
        let content = message_content(message.get("content"));
        if content.trim().is_empty() {
            continue;
        }
        output.push_str("\n[");
        output.push_str(role);
        output.push_str("]\n");
        output.push_str(&content);
        output.push('\n');
    }
    output
}

fn message_content(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Array(parts)) => parts
            .iter()
            .filter_map(|part| {
                part.get("text")
                    .and_then(Value::as_str)
                    .or_else(|| part.get("content").and_then(Value::as_str))
            })
            .collect::<Vec<_>>()
            .join("\n"),
        Some(other) => other.to_string(),
        None => String::new(),
    }
}

fn mcp_lifecycle_event(
    item: Option<&Value>,
    completed: bool,
    states: &mut HashMap<String, McpItemState>,
) -> Option<StreamEvent> {
    let item = item?;
    if item.get("type").and_then(Value::as_str) != Some("mcpToolCall") {
        return None;
    }
    let id = clean_json_string(item.get("id"))?;
    let previous = states.get(&id).cloned();
    let server = clean_json_string(item.get("server"));
    let tool = clean_json_string(item.get("tool")).or_else(|| clean_json_string(item.get("name")));
    let name = match (server, tool) {
        (Some(server), Some(tool)) => format!("{server} · {tool}"),
        (_, Some(tool)) => tool,
        _ => previous
            .as_ref()
            .map(|state| state.name.clone())
            .unwrap_or_else(|| "MCP tool".to_string()),
    };
    let arguments = item
        .get("arguments")
        .map(format_json)
        .or_else(|| previous.as_ref().map(|state| state.arguments.clone()))
        .unwrap_or_else(|| "{}".to_string());
    let arguments = truncate_text(&arguments, MCP_ARGUMENT_LIMIT);
    let status = mcp_status(item, completed);
    let content = truncate_text(&mcp_content(item, &status), MCP_CONTENT_LIMIT);
    if mcp_status_is_terminal(&status) {
        states.remove(&id);
    } else {
        states.insert(
            id.clone(),
            McpItemState {
                name: name.clone(),
                arguments: arguments.clone(),
            },
        );
    }
    Some(StreamEvent::ExternalToolActivity {
        id,
        name,
        arguments,
        content,
        status,
    })
}

fn mcp_progress_event(
    params: &Value,
    states: &HashMap<String, McpItemState>,
) -> Option<StreamEvent> {
    let id = clean_json_string(params.get("itemId"))?;
    let state = states.get(&id)?;
    let content = clean_json_string(params.get("message"))?;
    Some(StreamEvent::ExternalToolActivity {
        id,
        name: state.name.clone(),
        arguments: state.arguments.clone(),
        content: truncate_text(&content, MCP_CONTENT_LIMIT),
        status: "running".to_string(),
    })
}

fn mcp_status(item: &Value, completed: bool) -> String {
    match item
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or_default()
    {
        "inProgress" => "running".to_string(),
        "completed" => "completed".to_string(),
        "failed" => mcp_failure_status(item),
        _ if completed => "completed".to_string(),
        _ => "running".to_string(),
    }
}

fn mcp_failure_status(item: &Value) -> String {
    let message = item
        .pointer("/error/message")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    if message.contains("timed out") || message.contains("timeout") {
        "timed_out".to_string()
    } else if message.contains("cancel") || message.contains("interrupt") {
        "cancelled".to_string()
    } else {
        "failed".to_string()
    }
}

fn mcp_status_is_terminal(status: &str) -> bool {
    matches!(status, "completed" | "failed" | "timed_out" | "cancelled")
}

fn mcp_content(item: &Value, status: &str) -> String {
    if let Some(message) = item.pointer("/error/message").and_then(Value::as_str) {
        return message.to_string();
    }
    let Some(result) = item.get("result").filter(|value| !value.is_null()) else {
        return if status == "running" {
            "Running through Codex app-server and the configured Fennara MCP server.".to_string()
        } else {
            String::new()
        };
    };
    if let Some(value) = result
        .get("structuredContent")
        .filter(|value| !value.is_null())
    {
        return format!(
            "```json
{}
```",
            format_json(value)
        );
    }
    result
        .get("content")
        .and_then(Value::as_array)
        .map(|parts| {
            parts
                .iter()
                .filter_map(mcp_content_part)
                .collect::<Vec<_>>()
                .join(
                    "

",
                )
        })
        .unwrap_or_else(|| format_json(result))
}

fn mcp_content_part(part: &Value) -> Option<String> {
    if let Some(text) = part.get("text").and_then(Value::as_str) {
        return Some(text.to_string());
    }
    if part.get("type").and_then(Value::as_str) == Some("image") {
        let mime = part
            .get("mimeType")
            .or_else(|| part.get("mime_type"))
            .and_then(Value::as_str)
            .unwrap_or("image");
        return Some(format!("Image result ({mime})"));
    }
    (!part.is_null()).then(|| {
        format!(
            "```json
{}
```",
            format_json(part)
        )
    })
}

fn clean_json_string(value: Option<&Value>) -> Option<String> {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn format_json(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        _ => serde_json::to_string_pretty(value).unwrap_or_else(|_| value.to_string()),
    }
}

fn truncate_text(value: &str, limit: usize) -> String {
    if value.chars().count() <= limit {
        return value.to_string();
    }
    let mut output = value.chars().take(limit).collect::<String>();
    output.push_str(
        "

[Output truncated by Fennara]",
    );
    output
}

fn item_status_message(item: Option<&Value>, completed: bool) -> Option<String> {
    let item = item?;
    let item_type = item.get("type").and_then(Value::as_str)?;
    let suffix = if completed { "completed" } else { "running" };
    match item_type {
        "commandExecution" => Some(format!("Codex command {suffix}")),
        "fileChange" => Some(format!("Codex file change {suffix}")),
        "mcpToolCall" => {
            let name = item
                .get("tool")
                .or_else(|| item.get("name"))
                .and_then(Value::as_str)
                .unwrap_or("MCP tool");
            Some(format!("Codex {name} {suffix}"))
        }
        "webSearch" => Some(format!("Codex web search {suffix}")),
        _ => None,
    }
}

fn plan_status_message(params: &Value) -> Option<String> {
    let plan = params.get("plan")?.as_array()?;
    let active = plan.iter().find(|entry| {
        entry
            .get("status")
            .and_then(Value::as_str)
            .is_some_and(|status| status == "inProgress")
    })?;
    active
        .get("step")
        .and_then(Value::as_str)
        .map(|step| format!("Codex plan: {step}"))
}

fn final_agent_text(turn: &Value) -> Option<String> {
    turn.get("items")?
        .as_array()?
        .iter()
        .rev()
        .find(|item| item.get("type").and_then(Value::as_str) == Some("agentMessage"))?
        .get("text")?
        .as_str()
        .map(ToString::to_string)
}

struct CodexConnection {
    child: Child,
    stdin: ChildStdin,
    lines: Lines<BufReader<ChildStdout>>,
    next_id: u64,
    approval_tx: Option<ProviderApprovalSender>,
    runtime: Option<CodexRuntimeMetadata>,
    stderr_lines: Arc<AsyncMutex<VecDeque<String>>>,
    stderr_task: Option<JoinHandle<()>>,
}

impl CodexConnection {
    async fn spawn() -> Result<Self, LlmError> {
        Self::spawn_with_approvals(None).await
    }

    async fn spawn_with_approvals(
        approval_tx: Option<ProviderApprovalSender>,
    ) -> Result<Self, LlmError> {
        let runtime_spec = codex_runtime::resolve_runtime()?;
        Self::spawn_runtime(runtime_spec, approval_tx).await
    }

    async fn spawn_runtime(
        runtime_spec: codex_runtime::CodexRuntimeSpec,
        approval_tx: Option<ProviderApprovalSender>,
    ) -> Result<Self, LlmError> {
        let mut command = codex_runtime::build_app_server_command(&runtime_spec)?;
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let mut child = command.spawn().map_err(|error| LlmError::ProviderInit {
            provider: PROVIDER_NAME.to_string(),
            message: format!("Could not start Codex app-server: {error}"),
        })?;
        let stdin = child.stdin.take().ok_or_else(|| LlmError::ProviderInit {
            provider: PROVIDER_NAME.to_string(),
            message: "Codex app-server stdin was unavailable.".to_string(),
        })?;
        let stdout = child.stdout.take().ok_or_else(|| LlmError::ProviderInit {
            provider: PROVIDER_NAME.to_string(),
            message: "Codex app-server stdout was unavailable.".to_string(),
        })?;
        let stderr = child.stderr.take().ok_or_else(|| LlmError::ProviderInit {
            provider: PROVIDER_NAME.to_string(),
            message: "Codex app-server stderr was unavailable.".to_string(),
        })?;
        let stderr_lines = Arc::new(AsyncMutex::new(VecDeque::new()));
        let stderr_task = Some(tokio::spawn(drain_stderr(
            stderr,
            Arc::clone(&stderr_lines),
        )));
        let mut connection = Self {
            child,
            stdin,
            lines: BufReader::new(stdout).lines(),
            next_id: 1,
            approval_tx,
            runtime: None,
            stderr_lines,
            stderr_task,
        };
        let initialize = connection
            .request(
                "initialize",
                json!({
                    "clientInfo": {
                        "name": "fennara_godot_ai",
                        "title": "Fennara Godot AI",
                        "version": env!("CARGO_PKG_VERSION")
                    },
                    "capabilities": { "experimentalApi": true }
                }),
                INIT_TIMEOUT,
            )
            .await?;
        connection.runtime = Some(codex_runtime::metadata_from_initialize(
            &runtime_spec,
            &initialize,
        )?);
        connection
            .send_notification("initialized", json!({}))
            .await?;
        Ok(connection)
    }

    async fn request(
        &mut self,
        method: &str,
        params: Value,
        request_timeout: Duration,
    ) -> Result<Value, LlmError> {
        let id = self.next_id;
        self.next_id = self.next_id.saturating_add(1);
        self.write_json(&json!({ "id": id, "method": method, "params": params }))
            .await?;
        timeout(request_timeout, self.wait_for_response(id))
            .await
            .map_err(|_| LlmError::Timeout {
                provider: PROVIDER_NAME.to_string(),
                message: format!("Codex request timed out: {method}"),
            })?
    }

    async fn send_notification(&mut self, method: &str, params: Value) -> Result<(), LlmError> {
        self.write_json(&json!({ "method": method, "params": params }))
            .await
    }

    async fn wait_for_response(&mut self, id: u64) -> Result<Value, LlmError> {
        loop {
            let message = self.read_message().await?;
            if self.respond_to_server_request(&message).await? {
                continue;
            }
            if message.get("id").and_then(Value::as_u64) != Some(id) {
                continue;
            }
            if let Some(error) = message.get("error") {
                return Err(rpc_error(error));
            }
            return Ok(message.get("result").cloned().unwrap_or(Value::Null));
        }
    }

    async fn read_message(&mut self) -> Result<Value, LlmError> {
        loop {
            let line =
                self.lines
                    .next_line()
                    .await
                    .map_err(|error| LlmError::InvalidProviderOutput {
                        provider: PROVIDER_NAME.to_string(),
                        message: format!("Could not read Codex app-server output: {error}"),
                        raw: None,
                    })?;
            let Some(line) = line else {
                return Err(LlmError::ProviderApi {
                    provider: PROVIDER_NAME.to_string(),
                    status: None,
                    message: self.process_exit_message().await,
                    retryable: true,
                });
            };
            if line.trim().is_empty() {
                continue;
            }
            return serde_json::from_str(&line).map_err(|error| LlmError::InvalidProviderOutput {
                provider: PROVIDER_NAME.to_string(),
                message: format!("Codex app-server returned invalid JSON: {error}"),
                raw: Some(line),
            });
        }
    }

    async fn respond_to_server_request(&mut self, message: &Value) -> Result<bool, LlmError> {
        let Some(id) = message.get("id").cloned() else {
            return Ok(false);
        };
        let Some(method) = message.get("method").and_then(Value::as_str) else {
            return Ok(false);
        };
        let params = message.get("params").cloned().unwrap_or_else(|| json!({}));
        let result = match method {
            "item/commandExecution/requestApproval" | "item/fileChange/requestApproval" => {
                self.request_approval(method, params).await?
            }
            "tool/requestUserInput" => json!({ "answers": {} }),
            "mcpServer/elicitation/request" => json!({ "action": "decline" }),
            _ => json!({}),
        };
        self.write_json(&json!({ "id": id, "result": result }))
            .await?;
        Ok(true)
    }

    async fn request_approval(&mut self, method: &str, params: Value) -> Result<Value, LlmError> {
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
        approval_tx
            .send(request)
            .map_err(|_| LlmError::ProviderApi {
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
        let _ = self
            .request(
                "turn/interrupt",
                json!({ "threadId": thread_id }),
                Duration::from_secs(3),
            )
            .await;
    }

    async fn write_json(&mut self, value: &Value) -> Result<(), LlmError> {
        let mut bytes = serde_json::to_vec(value).map_err(|error| LlmError::Config {
            message: format!("Could not serialize Codex request: {error}"),
        })?;
        bytes.push(b'\n');
        self.stdin
            .write_all(&bytes)
            .await
            .map_err(|error| LlmError::ProviderApi {
                provider: PROVIDER_NAME.to_string(),
                status: None,
                message: format!("Could not write to Codex app-server: {error}"),
                retryable: false,
            })?;
        self.stdin
            .flush()
            .await
            .map_err(|error| LlmError::ProviderApi {
                provider: PROVIDER_NAME.to_string(),
                status: None,
                message: format!("Could not flush Codex app-server request: {error}"),
                retryable: false,
            })
    }

    async fn process_exit_message(&mut self) -> String {
        let status = match self.child.try_wait() {
            Ok(Some(status)) => Some(status),
            Ok(None) => match timeout(Duration::from_millis(500), self.child.wait()).await {
                Ok(Ok(status)) => Some(status),
                _ => None,
            },
            Err(_) => None,
        };
        if status.is_some() {
            if let Some(task) = self.stderr_task.take() {
                let _ = timeout(Duration::from_millis(500), task).await;
            }
        }
        let diagnostics = stderr_snapshot(&self.stderr_lines).await;
        let status_text = status
            .map(|status| format!(" with status {status}"))
            .unwrap_or_default();
        if diagnostics.is_empty() {
            format!("Codex app-server exited{status_text} before the request completed.")
        } else {
            format!(
                "Codex app-server exited{status_text} before the request completed. stderr: {diagnostics}"
            )
        }
    }

    async fn shutdown(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.start_kill();
            let _ = timeout(SHUTDOWN_TIMEOUT, self.child.wait()).await;
        }
        if let Some(task) = self.stderr_task.take() {
            task.abort();
        }
    }
}

async fn drain_stderr(stderr: ChildStderr, lines: Arc<AsyncMutex<VecDeque<String>>>) {
    let mut stderr = BufReader::new(stderr).lines();
    while let Ok(Some(line)) = stderr.next_line().await {
        let clean = line.trim();
        if clean.is_empty() {
            continue;
        }
        let mut buffered = lines.lock().await;
        push_stderr_line(&mut buffered, clean.to_string());
    }
}

fn push_stderr_line(lines: &mut VecDeque<String>, line: String) {
    if lines.len() >= STDERR_LINE_LIMIT {
        lines.pop_front();
    }
    lines.push_back(line);
}

async fn stderr_snapshot(lines: &Arc<AsyncMutex<VecDeque<String>>>) -> String {
    lines
        .lock()
        .await
        .iter()
        .cloned()
        .collect::<Vec<_>>()
        .join(" | ")
}

fn optional_string(value: &Value, key: &str) -> Option<String> {
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
    let message = error
        .get("message")
        .and_then(Value::as_str)
        .unwrap_or("Codex app-server request failed.")
        .to_string();
    let lower = message.to_ascii_lowercase();
    if lower.contains("auth") || lower.contains("login") {
        return LlmError::Auth {
            provider: "codex".to_string(),
            message,
        };
    }
    LlmError::ProviderApi {
        provider: PROVIDER_NAME.to_string(),
        status: None,
        message,
        retryable: false,
    }
}

#[cfg(test)]
mod integration_tests;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flattens_provider_messages_for_codex() {
        let prompt = prompt_from_messages(&[
            json!({ "role": "system", "content": "Use Godot tools." }),
            json!({ "role": "user", "content": "Create a node." }),
        ]);
        assert!(prompt.contains("[system]"));
        assert!(prompt.contains("Create a node."));
    }

    #[test]
    fn latest_user_prompt_uses_only_the_newest_user_message() {
        let prompt = latest_user_prompt(&[
            json!({ "role": "system", "content": "system" }),
            json!({ "role": "user", "content": "first" }),
            json!({ "role": "assistant", "content": "reply" }),
            json!({ "role": "user", "content": "second" }),
        ]);
        assert_eq!(prompt, "second");
    }

    #[test]
    fn codex_home_keys_are_normalized_and_compared_strictly() {
        assert!(codex_home_keys_match("/tmp/codex-home/", "/tmp/codex-home"));
        assert!(!codex_home_keys_match(
            "/tmp/codex-home-a",
            "/tmp/codex-home-b"
        ));
        #[cfg(windows)]
        assert!(codex_home_keys_match(
            r"C:\Users\Test\.codex",
            "c:/users/test/.codex/"
        ));
    }

    #[test]
    fn missing_thread_errors_are_classified_narrowly() {
        assert!(is_missing_thread_error(&LlmError::ProviderApi {
            provider: PROVIDER_NAME.to_string(),
            status: None,
            message: "Thread does not exist".to_string(),
            retryable: false,
        }));
        assert!(!is_missing_thread_error(&LlmError::ProviderApi {
            provider: PROVIDER_NAME.to_string(),
            status: None,
            message: "Permission denied".to_string(),
            retryable: false,
        }));
    }

    #[test]
    fn approval_results_use_codex_v2_decisions() {
        assert_eq!(
            approval_result(ProviderApprovalDecision::Approved),
            json!({ "decision": "accept" })
        );
        assert_eq!(
            approval_result(ProviderApprovalDecision::Denied),
            json!({ "decision": "decline" })
        );
        assert_eq!(
            approval_result(ProviderApprovalDecision::Cancelled),
            json!({ "decision": "cancel" })
        );
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
    fn stderr_buffer_is_bounded() {
        let mut lines = VecDeque::new();
        for index in 0..(STDERR_LINE_LIMIT + 5) {
            push_stderr_line(&mut lines, format!("line-{index}"));
        }
        assert_eq!(lines.len(), STDERR_LINE_LIMIT);
        assert_eq!(lines.front().map(String::as_str), Some("line-5"));
    }

    #[test]
    fn account_status_attaches_runtime_metadata() {
        let runtime = CodexRuntimeMetadata {
            version: Some(codex_runtime::PINNED_CODEX_VERSION.to_string()),
            compatibility: codex_runtime::CodexCompatibility::Tested,
            pinned_version: codex_runtime::PINNED_CODEX_VERSION,
            minimum_version: codex_runtime::MINIMUM_CODEX_VERSION,
            compatibility_error: None,
            source: codex_runtime::CodexRuntimeSource::Path,
            platform: codex_runtime::CodexRuntimePlatform::Linux,
            codex_home: Some("/tmp/codex".to_string()),
            server_platform_family: Some("unix".to_string()),
            server_platform_os: Some("linux".to_string()),
        };
        let status = attach_runtime(CodexAccountStatus::default(), Some(&runtime));
        assert_eq!(
            status
                .runtime
                .as_ref()
                .and_then(|runtime| runtime.version.as_deref()),
            Some(codex_runtime::PINNED_CODEX_VERSION)
        );
    }

    #[test]
    fn reads_chatgpt_account_status() {
        let status = account_status_from_result(
            &json!({
                "account": {
                    "type": "chatgpt",
                    "email": "user@example.com",
                    "planType": "plus"
                },
                "requiresOpenaiAuth": true
            }),
            true,
            false,
            None,
        );
        assert!(status.connected);
        assert_eq!(status.plan_type.as_deref(), Some("plus"));
    }
}
