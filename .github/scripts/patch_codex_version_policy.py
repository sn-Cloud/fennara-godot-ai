from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs')
s=p.read_text(encoding='utf-8')
start=s.index('pub(crate) fn compatibility_for_version(')
end=s.index('\nfn configured_codex_home',start)
new='''pub(crate) fn compatibility_for_version(version: Option<&str>) -> CodexCompatibility {
    let Some(version) = version.and_then(parse_version_tuple) else {
        return CodexCompatibility::Incompatible;
    };
    let pinned = parse_version_tuple(PINNED_CODEX_VERSION).expect("pinned Codex version");
    let minimum = parse_version_tuple(MINIMUM_CODEX_VERSION).expect("minimum Codex version");
    if version == pinned {
        CodexCompatibility::Tested
    } else if version >= minimum {
        CodexCompatibility::CompatibleUnverified
    } else {
        CodexCompatibility::Incompatible
    }
}

fn compatibility_error(
    version: &str,
    compatibility: CodexCompatibility,
) -> Option<String> {
    (compatibility == CodexCompatibility::Incompatible).then(|| {
        format!(
            "Codex {version} is older than the minimum supported version {MINIMUM_CODEX_VERSION}. Install the tested Codex {PINNED_CODEX_VERSION} runtime."
        )
    })
}

fn parse_version_tuple(version: &str) -> Option<(u64, u64, u64)> {
    let core = version.split_once('-').map_or(version, |(core, _)| core);
    let mut parts = core.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    Some((major, minor, patch))
}
'''
s=s[:start]+new+s[end:]
p.write_text(s,encoding='utf-8',newline='\n')
