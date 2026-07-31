from pathlib import Path
p=Path('local/crates/fennara-daemon/src/runtime_daemon/chat/providers/codex_app_server.rs')
s=p.read_text(encoding='utf-8')
s=s.replace('collections::VecDeque,','collections::{HashMap, VecDeque},',1)
s=s.replace('const STDERR_LINE_LIMIT: usize = 40;','const STDERR_LINE_LIMIT: usize = 40;\nconst MCP_ARGUMENT_LIMIT: usize = 8 * 1024;\nconst MCP_CONTENT_LIMIT: usize = 32 * 1024;',1)
marker='struct ActiveCodexLogin {\n    login_id: String,\n    cancel: oneshot::Sender<()>,\n}\n'
block=marker+'\n#[derive(Clone, Debug)]\nstruct McpItemState {\n    name: String,\n    arguments: String,\n}\n'
if 'struct McpItemState' not in s:
    if s.count(marker)!=1: raise RuntimeError('login state marker')
    s=s.replace(marker,block,1)
old='let mut latest_usage: Option<Usage> = None;\n    loop {'
new='let mut latest_usage: Option<Usage> = None;\n    let mut mcp_items: HashMap<String, McpItemState> = HashMap::new();\n    loop {'
if 'let mut mcp_items:' not in s:
    if s.count(old)!=1: raise RuntimeError('stream state marker')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8',newline='\n')
