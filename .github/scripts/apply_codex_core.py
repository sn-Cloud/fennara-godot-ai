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


# Provider IDs and adapter type.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/types.rs',
    '    pub(crate) const OPENAI: &\'static str = "openai";\n',
    '    pub(crate) const OPENAI: &\'static str = "openai";\n    pub(crate) const CODEX: &\'static str = "codex";\n',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/types.rs',
    'pub(crate) enum AdapterKind {\n    OpenAiCompatibleChat,\n    AnthropicCompatibleMessages,\n}',
    'pub(crate) enum AdapterKind {\n    OpenAiCompatibleChat,\n    AnthropicCompatibleMessages,\n    CodexAppServer,\n}',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/types.rs',
    'pub(crate) struct ChatRequest {\n    pub(crate) model: String,\n    pub(crate) reasoning_effort: String,\n    pub(crate) messages: Vec<Value>,\n    pub(crate) tools: Vec<Value>,\n    pub(crate) max_output_tokens: Option<u32>,\n}',
    'pub(crate) struct ChatRequest {\n    pub(crate) model: String,\n    pub(crate) reasoning_effort: String,\n    pub(crate) messages: Vec<Value>,\n    pub(crate) tools: Vec<Value>,\n    pub(crate) max_output_tokens: Option<u32>,\n    pub(crate) cwd: Option<String>,\n    pub(crate) approval_mode: String,\n}',
)

# Carry project and permission context into provider adapters.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/request.rs',
    'pub(crate) struct LlmRequest {\n    pub(crate) model: ResolvedModel,\n    pub(crate) messages: Vec<Value>,\n    pub(crate) tools: Vec<Value>,\n}',
    'pub(crate) struct LlmRequest {\n    pub(crate) model: ResolvedModel,\n    pub(crate) messages: Vec<Value>,\n    pub(crate) tools: Vec<Value>,\n    pub(crate) cwd: Option<String>,\n    pub(crate) approval_mode: String,\n}',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/request.rs',
    '            messages: request.messages.clone(),\n            tools: request.tools.clone(),\n',
    '            messages: request.messages.clone(),\n            tools: request.tools.clone(),\n            cwd: request.cwd.clone(),\n            approval_mode: request.approval_mode.clone(),\n',
)

# Register and dispatch the Codex adapter.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    'mod context;\npub(crate) mod custom;\nmod deepseek;',
    'mod context;\nmod codex;\npub(crate) mod codex_app_server;\npub(crate) mod custom;\nmod deepseek;',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    '    let mut providers = vec![\n        api_key_provider(',
    '    let mut providers = vec![\n        account_provider(codex::provider_definition()),\n        api_key_provider(',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    'fn api_key_provider(\n',
    'fn account_provider(provider: types::ProviderDefinition) -> PublicProvider {\n    let provider_id = provider.id.to_string();\n    PublicProvider {\n        id: provider_id.clone(),\n        name: provider.name,\n        kind: "agent",\n        auth: PublicProviderAuth {\n            kind: "account",\n            env: None,\n        },\n        connected: codex_app_server::cached_account_status().connected,\n        model_prefix: format!("{provider_id}/"),\n        setup: None,\n        custom: None,\n    }\n}\n\nfn api_key_provider(\n',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    'pub(crate) fn missing_auth_for_model(settings: &ChatSettings, model: &str) -> Option<LlmError> {\n    if custom::split_model_selection(&settings.custom_providers, model).is_some() {',
    'pub(crate) fn missing_auth_for_model(settings: &ChatSettings, model: &str) -> Option<LlmError> {\n    if has_provider_prefix(model.trim(), types::ProviderId::CODEX) {\n        if !codex_app_server::is_installed() {\n            return Some(LlmError::Auth {\n                provider: types::ProviderId::CODEX.to_string(),\n                message: "Install the Codex CLI before using ChatGPT account login.".to_string(),\n            });\n        }\n        if !codex_app_server::cached_account_status().connected {\n            return Some(LlmError::Auth {\n                provider: types::ProviderId::CODEX.to_string(),\n                message: "Sign in to Codex with your ChatGPT account first.".to_string(),\n            });\n        }\n        return None;\n    }\n    if custom::split_model_selection(&settings.custom_providers, model).is_some() {',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    '        types::ProviderId::OPENAI,\n        types::ProviderId::ANTHROPIC,',
    '        types::ProviderId::CODEX,\n        types::ProviderId::OPENAI,\n        types::ProviderId::ANTHROPIC,',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    '        types::AdapterKind::AnthropicCompatibleMessages => {\n            adapters::anthropic_compatible::stream_chat(&llm_request, trace, {',
    '        types::AdapterKind::AnthropicCompatibleMessages => {\n            adapters::anthropic_compatible::stream_chat(&llm_request, trace, {',
)
# Insert Codex match arm after the Anthropic arm block by matching its closing sequence.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs',
    '            .await?\n        }\n    };\n\n    let accumulator = accumulator.lock().await;',
    '            .await?\n        }\n        types::AdapterKind::CodexAppServer => {\n            codex_app_server::stream_chat(&llm_request, {\n                let accumulator = Arc::clone(&accumulator);\n                let on_item = Arc::clone(&on_item);\n                move |event| {\n                    let accumulator = Arc::clone(&accumulator);\n                    let on_item = Arc::clone(&on_item);\n                    async move {\n                        let items = {\n                            let mut accumulator = accumulator.lock().await;\n                            accumulator.items_for_event(event)?\n                        };\n                        for item in items {\n                            let mut on_item = on_item.lock().await;\n                            if !on_item(item).await? {\n                                return Ok(false);\n                            }\n                        }\n                        Ok(true)\n                    }\n                }\n            })\n            .await?;\n            ChatCompletion {\n                content: String::new(),\n                tool_calls: Vec::new(),\n                finish_reason: FinishReason::Stop,\n                tool_call_observation: ToolCallObservation::none(),\n            }\n        }\n    };\n\n    let accumulator = accumulator.lock().await;',
)
replace_all_existing(
    ['local/crates/fennara-daemon/src/runtime_daemon/chat/providers/mod.rs'],
    '            max_output_tokens: None,\n        },',
    '            max_output_tokens: None,\n            cwd: None,\n            approval_mode: "ask".to_string(),\n        },',
)

