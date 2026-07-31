from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, content: str) -> None:
    (ROOT / relative).write_text(content, encoding="utf-8", newline="\n")


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {label}, found {count}")
    return content.replace(old, new, 1)


cargo_path = "local/crates/fennara-daemon/Cargo.toml"
cargo = read(cargo_path)
if 'toml_edit = "0.22"' not in cargo:
    cargo = replace_once(
        cargo,
        'tokio = { version = "1.48", features = ["fs", "io-util", "macros", "net", "process", "rt-multi-thread", "sync", "time"] }\n',
        'tokio = { version = "1.48", features = ["fs", "io-util", "macros", "net", "process", "rt-multi-thread", "sync", "time"] }\ntoml_edit = "0.22"\n',
        "daemon dependency marker",
    )
    write(cargo_path, cargo)

mcp_path = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_mcp.rs"
write(
    mcp_path,
    r'''use serde::Serialize;
use std::{
    env, fs,
    path::{Path, PathBuf},
};
use toml_edit::{DocumentMut, Item};

#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub(crate) struct CodexMcpStatus {
    pub(crate) configured: bool,
    pub(crate) available: bool,
    pub(crate) error: Option<String>,
}

pub(crate) fn inspect() -> CodexMcpStatus {
    let Some(home) = selected_codex_home() else {
        return CodexMcpStatus {
            error: Some("Codex home directory is not available.".to_string()),
            ..CodexMcpStatus::default()
        };
    };
    inspect_home(&home)
}

fn selected_codex_home() -> Option<PathBuf> {
    env::var_os("FENNARA_CODEX_HOME")
        .filter(|value| !value.is_empty())
        .or_else(|| env::var_os("CODEX_HOME").filter(|value| !value.is_empty()))
        .map(PathBuf::from)
        .or_else(|| {
            env::var_os("USERPROFILE")
                .or_else(|| env::var_os("HOME"))
                .map(PathBuf::from)
                .map(|path| path.join(".codex"))
        })
}

fn inspect_home(home: &Path) -> CodexMcpStatus {
    let config_path = home.join("config.toml");
    if !config_path.is_file() {
        return CodexMcpStatus::default();
    }
    let raw = match fs::read_to_string(&config_path) {
        Ok(raw) => raw,
        Err(error) => {
            return CodexMcpStatus {
                error: Some(format!("Could not read Codex MCP configuration: {error}")),
                ..CodexMcpStatus::default()
            };
        }
    };
    let document = match raw.parse::<DocumentMut>() {
        Ok(document) => document,
        Err(error) => {
            return CodexMcpStatus {
                error: Some(format!("Could not parse Codex MCP configuration: {error}")),
                ..CodexMcpStatus::default()
            };
        }
    };
    let Some(fennara) = document
        .get("mcp_servers")
        .and_then(Item::as_table_like)
        .and_then(|servers| servers.get("fennara"))
        .and_then(Item::as_table_like)
    else {
        return CodexMcpStatus::default();
    };
    let command = fennara
        .get("command")
        .and_then(Item::as_value)
        .and_then(|value| value.as_str())
        .map(str::trim)
        .filter(|value| !value.is_empty());
    let Some(command) = command else {
        return CodexMcpStatus {
            configured: true,
            error: Some("Codex has a Fennara MCP entry without a command.".to_string()),
            ..CodexMcpStatus::default()
        };
    };
    let available = command_is_available(command);
    CodexMcpStatus {
        configured: true,
        available,
        error: (!available).then(|| {
            "The Fennara MCP command configured for Codex is not available. Run MCP setup again."
                .to_string()
        }),
    }
}

fn command_is_available(command: &str) -> bool {
    let path = Path::new(command);
    if path.is_absolute() || path.components().count() > 1 {
        return path.is_file();
    }
    let Some(search_path) = env::var_os("PATH") else {
        return false;
    };
    env::split_paths(&search_path).any(|directory| {
        let direct = directory.join(command);
        if direct.is_file() {
            return true;
        }
        cfg!(windows)
            && ["exe", "cmd", "bat"]
                .iter()
                .any(|extension| directory.join(format!("{command}.{extension}")).is_file())
    })
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;

    static COUNTER: AtomicU64 = AtomicU64::new(0);

    fn test_home(name: &str) -> PathBuf {
        let path = env::temp_dir().join(format!(
            "fennara-codex-mcp-{name}-{}-{}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn missing_config_is_not_configured() {
        let home = test_home("missing");
        assert_eq!(inspect_home(&home), CodexMcpStatus::default());
        fs::remove_dir_all(home).unwrap();
    }

    #[test]
    fn valid_fennara_entry_is_available() {
        let home = test_home("valid");
        let command = home.join(if cfg!(windows) {
            "fennara-mcp.exe"
        } else {
            "fennara-mcp"
        });
        fs::write(&command, b"fixture").unwrap();
        fs::write(
            home.join("config.toml"),
            format!(
                "[mcp_servers.fennara]\ncommand = {:?}\nstartup_timeout_sec = 30\ntool_timeout_sec = 300\n",
                command.display().to_string()
            ),
        )
        .unwrap();
        let status = inspect_home(&home);
        assert!(status.configured);
        assert!(status.available);
        assert!(status.error.is_none());
        fs::remove_dir_all(home).unwrap();
    }

    #[test]
    fn missing_fennara_command_requires_repair() {
        let home = test_home("missing-command");
        fs::write(
            home.join("config.toml"),
            "[mcp_servers.fennara]\ncommand = \"missing-fennara-mcp\"\n",
        )
        .unwrap();
        let status = inspect_home(&home);
        assert!(status.configured);
        assert!(!status.available);
        assert!(status.error.is_some());
        fs::remove_dir_all(home).unwrap();
    }

    #[test]
    fn malformed_config_reports_error_without_panicking() {
        let home = test_home("malformed");
        fs::write(home.join("config.toml"), "[mcp_servers.fennara\n").unwrap();
        let status = inspect_home(&home);
        assert!(!status.available);
        assert!(status.error.is_some());
        fs::remove_dir_all(home).unwrap();
    }
}
''',
)

