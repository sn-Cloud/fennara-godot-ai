from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one {label}, found {count}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")

cargo = ROOT / "local/crates/fennara-daemon/Cargo.toml"
content = cargo.read_text(encoding="utf-8")
if 'toml_edit = "0.22"' not in content:
    replace_once(
        cargo,
        'tokio = { version = "1.48", features = ["fs", "io-util", "macros", "net", "process", "rt-multi-thread", "sync", "time"] }\n',
        'tokio = { version = "1.48", features = ["fs", "io-util", "macros", "net", "process", "rt-multi-thread", "sync", "time"] }\ntoml_edit = "0.22"\n',
        "daemon dependency marker",
    )

module = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_mcp.rs"
module.write_text(r'''use serde::Serialize;
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
        let command = home.join(if cfg!(windows) { "fennara-mcp.exe" } else { "fennara-mcp" });
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
''', encoding="utf-8", newline="\n")

providers = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
content = providers.read_text(encoding="utf-8")
if "pub(crate) mod codex_mcp;" not in content:
    replace_once(
        providers,
        "pub(crate) mod codex_managed_runtime;\nmod codex_runtime;\n",
        "pub(crate) mod codex_managed_runtime;\npub(crate) mod codex_mcp;\nmod codex_runtime;\n",
        "Codex provider module marker",
    )

app_server = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs"
content = app_server.read_text(encoding="utf-8")
if "pub(crate) mcp: codex_mcp::CodexMcpStatus" not in content:
    content = content.replace(
        "    codex_runtime::{self, CodexRuntimeMetadata},\n",
        "    codex_mcp,\n    codex_runtime::{self, CodexRuntimeMetadata},\n",
        1,
    )
    content = content.replace(
        "    pub(crate) runtime: Option<CodexRuntimeMetadata>,\n",
        "    pub(crate) runtime: Option<CodexRuntimeMetadata>,\n    pub(crate) mcp: codex_mcp::CodexMcpStatus,\n",
        1,
    )
    content = content.replace(
        "                error: Some(error.user_message()),\n                ..CodexAccountStatus::default()\n",
        "                error: Some(error.user_message()),\n                mcp: codex_mcp::inspect(),\n                ..CodexAccountStatus::default()\n",
        1,
    )
    content = content.replace(
        "        runtime: runtime.clone(),\n    });\n",
        "        runtime: runtime.clone(),\n        mcp: codex_mcp::inspect(),\n    });\n",
        1,
    )
    content = content.replace(
        "        runtime: connection.runtime.clone(),\n        ..CodexAccountStatus::default()\n",
        "        runtime: connection.runtime.clone(),\n        mcp: codex_mcp::inspect(),\n        ..CodexAccountStatus::default()\n",
        1,
    )
    content = content.replace(
        "    status.runtime = runtime.cloned();\n    status\n",
        "    status.runtime = runtime.cloned();\n    status.mcp = codex_mcp::inspect();\n    status\n",
        1,
    )
    app_server.write_text(content, encoding="utf-8", newline="\n")

chat = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs"
content = chat.read_text(encoding="utf-8")
if '"codex_mcp_setup" =>' not in content:
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
    if marker not in content:
        raise RuntimeError("chat Codex account status handler marker not found")
    chat.write_text(content.replace(marker, block + marker, 1), encoding="utf-8", newline="\n")

for relative in ["ui/chat/app.js", "godot_demo/addons/fennara/dist/app.js"]:
    path = ROOT / relative
    content = path.read_text(encoding="utf-8")
    if "codexMcpSetupRequested" not in content:
        content = content.replace(
            "  let codexRuntimeInstallRequested = false;\n  let canRevert = false;\n",
            "  let codexRuntimeInstallRequested = false;\n  let codexMcpSetupRequested = false;\n  let canRevert = false;\n",
            1,
        )
        content = content.replace(
            '''      if (account.signing_in) {
        return "Waiting for browser login · click to cancel";
      }
''',
            '''      const mcp = account.mcp || null;
      if (mcp && !mcp.available) {
        if (mcp.configured) {
          return "Fennara MCP is unavailable · click to repair Godot tools";
        }
        return "Set up Fennara MCP for Godot tools";
      }
      if (account.signing_in) {
        return "Waiting for browser login · click to cancel";
      }
''',
            1,
        )
        content = content.replace(
            '''    if (!provider.connected) {
      const runtimeAvailable = provider.account?.installed !== false || codexRuntimeStatus?.installed;
''',
            '''    const mcp = provider.account?.mcp || null;
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
            1,
        )
        content = content.replace(
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
            1,
        )
        content = content.replace(
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
            1,
        )
        path.write_text(content, encoding="utf-8", newline="\n")

assets = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/assets.rs"
content = assets.read_text(encoding="utf-8")
if '"codex_mcp_setup"' not in content:
    content = content.replace(
        '            "codex_runtime_status",\n',
        '            "codex_runtime_status",\n            "codex_mcp_setup",\n            "codex_mcp_setup_completed",\n',
        1,
    )
    assets.write_text(content, encoding="utf-8", newline="\n")

print("Codex MCP readiness integration applied")
