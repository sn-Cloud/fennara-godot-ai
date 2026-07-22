extends SceneTree

var _mock_client: Object
var _mock_started_seen := false
var _mock_response_seen := false
var _mock_notification_seen := false
var _mock_server_request_seen := false
var _mock_approval_round_trip_seen := false
var _mock_error := ""
var _mock_stopped_reason := ""
var _mock_status := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	if not _test_resource_loading():
		return
	if not _test_config_manager():
		return
	if not await _test_app_server_transport():
		return
	print("Codex Native Chat smoke tests passed.")
	quit(0)

func _test_resource_loading() -> bool:
	var paths: Array[String] = [
		"res://addons/codex_native_chat/codex_app_server_client.gd",
		"res://addons/codex_native_chat/codex_config_manager.gd",
		"res://addons/codex_native_chat/codex_native_chat_dock.gd",
		"res://addons/codex_native_chat/codex_native_chat.gd",
		"res://addons/codex_native_chat/codex_native_chat_dock.tscn",
	]
	for path in paths:
		var resource := load(path)
		if resource == null:
			return _fail("Failed to load %s" % path)
	return true

func _test_config_manager() -> bool:
	var manager_script: Script = load("res://addons/codex_native_chat/codex_config_manager.gd")
	var manager: Object = manager_script.new()
	var test_root := ProjectSettings.globalize_path("res://.config_test")
	DirAccess.make_dir_recursive_absolute(test_root)
	var first: Dictionary = manager.ensure_project_mcp_config(test_root, "http://127.0.0.1:9080/mcp")
	if not bool(first.get("success", false)):
		return _fail("MCP config creation failed: %s" % first.get("error", ""))
	var second: Dictionary = manager.ensure_project_mcp_config(test_root, "http://127.0.0.1:19080/mcp")
	if not bool(second.get("success", false)):
		return _fail("MCP config update failed: %s" % second.get("error", ""))
	var config_path := test_root.path_join(".codex/config.toml")
	var file := FileAccess.open(config_path, FileAccess.READ)
	if file == null:
		return _fail("Generated config was not readable.")
	var content := file.get_as_text()
	file.close()
	if content.count("[mcp_servers.godot-mcp]") != 1 or not content.contains("19080"):
		return _fail("Generated MCP table is invalid:\n%s" % content)
	return true

func _test_app_server_transport() -> bool:
	var client_script: Script = load("res://addons/codex_native_chat/codex_app_server_client.gd")
	_mock_client = client_script.new()
	_mock_client.response_received.connect(_on_mock_response_received)
	_mock_client.notification_received.connect(_on_mock_notification_received)
	_mock_client.server_request_received.connect(_on_mock_server_request_received)
	_mock_client.protocol_error.connect(_on_mock_protocol_error)
	_mock_client.stderr_received.connect(_on_mock_stderr)
	_mock_client.stopped.connect(_on_mock_stopped)
	_mock_client.status_changed.connect(_on_mock_status_changed)

	var mock_path := ProjectSettings.globalize_path("res://mock_codex.py")
	var start_result: Dictionary = _mock_client.start(mock_path)
	if not bool(start_result.get("success", false)):
		return _fail("Mock app-server failed to start: %s" % start_result.get("error", ""))
	print("Mock app-server start result: %s" % start_result)

	var request_id: int = _mock_client.send_request("initialize", {
		"clientInfo": {
			"name": "godot_codex_native_chat_test",
			"title": "Godot Codex Native Chat Test",
			"version": "1.0.0",
		},
	})
	if request_id < 0:
		_mock_client.shutdown("test_failure")
		return _fail("Mock initialize request was not sent.")

	var deadline := Time.get_ticks_msec() + 5000
	while Time.get_ticks_msec() < deadline:
		_mock_client.poll()
		if _mock_started_seen and _mock_response_seen and _mock_notification_seen and _mock_server_request_seen and _mock_approval_round_trip_seen:
			break
		await create_timer(0.01).timeout

	var queued_lines: int = _mock_client._outgoing_lines.size()
	var pipe_error: int = _mock_client._stdio.get_error() if _mock_client._stdio != null else -1
	var was_running: bool = _mock_client.is_running()
	print("Transport deadline state: queued=%s pipe_error=%s running=%s" % [queued_lines, pipe_error, was_running])
	_mock_client.shutdown("test_complete")
	if not _mock_error.is_empty():
		return _fail(_mock_error)
	if not _mock_started_seen:
		return _fail("Mock process emitted no startup notification. running=%s status=%s stopped=%s" % [was_running, _mock_status, _mock_stopped_reason])
	if not _mock_response_seen:
		return _fail("No initialize response was received from the mock app-server. queued=%s pipe_error=%s running=%s status=%s stopped=%s" % [queued_lines, pipe_error, was_running, _mock_status, _mock_stopped_reason])
	if not _mock_notification_seen:
		return _fail("No notification was received from the mock app-server.")
	if not _mock_server_request_seen:
		return _fail("No server-to-client approval request was received.")
	if not _mock_approval_round_trip_seen:
		return _fail("The approval response did not complete a round trip.")
	return true

func _on_mock_response_received(_request_id: Variant, method: String, _result: Variant, error: Variant) -> void:
	if method == "initialize" and error == null:
		_mock_response_seen = true
	elif error != null:
		_mock_error = "Mock response error: %s" % error

func _on_mock_notification_received(method: String, params: Dictionary) -> void:
	if method == "mock/started":
		_mock_started_seen = true
		print("Mock process startup notification: %s" % params)
	elif method == "mock/notification" and bool(params.get("ok", false)):
		_mock_notification_seen = true
	elif method == "mock/approvalReceived" and str(params.get("decision", "")) == "accept":
		_mock_approval_round_trip_seen = true

func _on_mock_server_request_received(request_id: Variant, method: String, _params: Dictionary) -> void:
	if method != "item/commandExecution/requestApproval":
		return
	_mock_server_request_seen = true
	_mock_client.respond(request_id, {"decision": "accept"})

func _on_mock_protocol_error(message: String, raw_line: String) -> void:
	if message.contains("pipe read failed (error 14)"):
		print("Ignoring transient nonblocking pipe read status: %s" % message)
		return
	_mock_error = "Protocol error: %s %s" % [message, raw_line]

func _on_mock_stderr(text: String) -> void:
	_mock_error = "Mock app-server stderr: %s" % text

func _on_mock_stopped(reason: String) -> void:
	_mock_stopped_reason = reason

func _on_mock_status_changed(status: String) -> void:
	_mock_status = status

func _fail(message: String) -> bool:
	push_error(message)
	quit(1)
	return false
