from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] if '.github' in str(Path(__file__)) else Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='\n')


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: expected exactly one match, found {count}: {old[:100]!r}')
    write(path, content.replace(old, new, 1))


def replace_all_existing(paths: list[str], old: str, new: str) -> None:
    found = 0
    for path in paths:
        target = ROOT / path
        if not target.exists():
            continue
        content = target.read_text(encoding='utf-8')
        count = content.count(old)
        if count:
            target.write_text(content.replace(old, new), encoding='utf-8', newline='\n')
            found += count
    if not found:
        raise RuntimeError(f'no matches found in {paths}: {old[:100]!r}')


# Pass project path and approval mode to the provider request.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs',
    '    chat_id: &str,\n    trace: trace::TraceRecorder,\n',
    '    chat_id: &str,\n    project_path: Option<String>,\n    approval_mode: String,\n    trace: trace::TraceRecorder,\n',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs',
    '                max_output_tokens: None,\n            },',
    '                max_output_tokens: None,\n                cwd: project_path,\n                approval_mode,\n            },',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs',
    '            state,\n            &chat_id,\n            current_trace.clone(),\n',
    '            state,\n            &chat_id,\n            scope.project_path.clone(),\n            settings.approval_mode.as_str().to_string(),\n            current_trace.clone(),\n',
)

# Chat WebSocket account actions.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs',
    '        "get_project_status" => send_project_status(sender, request_id, state, bound_project).await,\n',
    '        "get_project_status" => send_project_status(sender, request_id, state, bound_project).await,\n        "codex_account_status" => {\n            match providers::codex_app_server::account_status().await {\n                Ok(status) => send_json(\n                    sender,\n                    json!({\n                        "type": "codex_account_status",\n                        "request_id": request_id,\n                        "status": status\n                    }),\n                )\n                .await,\n                Err(error) => send_error(sender, request_id, "codex_account_failed", &error).await,\n            }\n        }\n        "codex_login_start" => {\n            match providers::codex_app_server::start_login().await {\n                Ok(login) => send_json(\n                    sender,\n                    json!({\n                        "type": "codex_login_started",\n                        "request_id": request_id,\n                        "login": login\n                    }),\n                )\n                .await,\n                Err(error) => send_error(sender, request_id, "codex_login_failed", &error).await,\n            }\n        }\n        "codex_logout" => {\n            match providers::codex_app_server::logout().await {\n                Ok(status) => send_json(\n                    sender,\n                    json!({\n                        "type": "codex_account_status",\n                        "request_id": request_id,\n                        "status": status\n                    }),\n                )\n                .await,\n                Err(error) => send_error(sender, request_id, "codex_logout_failed", &error).await,\n            }\n        }\n',
)


# Add neutral defaults to existing request literals used by tests and helper paths.
def add_request_defaults(path: Path) -> None:
    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    output: list[str] = []
    index = 0
    changed = False
    while index < len(lines):
        line = lines[index]
        target = None
        if 'struct ChatRequest' not in line and 'ChatRequest {' in line:
            target = 'ChatRequest'
        elif 'struct LlmRequest' not in line and 'LlmRequest {' in line:
            target = 'LlmRequest'
        if target is None:
            output.append(line)
            index += 1
            continue

        block: list[str] = []
        depth = 0
        started = False
        while index < len(lines):
            current = lines[index]
            block.append(current)
            depth += current.count('{') - current.count('}')
            if '{' in current:
                started = True
            index += 1
            if started and depth == 0:
                break

        block_text = ''.join(block)
        if 'cwd:' not in block_text and 'approval_mode:' not in block_text:
            closing = block.pop()
            indent = closing[: len(closing) - len(closing.lstrip())]
            block.append(f'{indent}    cwd: None,\n')
            block.append(f'{indent}    approval_mode: "ask".to_string(),\n')
            block.append(closing)
            changed = True
        output.extend(block)

    if changed:
        path.write_text(''.join(output), encoding='utf-8', newline='\n')


for rust_path in (ROOT / 'local/crates/fennara-daemon/src/runtime_daemon/chat').rglob('*.rs'):
    add_request_defaults(rust_path)
