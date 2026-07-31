from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_runtime.rs')
s=p.read_text();old='''        assert_eq!(
            compatibility_for_version(Some("0.145.0-alpha.13")),
            CodexCompatibility::CompatibleUnverified
        );
        assert_eq!(compatibility_for_version(None), CodexCompatibility::Unknown);
''';new='''        assert_eq!(
            compatibility_for_version(Some("0.145.0-alpha.13")),
            CodexCompatibility::CompatibleUnverified
        );
        assert_eq!(
            compatibility_for_version(Some(MINIMUM_CODEX_VERSION)),
            CodexCompatibility::CompatibleUnverified
        );
        assert_eq!(
            compatibility_for_version(Some("0.143.99")),
            CodexCompatibility::Incompatible
        );
        assert_eq!(
            compatibility_for_version(None),
            CodexCompatibility::Incompatible
        );
        assert_eq!(parse_version_tuple("0.145.0-alpha.13"), Some((0, 145, 0)));
'''
if '0.143.99' not in s:
    if s.count(old)!=1: raise RuntimeError('compatibility test block')
    s=s.replace(old,new,1)
p.write_text(s,newline='\n')
