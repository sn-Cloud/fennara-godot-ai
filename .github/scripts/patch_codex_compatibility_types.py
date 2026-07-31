from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs')
s=p.read_text(encoding='utf-8')
s=s.replace('pub(crate) const PINNED_CODEX_VERSION: &str = "0.144.4";','pub(crate) const PINNED_CODEX_VERSION: &str = "0.144.4";\npub(crate) const MINIMUM_CODEX_VERSION: &str = "0.144.0";',1)
s=s.replace('''pub(crate) enum CodexCompatibility {
    Tested,
    CompatibleUnverified,
    Unknown,
}
''','''pub(crate) enum CodexCompatibility {
    Tested,
    CompatibleUnverified,
    Incompatible,
}
''',1)
s=s.replace('''    pub(crate) pinned_version: &'static str,
    pub(crate) source: CodexRuntimeSource,
''','''    pub(crate) pinned_version: &'static str,
    pub(crate) minimum_version: &'static str,
    pub(crate) compatibility_error: Option<String>,
    pub(crate) source: CodexRuntimeSource,
''',1)
p.write_text(s,encoding='utf-8',newline='\n')
