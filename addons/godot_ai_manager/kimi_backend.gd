@tool
extends AiAgentBackend
class_name KimiAgentBackend

const CLIENT_SCRIPT := preload("res://addons/godot_ai_manager/jsonrpc_process_client.gd")
const LOGIN_RUNNER_SCRIPT := preload("res://addons/godot_ai_manager/raw_process_runner.gd")
const RESOLVER_SCRIPT := preload("res://addons/godot_ai_manager/command_resolver.gd")

var _client: JsonRpcProcessClient
var _login_runner: RawProcessRunner
var _resolver: AiCommandResolver
var _initialized := false
var _connecting := false
var _queued_prompt := ""
var _request_context: Dictionary = {}
var _pending_permission_id: Variant = null
var _pending_permission_params: Dictionary = {}
var _pending_permission_options: Array = []
var _login_browser_opened := false
var _login_running := false
var _config_options: Array = []
var _current_diff := ""

func _init() -> void:
	_client = CLIENT_SCRIPT.new() as JsonRpcProcessClient
	_login_runner = LOGIN_RUNNER_SCRIPT.new() as RawProcessRunner
	_resolver = RESOLVER_SCRIPT.new() as AiCommandResolver
	_client.started.connect(_on_started)
	_client.stopped.connect(_on_stopped)
	_client.response_received.connect(_on_response)
	_client.notification_received.connect(_on_notification)
	_client.server_request_received.connect(_on_server_request)
	_client.stderr_received.connect(_on_stderr)
	_client.protocol_error.connect(_on_protocol_error)
	_login_runner.stdout_received.connect(_on_login_output)
	_login_runner.stderr_received.connect(_on_login_output)
	_login_runner.stopped.connect(_on_login_stopped)
	_login_runner.process_error.connect(_on_login_error)

func backend_id() -> String:
	return "kimi"

func backend_name() -> String:
	return "Kimi Code"

func supports_model_override() -> bool:
	return true

func can_logout() -> bool:
	return false

func is_backend_connected() -> bool:
	return _initialized and _client != null and _client.is_running()

func pending_request_count() -> int:
	var count := _request_context.size()
	if _client != null:
		count = maxi(count, _client.pending_request_count())
	if _pending_permission_id != null:
		count += 1
	return count

func connect_backend() -> void:
	if _connecting:
		return
	if is_backend_connected():
		_authenticate()
		return
	_connecting = true
	backend_status_changed.emit("正在启动")
	var launch := _resolver.resolve("kimi", executable_path, PackedStringArray(["acp"]))
	if not bool(launch.get("success", false)):
		_connecting = false
		backend_status_changed.emit("未安装")
		error_message.emit(str(launch.get("error", "未找到 Kimi Code CLI。")))
		return
	var start_result := _client.start_command(
		str(launch.get("executable", "")),
		launch.get("arguments", PackedStringArray()) as PackedStringArray,
		str(launch.get("description", "Kimi Code")),
		true
	)
	if not bool(start_result.get("success", false)):
		_connecting = false
		backend_status_changed.emit("启动失败")
		error_message.emit(str(start_result.get("error", "Kimi ACP 启动失败。")))
		return
	var request_id := _client.send_request("initialize", {
		"protocolVersion": 1,
		"clientCapabilities": {
			"fs": {
				"readTextFile": true,
				"writeTextFile": true,
			},
			"terminal": false,
		},
		"clientInfo": {
			"name": "godot-ai-manager",
			"title": "Godot AI 管理器",
			"version": "1.0.0",
		},
	})
	_track(request_id, "initialize")

func disconnect_backend() -> void:
	_connecting = false
	_initialized = false
	active_turn = false
	signed_in = false
	_pending_permission_id = null
	_pending_permission_params.clear()
	_pending_permission_options.clear()
	_request_context.clear()
	if _client != null:
		_client.shutdown("backend_disconnected")
	if _login_runner != null and _login_runner.is_running():
		_login_runner.shutdown("backend_disconnected")
	backend_status_changed.emit("未连接")
	account_status_changed.emit("未连接", false)
	turn_state_changed.emit(false)

func poll() -> void:
	if _client != null:
		_client.poll()
	if _login_runner != null:
		_login_runner.poll()

