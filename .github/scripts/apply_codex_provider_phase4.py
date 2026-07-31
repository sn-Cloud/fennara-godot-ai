from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def file(relative: str) -> Path:
    return ROOT / relative


def replace_once(relative: str, old: str, new: str) -> None:
    target = file(relative)
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one match, found {count}: {old[:140]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


CODEX = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
replace_once(
    CODEX,
    '''use std::{
    process::Stdio,
    sync::{Mutex, OnceLock},
    time::Duration,
};
''',
    '''use std::{
    collections::VecDeque,
    process::Stdio,
    sync::{Arc, Mutex, OnceLock},
    time::Duration,
};
''',
)
replace_once(
    CODEX,
    '''    io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Lines},
    process::{Child, ChildStdin, ChildStdout},
    sync::oneshot,
    time::timeout,
''',
    '''    io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Lines},
    process::{Child, ChildStderr, ChildStdin, ChildStdout},
    sync::{Mutex as AsyncMutex, oneshot},
    task::JoinHandle,
    time::timeout,
''',
)
replace_once(
    CODEX,
    "const APPROVAL_TIMEOUT: Duration = Duration::from_secs(15 * 60);\n",
    "const APPROVAL_TIMEOUT: Duration = Duration::from_secs(15 * 60);\nconst SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(3);\nconst STDERR_LINE_LIMIT: usize = 40;\n",
)
replace_once(
    CODEX,
    '''static ACCOUNT_STATUS: OnceLock<Mutex<CodexAccountStatus>> = OnceLock::new();
''',
    '''static ACCOUNT_STATUS: OnceLock<Mutex<CodexAccountStatus>> = OnceLock::new();
static ACTIVE_LOGIN: OnceLock<Mutex<Option<ActiveCodexLogin>>> = OnceLock::new();

struct ActiveCodexLogin {
    login_id: String,
    cancel: oneshot::Sender<()>,
}
''',
)
replace_once(
    CODEX,
    '''fn account_status_cache() -> &'static Mutex<CodexAccountStatus> {
    ACCOUNT_STATUS.get_or_init(|| Mutex::new(CodexAccountStatus::default()))
}
''',
    '''fn account_status_cache() -> &'static Mutex<CodexAccountStatus> {
    ACCOUNT_STATUS.get_or_init(|| Mutex::new(CodexAccountStatus::default()))
}

fn active_login() -> &'static Mutex<Option<ActiveCodexLogin>> {
    ACTIVE_LOGIN.get_or_init(|| Mutex::new(None))
}
''',
)
replace_once(
    CODEX,
    '''pub(crate) async fn start_login() -> Result<CodexLoginStart, String> {
    if cached_account_status().signing_in {
        return Err("A Codex ChatGPT login is already in progress.".to_string());
    }
''',
    '''pub(crate) async fn start_login() -> Result<CodexLoginStart, String> {
    if active_login()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .is_some()
    {
        return Err("A Codex ChatGPT login is already in progress.".to_string());
    }
''',
)
replace_once(
    CODEX,
    '''    let previous = cached_account_status();
    let runtime = connection.runtime.clone();
''',
    '''    let previous = cached_account_status();
    let runtime = connection.runtime.clone();
    let (cancel_tx, cancel_rx) = oneshot::channel();
    {
        let mut active = active_login()
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if active.is_some() {
            connection.shutdown().await;
            return Err("A Codex ChatGPT login is already in progress.".to_string());
        }
        *active = Some(ActiveCodexLogin {
            login_id: login_id.clone(),
            cancel: cancel_tx,
        });
    }
''',
)
replace_once(
    CODEX,
    '''    tokio::spawn(async move {
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
        store_account_status(attach_runtime(status, runtime.as_ref()));
        connection.shutdown().await;
    });
''',
    '''    let task_login_id = login_id.clone();
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
''',
)
replace_once(
    CODEX,
    '''pub(crate) async fn logout() -> Result<CodexAccountStatus, String> {
''',
    '''pub(crate) fn cancel_login() -> Result<CodexAccountStatus, String> {
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
''',
)
replace_once(
    CODEX,
    '''    approval_tx: Option<ProviderApprovalSender>,
    runtime: Option<CodexRuntimeMetadata>,
}
''',
    '''    approval_tx: Option<ProviderApprovalSender>,
    runtime: Option<CodexRuntimeMetadata>,
    stderr_lines: Arc<AsyncMutex<VecDeque<String>>>,
    stderr_task: Option<JoinHandle<()>>,
}
''',
)
replace_once(
    CODEX,
    '''            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true);
''',
    '''            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
''',
)
replace_once(
    CODEX,
    '''        let stdout = child.stdout.take().ok_or_else(|| LlmError::ProviderInit {
            provider: PROVIDER_NAME.to_string(),
            message: "Codex app-server stdout was unavailable.".to_string(),
        })?;
        let mut connection = Self {
''',
    '''        let stdout = child.stdout.take().ok_or_else(|| LlmError::ProviderInit {
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
''',
)
replace_once(
    CODEX,
    '''            approval_tx,
            runtime: None,
        };
''',
    '''            approval_tx,
            runtime: None,
            stderr_lines,
            stderr_task,
        };
''',
)
replace_once(
    CODEX,
    '''            let line = self
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
''',
    '''            let line = self
                .lines
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
''',
)
replace_once(
    CODEX,
    '''    async fn shutdown(&mut self) {
        let _ = self.child.kill().await;
        let _ = self.child.wait().await;
    }
}
''',
    '''    async fn process_exit_message(&mut self) -> String {
        let status = self.child.try_wait().ok().flatten();
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
''',
)
replace_once(
    CODEX,
    '''    fn account_status_attaches_runtime_metadata() {
''',
    '''    fn stderr_buffer_is_bounded() {
        let mut lines = VecDeque::new();
        for index in 0..(STDERR_LINE_LIMIT + 5) {
            push_stderr_line(&mut lines, format!("line-{index}"));
        }
        assert_eq!(lines.len(), STDERR_LINE_LIMIT);
        assert_eq!(lines.front().map(String::as_str), Some("line-5"));
    }

    #[test]
    fn account_status_attaches_runtime_metadata() {
''',
)

CHAT = "local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs"
replace_once(
    CHAT,
    '''        "codex_logout" => match providers::codex_app_server::logout().await {
''',
    '''        "codex_login_cancel" => match providers::codex_app_server::cancel_login() {
            Ok(status) => {
                send_json(
                    sender,
                    json!({
                        "type": "codex_account_status",
                        "request_id": request_id,
                        "status": status
                    }),
                )
                .await
            }
            Err(error) => send_error(sender, request_id, "codex_login_cancel_failed", &error).await,
        },
        "codex_logout" => match providers::codex_app_server::logout().await {
''',
)

print("phase four migration applied")
