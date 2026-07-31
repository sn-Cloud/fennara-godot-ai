use std::{
    env,
    path::{Path, PathBuf},
};

use serde::Serialize;
use tokio::process::Command;

use super::error::LlmError;

pub(crate) const PINNED_CODEX_VERSION: &str = "0.144.4";
pub(crate) const CODEX_COMMAND_ENV: &str = "FENNARA_CODEX_COMMAND";
pub(crate) const FENNARA_CODEX_HOME_ENV: &str = "FENNARA_CODEX_HOME";
pub(crate) const CODEX_HOME_ENV: &str = "CODEX_HOME";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum CodexRuntimePlatform {
    Windows,
    Linux,
    Macos,
    Unsupported,
}

impl CodexRuntimePlatform {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Windows => "windows",
            Self::Linux => "linux",
            Self::Macos => "macos",
            Self::Unsupported => "unsupported",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum CodexRuntimeSource {
    Configured,
    Path,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum CodexCompatibility {
    Tested,
    CompatibleUnverified,
    Unknown,
}

#[derive(Clone, Debug)]
pub(crate) struct CodexRuntimeSpec {
    pub(crate) executable: PathBuf,
    pub(crate) source: CodexRuntimeSource,
    pub(crate) platform: CodexRuntimePlatform,
    pub(crate) codex_home: Option<PathBuf>,
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct CodexRuntimeMetadata {
    pub(crate) version: Option<String>,
    pub(crate) compatibility: CodexCompatibility,
    pub(crate) pinned_version: &'static str,
    pub(crate) source: CodexRuntimeSource,
    pub(crate) platform: CodexRuntimePlatform,
    pub(crate) codex_home: Option<String>,
    pub(crate) server_platform_family: Option<String>,
    pub(crate) server_platform_os: Option<String>,
}

pub(crate) fn resolve_runtime() -> Result<CodexRuntimeSpec, LlmError> {
    let platform = current_platform();
    if platform == CodexRuntimePlatform::Unsupported {
        return Err(provider_init(format!(
            "The embedded Codex provider is not supported on {} yet.",
            env::consts::OS
        )));
    }

    let codex_home = configured_codex_home()?;
    if let Some(configured) = env::var_os(CODEX_COMMAND_ENV).filter(|value| !value.is_empty()) {
        let executable = expand_home(PathBuf::from(configured));
        if !is_executable_candidate(&executable) {
            return Err(provider_init(format!(
                "{CODEX_COMMAND_ENV} does not point to a Codex executable: {}",
                executable.display()
            )));
        }
        return Ok(CodexRuntimeSpec {
            executable,
            source: CodexRuntimeSource::Configured,
            platform,
            codex_home,
        });
    }

    let search_path = env::var_os("PATH").ok_or_else(|| {
        provider_init("PATH is not available, so the Codex CLI cannot be discovered.".to_string())
    })?;
    for directory in env::split_paths(&search_path) {
        for name in executable_names(platform) {
            let candidate = directory.join(name);
            if is_executable_candidate(&candidate) {
                return Ok(CodexRuntimeSpec {
                    executable: candidate,
                    source: CodexRuntimeSource::Path,
                    platform,
                    codex_home,
                });
            }
        }
    }

    Err(provider_init(
        "Codex CLI was not found. Install @openai/codex or set FENNARA_CODEX_COMMAND.".to_string(),
    ))
}

pub(crate) fn build_app_server_command(runtime: &CodexRuntimeSpec) -> Result<Command, LlmError> {
    let mut command = platform_app_server_command(runtime)?;
    if let Some(codex_home) = runtime.codex_home.as_ref() {
        command.env(CODEX_HOME_ENV, codex_home);
    }
    Ok(command)
}

pub(crate) fn metadata_from_initialize(
    runtime: &CodexRuntimeSpec,
    initialize: &serde_json::Value,
) -> CodexRuntimeMetadata {
    let user_agent = initialize
        .get("userAgent")
        .and_then(serde_json::Value::as_str);
    let version = user_agent.and_then(parse_codex_version);
    let compatibility = compatibility_for_version(version.as_deref());
    let codex_home = initialize
        .get("codexHome")
        .and_then(serde_json::Value::as_str)
        .map(ToString::to_string)
        .or_else(|| {
            runtime
                .codex_home
                .as_ref()
                .map(|path| path.display().to_string())
        });
    CodexRuntimeMetadata {
        version,
        compatibility,
        pinned_version: PINNED_CODEX_VERSION,
        source: runtime.source,
        platform: runtime.platform,
        codex_home,
        server_platform_family: initialize
            .get("platformFamily")
            .and_then(serde_json::Value::as_str)
            .map(ToString::to_string),
        server_platform_os: initialize
            .get("platformOs")
            .and_then(serde_json::Value::as_str)
            .map(ToString::to_string),
    }
}

pub(crate) fn parse_codex_version(user_agent: &str) -> Option<String> {
    user_agent
        .split(|character: char| {
            character.is_whitespace()
                || matches!(character, '/' | '(' | ')' | '[' | ']' | ';' | ',')
        })
        .map(|candidate| candidate.trim_start_matches('v'))
        .find(|candidate| looks_like_version(candidate))
        .map(ToString::to_string)
}

pub(crate) fn compatibility_for_version(version: Option<&str>) -> CodexCompatibility {
    match version {
        Some(version) if version == PINNED_CODEX_VERSION => CodexCompatibility::Tested,
        Some(_) => CodexCompatibility::CompatibleUnverified,
        None => CodexCompatibility::Unknown,
    }
}

fn configured_codex_home() -> Result<Option<PathBuf>, LlmError> {
    let configured = env::var_os(FENNARA_CODEX_HOME_ENV)
        .filter(|value| !value.is_empty())
        .or_else(|| env::var_os(CODEX_HOME_ENV).filter(|value| !value.is_empty()));
    let Some(configured) = configured else {
        return Ok(None);
    };
    let path = expand_home(PathBuf::from(configured));
    if !path.is_dir() {
        return Err(provider_init(format!(
            "Configured CODEX_HOME is not a directory: {}",
            path.display()
        )));
    }
    Ok(Some(path))
}

fn expand_home(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();
    let remainder = text.strip_prefix("~/").or_else(|| text.strip_prefix("~\\"));
    let Some(remainder) = remainder else {
        return path;
    };
    let Some(home) = env::var_os("HOME").or_else(|| env::var_os("USERPROFILE")) else {
        return path;
    };
    PathBuf::from(home).join(remainder)
}

fn current_platform() -> CodexRuntimePlatform {
    if cfg!(windows) {
        CodexRuntimePlatform::Windows
    } else if cfg!(target_os = "linux") {
        CodexRuntimePlatform::Linux
    } else if cfg!(target_os = "macos") {
        CodexRuntimePlatform::Macos
    } else {
        CodexRuntimePlatform::Unsupported
    }
}

fn executable_names(platform: CodexRuntimePlatform) -> &'static [&'static str] {
    match platform {
        CodexRuntimePlatform::Windows => &["codex.exe", "codex.cmd", "codex.bat"],
        CodexRuntimePlatform::Linux | CodexRuntimePlatform::Macos => &["codex"],
        CodexRuntimePlatform::Unsupported => &[],
    }
}

fn windows_app_server_command_line(executable: &Path) -> String {
    format!("\"\"{}\" app-server --stdio\"", executable.display())
}

#[cfg(windows)]
fn platform_app_server_command(runtime: &CodexRuntimeSpec) -> Result<Command, LlmError> {
    let extension = runtime
        .executable
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command
            .args(["/D", "/S", "/C"])
            .arg(windows_app_server_command_line(&runtime.executable));
        return Ok(command);
    }
    let mut command = Command::new(&runtime.executable);
    command.args(["app-server", "--stdio"]);
    Ok(command)
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
fn platform_app_server_command(runtime: &CodexRuntimeSpec) -> Result<Command, LlmError> {
    let mut command = Command::new(&runtime.executable);
    command.args(["app-server", "--stdio"]);
    Ok(command)
}

#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
fn platform_app_server_command(_runtime: &CodexRuntimeSpec) -> Result<Command, LlmError> {
    Err(provider_init(format!(
        "The embedded Codex provider is not supported on {} yet.",
        env::consts::OS
    )))
}

fn is_executable_candidate(path: &Path) -> bool {
    path.is_file()
}

fn looks_like_version(candidate: &str) -> bool {
    let core = candidate
        .split_once('-')
        .map_or(candidate, |(core, _)| core);
    let parts = core.split('.').collect::<Vec<_>>();
    parts.len() >= 3
        && parts
            .iter()
            .take(3)
            .all(|part| !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit()))
}

fn provider_init(message: String) -> LlmError {
    LlmError::ProviderInit {
        provider: "Codex".to_string(),
        message,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_version_from_codex_user_agent() {
        assert_eq!(
            parse_codex_version("codex_cli_rs/0.144.4 (linux; x86_64)"),
            Some("0.144.4".to_string())
        );
        assert_eq!(
            parse_codex_version("fennara codex/0.145.0-alpha.13"),
            Some("0.145.0-alpha.13".to_string())
        );
    }

    #[test]
    fn classifies_pinned_and_unverified_versions() {
        assert_eq!(
            compatibility_for_version(Some(PINNED_CODEX_VERSION)),
            CodexCompatibility::Tested
        );
        assert_eq!(
            compatibility_for_version(Some("0.145.0-alpha.13")),
            CodexCompatibility::CompatibleUnverified
        );
        assert_eq!(compatibility_for_version(None), CodexCompatibility::Unknown);
    }

    #[test]
    fn windows_batch_command_line_uses_cmd_outer_quotes() {
        let command =
            windows_app_server_command_line(Path::new("C:/Program Files/Codex/codex.cmd"));
        assert!(command.starts_with("\"\""), "{command}");
        assert!(
            command.contains("codex.cmd\" app-server --stdio"),
            "{command}"
        );
        assert!(command.ends_with("--stdio\""), "{command}");
    }

    #[test]
    fn platform_names_are_explicit() {
        assert_eq!(CodexRuntimePlatform::Windows.as_str(), "windows");
        assert_eq!(CodexRuntimePlatform::Linux.as_str(), "linux");
        assert_eq!(CodexRuntimePlatform::Macos.as_str(), "macos");
        assert_eq!(CodexRuntimePlatform::Unsupported.as_str(), "unsupported");
    }
}
