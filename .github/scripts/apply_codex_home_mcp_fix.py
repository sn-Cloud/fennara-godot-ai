from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "local/crates/fennara-cli/src/mcp_setup.rs"
content = TARGET.read_text(encoding="utf-8")

old = '''fn codex_config_path() -> Result<PathBuf, String> {
    home_dir()
        .map(|path| path.join(".codex").join("config.toml"))
        .ok_or_else(|| "home directory is not available".to_string())
}
'''
new = '''fn codex_config_path() -> Result<PathBuf, String> {
    let fennara_home = env::var_os("FENNARA_CODEX_HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);
    let codex_home = env::var_os("CODEX_HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);
    resolve_codex_home(fennara_home, codex_home, home_dir()).map(|path| path.join("config.toml"))
}

fn resolve_codex_home(
    fennara_home: Option<PathBuf>,
    codex_home: Option<PathBuf>,
    user_home: Option<PathBuf>,
) -> Result<PathBuf, String> {
    fennara_home
        .or(codex_home)
        .or_else(|| user_home.map(|path| path.join(".codex")))
        .ok_or_else(|| "Codex home directory is not available".to_string())
}
'''
if old not in content:
    if "fn resolve_codex_home(" not in content:
        raise RuntimeError("expected Codex config path block was not found")
else:
    content = content.replace(old, new, 1)

marker = "fn codex_home_prefers_fennara_specific_override()"
if marker not in content:
    content = content.rstrip() + r'''

#[cfg(test)]
mod codex_home_tests {
    use super::*;

    #[test]
    fn codex_home_prefers_fennara_specific_override() {
        let resolved = resolve_codex_home(
            Some(PathBuf::from("fennara-home")),
            Some(PathBuf::from("codex-home")),
            Some(PathBuf::from("user-home")),
        )
        .unwrap();
        assert_eq!(resolved, PathBuf::from("fennara-home"));
    }

    #[test]
    fn codex_home_uses_codex_home_when_fennara_override_is_absent() {
        let resolved = resolve_codex_home(
            None,
            Some(PathBuf::from("codex-home")),
            Some(PathBuf::from("user-home")),
        )
        .unwrap();
        assert_eq!(resolved, PathBuf::from("codex-home"));
    }

    #[test]
    fn codex_home_defaults_to_dot_codex_under_user_home() {
        let resolved = resolve_codex_home(None, None, Some(PathBuf::from("user-home"))).unwrap();
        assert_eq!(resolved, PathBuf::from("user-home").join(".codex"));
    }

    #[test]
    fn codex_home_reports_clear_error_without_any_home_source() {
        let error = resolve_codex_home(None, None, None).unwrap_err();
        assert!(error.contains("Codex home directory"));
    }

    #[test]
    fn codex_mcp_entry_preserves_unrelated_configuration() {
        let mut document = r#"
model = "gpt-test"

[mcp_servers.other]
command = "other-mcp"
"#
        .parse::<DocumentMut>()
        .unwrap();
        upsert_codex_fennara_entry(&mut document, Path::new("/opt/fennara-mcp")).unwrap();
        assert_eq!(document["model"].as_str(), Some("gpt-test"));
        assert_eq!(
            document["mcp_servers"]["other"]["command"].as_str(),
            Some("other-mcp")
        );
        assert_eq!(
            document["mcp_servers"]["fennara"]["command"].as_str(),
            Some("/opt/fennara-mcp")
        );
        assert_eq!(
            document["mcp_servers"]["fennara"]["startup_timeout_sec"].as_integer(),
            Some(MCP_STARTUP_TIMEOUT_SEC)
        );
        assert_eq!(
            document["mcp_servers"]["fennara"]["tool_timeout_sec"].as_integer(),
            Some(MCP_TOOL_TIMEOUT_SEC)
        );
    }
}
''' + "\n"

TARGET.write_text(content, encoding="utf-8", newline="\n")
print("Codex MCP home ownership fix applied")
