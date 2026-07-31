from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server/integration_tests.rs');s=p.read_text();a='use std::{\n';b='use std::{\n    collections::HashMap,\n';p.write_text(s if 'collections::HashMap' in s else s.replace(a,b,1),newline='\n')