providers_path = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
providers = read(providers_path)
if "pub(crate) mod codex_mcp;" not in providers:
    providers = replace_once(
        providers,
        "pub(crate) mod codex_managed_runtime;\nmod codex_runtime;\n",
        "pub(crate) mod codex_managed_runtime;\npub(crate) mod codex_mcp;\nmod codex_runtime;\n",
        "Codex provider module marker",
    )
    write(providers_path, providers)

app_path = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
app = read(app_path)
if "pub(crate) mcp: codex_mcp::CodexMcpStatus" not in app:
    app = replace_once(
        app,
        "    codex_runtime::{self, CodexRuntimeMetadata},\n",
        "    codex_mcp,\n    codex_runtime::{self, CodexRuntimeMetadata},\n",
        "Codex runtime import",
    )
    app = replace_once(
        app,
        "    pub(crate) runtime: Option<CodexRuntimeMetadata>,\n",
        "    pub(crate) runtime: Option<CodexRuntimeMetadata>,\n    pub(crate) mcp: codex_mcp::CodexMcpStatus,\n",
        "Codex account runtime field",
    )
    app = replace_once(
        app,
        "        runtime: runtime.clone(),\n    });\n",
        "        runtime: runtime.clone(),\n        mcp: codex_mcp::inspect(),\n    });\n",
        "signing-in account status",
    )
    app = replace_once(
        app,
        "        runtime: connection.runtime.clone(),\n        ..CodexAccountStatus::default()\n",
        "        runtime: connection.runtime.clone(),\n        mcp: codex_mcp::inspect(),\n        ..CodexAccountStatus::default()\n",
        "logout account status",
    )
    app = replace_once(
        app,
        "                    error: None,\n                    runtime: None,\n                };",
        "                    error: None,\n                    runtime: None,\n                    mcp: codex_mcp::inspect(),\n                };",
        "login completion account update",
    )
    app = replace_once(
        app,
        "        error,\n        runtime: None,\n    }\n}\n\nfn attach_runtime",
        "        error,\n        runtime: None,\n        mcp: codex_mcp::inspect(),\n    }\n}\n\nfn attach_runtime",
        "decoded account status",
    )
    app = replace_once(
        app,
        "    status.runtime = runtime.cloned();\n    status\n",
        "    status.runtime = runtime.cloned();\n    status.mcp = codex_mcp::inspect();\n    status\n",
        "runtime attachment",
    )
    write(app_path, app)

chat_path = "local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs"
chat = read(chat_path)
if '"codex_mcp_setup" =>' not in chat:
    marker = '        "codex_account_status" => match providers::codex_app_server::account_status().await {\n'
    block = '''        "codex_mcp_status" => {
            send_json(
                sender,
                json!({
                    "type": "codex_mcp_status",
                    "request_id": request_id,
                    "status": providers::codex_mcp::inspect()
                }),
            )
            .await
        }
        "codex_mcp_setup" => match mcp_setup::run("codex").await {
            Ok(result) => {
                send_json(
                    sender,
                    json!({
                        "type": "codex_mcp_setup_completed",
                        "request_id": request_id,
                        "status": providers::codex_mcp::inspect(),
                        "report": result.report,
                        "warning": result.warning
                    }),
                )
                .await
            }
            Err(error) => send_error(sender, request_id, "codex_mcp_setup_failed", &error).await,
        },
'''
    chat = replace_once(chat, marker, block + marker, "Codex account handler")
    write(chat_path, chat)

