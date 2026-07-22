extends SceneTree

var _client: Object
var _resolver: Object
var _phase := ""
var _done := false
var _error := ""

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var resolver_script: Script = load("res://addons/godot_ai_manager/command_resolver.gd")
	_resolver = resolver_script.new()
	if not await _test_codex():
		_fail(_error)
		return
	if not await _test_kimi():
		_fail(_error)
		return
	print("Official Codex and Kimi ACP smoke tests passed.")
	quit(0)

func _new_client() -> Object:
	var script: Script = load("res://addons/godot_ai_manager/jsonrpc_process_client.gd")
	var client: Object = script.new()
	client.response_received.connect(_on_response)
	client.protocol_error.connect(_on_protocol_error)
	client.stderr_received.connect(_on_stderr)
	return client

func _test_codex() -> bool:
	_reset("codex_initialize")
	_client = _new_client()
	var launch: Dictionary = _resolver.resolve("codex", "", PackedStringArray(["app-server", "--stdio"]))
	if not bool(launch.get("success", false)):
		_error = str(launch.get("error", "未找到官方 Codex CLI。"))
		return false
	var started: Dictionary = _client.start_command(
		str(launch.get("executable", "")),
		launch.get("arguments", PackedStringArray()) as PackedStringArray,
		str(launch.get("description", "codex")),
		false
	)
	if not bool(started.get("success", false)):
		_error = str(started.get("error", "Codex 启动失败。"))
		return false
	_client.send_request("initialize", {
		"clientInfo": {"name": "godot_ai_manager_ci", "title": "Godot AI Manager CI", "version": "1.0.0"},
		"capabilities": {"experimentalApi": true},
	})
	if not await _wait(30000):
		_client.shutdown("test_failed")
		return false
	_client.shutdown("codex_test_complete")
	return _error.is_empty()

func _test_kimi() -> bool:
	_reset("kimi_initialize")
	_client = _new_client()
	var launch: Dictionary = _resolver.resolve("kimi", "", PackedStringArray(["acp"]))
	if not bool(launch.get("success", false)):
		_error = str(launch.get("error", "未找到官方 Kimi Code CLI。"))
		return false
	var started: Dictionary = _client.start_command(
		str(launch.get("executable", "")),
		launch.get("arguments", PackedStringArray()) as PackedStringArray,
		str(launch.get("description", "kimi")),
		true
	)
	if not bool(started.get("success", false)):
		_error = str(started.get("error", "Kimi ACP 启动失败。"))
		return false
	_client.send_request("initialize", {
		"protocolVersion": 1,
		"clientCapabilities": {"fs": {"readTextFile": true, "writeTextFile": true}, "terminal": false},
		"clientInfo": {"name": "godot-ai-manager-ci", "title": "Godot AI Manager CI", "version": "1.0.0"},
	})
	if not await _wait(30000):
		_client.shutdown("test_failed")
		return false
	_client.shutdown("kimi_test_complete")
	return _error.is_empty()

func _on_response(_request_id: Variant, method: String, result: Variant, error: Variant) -> void:
	if _phase == "codex_initialize" and method == "initialize":
		if error != null:
			_error = "官方 Codex initialize 失败：%s" % error
			_done = true
			return
		_client.send_notification("initialized", {})
		_phase = "codex_account"
		_client.send_request("account/read", {"refreshToken": false})
		return
	if _phase == "codex_account" and method == "account/read":
		if error != null:
			_error = "官方 Codex account/read 失败：%s" % error
		_done = true
		return
	if _phase == "kimi_initialize" and method == "initialize":
		if error != null:
			_error = "官方 Kimi ACP initialize 失败：%s" % error
			_done = true
			return
		var result_dict: Dictionary = {}
		if result is Dictionary:
			result_dict = result as Dictionary
		var agent_info := result_dict.get("agentInfo", {}) as Dictionary
		if str(agent_info.get("name", "")).is_empty():
			_error = "官方 Kimi ACP initialize 未返回 agentInfo。"
			_done = true
			return
		_phase = "kimi_auth"
		_client.send_request("authenticate", {"methodId": "login"})
		return
	if _phase == "kimi_auth" and method == "authenticate":
		if error != null:
			var dictionary: Dictionary = {}
			if error is Dictionary:
				dictionary = error as Dictionary
			if int(dictionary.get("code", 0)) != -32000:
				_error = "官方 Kimi ACP authenticate 返回意外错误：%s" % error
		_done = true

func _on_protocol_error(message: String, raw_line: String) -> void:
	_error = "%s %s" % [message, raw_line]
	_done = true

func _on_stderr(text: String) -> void:
	print("[official CLI stderr] %s" % text)

func _wait(timeout_ms: int) -> bool:
	var deadline := Time.get_ticks_msec() + timeout_ms
	while Time.get_ticks_msec() < deadline:
		_client.poll()
		if _done:
			return _error.is_empty()
		await create_timer(0.01).timeout
	_error = "官方 CLI 测试超时，阶段：%s" % _phase
	return false

func _reset(phase: String) -> void:
	_phase = phase
	_done = false
	_error = ""

func _fail(message: String) -> void:
	push_error(message)
	quit(1)
