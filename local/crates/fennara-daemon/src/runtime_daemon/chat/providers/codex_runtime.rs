//! Managed Codex updates are opt-in by installation layout, never global installs.
use crate::runtime_daemon::util::fennara_app_dir;
use serde_json::Value;
use std::{
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

// Called when Codex is used/discovered. Keep update I/O off the chat path; the CLI
// serializes checks across processes and persists the six-hour retry interval.
pub(super) fn check_in_background() {
    static LAST_ATTEMPT: AtomicU64 = AtomicU64::new(0);
    if !cfg!(all(windows, target_arch = "x86_64"))
        || std::env::var_os("FENNARA_CODEX_COMMAND").is_some()
        || std::env::var_os("FENNARA_CODEX_AUTO_UPDATE_DISABLED").is_some()
    {
        return;
    }
    let Some(parent) = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
    else {
        return;
    };
    if !parent.join("codex/codex-package.json").is_file() || !parent.join("fennara.exe").is_file() {
        return;
    }
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let previous = LAST_ATTEMPT.load(Ordering::Relaxed);
    if now.saturating_sub(previous) < 6 * 60 * 60
        || LAST_ATTEMPT
            .compare_exchange(previous, now, Ordering::Relaxed, Ordering::Relaxed)
            .is_err()
    {
        return;
    }
    tokio::spawn(async move {
        let mut command = tokio::process::Command::new(parent.join("fennara.exe"));
        command
            .arg("codex-update")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let _ = command.status().await;
    });
}

// Select a newer managed runtime for new connections only. A bad/missing pointer
// falls back to the bundled runtime; explicit user overrides still win upstream.
pub(super) fn managed_command(bundled: &Path) -> Option<PathBuf> {
    let root = fennara_app_dir().ok()?.join("codex-runtime");
    managed_command_at(&root, bundled)
}

fn managed_command_at(root: &Path, bundled: &Path) -> Option<PathBuf> {
    let pointer: Value =
        serde_json::from_slice(&std::fs::read(root.join("current.json")).ok()?).ok()?;
    let version = pointer["version"].as_str()?;
    let parts = numeric_version(version)?;
    let metadata: Value =
        serde_json::from_slice(&std::fs::read(bundled.join("codex-package.json")).ok()?).ok()?;
    if parts <= numeric_version(metadata["version"].as_str()?)? {
        return None;
    }
    let command = root.join(version).join("bin/codex.exe");
    let active = root.join(version);
    let active_metadata: Value =
        serde_json::from_slice(&std::fs::read(active.join("codex-package.json")).ok()?).ok()?;
    (active_metadata["version"] == version
        && command.is_file()
        && active
            .join("codex-resources/codex-command-runner.exe")
            .is_file()
        && active
            .join("codex-resources/codex-windows-sandbox-setup.exe")
            .is_file())
    .then_some(command)
}

fn numeric_version(version: &str) -> Option<Vec<u64>> {
    let parts: Option<Vec<u64>> = version
        .split('.')
        .map(|v| {
            if !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit()) {
                v.parse().ok()
            } else {
                None
            }
        })
        .collect();
    parts.filter(|v| v.len() == 3)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn managed_selection_requires_a_complete_newer_runtime() {
        let root =
            std::env::temp_dir().join(format!("fennara-managed-codex-test-{}", std::process::id()));
        let bundled = root.join("bundled");
        std::fs::create_dir_all(&bundled).unwrap();
        std::fs::write(
            bundled.join("codex-package.json"),
            br#"{"version":"0.155.1"}"#,
        )
        .unwrap();
        std::fs::write(root.join("current.json"), br#"{"version":"0.156.0"}"#).unwrap();
        assert!(managed_command_at(&root, &bundled).is_none());
        let active = root.join("0.156.0");
        for file in [
            "bin/codex.exe",
            "codex-resources/codex-command-runner.exe",
            "codex-resources/codex-windows-sandbox-setup.exe",
        ] {
            let path = active.join(file);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, b"fixture").unwrap();
        }
        std::fs::write(
            active.join("codex-package.json"),
            br#"{"version":"0.156.0"}"#,
        )
        .unwrap();
        assert_eq!(
            managed_command_at(&root, &bundled),
            Some(active.join("bin/codex.exe"))
        );
        std::fs::write(
            bundled.join("codex-package.json"),
            br#"{"version":"0.157.0"}"#,
        )
        .unwrap();
        assert!(managed_command_at(&root, &bundled).is_none());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn pointer_version_cannot_escape_managed_root() {
        for value in ["../0.155.1", "C:/runtime", "0.155.1-alpha", "0.155"] {
            assert!(numeric_version(value).is_none());
        }
        assert!(numeric_version("0.156.0") > numeric_version("0.155.1"));
    }
}
