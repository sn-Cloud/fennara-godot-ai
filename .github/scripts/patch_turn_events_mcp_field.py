from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();a='    compaction_completed: usize,\n    completed: bool,\n';b='    compaction_completed: usize,\n    mcp_activities: Vec<ObservedMcpActivity>,\n    completed: bool,\n';p.write_text(s if 'mcp_activities:' in s else s.replace(a,b,1),newline='\n')
