from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


def replace_all(path: str, old: str, new: str, expected: int) -> None:
    content = read(path)
    count = content.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} matches, found {count}: {old[:120]!r}")
    write(path, content.replace(old, new))


# Carry the stable Fennara chat identity into provider adapters.
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/types.rs",
    """pub(crate) struct ChatRequest {
    pub(crate) model: String,
    pub(crate) reasoning_effort: String,
    pub(crate) messages: Vec<Value>,
    pub(crate) tools: Vec<Value>,
    pub(crate) max_output_tokens: Option<u32>,
    pub(crate) cwd: Option<String>,
    pub(crate) approval_mode: String,
}""",
    """pub(crate) struct ChatRequest {
    pub(crate) model: String,
    pub(crate) reasoning_effort: String,
    pub(crate) messages: Vec<Value>,
    pub(crate) tools: Vec<Value>,
    pub(crate) max_output_tokens: Option<u32>,
    pub(crate) chat_id: Option<String>,
    pub(crate) cwd: Option<String>,
    pub(crate) approval_mode: String,
}""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/request.rs",
    """pub(crate) struct LlmRequest {
    pub(crate) model: ResolvedModel,
    pub(crate) messages: Vec<Value>,
    pub(crate) tools: Vec<Value>,
    pub(crate) cwd: Option<String>,
    pub(crate) approval_mode: String,
}""",
    """pub(crate) struct LlmRequest {
    pub(crate) model: ResolvedModel,
    pub(crate) messages: Vec<Value>,
    pub(crate) tools: Vec<Value>,
    pub(crate) chat_id: Option<String>,
    pub(crate) cwd: Option<String>,
    pub(crate) approval_mode: String,
}""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/request.rs",
    """            messages: request.messages.clone(),
            tools: request.tools.clone(),
            cwd: request.cwd.clone(),
            approval_mode: request.approval_mode.clone(),""",
    """            messages: request.messages.clone(),
            tools: request.tools.clone(),
            chat_id: request.chat_id.clone(),
            cwd: request.cwd.clone(),
            approval_mode: request.approval_mode.clone(),""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs",
    """                max_output_tokens: None,
                cwd: project_path,
                approval_mode,""",
    """                max_output_tokens: None,
                chat_id: Some(chat_id_for_task.clone()),
                cwd: project_path,
                approval_mode,""",
)
replace_all(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs",
    """            max_output_tokens: None,
            cwd: None,
            approval_mode: \"ask\".to_string(),""",
    """            max_output_tokens: None,
            chat_id: None,
            cwd: None,
            approval_mode: \"ask\".to_string(),""",
    expected=2,
)

# Codex owns context compaction. Existing providers keep the current Fennara path.
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs",
    """    let summary_budgets =
        summary_budgets_for_model(&provider_settings, &model, &reasoning_effort, &trace);""",
    """    let is_codex_provider = model.starts_with(\"codex/\");
    let summary_budgets = if is_codex_provider {
        None
    } else {
        summary_budgets_for_model(&provider_settings, &model, &reasoning_effort, &trace)
    };""",
)

# Add the non-secret Fennara-chat/Codex-thread binding table.
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/schema.rs",
    """    run_migration_once(conn, 12, \"chat_context_summaries\", |conn| {
        create_context_summary_tables(conn)
    })?;
    Ok(())""",
    """    run_migration_once(conn, 12, \"chat_context_summaries\", |conn| {
        create_context_summary_tables(conn)
    })?;
    run_migration_once(conn, 13, \"chat_provider_sessions\", |conn| {
        create_provider_session_table(conn)
    })?;
    Ok(())""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/schema.rs",
    """pub(crate) fn to_store_error(error: rusqlite::Error) -> String {""",
    """fn create_provider_session_table(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        \"CREATE TABLE IF NOT EXISTS chat_provider_sessions (
           chat_id TEXT NOT NULL,
           provider_id TEXT NOT NULL,
           provider_thread_id TEXT NOT NULL,
           codex_home_key TEXT NOT NULL DEFAULT 'default',
           runtime_version TEXT,
           resume_status TEXT NOT NULL DEFAULT 'ready',
           created_at_ms INTEGER NOT NULL,
           updated_at_ms INTEGER NOT NULL,
           PRIMARY KEY (chat_id, provider_id),
           FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
         );
         CREATE INDEX IF NOT EXISTS idx_chat_provider_sessions_thread
           ON chat_provider_sessions(provider_id, provider_thread_id);\",
    )
    .map_err(to_store_error)
}

