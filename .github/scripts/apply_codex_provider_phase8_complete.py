from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs"
content = TARGET.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global content
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"codex_runtime.rs: expected one match, found {count}: {old[:160]!r}")
    content = content.replace(old, new, 1)


replace_once(
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

TARGET.write_text(content, encoding="utf-8", newline="\n")
print("final Windows runtime migration applied")
