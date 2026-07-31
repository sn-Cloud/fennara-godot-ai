from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def file(relative: str) -> Path:
    return ROOT / relative


def replace_once(relative: str, old: str, new: str) -> None:
    target = file(relative)
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one match, found {count}: {old[:120]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


MOD = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
replace_once(MOD, "pub(crate) mod codex_app_server;\n", "pub(crate) mod codex_app_server;\nmod codex_runtime;\n")

CODEX = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
replace_once(
    CODEX,
    '''use std::{
    env,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{Mutex, OnceLock},
    time::Duration,
};
''',
    '''use std::{
    process::Stdio,
    sync::{Mutex, OnceLock},
    time::Duration,
};
''',
)
replace_once(
    CODEX,
    "    process::{Child, ChildStdin, ChildStdout, Command},\n",
    "    process::{Child, ChildStdin, ChildStdout},\n",
)
replace_once(
    CODEX,
    '''    control::{
        ProviderApprovalDecision, ProviderApprovalKind, ProviderApprovalRequest,
        ProviderApprovalSender,
    },
    error::LlmError,
''',
    '''    codex_runtime::{self, CodexRuntimeMetadata},
    control::{
        ProviderApprovalDecision, ProviderApprovalKind, ProviderApprovalRequest,
        ProviderApprovalSender,
    },
    error::LlmError,
''',
)
replace_once(
    CODEX,
    'const CODEX_COMMAND_ENV: &str = "FENNARA_CODEX_COMMAND";\n',
    "",
)
replace_once(
    CODEX,
    "    pub(crate) error: Option<String>,\n}\n",
    "    pub(crate) error: Option<String>,\n    pub(crate) runtime: Option<CodexRuntimeMetadata>,\n}\n",
)
replace_once(
    CODEX,
    '''pub(crate) fn is_installed() -> bool {
    resolve_codex_command().is_some()
}
''',
    '''pub(crate) fn is_installed() -> bool {
    codex_runtime::resolve_runtime().is_ok()
}
''',
)
replace_once(
    CODEX,
    '''pub(crate) async fn account_status() -> Result<CodexAccountStatus, String> {
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
''',
    '''pub(crate) async fn account_status() -> Result<CodexAccountStatus, String> {
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
''',
)
replace_once(
    CODEX,
    "    let status = account_status_from_result(&result, true, false, None);\n",
    "    let status = attach_runtime(\n        account_status_from_result(&result, true, false, None),\n        connection.runtime.as_ref(),\n    );\n",
)
replace_once(
    CODEX,
    '''pub(crate) async fn start_login() -> Result<CodexLoginStart, String> {
    if !is_installed() {
        return Err(
            "Codex CLI was not found. Install @openai/codex or set FENNARA_CODEX_COMMAND."
                .to_string(),
        );
    }
    if cached_account_status().signing_in {
''',
    '''pub(crate) async fn start_login() -> Result<CodexLoginStart, String> {
    if cached_account_status().signing_in {
''',
)
replace_once(
    CODEX,
    '''    let previous = cached_account_status();
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
''',
    '''    let previous = cached_account_status();
    let runtime = connection.runtime.clone();
    store_account_status(CodexAccountStatus {
        installed: true,
        connected: previous.connected,
        signing_in: true,
        auth_mode: previous.auth_mode,
        plan_type: previous.plan_type,
        email: previous.email,
        error: None,
        runtime: runtime.clone(),
    });

    tokio::spawn(async move {
''',
)
replace_once(
    CODEX,
    '''        };
        store_account_status(status);
        connection.shutdown().await;
''',
    '''        };
        store_account_status(attach_runtime(status, runtime.as_ref()));
        connection.shutdown().await;
''',
)
replace_once(
    CODEX,
    '''pub(crate) async fn logout() -> Result<CodexAccountStatus, String> {
    if !is_installed() {
        return Err("Codex CLI was not found.".to_string());
    }
    let mut connection = CodexConnection::spawn()
''',
    '''pub(crate) async fn logout() -> Result<CodexAccountStatus, String> {
    let mut connection = CodexConnection::spawn()
''',
)
replace_once(
    CODEX,
    '''    let status = CodexAccountStatus {
        installed: true,
        ..CodexAccountStatus::default()
    };
''',
    '''    let status = CodexAccountStatus {
        installed: true,
        runtime: connection.runtime.clone(),
        ..CodexAccountStatus::default()
    };
''',
)
replace_once(
    CODEX,
    "    let account_status = account_status_from_result(&account, true, false, None);\n",
    "    let account_status = attach_runtime(\n        account_status_from_result(&account, true, false, None),\n        connection.runtime.as_ref(),\n    );\n",
)
replace_once(
    CODEX,
    '''        email: account
            .and_then(|value| value.get("email"))
            .and_then(Value::as_str)
            .map(ToString::to_string),
        error,
    }
}
''',
    '''        email: account
            .and_then(|value| value.get("email"))
            .and_then(Value::as_str)
            .map(ToString::to_string),
        error,
        runtime: None,
    }
}

fn attach_runtime(
    mut status: CodexAccountStatus,
    runtime: Option<&CodexRuntimeMetadata>,
) -> CodexAccountStatus {
    status.runtime = runtime.cloned();
    status
}
''',
)
replace_once(
    CODEX,
    '''    next_id: u64,
    approval_tx: Option<ProviderApprovalSender>,
}
''',
    '''    next_id: u64,
    approval_tx: Option<ProviderApprovalSender>,
    runtime: Option<CodexRuntimeMetadata>,
}
''',
)
replace_once(
    CODEX,
    '''        let mut command = codex_app_server_command()?;
        command
''',
    '''        let runtime_spec = codex_runtime::resolve_runtime()?;
        let mut command = codex_runtime::build_app_server_command(&runtime_spec)?;
        command
''',
)
replace_once(
    CODEX,
    '''            next_id: 1,
            approval_tx,
        };
        connection
            .request(
''',
    '''            next_id: 1,
            approval_tx,
            runtime: None,
        };
        let initialize = connection
            .request(
''',
)
replace_once(
    CODEX,
    '''            )
            .await?;
        connection
            .send_notification("initialized", json!({}))
            .await?;
        Ok(connection)
''',
    '''            )
            .await?;
        connection.runtime = Some(codex_runtime::metadata_from_initialize(
            &runtime_spec,
            &initialize,
        ));
        connection
            .send_notification("initialized", json!({}))
            .await?;
        Ok(connection)
''',
)
start = '''fn codex_app_server_command() -> Result<Command, LlmError> {
'''
end = '''fn is_executable_candidate(path: &Path) -> bool {
    path.is_file()
}

'''
target = file(CODEX)
content = target.read_text(encoding="utf-8")
start_index = content.find(start)
end_index = content.find(end)
if start_index < 0 or end_index < 0 or end_index < start_index:
    raise RuntimeError("could not locate legacy Codex runtime helpers")
end_index += len(end)
target.write_text(content[:start_index] + content[end_index:], encoding="utf-8", newline="\n")

replace_once(
    CODEX,
    '''    fn reads_chatgpt_account_status() {
''',
    '''    fn account_status_attaches_runtime_metadata() {
        let runtime = CodexRuntimeMetadata {
            version: Some(codex_runtime::PINNED_CODEX_VERSION.to_string()),
            compatibility: codex_runtime::CodexCompatibility::Tested,
            pinned_version: codex_runtime::PINNED_CODEX_VERSION,
            source: codex_runtime::CodexRuntimeSource::Path,
            platform: codex_runtime::CodexRuntimePlatform::Linux,
            codex_home: Some("/tmp/codex".to_string()),
            server_platform_family: Some("unix".to_string()),
            server_platform_os: Some("linux".to_string()),
        };
        let status = attach_runtime(CodexAccountStatus::default(), Some(&runtime));
        assert_eq!(
            status.runtime.as_ref().and_then(|runtime| runtime.version.as_deref()),
            Some(codex_runtime::PINNED_CODEX_VERSION)
        );
    }

    #[test]
    fn reads_chatgpt_account_status() {
''',
)

print("phase three migration applied")
