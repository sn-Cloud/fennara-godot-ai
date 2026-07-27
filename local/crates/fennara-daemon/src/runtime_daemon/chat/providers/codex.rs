use super::types::{
    AdapterKind, Auth, Capabilities, GenerationDefaults, Limits, ModelDefinition, ModelId,
    ProviderDefinition, ProviderId, RequestDefaults,
};

pub(crate) const PROVIDER_ID: &str = ProviderId::CODEX;
pub(crate) const DEFAULT_MODEL_ID: &str = "default";

pub(crate) fn provider_definition() -> ProviderDefinition {
    ProviderDefinition {
        id: ProviderId::unchecked(PROVIDER_ID),
        name: "Codex (ChatGPT account)".to_string(),
        adapter: AdapterKind::CodexAppServer,
        base_url: None,
        auth: Auth::None,
        request: RequestDefaults::default(),
        disabled: false,
    }
}

pub(crate) fn model_definition(model_id: &str, display_name: Option<String>) -> ModelDefinition {
    let mut request = RequestDefaults::default();
    request.generation = GenerationDefaults {
        temperature: None,
        max_output_tokens: None,
        reasoning_effort: Some("medium".to_string()),
    };

    ModelDefinition {
        id: ModelId::new(model_id).expect("Codex model id is valid"),
        provider: ProviderId::unchecked(PROVIDER_ID),
        display_name: display_name.unwrap_or_else(|| fallback_display_name(model_id)),
        adapter_model_id: model_id.to_string(),
        capabilities: Capabilities {
            tools: true,
            input: vec!["text".to_string()],
            output: vec!["text".to_string()],
            reasoning: true,
        },
        limits: Limits::default(),
        request,
        enabled: true,
    }
}

fn fallback_display_name(model_id: &str) -> String {
    if model_id == DEFAULT_MODEL_ID {
        "Codex account default".to_string()
    } else {
        model_id.replace('-', " ")
    }
}
