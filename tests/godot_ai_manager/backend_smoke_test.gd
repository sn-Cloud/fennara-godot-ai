extends SceneTree

var _current_backend: Object
var _message := ""
var _diff := ""
var _mcp_status := ""
var _errors: Array[String] = []
var _approval_seen := false
var _turn_completed := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	if not _test_resource_loading():
		return
	if not _test_config_manager():
		return
	if not await _test_codex_backend():
		return
	if not await _test_kimi_backend():
		return
	if not await _test_manager_dock():
		return
	print("Godot AI Manager backend smoke tests passed.")
	quit(0)

func _test_resource_loading() -> bool:
	var paths: Array[String] = [
		"res://addons/godot_ai_manager/agent_backend.gd",
		"res://addons/godot_ai_manager/jsonrpc_process_client.gd",
		"res://addons/godot_ai_manager/raw_process_runner.gd",
		"res://addons/godot_ai_manager/command_resolver.gd",
		"res://addons/godot_ai_manager/codex_config_manager.gd",
		"res://addons/godot_ai_manager/codex_backend.gd",
		"res://addons/godot_ai_manager/kimi_backend.gd",
		"res://addons/godot_ai_manager/godot_ai_manager_dock.gd",
		"res://addons/godot_ai_manager/godot_ai_manager.gd",
		"res://addons/godot_ai_manager/godot_ai_manager_dock.tscn",
	]
	for path in paths:
		if load(path) == null:
			return _fail("无法加载：%s" % path)
	return true

func _test_config_manager() -> bool:
	var script: Script = load("res://addons/godot_ai_manager/codex_config_manager.gd")
	var manager: Object = script.new()
	var root_path := ProjectSettings.globalize_path("res://.config_test")
	DirAccess.make_dir_recursive_absolute(root_path.path_join(".codex"))
	var config_path := root_path.path_join(".codex/config.toml")
	var initial := FileAccess.open(config_path, FileAccess.WRITE)
	if initial == null:
		return _fail("无法创建配置测试文件。")
	initial.store_string("[other]\nvalue = 7\n\n[mcp_servers.godot-mcp]\nurl = \"old\"\n")
	initial.close()
	var result: Dictionary = manager.ensure_config(root_path, "http://127.0.0.1:19080/mcp")
	if not bool(result.get("success", false)):
		return _fail(str(result.get("error", "配置测试失败")))
	var read_file := FileAccess.open(config_path, FileAccess.READ)
	if read_file == null:
		return _fail("无法读取配置测试结果。")
	var content := read_file.get_as_text()
	read_file.close()
	if content.count("[mcp_servers.godot-mcp]") != 1:
		return _fail("godot-mcp 表数量错误。\n%s" % content)
	if not content.contains("19080") or not content.contains("[other]") or not content.contains("value = 7"):
		return _fail("配置管理器覆盖了无关配置。\n%s" % content)
	if content.to_lower().contains("fennara"):
		return _fail("配置管理器生成了 Fennara 条目。")
	return true

func _test_codex_backend() -> bool:
	_reset_state()
	var script: Script = load("res://addons/godot_ai_manager/codex_backend.gd")
	_current_backend = script.new()
	_connect_signals(_current_backend)
	var mock_name := "mock_codex.cmd" if OS.get_name() == "Windows" else "mock_codex.py"
	_current_backend.configure({
		"project_root": ProjectSettings.globalize_path("res://"),
		"executable_path": ProjectSettings.globalize_path("res://" + mock_name),
		"mcp_endpoint": "http://127.0.0.1:9080/mcp",
		"sandbox_mode": "workspace-write",
		"approval_policy": "on-request",
	})
	_current_backend.connect_backend()
	if not await _wait_for_state("connected", 10000):
		return _fail("Codex 后端未完成连接和账户读取。")
	_current_backend.send_prompt("执行 Codex 后端测试")
	if not await _wait_for_state("approval", 10000):
		return _fail("Codex 未显示审批请求。")
	if not await _wait_for_state("codex_completed", 10000):
		return _fail("Codex 未完成流式任务。消息：%s" % _message)
	if not _diff.contains("player.gd"):
		return _fail("Codex Diff 未更新。")
	if not _mcp_status.to_lower().contains("ready"):
		return _fail("Codex 未读取 godot-mcp 状态：%s" % _mcp_status)
	if not _errors.is_empty():
		return _fail("Codex 后端出现错误：%s" % _errors)
	_current_backend.disconnect_backend()
	return true

