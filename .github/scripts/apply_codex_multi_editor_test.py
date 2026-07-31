from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


tests = Path(
    "local/crates/fennara-daemon/src/runtime_daemon/chat/providers/"
    "codex_app_server/integration_tests.rs"
)
marker = '''#[tokio::test]
async fn turn_interrupt_finishes_and_reaps_the_app_server() {'''
addition = '''#[test]
fn multiple_godot_project_scopes_keep_codex_bindings_isolated() {
    let suffix = FIXTURE_COUNTER.fetch_add(1, Ordering::Relaxed);
    let first_scope = store::ProjectScope {
        project_path: Some(format!("/tmp/fennara-editor-first-{suffix}")),
        project_name: Some(format!("First editor {suffix}")),
    };
    let second_scope = store::ProjectScope {
        project_path: Some(format!("/tmp/fennara-editor-second-{suffix}")),
        project_name: Some(format!("Second editor {suffix}")),
    };
    let first_chat = store::create_chat(
        &first_scope,
        "codex/gpt-5.5-codex",
        "medium",
        &[],
    )
    .expect("create first editor chat");
    let second_chat = store::create_chat(
        &second_scope,
        "codex/gpt-5.5-codex",
        "medium",
        &[],
    )
    .expect("create second editor chat");

    store::upsert_provider_session_binding(
        &first_chat.chat.id,
        "codex",
        "thread-editor-first",
        "/tmp/codex-home-first",
        Some("0.144.4"),
    )
    .expect("bind first editor");
    store::upsert_provider_session_binding(
        &second_chat.chat.id,
        "codex",
        "thread-editor-second",
        "/tmp/codex-home-second",
        Some("0.144.4"),
    )
    .expect("bind second editor");

    let first_chats = store::list_chats(&first_scope).expect("list first editor chats");
    let second_chats = store::list_chats(&second_scope).expect("list second editor chats");
    assert!(first_chats.iter().any(|chat| chat.id == first_chat.chat.id));
    assert!(!first_chats.iter().any(|chat| chat.id == second_chat.chat.id));
    assert!(second_chats.iter().any(|chat| chat.id == second_chat.chat.id));
    assert!(!second_chats.iter().any(|chat| chat.id == first_chat.chat.id));
    assert!(store::open_chat(&first_scope, &second_chat.chat.id).is_err());
    assert!(store::open_chat(&second_scope, &first_chat.chat.id).is_err());

    store::mark_provider_session_broken(&first_chat.chat.id, "codex")
        .expect("mark first editor binding broken");
    let first_binding = store::provider_session_binding(&first_chat.chat.id, "codex")
        .expect("read first editor binding")
        .expect("first editor binding");
    let second_binding = store::provider_session_binding(&second_chat.chat.id, "codex")
        .expect("read second editor binding")
        .expect("second editor binding");
    assert_eq!(first_binding.provider_thread_id, "thread-editor-first");
    assert_eq!(first_binding.resume_status, "broken");
    assert_eq!(second_binding.provider_thread_id, "thread-editor-second");
    assert_eq!(second_binding.resume_status, "ready");
}

#[tokio::test]
async fn turn_interrupt_finishes_and_reaps_the_app_server() {'''
replace_once(tests, marker, addition)


doc = Path("docs/codex-app-server-ownership.md")
replace_once(
    doc,
    '''| Multiple chats/editors | `provider_session_bindings_survive_reopened_store_connections`, `multiple_app_server_sessions_are_isolated` |
''',
    '''| Multiple chats/editors | `provider_session_bindings_survive_reopened_store_connections`, `multiple_godot_project_scopes_keep_codex_bindings_isolated`, `multiple_app_server_sessions_are_isolated` |
''',
)