# Catalog registration.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/catalog.rs',
    'use super::custom;\nuse super::deepseek;',
    'use super::custom;\nuse super::codex;\nuse super::deepseek;',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/catalog.rs',
    '        catalog.local_model_limits = settings.local_model_limits.clone();\n        catalog.insert_provider(openai::provider_definition(',
    '        catalog.local_model_limits = settings.local_model_limits.clone();\n        catalog.insert_provider(codex::provider_definition());\n        catalog.insert_model(codex::model_definition(\n            codex::DEFAULT_MODEL_ID,\n            Some("Codex account default".to_string()),\n        ));\n        catalog.insert_provider(openai::provider_definition(',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/providers/catalog.rs',
    '        ProviderId::OPENAI => openai::model_definition(model_id.as_str(), None),',
    '        ProviderId::CODEX => codex::model_definition(model_id.as_str(), None),\n        ProviderId::OPENAI => openai::model_definition(model_id.as_str(), None),',
)

# Static Codex account model in the UI catalog.
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/models.rs',
    '        || has_nvidia_key;\n    let mut models = Vec::new();\n',
    '        || has_nvidia_key;\n    let mut models = Vec::new();\n    if providers::codex_app_server::is_installed() {\n        models.push(codex_model_info());\n    }\n',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/models.rs',
    '    let custom_live = !settings.custom_providers.is_empty();\n    let live = openrouter_error.is_none() || ollama_live || local_live || custom_live;',
    '    let custom_live = !settings.custom_providers.is_empty();\n    let codex_live = providers::codex_app_server::is_installed();\n    let live = openrouter_error.is_none() || ollama_live || local_live || custom_live || codex_live;',
)
replace_once(
    'local/crates/fennara-daemon/src/runtime_daemon/chat/models.rs',
    'fn append_openrouter_catalog_models(\n',
    'fn codex_model_info() -> ModelInfo {\n    ModelInfo {\n        id: "codex/default".to_string(),\n        display_name: "Codex account default".to_string(),\n        provider_id: ProviderId::CODEX.to_string(),\n        provider: "Codex (ChatGPT account)".to_string(),\n        source: "account",\n        recommended: true,\n        custom: false,\n        verified: true,\n        latest_alias: true,\n        canonical_slug: Some("default".to_string()),\n        context_length: None,\n        max_output_tokens: None,\n        input_cost_per_million: None,\n        output_cost_per_million: None,\n        cache_read_cost_per_million: None,\n        cache_write_cost_per_million: None,\n        tokens_per_second: None,\n        modalities: vec!["in:text".to_string(), "out:text".to_string()],\n        supports_tools: true,\n        supports_reasoning: true,\n        supported_reasoning_efforts: vec![\n            "low".to_string(),\n            "medium".to_string(),\n            "high".to_string(),\n        ],\n        description: Some(\n            "Uses the installed Codex CLI and its ChatGPT account authentication.".to_string(),\n        ),\n    }\n}\n\nfn append_openrouter_catalog_models(\n',
)
