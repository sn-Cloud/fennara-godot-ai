use std::{
    env,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{Mutex, OnceLock},
    time::Duration,
};

use serde::Serialize;
use serde_json::{Map, Value, json};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Lines},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::oneshot,
    time::timeout,
};

use super::super::store;
use super::{
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
const CODEX_COMMAND_ENV: &str = "FENNARA_CODEX_COMMAND";

#[derive(Clone, Debug, Default, Serialize)]
pub(crate) struct CodexAccountStatus {
    pub(crate) installed: bool,
    pub(crate) connected: bool,
    pub(crate) signing_in: bool,
    pub(crate) auth_mode: Option<String>,
    pub(crate) plan_type: Option<String>,
    pub(crate) email: Option<String>,
    pub(crate) error: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct CodexLoginStart {
    pub(crate) login_id: String,
    pub(crate) auth_url: String,
}

static ACCOUNT_STATUS: OnceLock<Mutex<CodexAccountStatus>> = OnceLock::new();

fn account_status_cache() -> &'static Mutex<CodexAccountStatus> {
    ACCOUNT_STATUS.get_or_init(|| Mutex::new(CodexAccountStatus::default()))
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
    resolve_codex_command().is_some()
}

pub(crate) async fn account_status() -> Result<CodexAccountStatus, String> {
    if !is_installed() {
        let status = CodexAccountStatus {
            installed: false,
            error: Some(
                "Codex CLI was not found. Install @openai/codex or set FENNARA_CODEX_COMMAND."
                    .to_string(),
            ),
            ..CodexAccountStatus::default()
        };
        store_account_status(status.clone());
        return Ok(status);
    }

    let mut connection = CodexConnection::spawn()
        .await
        .map_err(|error| error.user_message())?;
    let result = connection
        .request(
            "account/read",
            json!({ "refreshToken": false }),
            RPC_TIMEOUT,
        )
        .await
        .map_err(|error| error.user_message())?;
    let status = account_status_from_result(&result, true, false, None);
    store_account_status(status.clone());
    connection.shutdown().await;
    Ok(status)
}

pub(crate) async fn start_login() -> Result<CodexLoginStart, String> {
    if !is_installed() {
        return Err(
            "Codex CLI was not found. Install @openai/codex or set FENNARA_CODEX_COMMAND."
                .to_string(),
        );
    }
    if cached_account_status().signing_in {
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
    store_account_status(CodexAccountStatus {
        installed: true,
        connected: previous.connected,
        signing_in: true,
        auth_mode: previous.auth_mode,
        plan_type: previous.plan_type,
        email: previous.email,
        error: None,
    });

    tokio::spawn(async move {
        let outcome = timeout(LOGIN_TIMEOUT, wait_for_login_completion(&mut connection)).await;
        let status = match outcome {
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
        };
        store_account_status(status);
        connection.shutdown().await;
    });

    Ok(CodexLoginStart { login_id, auth_url })
}

pub(crate) async fn logout() -> Result<CodexAccountStatus, String> {
    if !is_installed() {
        return Err("Codex CLI was not found.".to_string());
    }
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
    let account_status = account_status_from_result(&account, true, false, None);
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
    store::upsert_provider_session_binding(chat_id, "codex", &thread_id, "default", None)
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
                if let Some(status) = item_status_message(params.get("item"), false) {
                    if !on_event(StreamEvent::Status { message: status }).await? {
                        connection.interrupt_turn(&thread_id).await;
                        connection.shutdown().await;
                        return Ok(());
                    }
                }
            }
            "item/completed" => {
                if let Some(status) = item_status_message(params.get("item"), true) {
                    if !on_event(StreamEvent::Status { message: status }).await? {
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
    }
}

fn latest_user_prompt(messages: &[Value]) -> String {
    messages
        .iter()
        .rev()
        .find(|message| message.get("role").and_then(Value::as_str) == Some("user"))
        .map(|message| message_content(message.get("content")))
        .filter(|content| !content.trim().is_empty())
        .unwrap_or_else(|| prompt_from_messages(messages))
}

fn is_missing_thread_error(error: &LlmError) -> bool {
    let message = error.user_message().to_ascii_lowercase();
    message.contains("thread")
        && (message.contains("not found")
            || message.contains("does not exist")
            || message.contains("missing"))
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
}

impl CodexConnection {
    async fn spawn() -> Result<Self, LlmError> {
        Self::spawn_with_approvals(None).await
    }

    async fn spawn_with_approvals(
        approval_tx: Option<ProviderApprovalSender>,
    ) -> Result<Self, LlmError> {
        let mut command = codex_app_server_command()?;
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
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
        let mut connection = Self {
            child,
            stdin,
            lines: BufReader::new(stdout).lines(),
            next_id: 1,
            approval_tx,
        };
        connection
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
            let line = self
                .lines
                .next_line()
                .await
                .map_err(|error| LlmError::InvalidProviderOutput {
                    provider: PROVIDER_NAME.to_string(),
                    message: format!("Could not read Codex app-server output: {error}"),
                    raw: None,
                })?
                .ok_or_else(|| LlmError::ProviderApi {
                    provider: PROVIDER_NAME.to_string(),
                    status: None,
                    message: "Codex app-server exited before the request completed.".to_string(),
                    retryable: false,
                })?;
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

    async fn shutdown(&mut self) {
        let _ = self.child.kill().await;
        let _ = self.child.wait().await;
    }
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

fn codex_app_server_command() -> Result<Command, LlmError> {
    let executable = resolve_codex_command().ok_or_else(|| LlmError::ProviderInit {
        provider: PROVIDER_NAME.to_string(),
        message: "Codex CLI was not found. Install @openai/codex or set FENNARA_CODEX_COMMAND."
            .to_string(),
    })?;

    #[cfg(windows)]
    {
        let extension = executable
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        if matches!(extension.as_str(), "cmd" | "bat") {
            let mut command = Command::new("cmd.exe");
            command
                .args(["/D", "/S", "/C"])
                .arg(format!("\"{}\" app-server --stdio", executable.display()));
            return Ok(command);
        }
    }

    let mut command = Command::new(executable);
    command.args(["app-server", "--stdio"]);
    Ok(command)
}

fn resolve_codex_command() -> Option<PathBuf> {
    if let Some(configured) = env::var_os(CODEX_COMMAND_ENV).filter(|value| !value.is_empty()) {
        let path = PathBuf::from(configured);
        if path.is_file() {
            return Some(path);
        }
    }

    let path = env::var_os("PATH")?;
    let names: &[&str] = if cfg!(windows) {
        &["codex.exe", "codex.cmd", "codex.bat"]
    } else {
        &["codex"]
    };
    for directory in env::split_paths(&path) {
        for name in names {
            let candidate = directory.join(name);
            if is_executable_candidate(&candidate) {
                return Some(candidate);
            }
        }
    }
    None
}

fn is_executable_candidate(path: &Path) -> bool {
    path.is_file()
}

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