func login() -> void:
	if _login_running:
		login_message.emit("Kimi 官方登录流程正在等待浏览器授权。")
		return
	var launch := _resolver.resolve("kimi", executable_path, PackedStringArray(["login"]))
	if not bool(launch.get("success", false)):
		error_message.emit(str(launch.get("error", "未找到 Kimi Code CLI。")))
		return
	_login_browser_opened = false
	_login_running = true
	account_status_changed.emit("等待会员授权", false)
	var result := _login_runner.start_command(
		str(launch.get("executable", "")),
		launch.get("arguments", PackedStringArray()) as PackedStringArray,
		str(launch.get("description", "kimi login"))
	)
	if not bool(result.get("success", false)):
		_login_running = false
		error_message.emit(str(result.get("error", "无法启动 Kimi 官方登录流程。")))
		return
	login_message.emit("已启动官方 `kimi login`。请根据设备码提示在浏览器完成 Kimi 会员授权。")

func logout() -> void:
	login_message.emit("Kimi ACP 没有官方 logout 方法。请在 Kimi Code CLI 交互界面执行 `/logout`。")

func new_session() -> void:
	if active_turn:
		error_message.emit("请先停止当前任务。")
		return
	session_id = ""
	_current_diff = ""
	diff_changed.emit("")
	session_changed.emit("")
	backend_status_changed.emit("已连接")

func resume_session(stored_session_id: String) -> void:
	if not is_backend_connected():
		error_message.emit("Kimi ACP 尚未连接。")
		return
	if not signed_in:
		login_message.emit("请先完成 Kimi 会员登录。")
		return
	if stored_session_id.strip_edges().is_empty():
		error_message.emit("没有可恢复的 Kimi 会话。")
		return
	var params := _session_params()
	params["sessionId"] = stored_session_id
	_track(_client.send_request("session/load", params), "session/load")
	backend_status_changed.emit("正在恢复会话")

func send_prompt(prompt: String) -> void:
	var text := prompt.strip_edges()
	if text.is_empty():
		return
	if not is_backend_connected():
		_queued_prompt = text
		connect_backend()
		login_message.emit("消息已暂存，等待 Kimi ACP 连接。")
		return
	if active_turn:
		error_message.emit("Kimi 正在处理上一项任务。")
		return
	if not signed_in:
		_queued_prompt = text
		login_message.emit("需要先通过官方 `kimi login` 完成 Kimi 会员登录。")
		return
	if session_id.is_empty():
		_queued_prompt = text
		_track(_client.send_request("session/new", _session_params()), "session/new")
		backend_status_changed.emit("正在创建会话")
		return
	_start_prompt(text)

func cancel_turn() -> void:
	if not active_turn or session_id.is_empty():
		return
	_client.send_notification("session/cancel", {"sessionId": session_id})
	log_message.emit("已向 Kimi ACP 请求取消当前任务。")

func resolve_approval(choice_id: String, text_value: String, cancelled: bool) -> void:
	if _pending_permission_id == null:
		return
	var request_id: Variant = _pending_permission_id
	if cancelled or choice_id == "reject":
		_client.respond(request_id, {
			"outcome": {"outcome": "cancelled"},
		})
	else:
		var selected_id := choice_id
		if selected_id == "answer" and not text_value.strip_edges().is_empty():
			selected_id = _match_option_for_text(text_value)
		if selected_id.is_empty() and not _pending_permission_options.is_empty():
			var first := _as_dictionary(_pending_permission_options[0])
			selected_id = str(first.get("optionId", first.get("id", "")))
		_client.respond(request_id, {
			"outcome": {
				"outcome": "selected",
				"optionId": selected_id,
			},
		})
	_pending_permission_id = null
	_pending_permission_params.clear()
	_pending_permission_options.clear()

func _authenticate() -> void:
	if not _initialized:
		return
	_track(_client.send_request("authenticate", {"methodId": "login"}), "authenticate")
	account_status_changed.emit("正在验证会员登录", false)

func _session_params() -> Dictionary:
	return {
		"cwd": project_root,
		"mcpServers": [{
			"name": "godot-mcp",
			"type": "http",
			"url": mcp_endpoint,
			"headers": [],
		}],
	}

