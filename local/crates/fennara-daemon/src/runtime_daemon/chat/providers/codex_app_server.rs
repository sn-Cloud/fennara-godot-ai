use std::{
    env,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{Mutex, OnceLock},
    time::Duration,
};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Lines},
    process::{Child, ChildStdin, ChildStdout, Command},
    time::timeout,
};

use super::{
    error::LlmError,
    request::LlmRequest,
    stream::{FinishReason, StreamEvent, Usage},
};

const PROVIDER_NAME: &str = "Codex";
const INIT_TIMEOUT: Duration = Duration::from_secs(20);
const RPC_TIMEOUT: Duration = Duration::from_secs(30);
const LOGIN_TIMEOUT: Duration = Duration::from_secs(15 * 60);
const CODEX_COMMAND_ENV: &str = "FENNARA_CODEX_COMMAND";

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CodexModel {
    pub(crate) model: String,
    pub(crate) display_name: String,
    pub(crate) description: String,
    #[serde(default)]
    pub(crate) hidden: bool,
    pub(crate) is_default: bool,
    pub(crate) default_reasoning_effort: String,
    pub(crate) supported_reasoning_efforts: Vec<CodexEffort>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CodexEffort {
    pub(crate) reasoning_effort: String,
}

// Discover picker-visible models from the official app-server on each refresh.
// Always follow cursors, and never substitute a static list on failure.
pub(crate) async fn list_models() -> Result<Vec<CodexModel>, String> {
    super::codex_runtime::check_in_background();
    let mut connection = CodexConnection::spawn()
        .await
        .map_err(|e| e.user_message())?;
    let result = connection.list_models().await.map_err(|e| e.user_message());
    connection.shutdown().await;
    result
}

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

// Report catalog/selection failures as actionable provider errors without
// sending an unsupported model or effort to a generation request.
fn codex_catalog_error(message: String) -> LlmError {
    LlmError::ProviderInit {
        provider: PROVIDER_NAME.to_string(),
        message,
    }
}

fn select_codex_model<'a>(models: &'a [CodexModel], id: &str) -> Result<&'a CodexModel, LlmError> {
    models.iter().find(|m| if id == "default" || id.is_empty() { m.is_default } else { m.model == id })
        .ok_or_else(|| codex_catalog_error("The selected Codex model is unavailable. Refresh the model list and choose a model.".into()))
}

