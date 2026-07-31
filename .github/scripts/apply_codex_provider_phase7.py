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


RUNTIME = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs"
replace_once(
    RUNTIME,
    '''    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command.args(["/D", "/S", "/C"]).arg(format!(
            "\\\"{}\\\" app-server --stdio",
            runtime.executable.display()
        ));
        return Ok(command);
    }
''',
    '''    if matches!(extension.as_str(), "cmd" | "bat") {
        let mut command = Command::new("cmd.exe");
        command
            .args(["/D", "/S", "/C"])
            .arg(windows_app_server_command_line(&runtime.executable));
        return Ok(command);
    }
''',
)
replace_once(
    RUNTIME,
    '''#[cfg(windows)]
fn platform_app_server_command(runtime: &CodexRuntimeSpec) -> Result<Command, LlmError> {
''',
    '''fn windows_app_server_command_line(executable: &Path) -> String {
    format!("\\\"\\\"{}\\\" app-server --stdio\\\"", executable.display())
}

#[cfg(windows)]
fn platform_app_server_command(runtime: &CodexRuntimeSpec) -> Result<Command, LlmError> {
''',
)
replace_once(
    RUNTIME,
    '''    #[test]
    fn platform_names_are_explicit() {
''',
    '''    #[test]
    fn windows_batch_command_line_uses_cmd_outer_quotes() {
        let command = windows_app_server_command_line(Path::new("C:/Program Files/Codex/codex.cmd"));
        assert!(command.starts_with("\\\"\\\""), "{command}");
        assert!(command.contains("codex.cmd\\\" app-server --stdio"), "{command}");
        assert!(command.ends_with("--stdio\\\""), "{command}");
    }

    #[test]
    fn platform_names_are_explicit() {
''',
)

PROVIDERS = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs"
replace_once(
    PROVIDERS,
    '''    fn custom_provider_config() -> custom::CustomProviderConfig {
''',
    '''    #[test]
    fn burst_text_events_are_coalesced_before_ui_delivery() {
        let mut accumulator = StreamAccumulator::default();
        let mut intermediate_updates = 0usize;
        for _ in 0..10_000 {
            intermediate_updates += accumulator
                .items_for_event(StreamEvent::TextDelta {
                    id: "codex-agent".to_string(),
                    text: "x".to_string(),
                })
                .unwrap()
                .len();
        }
        let final_items = accumulator
            .items_for_event(StreamEvent::Finish {
                reason: FinishReason::Stop,
                usage: None,
            })
            .unwrap();
        assert!(
            intermediate_updates <= 417,
            "10,000 byte deltas produced {intermediate_updates} UI updates"
        );
        let final_text = final_items
            .iter()
            .find_map(|item| match item {
                StreamItem::Text { content, done: true } => Some(content),
                _ => None,
            })
            .expect("final coalesced text item");
        assert_eq!(final_text.len(), 10_000);
    }

    fn custom_provider_config() -> custom::CustomProviderConfig {
''',
)

INTEGRATION = "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs"
replace_once(
    INTEGRATION,
    '''#[tokio::test]
async fn invalid_json_is_reported_as_provider_output_error() {
''',
    '''#[tokio::test]
async fn multiple_app_server_sessions_are_isolated() {
    let (_first_fixture, mut first) = spawn_fixture("authenticated", None).await;
    let (_second_fixture, mut second) = spawn_fixture("authenticated", None).await;
    let first_thread = start_thread(&mut first).await;
    let second_thread = start_thread(&mut second).await;
    assert_ne!(first_thread, second_thread);
    start_turn(&mut first, &first_thread).await;
    start_turn(&mut second, &second_thread).await;
    let (first_events, second_events) = tokio::join!(drain_turn(&mut first), drain_turn(&mut second));
    assert!(first_events.completed);
    assert!(second_events.completed);
    assert_eq!(first_events.deltas, 2);
    assert_eq!(second_events.deltas, 2);
    first.shutdown().await;
    second.shutdown().await;
}

#[tokio::test]
async fn invalid_json_is_reported_as_provider_output_error() {
''',
)

print("phase seven migration applied")