func _start_prompt(prompt: String) -> void:
	var instruction := "\n\n[Godot 集成规则] Godot 编辑器专用操作必须使用名为 godot-mcp 的 Godot MCP Native。不要连接、启动或配置 Fennara MCP。完成修改后通过 Godot MCP Native 验证。"
	_track(_client.send_request("session/prompt", {
		"sessionId": session_id,
		"prompt": [{
			"type": "text",
			"text": prompt + instruction,
		}],
	}), "session/prompt")
	active_turn = true
	turn_state_changed.emit(true)
	backend_status_changed.emit("工作中")

func _apply_model_override() -> void:
	if model_override.is_empty() or session_id.is_empty():
		return
	_track(_client.send_request("session/set_config_option", {
		"sessionId": session_id,
		"configId": "model",
		"value": model_override,
	}), "session/set_config_option")

func _on_started(pid: int, description: String) -> void:
	log_message.emit("Kimi ACP 已启动，PID=%s，程序=%s" % [pid, description])
	backend_status_changed.emit("正在初始化")

func _on_stopped(reason: String) -> void:
	_initialized = false
	_connecting = false
	active_turn = false
	turn_state_changed.emit(false)
	backend_status_changed.emit("已停止")
	log_message.emit("Kimi ACP 已停止：%s" % reason)

func _on_response(request_id: Variant, method: String, result: Variant, error: Variant) -> void:
	var key := _request_key(request_id)
	var context := str(_request_context.get(key, method))
	_request_context.erase(key)
	if error != null:
		_handle_request_error(context, error)
		return
	var result_dict := _as_dictionary(result)
	match context:
		"initialize":
			_initialized = true
			_connecting = false
			backend_status_changed.emit("已连接")
			var agent_info := _as_dictionary(result_dict.get("agentInfo", {}))
			log_message.emit("Kimi ACP 初始化完成：%s %s" % [agent_info.get("name", "Kimi Code CLI"), agent_info.get("version", "")])
			_authenticate()
		"authenticate":
			signed_in = true
			account_status_changed.emit("Kimi Code 会员已登录", true)
			_send_queued_if_ready()
		"session/new", "session/load", "session/resume":
			session_id = str(result_dict.get("sessionId", result_dict.get("id", session_id)))
			_config_options = _as_array(result_dict.get("configOptions", []))
			if session_id.is_empty():
				error_message.emit("Kimi ACP 返回的会话没有 ID。")
				return
			session_changed.emit(session_id)
			backend_status_changed.emit("已连接")
			mcp_status_changed.emit("已随 Kimi 会话转发")
			_apply_model_override()
			if context == "session/new" and not _queued_prompt.is_empty():
				var prompt := _queued_prompt
				_queued_prompt = ""
				_start_prompt(prompt)
		"session/prompt":
			active_turn = false
			turn_state_changed.emit(false)
			backend_status_changed.emit("已连接")
			message_completed.emit()
		"session/set_config_option":
			log_message.emit("Kimi 模型设置已应用：%s" % model_override)
		_:
			log_message.emit("Kimi ACP 请求完成：%s" % context)

func _handle_request_error(context: String, error: Variant) -> void:
	var dictionary := _as_dictionary(error)
	var code := int(dictionary.get("code", 0))
	var message := str(dictionary.get("message", error))
	if context == "authenticate" and code == -32000:
		signed_in = false
		account_status_changed.emit("未登录 Kimi Code", false)
		login_message.emit("Kimi ACP 需要会员登录。点击登录将运行官方 `kimi login` 设备码流程。")
		return
	if context == "initialize":
		_connecting = false
		backend_status_changed.emit("协议错误")
	if context == "session/prompt":
		active_turn = false
		turn_state_changed.emit(false)
	error_message.emit("Kimi ACP 请求失败（%s）：%s" % [context, message])

func _on_notification(method: String, params: Dictionary) -> void:
	if method == "session/update":
		_handle_session_update(params)
		return
	log_message.emit("Kimi ACP 通知：%s" % method)

