from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs')
s=p.read_text();s=s.replace('assert_eq!(runtime.version.as_deref(), Some("0.0.0-fake"));','assert_eq!(runtime.version.as_deref(), Some("0.144.4"));',1);s=s.replace('runtime.compatibility,\n        codex_runtime::CodexCompatibility::CompatibleUnverified','runtime.compatibility,\n        codex_runtime::CodexCompatibility::Tested',1);p.write_text(s,newline='\n')