pub(crate) fn to_store_error(error: rusqlite::Error) -> String {""",
)

replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/store.rs",
    """#[derive(Clone, Debug)]
pub(crate) struct StartedGeneration {
    pub(crate) id: String,
}

#[derive(Clone, Debug)]""",
    """#[derive(Clone, Debug)]
pub(crate) struct StartedGeneration {
    pub(crate) id: String,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct ProviderSessionBinding {
    pub(crate) chat_id: String,
    pub(crate) provider_id: String,
    pub(crate) provider_thread_id: String,
    pub(crate) codex_home_key: String,
    pub(crate) runtime_version: Option<String>,
    pub(crate) resume_status: String,
    pub(crate) created_at_ms: i64,
    pub(crate) updated_at_ms: i64,
}

#[derive(Clone, Debug)]""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/store.rs",
    """pub(crate) fn list_chats(scope: &ProjectScope) -> Result<Vec<ChatSummary>, String> {""",
    """pub(crate) fn provider_session_binding(
    chat_id: &str,
    provider_id: &str,
) -> Result<Option<ProviderSessionBinding>, String> {
    let conn = connection()?;
    conn.query_row(
        \"SELECT chat_id, provider_id, provider_thread_id, codex_home_key,
                runtime_version, resume_status, created_at_ms, updated_at_ms
         FROM chat_provider_sessions
         WHERE chat_id = ?1 AND provider_id = ?2\",
        params![chat_id, provider_id],
        |row| {
            Ok(ProviderSessionBinding {
                chat_id: row.get(0)?,
                provider_id: row.get(1)?,
                provider_thread_id: row.get(2)?,
                codex_home_key: row.get(3)?,
                runtime_version: row.get(4)?,
                resume_status: row.get(5)?,
                created_at_ms: row.get(6)?,
                updated_at_ms: row.get(7)?,
            })
        },
    )
    .optional()
    .map_err(to_store_error)
}

pub(crate) fn upsert_provider_session_binding(
    chat_id: &str,
    provider_id: &str,
    provider_thread_id: &str,
    codex_home_key: &str,
    runtime_version: Option<&str>,
) -> Result<(), String> {
    let conn = connection()?;
    let now = now_ms();
    conn.execute(
        \"INSERT INTO chat_provider_sessions
         (chat_id, provider_id, provider_thread_id, codex_home_key, runtime_version,
          resume_status, created_at_ms, updated_at_ms)
         VALUES (?1, ?2, ?3, ?4, ?5, 'ready', ?6, ?6)
         ON CONFLICT(chat_id, provider_id) DO UPDATE SET
           provider_thread_id = excluded.provider_thread_id,
           codex_home_key = excluded.codex_home_key,
           runtime_version = excluded.runtime_version,
           resume_status = 'ready',
           updated_at_ms = excluded.updated_at_ms\",
        params![
            chat_id,
            provider_id,
            provider_thread_id,
            codex_home_key,
            runtime_version,
            now
        ],
    )
    .map_err(to_store_error)?;
    Ok(())
}

pub(crate) fn mark_provider_session_broken(
    chat_id: &str,
    provider_id: &str,
) -> Result<(), String> {
    let conn = connection()?;
    conn.execute(
        \"UPDATE chat_provider_sessions
         SET resume_status = 'broken', updated_at_ms = ?3
         WHERE chat_id = ?1 AND provider_id = ?2\",
        params![chat_id, provider_id, now_ms()],
    )
    .map_err(to_store_error)?;
    Ok(())
}

pub(crate) fn list_chats(scope: &ProjectScope) -> Result<Vec<ChatSummary>, String> {""",
)

# Resume an authoritative Codex thread instead of reconstructing it from Fennara history.
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """use super::{
    error::LlmError,
    request::LlmRequest,
    stream::{FinishReason, StreamEvent, Usage},
};""",
    """use super::super::store;
use super::{
    error::LlmError,
    request::LlmRequest,
    stream::{FinishReason, StreamEvent, Usage},
};""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """    let mut thread_params = Map::new();""",
    """    let chat_id = request.chat_id.as_deref().ok_or_else(|| LlmError::Config {
        message: \"Codex requests require a Fennara chat id.\".to_string(),
    })?;
    let existing_binding = store::provider_session_binding(chat_id, \"codex\")
        .map_err(|message| LlmError::Config { message })?;

    let mut thread_params = Map::new();""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """    thread_params.insert(
        \"approvalPolicy\".to_string(),
        Value::String(\"never\".to_string()),
    );""",
    """    thread_params.insert(
        \"approvalPolicy\".to_string(),
        Value::String(
            if request.approval_mode == \"full_access\" {
                \"never\"
            } else {
                \"on-request\"
            }
            .to_string(),
        ),
    );""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """    thread_params.insert(\"ephemeral\".to_string(), Value::Bool(true));
""",
    "",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """    let thread_result = connection
        .request(\"thread/start\", Value::Object(thread_params), RPC_TIMEOUT)
        .await?;
    let thread_id = thread_result
        .pointer(\"/thread/id\")
        .and_then(Value::as_str)
        .ok_or_else(|| LlmError::InvalidProviderOutput {
            provider: PROVIDER_NAME.to_string(),
            message: \"Codex did not return a thread id.\".to_string(),
            raw: Some(thread_result.to_string()),
        })?
        .to_string();

    let prompt = prompt_from_messages(&request.messages);""",
    """    let resumed = existing_binding.is_some();
    let thread_result = if let Some(binding) = existing_binding.as_ref() {
        let mut resume_params = thread_params.clone();
        resume_params.insert(
            \"threadId\".to_string(),
            Value::String(binding.provider_thread_id.clone()),
        );
        match connection
            .request(\"thread/resume\", Value::Object(resume_params), RPC_TIMEOUT)
            .await
        {
            Ok(result) => result,
            Err(error) if is_missing_thread_error(&error) => {
                let _ = store::mark_provider_session_broken(chat_id, \"codex\");
                connection.shutdown().await;
                return Err(LlmError::ProviderApi {
                    provider: PROVIDER_NAME.to_string(),
                    status: None,
                    message: \"The Codex thread for this Fennara chat is no longer available. Start a new Codex thread explicitly; Fennara will not silently rebuild it from local history.\".to_string(),
                    retryable: false,
                });
            }
            Err(error) => return Err(error),
        }
    } else {
        connection
            .request(\"thread/start\", Value::Object(thread_params), RPC_TIMEOUT)
            .await?
    };
    let thread_id = thread_result
        .pointer(\"/thread/id\")
        .and_then(Value::as_str)
        .or_else(|| existing_binding.as_ref().map(|binding| binding.provider_thread_id.as_str()))
        .ok_or_else(|| LlmError::InvalidProviderOutput {
            provider: PROVIDER_NAME.to_string(),
            message: \"Codex did not return a thread id.\".to_string(),
            raw: Some(thread_result.to_string()),
        })?
        .to_string();
    store::upsert_provider_session_binding(chat_id, \"codex\", &thread_id, \"default\", None)
        .map_err(|message| LlmError::Config { message })?;

    let prompt = if resumed {
        latest_user_prompt(&request.messages)
    } else {
        prompt_from_messages(&request.messages)
    };""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """fn prompt_from_messages(messages: &[Value]) -> String {""",
    """fn latest_user_prompt(messages: &[Value]) -> String {
    messages
        .iter()
        .rev()
        .find(|message| message.get(\"role\").and_then(Value::as_str) == Some(\"user\"))
        .map(|message| message_content(message.get(\"content\")))
        .filter(|content| !content.trim().is_empty())
        .unwrap_or_else(|| prompt_from_messages(messages))
}

fn is_missing_thread_error(error: &LlmError) -> bool {
    let message = error.user_message().to_ascii_lowercase();
    message.contains(\"thread\")
        && (message.contains(\"not found\")
            || message.contains(\"does not exist\")
            || message.contains(\"missing\"))
}

fn prompt_from_messages(messages: &[Value]) -> String {""",
)
replace_once(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs",
    """    #[test]
    fn reads_chatgpt_account_status() {""",
    """    #[test]
    fn latest_user_prompt_uses_only_the_newest_user_message() {
        let prompt = latest_user_prompt(&[
            json!({ \"role\": \"system\", \"content\": \"system\" }),
            json!({ \"role\": \"user\", \"content\": \"first\" }),
            json!({ \"role\": \"assistant\", \"content\": \"reply\" }),
            json!({ \"role\": \"user\", \"content\": \"second\" }),
        ]);
        assert_eq!(prompt, \"second\");
    }

    #[test]
    fn missing_thread_errors_are_classified_narrowly() {
        assert!(is_missing_thread_error(&LlmError::ProviderApi {
            provider: PROVIDER_NAME.to_string(),
            status: None,
            message: \"Thread does not exist\".to_string(),
            retryable: false,
        }));
        assert!(!is_missing_thread_error(&LlmError::ProviderApi {
            provider: PROVIDER_NAME.to_string(),
            status: None,
            message: \"Permission denied\".to_string(),
            retryable: false,
        }));
    }

    #[test]
    fn reads_chatgpt_account_status() {""",
)

# Remove the one-shot trigger after the migration has been applied.
trigger = ROOT / ".github/codex-provider-phase1.trigger"
if trigger.exists():
    trigger.unlink()
