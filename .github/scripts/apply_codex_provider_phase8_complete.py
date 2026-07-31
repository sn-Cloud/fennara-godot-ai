from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def file(relative: str) -> Path:
    return ROOT / relative


def replace_once(relative: str, old: str, new: str) -> None:
    target = file(relative)
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one match, found {count}: {old[:160]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")


PROVIDERS = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
replace_once(
    PROVIDERS,
    "pub(crate) mod codex_app_server;\nmod codex_runtime;\n",
    "pub(crate) mod codex_app_server;\npub(crate) mod codex_managed_runtime;\nmod codex_runtime;\n",
)

RUNTIME = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs"
replace_once(
    RUNTIME,
    '''use std::{
    env,
    path::{Path, PathBuf},
};
''',
    '''use std::{
    env,
    ffi::OsString,
    path::{Path, PathBuf},
};
''',
)
replace_once(
    RUNTIME,
    "use super::error::LlmError;\n",
    "use super::{codex_managed_runtime, error::LlmError};\n",
)
replace_once(
    RUNTIME,
    '''pub(crate) enum CodexRuntimeSource {
    Configured,
    Path,
}
''',
    '''pub(crate) enum CodexRuntimeSource {
    Configured,
    Managed,
    Path,
}
''',
)
replace_once(
    RUNTIME,
    '''        return Ok(CodexRuntimeSpec {
            executable,
            source: CodexRuntimeSource::Configured,
            platform,
            codex_home,
        });
    }

    let search_path = env::var_os("PATH").ok_or_else(|| {
''',
    '''        return Ok(CodexRuntimeSpec {
            executable,
            source: CodexRuntimeSource::Configured,
            platform,
            codex_home,
        });
    }

    if let Some(executable) = codex_managed_runtime::verified_executable() {
        return Ok(CodexRuntimeSpec {
            executable,
            source: CodexRuntimeSource::Managed,
            platform,
            codex_home,
        });
    }

    let search_path = env::var_os("PATH").ok_or_else(|| {
''',
)
replace_once(
    RUNTIME,
    '''    Err(provider_init(
        "Codex CLI was not found. Install @openai/codex or set FENNARA_CODEX_COMMAND.".to_string(),
    ))
''',
    '''    Err(provider_init(
        "Codex CLI was not found. Install @openai/codex, set FENNARA_CODEX_COMMAND, or install the Fennara-managed runtime."
            .to_string(),
    ))
''',
)
replace_once(
    RUNTIME,
    '''fn windows_app_server_command_line(executable: &Path) -> String {
    format!("\\\"\\\"{}\\\" app-server --stdio\\\"", executable.display())
}
''',
    '''fn windows_batch_command_args(executable: &Path) -> Vec<OsString> {
    vec![
        OsString::from("/D"),
        OsString::from("/C"),
        OsString::from("call"),
        executable.as_os_str().to_os_string(),
        OsString::from("app-server"),
        OsString::from("--stdio"),
    ]
}
''',
)
replace_once(
    RUNTIME,
    '''    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command
            .args(["/D", "/S", "/C"])
            .arg(windows_app_server_command_line(&runtime.executable));
        return Ok(command);
    }
''',
    '''    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command.args(windows_batch_command_args(&runtime.executable));
        return Ok(command);
    }
''',
)
replace_once(
    RUNTIME,
    '''    #[test]
    fn windows_batch_command_line_uses_cmd_outer_quotes() {
        let command =
            windows_app_server_command_line(Path::new("C:/Program Files/Codex/codex.cmd"));
        assert!(command.starts_with("\\\"\\\""), "{command}");
        assert!(
            command.contains("codex.cmd\\\" app-server --stdio"),
            "{command}"
        );
        assert!(command.ends_with("--stdio\\\""), "{command}");
    }
''',
    '''    #[test]
    fn windows_batch_runtime_uses_structured_call_arguments() {
        let args = windows_batch_command_args(Path::new("C:/Program Files/Codex/codex.cmd"));
        let args = args
            .iter()
            .map(|value| value.to_string_lossy().to_string())
            .collect::<Vec<_>>();
        assert_eq!(
            args,
            vec![
                "/D",
                "/C",
                "call",
                "C:/Program Files/Codex/codex.cmd",
                "app-server",
                "--stdio"
            ]
        );
    }
''',
)

CHAT = "local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs"
replace_once(
    CHAT,
    '''        "codex_account_status" => match providers::codex_app_server::account_status().await {
''',
    '''        "codex_runtime_status" => {
            let status = providers::codex_managed_runtime::status().await;
            send_json(
                sender,
                json!({
                    "type": "codex_runtime_status",
                    "request_id": request_id,
                    "status": status
                }),
            )
            .await
        }
        "codex_runtime_install_start" => {
            match providers::codex_managed_runtime::start_install().await {
                Ok(status) => {
                    send_json(
                        sender,
                        json!({
                            "type": "codex_runtime_status",
                            "request_id": request_id,
                            "status": status
                        }),
                    )
                    .await
                }
                Err(error) => {
                    send_error(sender, request_id, "codex_runtime_install_failed", &error).await
                }
            }
        }
        "codex_runtime_install_cancel" => {
            match providers::codex_managed_runtime::cancel_install().await {
                Ok(status) => {
                    send_json(
                        sender,
                        json!({
                            "type": "codex_runtime_status",
                            "request_id": request_id,
                            "status": status
                        }),
                    )
                    .await
                }
                Err(error) => {
                    send_error(sender, request_id, "codex_runtime_cancel_failed", &error).await
                }
            }
        }
        "codex_account_status" => match providers::codex_app_server::account_status().await {
''',
)

MANAGED = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_managed_runtime.rs"
replace_once(
    MANAGED,
    '''        let (cancel_tx, cancel_rx) = oneshot::channel();
        let task = tokio::spawn({
            let partial = partial.clone();
            async move {
                download_asset(
                    &reqwest::Client::new(),
                    &url,
                    &digest(&expected),
                    &partial,
                    cancel_rx,
                    |downloaded, _| async move {
                        if downloaded >= 1024 {
                            let _ = cancel_tx.send(());
                        }
                    },
                )
                .await
            }
        });
''',
    '''        let (cancel_tx, cancel_rx) = oneshot::channel();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(100)).await;
            let _ = cancel_tx.send(());
        });
        let task = tokio::spawn({
            let partial = partial.clone();
            async move {
                download_asset(
                    &reqwest::Client::new(),
                    &url,
                    &digest(&expected),
                    &partial,
                    cancel_rx,
                    |_, _| async {},
                )
                .await
            }
        });
''',
)
replace_once(
    MANAGED,
    "    use axum::{Router, body::Body, http::StatusCode, response::Response, routing::get};\n",
    "    use axum::{Router, body::Body, response::Response, routing::get};\n",
)
replace_once(
    MANAGED,
    '''        assert_eq!(WINDOWS_X64_ASSET_NAME, "codex-x86_64-pc-windows-msvc.exe");
        assert_eq!(StatusCode::OK.as_u16(), 200);
''',
    '''        assert_eq!(WINDOWS_X64_ASSET_NAME, "codex-x86_64-pc-windows-msvc.exe");
        assert_eq!(
            WINDOWS_X64_SHA256,
            "51398051c2332b6afe08dc3b9dbb4056085c197f35ca57a307ee303d450cada5"
        );
''',
)

print("complete phase eight migration applied")