func _handle_session_update(params: Dictionary) -> void:
	var update := _as_dictionary(params.get("update", {}))
	var kind := str(update.get("sessionUpdate", update.get("type", "")))
	match kind:
		"agent_message_chunk":
			message_delta.emit(_content_text(update.get("content", {})))
		"agent_thought_chunk":
			thought_delta.emit(_content_text(update.get("content", {})))
		"tool_call":
			var title := str(update.get("title", update.get("name", "工具调用")))
			var details := JSON.stringify(update.get("rawInput", update.get("content", {})), "  ")
			tool_event.emit(title, details, str(update.get("status", "开始")))
			_try_update_diff(update)
		"tool_call_update":
			var title := str(update.get("title", update.get("toolCallId", "工具调用")))
			var details := JSON.stringify(update.get("rawOutput", update.get("content", {})), "  ")
			tool_event.emit(title, details, str(update.get("status", "更新")))
			_try_update_diff(update)
		"plan":
			tool_event.emit("计划", JSON.stringify(update.get("entries", update), "  "), "更新")
		"config_option_update":
			_config_options = _as_array(update.get("configOptions", _config_options))
			log_message.emit("Kimi 会话配置选项已更新。")
		"available_commands_update":
			log_message.emit("Kimi 可用命令列表已更新。")
		_:
			log_message.emit("Kimi 会话更新：%s" % kind)

func _on_server_request(request_id: Variant, method: String, params: Dictionary) -> void:
	match method:
		"session/request_permission":
			_show_permission(request_id, params)
		"fs/read_text_file":
			_handle_read_file(request_id, params)
		"fs/write_text_file":
			_handle_write_file(request_id, params)
		_:
			_client.respond_error(request_id, -32601, "Godot AI 管理器未实现该 ACP 反向请求：%s" % method)

func _show_permission(request_id: Variant, params: Dictionary) -> void:
	if _pending_permission_id != null:
		_client.respond(request_id, {"outcome": {"outcome": "cancelled"}})
		return
	_pending_permission_id = request_id
	_pending_permission_params = params
	_pending_permission_options = _as_array(params.get("options", []))
	var choices: Array = []
	for option_value in _pending_permission_options:
		var option := _as_dictionary(option_value)
		var option_id := str(option.get("optionId", option.get("id", "")))
		var label := str(option.get("name", option.get("label", option_id)))
		choices.append({"id": option_id, "label": label})
	choices.append({"id": "reject", "label": "拒绝"})
	var tool_call := _as_dictionary(params.get("toolCall", {}))
	var title := str(tool_call.get("title", tool_call.get("name", "Kimi 请求权限")))
	var details := JSON.stringify(tool_call, "  ")
	var needs_text := bool(params.get("needsInput", false)) or _pending_permission_options.is_empty()
	approval_requested.emit(title, details, choices, needs_text, "可填写答案或选择上方选项")

func _handle_read_file(request_id: Variant, params: Dictionary) -> void:
	var path_result := _resolve_safe_path(str(params.get("path", "")))
	if not bool(path_result.get("success", false)):
		_client.respond_error(request_id, -32001, str(path_result.get("error", "文件路径无效。")))
		return
	var path := str(path_result.get("path", ""))
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_client.respond_error(request_id, -32002, "无法读取文件：%s" % path)
		return
	var content := file.get_as_text()
	file.close()
	var line_number := maxi(1, int(params.get("line", 1)))
	var limit := int(params.get("limit", 0))
	if line_number > 1 or limit > 0:
		var lines := content.split("\n", true)
		var start := mini(line_number - 1, lines.size())
		var end := lines.size() if limit <= 0 else mini(start + limit, lines.size())
		content = "\n".join(lines.slice(start, end))
	_client.respond(request_id, {"content": content})

