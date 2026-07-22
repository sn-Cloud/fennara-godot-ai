extends PanelContainer

var codex_process: int = -1

func _ready():
	# Future implementation:
	# 1. Start `codex app-server`.
	# 2. Communicate through JSON-RPC over stdio.
	# 3. Configure MCP server:
	#    http://127.0.0.1:9080/mcp
	# 4. Stream Codex responses into this dock.
	pass
