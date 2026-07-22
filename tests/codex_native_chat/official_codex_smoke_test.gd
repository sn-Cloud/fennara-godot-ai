extends SceneTree

var _client: Object
var _initialize_seen := false
var _account_seen := false
var _mcp_reload_seen := false
var _mcp_status_seen := false
var _error := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var client_script: Script = load("res://addons/codex_native_chat/codex_app_server_client.gd")
	_client = client_script.new()
	_client.response_received.connect(_on_response_received)
	_client.protocol_error.connect(_on_protocol_error)
	_client.stderr_received.connect(_on_stderr_received)

	var start_result: Dictionary = _client.start("")
	if not bool(start_result.get("success", false)):
		_fail("Official Codex app-server failed to start: %s" % start_result.get("error", ""))
		return

	var request_id: int = _client.send_request("initialize", {
		"clientInfo": {
			"name": "godot_codex_native_chat_ci",
			"title": "Godot Codex Native Chat CI",
			"version": "1.0.0",
		},
		"capabilities": {
			"experimentalApi": true,
		},
	})
	if request_id < 0:
		_client.shutdown("test_failure")
		_fail("Official Codex initialize request was not sent.")
		return

	var deadline := Time.get_ticks_msec() + 30000
	while Time.get_ticks_msec() < deadline:
		_client.poll()
		if _initialize_seen and _account_seen and _mcp_reload_seen and _mcp_status_seen:
			break
		if not _error.is_empty():
			break
		await create_timer(0.01).timeout

	_client.shutdown("test_complete")
	if not _error.is_empty():
		_fail(_error)
		return
	if not _initialize_seen:
		_fail("Official Codex app-server did not complete initialize.")
		return
	if not _account_seen:
		_fail("Official Codex app-server did not answer account/read.")
		return
	if not _mcp_reload_seen:
		_fail("Official Codex app-server did not reload MCP configuration.")
		return
	if not _mcp_status_seen:
		_fail("Official Codex app-server did not answer mcpServerStatus/list.")
		return

	print("Official Codex app-server smoke test passed.")
	quit(0)

func _on_response_received(_request_id: Variant, method: String, _result: Variant, error: Variant) -> void:
	if error != null:
		_error = "Official Codex RPC failed (%s): %s" % [method, error]
		return
	if method == "initialize":
		_initialize_seen = true
		_client.send_notification("initialized", {})
		_client.send_request("account/read", {"refreshToken": false})
	elif method == "account/read":
		_account_seen = true
		_client.send_request("config/mcpServer/reload", {})
	elif method == "config/mcpServer/reload":
		_mcp_reload_seen = true
		_client.send_request("mcpServerStatus/list", {})
	elif method == "mcpServerStatus/list":
		_mcp_status_seen = true

func _on_protocol_error(message: String, raw_line: String) -> void:
	_error = "Official Codex protocol error: %s %s" % [message, raw_line]

func _on_stderr_received(text: String) -> void:
	print("[official codex stderr] %s" % text)

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
