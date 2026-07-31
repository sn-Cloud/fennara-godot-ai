from pathlib import Path

path = Path(__file__).resolve().parents[2] / "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs"
content = path.read_text(encoding="utf-8")

old_import = '''use std::{
    env,
    path::{Path, PathBuf},
};
'''
new_import = '''use std::{
    env,
    ffi::OsString,
    path::{Path, PathBuf},
};
'''
if content.count(old_import) != 1:
    raise RuntimeError("expected one codex runtime import block")
content = content.replace(old_import, new_import, 1)

old_helper = '''fn windows_app_server_command_line(executable: &Path) -> String {
    format!("\\\"\\\"{}\\\" app-server --stdio\\\"", executable.display())
}
'''
new_helper = '''fn windows_batch_command_args(executable: &Path) -> Vec<OsString> {
    vec![
        OsString::from("/D"),
        OsString::from("/C"),
        OsString::from("call"),
        executable.as_os_str().to_os_string(),
        OsString::from("app-server"),
        OsString::from("--stdio"),
    ]
}
'''
if content.count(old_helper) != 1:
    raise RuntimeError("expected one Windows command line helper")
content = content.replace(old_helper, new_helper, 1)

old_command = '''    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command
            .args(["/D", "/S", "/C"])
            .arg(windows_app_server_command_line(&runtime.executable));
        return Ok(command);
    }
'''
new_command = '''    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command.args(windows_batch_command_args(&runtime.executable));
        return Ok(command);
    }
'''
if content.count(old_command) != 1:
    raise RuntimeError("expected one Windows batch launch block")
content = content.replace(old_command, new_command, 1)

old_test = '''    #[test]
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
'''
new_test = '''    #[test]
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
'''
if content.count(old_test) != 1:
    raise RuntimeError("expected one Windows launch unit test")
content = content.replace(old_test, new_test, 1)

path.write_text(content, encoding="utf-8", newline="\n")