func _test_kimi_backend() -> bool:
	_reset_state()
	var script: Script = load("res://addons/godot_ai_manager/kimi_backend.gd")
	_current_backend = script.new()
	_connect_signals(_current_backend)
	var mock_name := "mock_kimi.cmd" if OS.get_name() == "Windows" else "mock_kimi.py"
	_current_backend.configure({
		"project_root": ProjectSettings.globalize_path("res://"),
		"executable_path": ProjectSettings.globalize_path("res://" + mock_name),
		"mcp_endpoint": "http://127.0.0.1:9080/mcp",
		"model_override": "mock-model",
	})
	var generated_path := ProjectSettings.globalize_path("res://generated_by_kimi.txt")
	if FileAccess.file_exists(generated_path):
		DirAccess.remove_absolute(generated_path)
	var escaped_path := ProjectSettings.globalize_path("res://../escape.txt")
	if FileAccess.file_exists(escaped_path):
		DirAccess.remove_absolute(escaped_path)
	_current_backend.connect_backend()
	if not await _wait_for_state("connected", 10000):
		return _fail("Kimi 后端未完成 ACP 初始化和会员验证。")
	_current_backend.send_prompt("执行 Kimi ACP 后端测试")
	if not await _wait_for_state("approval", 10000):
		return _fail("Kimi ACP 未显示权限请求。")
	if not await _wait_for_state("kimi_completed", 10000):
		return _fail("Kimi ACP 未完成流式任务。消息：%s" % _message)
	if not FileAccess.file_exists(generated_path):
		return _fail("Kimi ACP 文件写入反向 RPC 未执行。")
	if FileAccess.file_exists(escaped_path):
		return _fail("Kimi ACP 越权写入项目目录之外。")
	if not _diff.contains("kimi.gd"):
		return _fail("Kimi 工具更新中的 Diff 未显示。")
	if not _mcp_status.contains("Kimi"):
		return _fail("Kimi 会话未报告 Godot MCP Native 转发状态：%s" % _mcp_status)
	if not _errors.is_empty():
		return _fail("Kimi 后端出现错误：%s" % _errors)
	_current_backend.disconnect_backend()
	return true

func _test_manager_dock() -> bool:
	var scene: PackedScene = load("res://addons/godot_ai_manager/godot_ai_manager_dock.tscn")
	if scene == null:
		return _fail("无法加载管理器 Dock 场景。")
	var dock: Control = scene.instantiate()
	root.add_child(dock)
	await process_frame
	dock.select_backend("kimi")
	if dock.active_backend_id() != "kimi":
		dock.queue_free()
		return _fail("Dock 无法切换到 Kimi 后端。")
	dock.select_backend("codex")
	if dock.active_backend_id() != "codex":
		dock.queue_free()
		return _fail("Dock 无法切换回 Codex 后端。")
	dock.shutdown()
	dock.queue_free()
	return true

func _connect_signals(backend: Object) -> void:
	backend.message_delta.connect(_on_message_delta)
	backend.diff_changed.connect(_on_diff_changed)
	backend.mcp_status_changed.connect(_on_mcp_status_changed)
	backend.error_message.connect(_on_backend_error)
	backend.message_completed.connect(_on_message_completed)
	backend.approval_requested.connect(_on_approval_requested)

func _on_message_delta(text: String) -> void:
	_message += text

func _on_diff_changed(text: String) -> void:
	_diff = text

func _on_mcp_status_changed(text: String) -> void:
	_mcp_status = text

func _on_backend_error(text: String) -> void:
	_errors.append(text)

func _on_message_completed() -> void:
	_turn_completed = true

func _on_approval_requested(
	_title: String,
	_details: String,
	choices: Array,
	_needs_text: bool,
	_placeholder: String
) -> void:
	_approval_seen = true
	var choice_id := "once"
	if _current_backend.backend_id() == "kimi":
		choice_id = ""
		for value in choices:
			var choice := value as Dictionary
			if str(choice.get("id", "")) == "allow_once":
				choice_id = "allow_once"
				break
		if choice_id.is_empty() and not choices.is_empty():
			choice_id = str((choices[0] as Dictionary).get("id", ""))
	_current_backend.call_deferred("resolve_approval", choice_id, "", false)

func _wait_for_state(state: String, timeout_ms: int) -> bool:
	var deadline := Time.get_ticks_msec() + timeout_ms
	while Time.get_ticks_msec() < deadline:
		if _current_backend != null:
			_current_backend.poll()
		var reached := false
		match state:
			"connected":
				reached = _current_backend.is_backend_connected() and _current_backend.signed_in
			"approval":
				reached = _approval_seen
			"codex_completed":
				reached = _turn_completed and _message.contains("Codex 已通过")
			"kimi_completed":
				reached = _turn_completed and _message.contains("Kimi 已通过")
		if reached:
			return true
		await create_timer(0.01).timeout
	return false

func _reset_state() -> void:
	_current_backend = null
	_message = ""
	_diff = ""
	_mcp_status = ""
	_errors.clear()
	_approval_seen = false
	_turn_completed = false

func _fail(message: String) -> bool:
	if _current_backend != null:
		_current_backend.disconnect_backend()
	push_error(message)
	quit(1)
	return false