func _handle_write_file(request_id: Variant, params: Dictionary) -> void:
	var path_result := _resolve_safe_path(str(params.get("path", "")))
	if not bool(path_result.get("success", false)):
		_client.respond_error(request_id, -32001, str(path_result.get("error", "文件路径无效。")))
		return
	var path := str(path_result.get("path", ""))
	var parent := path.get_base_dir()
	var make_error := DirAccess.make_dir_recursive_absolute(parent)
	if make_error != OK and make_error != ERR_ALREADY_EXISTS:
		_client.respond_error(request_id, -32003, "无法创建目录：%s" % parent)
		return
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_client.respond_error(request_id, -32004, "无法写入文件：%s" % path)
		return
	file.store_string(str(params.get("content", "")))
	var write_error := file.get_error()
	file.close()
	if write_error != OK:
		_client.respond_error(request_id, -32005, "写入文件失败，错误码：%s" % write_error)
		return
	_client.respond(request_id, {})

func _resolve_safe_path(requested: String) -> Dictionary:
	if requested.strip_edges().is_empty():
		return {"success": false, "error": "文件路径为空。"}
	var root := project_root.replace("\\", "/").simplify_path().trim_suffix("/")
	var candidate := requested
	if candidate.begins_with("res://"):
		candidate = ProjectSettings.globalize_path(candidate)
	elif not candidate.is_absolute_path():
		candidate = root.path_join(candidate)
	candidate = candidate.replace("\\", "/").simplify_path()
	if candidate != root and not candidate.begins_with(root + "/"):
		return {"success": false, "error": "Kimi 请求访问项目目录之外的文件，已拒绝：%s" % requested}
	return {"success": true, "path": candidate}

func _on_stderr(text: String) -> void:
	log_message.emit("[Kimi ACP] %s" % text)

func _on_protocol_error(message: String, raw_line: String) -> void:
	error_message.emit("Kimi ACP 通信错误：%s%s" % [message, ("\n" + raw_line) if not raw_line.is_empty() else ""])

func _on_login_output(text: String) -> void:
	login_message.emit(text)
	if _login_browser_opened:
		return
	var regex := RegEx.new()
	if regex.compile("https?://[^\\s]+") != OK:
		return
	var match_value := regex.search(text)
	if match_value == null:
		return
	var url := match_value.get_string().trim_suffix(".").trim_suffix(",")
	_login_browser_opened = true
	OS.shell_open(url)
	login_message.emit("已打开 Kimi 官方设备授权页面。请按输出中的用户码完成登录。")

func _on_login_stopped(reason: String) -> void:
	_login_running = false
	login_message.emit("Kimi 官方登录进程已结束，正在重新验证会员状态。")
	if is_backend_connected():
		_authenticate()
	else:
		connect_backend()
	log_message.emit("kimi login 结束：%s" % reason)

func _on_login_error(message: String) -> void:
	_login_running = false
	error_message.emit(message)

func _track(request_id: int, context: String) -> void:
	if request_id >= 0:
		_request_context[_request_key(request_id)] = context

func _request_key(value: Variant) -> String:
	if value is float and is_equal_approx(float(value), round(float(value))):
		return str(int(round(float(value))))
	return str(value)

func _send_queued_if_ready() -> void:
	if not signed_in or _queued_prompt.is_empty():
		return
	var prompt := _queued_prompt
	_queued_prompt = ""
	send_prompt(prompt)

func _content_text(content: Variant) -> String:
	if content is Dictionary:
		return str((content as Dictionary).get("text", ""))
	if content is String:
		return str(content)
	return ""

func _try_update_diff(update: Dictionary) -> void:
	var candidates: Array = [
		update.get("diff"),
		update.get("rawOutput"),
		update.get("content"),
	]
	for value in candidates:
		var text := ""
		if value is String:
			text = str(value)
		elif value is Dictionary:
			var dictionary := value as Dictionary
			text = str(dictionary.get("diff", dictionary.get("text", "")))
		if text.contains("diff --git") or text.contains("@@"):
			_current_diff = text
			diff_changed.emit(_current_diff)
			return

func _match_option_for_text(text: String) -> String:
	var needle := text.strip_edges().to_lower()
	for option_value in _pending_permission_options:
		var option := _as_dictionary(option_value)
		var label := str(option.get("name", option.get("label", ""))).to_lower()
		if label == needle:
			return str(option.get("optionId", option.get("id", "")))
	return ""

func _as_dictionary(value: Variant) -> Dictionary:
	if value is Dictionary:
		return value as Dictionary
	return {}

func _as_array(value: Variant) -> Array:
	if value is Array:
		return value as Array
	return []
