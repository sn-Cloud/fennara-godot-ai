from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] if '.github' in str(Path(__file__)) else Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='\n')


def replace_expected(path: str, old: str, new: str, expected: int = 1) -> None:
    content = read(path)
    count = content.count(old)
    if count != expected:
        raise RuntimeError(
            f'{path}: expected {expected} matches, found {count}: {old[:120]!r}'
        )
    write(path, content.replace(old, new))


# Pass project path and approval mode to the provider request.
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs',
    '    chat_id: &str,\n    trace: trace::TraceRecorder,\n',
    '    chat_id: &str,\n    project_path: Option<String>,\n    approval_mode: String,\n    trace: trace::TraceRecorder,\n',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/publisher.rs',
    '                max_output_tokens: None,\n            },',
    '                max_output_tokens: None,\n                cwd: project_path,\n                approval_mode,\n            },',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs',
    '            state,\n            &chat_id,\n            current_trace.clone(),\n',
    '            state,\n            &chat_id,\n            scope.project_path.clone(),\n            settings.approval_mode.as_str().to_string(),\n            current_trace.clone(),\n',
)

# Chat WebSocket account actions.
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/mod.rs',
    '        "get_project_status" => send_project_status(sender, request_id, state, bound_project).await,\n',
    '        "get_project_status" => send_project_status(sender, request_id, state, bound_project).await,\n        "codex_account_status" => {\n            match providers::codex_app_server::account_status().await {\n                Ok(status) => send_json(\n                    sender,\n                    json!({\n                        "type": "codex_account_status",\n                        "request_id": request_id,\n                        "status": status\n                    }),\n                )\n                .await,\n                Err(error) => send_error(sender, request_id, "codex_account_failed", &error).await,\n            }\n        }\n        "codex_login_start" => {\n            match providers::codex_app_server::start_login().await {\n                Ok(login) => send_json(\n                    sender,\n                    json!({\n                        "type": "codex_login_started",\n                        "request_id": request_id,\n                        "login": login\n                    }),\n                )\n                .await,\n                Err(error) => send_error(sender, request_id, "codex_login_failed", &error).await,\n            }\n        }\n        "codex_logout" => {\n            match providers::codex_app_server::logout().await {\n                Ok(status) => send_json(\n                    sender,\n                    json!({\n                        "type": "codex_account_status",\n                        "request_id": request_id,\n                        "status": status\n                    }),\n                )\n                .await,\n                Err(error) => send_error(sender, request_id, "codex_logout_failed", &error).await,\n            }\n        }\n',
)

# Existing ChatRequest helpers and tests need neutral context defaults.
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs',
    '            tools: tools::definitions(),\n            max_output_tokens: None,\n        },',
    '            tools: tools::definitions(),\n            max_output_tokens: None,\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        },',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/generation/runner.rs',
    '            tools: Vec::new(),\n            max_output_tokens: Some(summary_output_max_tokens),\n        },',
    '            tools: Vec::new(),\n            max_output_tokens: Some(summary_output_max_tokens),\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        },',
    expected=2,
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/context.rs',
    '                max_output_tokens: None,\n            },',
    '                max_output_tokens: None,\n                cwd: None,\n                approval_mode: "ask".to_string(),\n            },',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    '        max_output_tokens: None,\n    };',
    '        max_output_tokens: None,\n        cwd: None,\n        approval_mode: "ask".to_string(),\n    };',
)

# Existing LlmRequest test literals need the same neutral defaults.
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/adapters/anthropic_compatible.rs',
    '            tools: Vec::new(),\n        }\n    }\n}',
    '            tools: Vec::new(),\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        }\n    }\n}',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/adapters/openai_compatible.rs',
    '            tools: Vec::new(),\n        }\n    }\n}',
    '            tools: Vec::new(),\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        }\n    }\n}',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/capability_check.rs',
    '            tools: Vec::new(),\n        }\n    }\n\n    #[test]',
    '            tools: Vec::new(),\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        }\n    }\n\n    #[test]',
)
replace_expected(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/context.rs',
    '            tools: Vec::new(),\n        };',
    '            tools: Vec::new(),\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        };',
    expected=4,
)