fn select_codex_effort<'a>(
    model: &'a CodexModel,
    requested: Option<&'a str>,
) -> Result<Option<&'a str>, LlmError> {
    if model.supported_reasoning_efforts.is_empty() {
        return Ok(None);
    }
    let effort = requested
        .filter(|value| !value.is_empty())
        .unwrap_or(&model.default_reasoning_effort);
    if model
        .supported_reasoning_efforts
        .iter()
        .any(|option| option.reasoning_effort == effort)
    {
        Ok(Some(effort))
    } else {
        Err(codex_catalog_error(format!(
            "Codex model {} does not support effort {effort}. Refresh the model list and choose a supported effort.",
            model.model
        )))
    }
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
    mut on_event: F,
) -> Result<(), LlmError>
where
    F: FnMut(StreamEvent) -> Fut + Send,
    Fut: std::future::Future<Output = Result<bool, LlmError>> + Send,
{
    let mut connection = CodexConnection::spawn().await?;
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
        Value::String("never".to_string()),
    );
    thread_params.insert(
        "sandbox".to_string(),
        Value::String(thread_sandbox_mode(&request.approval_mode).to_string()),
    );
    thread_params.insert("ephemeral".to_string(), Value::Bool(true));
    thread_params.insert(
        "serviceName".to_string(),
        Value::String("fennara_godot_ai".to_string()),
    );
    // Resolve the legacy default alias and validate effort against the same
    // official catalog used by the picker before starting a generation.
    let models = connection.list_models().await?;
    let selected = select_codex_model(&models, request.model.model.adapter_model_id.trim())?;
    let effort = request.model.request.generation.reasoning_effort.as_deref();
    let effort = select_codex_effort(selected, effort)?;
    thread_params.insert("model".to_string(), Value::String(selected.model.clone()));

    let thread_result = connection
        .request("thread/start", Value::Object(thread_params), RPC_TIMEOUT)
        .await?;
    let thread_id = thread_result
        .pointer("/thread/id")
        .and_then(Value::as_str)
        .ok_or_else(|| LlmError::InvalidProviderOutput {
            provider: PROVIDER_NAME.to_string(),
            message: "Codex did not return a thread id.".to_string(),
            raw: Some(thread_result.to_string()),
        })?
        .to_string();

    let prompt = prompt_from_messages(&request.messages);
    let turn_params = json!({
        "threadId": thread_id.clone(),
        "input": [{ "type": "text", "text": prompt }],
        "effort": effort,
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
}

impl CodexConnection {
    // List all visible pages on this initialized connection. Reject malformed
    // data and repeated cursors rather than hanging or advertising guessed models.
    async fn list_models(&mut self) -> Result<Vec<CodexModel>, LlmError> {
        let mut models = Vec::new();
        let mut cursor: Option<String> = None;
        let mut seen = std::collections::HashSet::new();
        loop {
            let page = self
                .request(
                    "model/list",
                    json!({"limit": 100, "cursor": cursor, "includeHidden": false}),
                    RPC_TIMEOUT,
                )
                .await?;
            let entries: Vec<CodexModel> = serde_json::from_value(
                page.get("data").cloned().unwrap_or(Value::Null),
            )
            .map_err(|e| codex_catalog_error(format!("Invalid model/list response: {e}")))?;
            models.extend(entries.into_iter().filter(|m| !m.hidden));
            cursor = page
                .get("nextCursor")
                .and_then(Value::as_str)
                .map(str::to_owned);
            match &cursor {
                None => break,
                Some(value) if seen.insert(value.clone()) => {}
                Some(_) => {
                    return Err(codex_catalog_error(
                        "model/list returned a repeated cursor".into(),
                    ));
                }
            }
        }
        Ok(models)
    }

    async fn spawn() -> Result<Self, LlmError> {
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
                    "capabilities": {}
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
        let result = match method {
            "item/commandExecution/requestApproval" | "item/fileChange/requestApproval" => {
                json!({ "decision": "decline" })
            }
            "tool/requestUserInput" => json!({ "answers": {} }),
            "mcpServer/elicitation/request" => json!({ "action": "decline" }),
            _ => json!({}),
        };
        self.write_json(&json!({ "id": id, "result": result }))
            .await?;
        Ok(true)
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

    // Complete addons carry the native Codex distribution next to the daemon.
    // Prefer it to PATH after an explicit user override, including its sandbox helpers.
    if let Ok(executable) = env::current_exe() {
        if let Some(parent) = executable.parent() {
            let bundled = parent.join("codex").join("bin").join(if cfg!(windows) {
                "codex.exe"
            } else {
                "codex"
            });
            if bundled.is_file() {
                return super::codex_runtime::managed_command(&parent.join("codex"))
                    .or(Some(bundled));
            }
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

// thread/start takes the kebab-case SandboxMode enum, not the camel-case
// SandboxPolicy discriminator returned in responses. Only explicit full access
// should disable the workspace sandbox.
fn thread_sandbox_mode(approval_mode: &str) -> &'static str {
    if approval_mode == "full_access" {
        "danger-full-access"
    } else {
        "workspace-write"
    }
}

fn is_executable_candidate(path: &Path) -> bool {
    path.is_file()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn official_metadata_controls_model_and_effort_selection() {
        let models: Vec<CodexModel> = serde_json::from_value(json!([{
            "model": "future-model", "displayName": "Future model", "description": "test",
            "isDefault": true, "defaultReasoningEffort": "ultra",
            "supportedReasoningEfforts": [{"reasoningEffort": "ultra", "description": "test"}]
        }]))
        .unwrap();
        let selected = select_codex_model(&models, "default").unwrap();
        assert_eq!(selected.model, "future-model");
        assert_eq!(select_codex_effort(selected, None).unwrap(), Some("ultra"));
        assert_eq!(
            select_codex_effort(selected, Some("ultra")).unwrap(),
            Some("ultra")
        );
        assert!(select_codex_effort(selected, Some("medium")).is_err());
        assert!(select_codex_model(&models, "removed-model").is_err());
        assert!(select_codex_model(&[], "default").is_err());
        let mut no_effort = selected.clone();
        no_effort.supported_reasoning_efforts.clear();
        assert_eq!(
            select_codex_effort(&no_effort, Some("medium")).unwrap(),
            None
        );
    }

    // Opt-in read-only integration check against the actual bundled app-server.
    #[tokio::test]
    #[ignore = "requires installed Codex and model catalog access"]
    async fn live_official_model_catalog() {
        let models = list_models().await.unwrap();
        assert!(!models.is_empty());
        for model in &models {
            assert!(!model.hidden);
            select_codex_effort(model, None).unwrap();
            println!(
                "{}: {:?}",
                model.model,
                model
                    .supported_reasoning_efforts
                    .iter()
                    .map(|v| &v.reasoning_effort)
                    .collect::<Vec<_>>()
            );
        }
    }

    // Exercise the real protocol parser without starting a turn or running tools.
    #[tokio::test]
    #[ignore = "requires installed Codex and model catalog access"]
    async fn live_official_thread_sandbox_modes() {
        let mut connection = CodexConnection::spawn().await.unwrap();
        let models = connection.list_models().await.unwrap();
        let model = models
            .iter()
            .find(|model| model.model.contains("astra"))
            .unwrap_or_else(|| select_codex_model(&models, "default").unwrap());
        for mode in ["default", "full_access"] {
            let result = connection
                .request(
                    "thread/start",
                    json!({
                        "model": model.model,
                        "approvalPolicy": "never",
                        "sandbox": thread_sandbox_mode(mode),
                        "ephemeral": true,
                        "serviceName": "fennara_godot_ai"
                    }),
                    RPC_TIMEOUT,
                )
                .await
                .unwrap();
            assert!(
                result
                    .pointer("/thread/id")
                    .and_then(Value::as_str)
                    .is_some()
            );
            assert_eq!(
                result.pointer("/sandbox/type").and_then(Value::as_str),
                Some(if mode == "full_access" {
                    "dangerFullAccess"
                } else {
                    "workspaceWrite"
                })
            );
            println!("{}: {} accepted", model.model, thread_sandbox_mode(mode));
        }
        connection.shutdown().await;
    }

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
