from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs')
s=p.read_text(encoding='utf-8')
start=s.index('pub(crate) fn metadata_from_initialize(')
end=s.index('\npub(crate) fn parse_codex_version',start)
new='''pub(crate) fn metadata_from_initialize(
    runtime: &CodexRuntimeSpec,
    initialize: &serde_json::Value,
) -> Result<CodexRuntimeMetadata, LlmError> {
    let user_agent = required_initialize_string(initialize, "userAgent")?;
    let codex_home = required_initialize_string(initialize, "codexHome")?;
    let platform_family = required_initialize_string(initialize, "platformFamily")?;
    let platform_os = required_initialize_string(initialize, "platformOs")?;
    if platform_os != runtime.platform.as_str() {
        return Err(provider_init(format!(
            "Codex app-server reported platform {platform_os}, but Fennara started it for {}.",
            runtime.platform.as_str()
        )));
    }
    let version = parse_codex_version(&user_agent).ok_or_else(|| {
        provider_init(format!(
            "Codex app-server returned an unrecognized userAgent: {user_agent}. Install the tested Codex {PINNED_CODEX_VERSION} runtime."
        ))
    })?;
    let compatibility = compatibility_for_version(Some(&version));
    let compatibility_error = compatibility_error(&version, compatibility);
    if let Some(error) = compatibility_error.as_ref() {
        return Err(provider_init(error.clone()));
    }
    Ok(CodexRuntimeMetadata {
        version: Some(version),
        compatibility,
        pinned_version: PINNED_CODEX_VERSION,
        minimum_version: MINIMUM_CODEX_VERSION,
        compatibility_error,
        source: runtime.source,
        platform: runtime.platform,
        codex_home: Some(codex_home),
        server_platform_family: Some(platform_family),
        server_platform_os: Some(platform_os),
    })
}

fn required_initialize_string(
    initialize: &serde_json::Value,
    field: &str,
) -> Result<String, LlmError> {
    initialize
        .get(field)
        .and_then(serde_json::Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
        .ok_or_else(|| {
            provider_init(format!(
                "Codex app-server initialize response is missing required field {field}. Install the tested Codex {PINNED_CODEX_VERSION} runtime."
            ))
        })
}
'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding='utf-8',newline='\n')
