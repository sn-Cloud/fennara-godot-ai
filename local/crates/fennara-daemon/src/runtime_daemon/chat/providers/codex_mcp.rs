use serde::Serialize;
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