for ui_path in ["ui/chat/app.js", "godot_demo/addons/fennara/dist/app.js"]:
    ui = read(ui_path)
    if "codexMcpSetupRequested" in ui:
        continue
    ui = replace_once(
        ui,
        "  let codexRuntimeInstallRequested = false;\n  let canRevert = false;\n",
        "  let codexRuntimeInstallRequested = false;\n  let codexMcpSetupRequested = false;\n  let canRevert = false;\n",
        f"{ui_path} Codex state",
    )
    ui = replace_once(
        ui,
        '''      if (account.signing_in) {
        return "Waiting for browser login · click to cancel";
      }
      if (provider.connected) {
''',
        '''      if (account.signing_in) {
        return "Waiting for browser login · click to cancel";
      }
      const mcp = account.mcp || null;
      if (mcp && !mcp.available) {
        if (mcp.configured) {
          return "Fennara MCP is unavailable · click to repair Godot tools";
        }
        return "Set up Fennara MCP for Godot tools";
      }
      if (provider.connected) {
''',
        f"{ui_path} account status",
    )
    ui = replace_once(
        ui,
        '''    if (!provider.connected) {
      const runtimeAvailable = provider.account?.installed !== false || codexRuntimeStatus?.installed;
''',
        '''    if (provider.account?.signing_in) {
      appendSystem("Cancelling Codex ChatGPT login...");
      send({
        type: "codex_login_cancel",
        request_id: nextRequestId("codex-login-cancel"),
      });
      return;
    }
    const mcp = provider.account?.mcp || null;
    if (mcp && !mcp.available) {
      codexMcpSetupRequested = !provider.connected;
      appendSystem(mcp.configured
        ? "Repairing Fennara MCP access for Codex..."
        : "Setting up Fennara MCP access for Codex...");
      send({
        type: "codex_mcp_setup",
        request_id: nextRequestId("codex-mcp-setup"),
      });
      return;
    }
    if (!provider.connected) {
      const runtimeAvailable = provider.account?.installed !== false || codexRuntimeStatus?.installed;
''',
        f"{ui_path} provider action",
    )
    old_cancel = '''      if (provider.account?.signing_in) {
        appendSystem("Cancelling Codex ChatGPT login...");
        send({
          type: "codex_login_cancel",
          request_id: nextRequestId("codex-login-cancel"),
        });
        return;
      }
'''
    if ui.count(old_cancel) != 1:
        raise RuntimeError(f"{ui_path}: expected one obsolete inner login cancellation block")
    ui = ui.replace(old_cancel, "", 1)
    ui = replace_once(
        ui,
        '''    if (message.type === "codex_runtime_status") {
''',
        '''    if (message.type === "codex_mcp_setup_completed") {
      const shouldStartLogin = codexMcpSetupRequested && !providerConnected("codex");
      codexMcpSetupRequested = false;
      appendSystem(message.warning || "Fennara MCP is ready for Codex Godot tools.");
      requestCodexAccountStatus();
      if (shouldStartLogin) {
        send({
          type: "codex_login_start",
          request_id: nextRequestId("codex-login-after-mcp-setup"),
        });
      }
      return;
    }
    if (message.type === "codex_mcp_status") {
      requestCodexAccountStatus();
      return;
    }
    if (message.type === "codex_runtime_status") {
''',
        f"{ui_path} daemon message",
    )
    ui = replace_once(
        ui,
        '''      if (requestId.startsWith("codex-runtime")) {
        codexRuntimeInstallRequested = false;
        stopCodexRuntimePolling();
        requestCodexRuntimeStatus();
      }
''',
        '''      if (requestId.startsWith("codex-runtime")) {
        codexRuntimeInstallRequested = false;
        stopCodexRuntimePolling();
        requestCodexRuntimeStatus();
      }
      if (requestId.startsWith("codex-mcp-setup")) {
        codexMcpSetupRequested = false;
        requestCodexAccountStatus();
      }
''',
        f"{ui_path} error handler",
    )
    write(ui_path, ui)

assets_path = "local/crates/fennara-daemon/src/runtime_daemon/chat/assets.rs"
assets = read(assets_path)
if '"codex_mcp_setup"' not in assets:
    assets = replace_once(
        assets,
        '            "codex_runtime_status",\n',
        '            "codex_runtime_status",\n            "codex_mcp_setup",\n            "codex_mcp_setup_completed",\n',
        "embedded Codex UI marker",
    )
    write(assets_path, assets)

print("Codex MCP readiness integration applied")
