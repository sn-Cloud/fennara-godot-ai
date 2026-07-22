@tool
extends AiAgentBackend
class_name CodexAgentBackend

const CLIENT_SCRIPT := preload("res://addons/godot_ai_manager/jsonrpc_process_client.gd")
const RESOLVER_SCRIPT := preload("res://addons/godot_ai_manager/command_resolver.gd")
const CONFIG_SCRIPT := preload("res://addons/godot_ai_manager/codex_config_manager.gd")

var sandbox_mode := "workspace-write"
var approval_policy := "on-request"

var _client: JsonRpcProcessClient
var _resolver: AiCommandResolver
var _config_manager: CodexGodotMcpConfigManager
var _initialized := false
var _connecting := false
var _requires_auth := true
var _account: Dictionary = {}
var _turn_id := ""
var _queued_prompt := ""
var _request_context: Dictionary = {}
var _pending_server_request_id: Variant = null
var _pending_server_request_method := ""
var _pending_server_request_params: Dictionary = {}
var _current_diff := ""

func _init() -> void:
	_client = CLIENT_SCRIPT.new() as JsonRpcProcessClient
	_resolver = RESOLVER_SCRIPT.new() as AiCommandResolver
	_config_manager = CONFIG_SCRIPT.new() as CodexGodotMcpConfigManager
	_client.started.connect(_on_started)
	_client.stopped.connect(_on_stopped)
	_client.response_received.connect(_on_response)
	_client.notification_received.connect(_on_notification)
	_client.server_request_received.connect(_on_server_request)
	_client.stderr_received.connect(_on_stderr)
	_client.protocol_error.connect(_on_protocol_error)

func configure(options: Dictionary) -> void:
	super.configure(options)
	sandbox_mode = str(options.get("sandbox_mode", sandbox_mode))
	approval_policy = str(options.get("approval_policy", approval_policy))

func backend_id() -> String:
	return "codex"

func backend_name() -> String:
	return "Codex"

func supports_model_override() -> bool:
	return true

func can_logout() -> bool:
	return true

func is_backend_connected() -> bool:
	return _initialized and _client != null and _client.is_running()

func pending_request_count() -> int:
	var count := _request_context.size()
	if _client != null:
		count = maxi(count, _client.pending_request_count())
	if _pending_server_request_id != null:
		count += 1
	return count

func connect_backend() -> void:
	if _connecting:
		return
	if is_backend_connected():
		_refresh_account()
		_refresh_mcp_status()
		return

	_connecting = true
	backend_status_changed.emit("正在启动")
	var config_result := _config_manager.ensure_config(project_root, mcp_endpoint)
	if not bool(config_result.get("success", false)):
		_connecting = false
		error_message.emit(str(config_result.get("error", "无法写入 Codex MCP 配置。")))
		backend_status_changed.emit("配置失败")
		return
	if bool(config_result.get("legacy_fennara_mcp_found", false)):
		log_message.emit("检测到用户 Codex 配置中仍有旧 Fennara MCP 条目；本插件不会启动或修改它，请按需手动移除。")
	var config_action := "已更新" if bool(config_result.get("changed", false)) else "已确认"
	log_message.emit("Godot MCP Native 的 Codex 配置%s：%s" % [config_action, config_result.get("path", "")])

	var launch := _resolver.resolve("codex", executable_path, PackedStringArray(["app-server", "--stdio"]))
	if not bool(launch.get("success", false)):
		_connecting = false
		backend_status_changed.emit("未安装")
		error_message.emit(str(launch.get("error", "未找到 Codex。")))
		return
	var start_result := _client.start_command(
		str(launch.get("executable", "")),
		launch.get("arguments", PackedStringArray()) as PackedStringArray,
		str(launch.get("description", "Codex")),
		false
	)
	if not bool(start_result.get("success", false)):
		_connecting = false
		backend_status_changed.emit("启动失败")
		error_message.emit(str(start_result.get("error", "Codex 启动失败。")))
		return

	var request_id := _client.send_request("initialize", {
		"clientInfo": {
			"name": "godot_ai_manager",
			"title": "Godot AI 管理器",
			"version": "1.0.0",
		},
		"capabilities": {
			"experimentalApi": true,
		},
	})
	_track(request_id, "initialize")

func disconnect_backend() -> void:
	_connecting = false
	_initialized = false
	active_turn = false
	signed_in = false
	_turn_id = ""
	_pending_server_request_id = null
	_pending_server_request_method = ""
	_pending_server_request_params.clear()
	_request_context.clear()
	if _client != null:
		_client.shutdown("backend_disconnected")
	backend_status_changed.emit("未连接")
	account_status_changed.emit("未连接", false)
	turn_state_changed.emit(false)

func poll() -> void:
	if _client != null:
		_client.poll()

func login() -> void:
	if not is_backend_connected():
		connect_backend()
		login_message.emit("请在 Codex 连接完成后再次点击登录。")
		return
	var request_id := _client.send_request("account/login/start", {
		"type": "chatgpt",
		"useHostedLoginSuccessPage": true,
		"appBrand": "codex",
	})
	_track(request_id, "account/login/start")
	account_status_changed.emit("正在打开登录", false)

func logout() -> void:
	if not is_backend_connected():
		return
	_track(_client.send_request("account/logout", {}), "account/logout")

func new_session() -> void:
	if active_turn:
		error_message.emit("请先停止当前任务。")
		return
	session_id = ""
	_turn_id = ""
	_current_diff = ""
	diff_changed.emit("")
	session_changed.emit("")
	backend_status_changed.emit("已连接")

func resume_session(stored_session_id: String) -> void:
	if not is_backend_connected():
		error_message.emit("Codex 尚未连接。")
		return
	if stored_session_id.strip_edges().is_empty():
		error_message.emit("没有可恢复的 Codex 会话。")
		return
	_track(_client.send_request("thread/resume", {
		"threadId": stored_session_id,
	}), "thread/resume")
	backend_status_changed.emit("正在恢复会话")

func send_prompt(prompt: String) -> void:
	var text := prompt.strip_edges()
	if text.is_empty():
		return
	if not is_backend_connected():
		_queued_prompt = text
		connect_backend()
		login_message.emit("消息已暂存，等待 Codex 连接。")
		return
	if active_turn:
		error_message.emit("Codex 正在处理上一项任务。")
		return
	if _requires_auth and not signed_in:
		_queued_prompt = text
		login_message.emit("需要先完成 ChatGPT／Codex 会员登录。")
		return
	if session_id.is_empty():
		_queued_prompt = text
		_start_thread()
	else:
		_start_turn(text)

func cancel_turn() -> void:
	if not active_turn or session_id.is_empty() or _turn_id.is_empty():
		return
	_track(_client.send_request("turn/interrupt", {
		"threadId": session_id,
		"turnId": _turn_id,
	}), "turn/interrupt")

func resolve_approval(choice_id: String, text_value: String, cancelled: bool) -> void:
	if _pending_server_request_id == null:
		return
	var request_id: Variant = _pending_server_request_id
	var method := _pending_server_request_method
	var params := _pending_server_request_params
	var rejected := cancelled or choice_id == "reject"
	match method:
		"item/commandExecution/requestApproval", "item/fileChange/requestApproval":
			_client.respond(request_id, {
				"decision": "decline" if rejected else ("acceptForSession" if choice_id == "session" else "accept"),
			})
		"item/permissions/requestApproval":
			_client.respond(request_id, {
				"permissions": {} if rejected else _as_dictionary(params.get("permissions", {})),
				"scope": "session" if choice_id == "session" else "turn",
				"strictAutoReview": false,
			})
		"item/tool/requestUserInput":
			if rejected:
				_client.respond_error(request_id, -32000, "用户拒绝回答。")
			else:
				var answers := {}
				for question_value in _as_array(params.get("questions", [])):
					var question := _as_dictionary(question_value)
					answers[str(question.get("id", "question"))] = {"answers": [text_value]}
				_client.respond(request_id, {"answers": answers})
		"mcpServer/elicitation/request":
			if rejected:
				_client.respond(request_id, {"action": "decline", "content": null, "_meta": null})
			else:
				var content: Variant = {"value": text_value}
				var parsed := JSON.parse_string(text_value)
				if parsed != null:
					content = parsed
				_client.respond(request_id, {"action": "accept", "content": content, "_meta": null})
		"execCommandApproval", "applyPatchApproval":
			_client.respond(request_id, {"decision": "denied" if rejected else "approved"})
		_:
			_client.respond_error(request_id, -32601, "不支持的审批方法：%s" % method)
	_pending_server_request_id = null
	_pending_server_request_method = ""
	_pending_server_request_params.clear()

func _start_thread() -> void:
	var params := {
		"cwd": project_root,
		"approvalPolicy": approval_policy,
		"sandbox": sandbox_mode,
		"developerInstructions": "你正在 Godot 编辑器内工作。Godot 编辑器专用操作必须优先使用名为 godot-mcp 的 Godot MCP Native；文件、Shell 和 Git 可使用 Codex 自带工具。不要连接、启动或配置 Fennara MCP。完成有意义的修改后，通过 Godot MCP Native 验证场景、脚本、运行状态或截图，再报告结果。",
		"sessionStartSource": "startup",
	}
	if not model_override.is_empty():
		params["model"] = model_override
	_track(_client.send_request("thread/start", params), "thread/start")
	backend_status_changed.emit("正在创建会话")

func _start_turn(prompt: String) -> void:
	var params := {
		"threadId": session_id,
		"input": [{
			"type": "text",
			"text": prompt,
			"text_elements": [],
		}],
		"cwd": project_root,
		"approvalPolicy": approval_policy,
	}
	if not model_override.is_empty():
		params["model"] = model_override
	_track(_client.send_request("turn/start", params), "turn/start")
	active_turn = true
	turn_state_changed.emit(true)
	backend_status_changed.emit("工作中")

func _refresh_account() -> void:
	if not _initialized:
		return
	_track(_client.send_request("account/read", {"refreshToken": false}), "account/read")

func _reload_mcp() -> void:
	if _initialized:
		_track(_client.send_request("config/mcpServer/reload", {}), "config/mcpServer/reload")

func _refresh_mcp_status() -> void:
	if not _initialized:
		return
	var params := {}
	if not session_id.is_empty():
		params["threadId"] = session_id
	_track(_client.send_request("mcpServerStatus/list", params), "mcpServerStatus/list")
	mcp_status_changed.emit("正在检查")

func _on_started(pid: int, description: String) -> void:
	log_message.emit("Codex app-server 已启动，PID=%s，程序=%s" % [pid, description])
	backend_status_changed.emit("正在初始化")

func _on_stopped(reason: String) -> void:
	_initialized = false
	_connecting = false
	active_turn = false
	turn_state_changed.emit(false)
	backend_status_changed.emit("已停止")
	log_message.emit("Codex app-server 已停止：%s" % reason)

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
			_client.send_notification("initialized", {})
			backend_status_changed.emit("已连接")
			_refresh_account()
			_reload_mcp()
		"account/read":
			_requires_auth = bool(result_dict.get("requiresOpenaiAuth", true))
			_account = _as_dictionary(result_dict.get("account", {}))
			signed_in = not _account.is_empty() or not _requires_auth
			account_status_changed.emit(_account_summary(), signed_in)
			_send_queued_if_ready()
		"account/login/start":
			var auth_url := str(result_dict.get("authUrl", result_dict.get("authorization_url", "")))
			if not auth_url.is_empty():
				OS.shell_open(auth_url)
				login_message.emit("已在浏览器中打开 ChatGPT／Codex 官方登录页面。")
			else:
				login_message.emit("Codex 已启动登录流程，请按官方窗口提示完成授权。")
		"account/logout":
			_account.clear()
			signed_in = false
			account_status_changed.emit("未登录", false)
		"thread/start", "thread/resume":
			var thread := _as_dictionary(result_dict.get("thread", result_dict))
			session_id = str(thread.get("id", ""))
			if session_id.is_empty():
				error_message.emit("Codex 返回的会话没有 ID。")
				return
			session_changed.emit(session_id)
			backend_status_changed.emit("已连接")
			_refresh_mcp_status()
			if context == "thread/start" and not _queued_prompt.is_empty():
				var prompt := _queued_prompt
				_queued_prompt = ""
				_start_turn(prompt)
		"turn/start":
			var turn := _as_dictionary(result_dict.get("turn", result_dict))
			_turn_id = str(turn.get("id", _turn_id))
			active_turn = true
			turn_state_changed.emit(true)
		"turn/interrupt":
			log_message.emit("已向 Codex 请求中断当前任务。")
		"config/mcpServer/reload":
			_refresh_mcp_status()
		"mcpServerStatus/list":
			_apply_mcp_status(result_dict)
		_:
			log_message.emit("Codex 请求完成：%s" % context)

func _handle_request_error(context: String, error: Variant) -> void:
	var text := _format_error(error)
	if context == "initialize":
		_connecting = false
		backend_status_changed.emit("协议错误")
	if context == "account/login/start":
		account_status_changed.emit("登录失败", false)
	error_message.emit("Codex 请求失败（%s）：%s" % [context, text])

func _on_notification(method: String, params: Dictionary) -> void:
	match method:
		"account/updated":
			var auth_mode := params.get("authMode")
			if auth_mode == null:
				_account.clear()
				signed_in = false
			else:
				_account = {"authMode": auth_mode, "planType": params.get("planType")}
				signed_in = true
			account_status_changed.emit(_account_summary(), signed_in)
			_send_queued_if_ready()
		"account/login/completed":
			if bool(params.get("success", false)):
				login_message.emit("ChatGPT／Codex 登录完成。")
				_refresh_account()
			else:
				error_message.emit("ChatGPT／Codex 登录失败：%s" % params.get("error", "未知错误"))
		"turn/started":
			var turn := _as_dictionary(params.get("turn", params))
			_turn_id = str(turn.get("id", _turn_id))
			active_turn = true
			turn_state_changed.emit(true)
		"turn/completed":
			var turn := _as_dictionary(params.get("turn", params))
			var status := str(turn.get("status", "completed"))
			active_turn = false
			_turn_id = ""
			turn_state_changed.emit(false)
			backend_status_changed.emit("已连接")
			message_completed.emit()
			if status == "failed":
				error_message.emit("Codex 任务失败：%s" % _format_error(turn.get("error")))
			elif status == "interrupted":
				login_message.emit("Codex 任务已中断。")
		"turn/diff/updated":
			_current_diff = str(params.get("diff", ""))
			diff_changed.emit(_current_diff)
		"item/agentMessage/delta":
			message_delta.emit(str(params.get("delta", "")))
		"item/reasoning/summaryTextDelta":
			thought_delta.emit(str(params.get("delta", "")))
		"item/commandExecution/outputDelta":
			log_message.emit(str(params.get("delta", "")))
		"item/started":
			_render_item(_as_dictionary(params.get("item", {})), "开始")
		"item/completed":
			var item := _as_dictionary(params.get("item", {}))
			if str(item.get("type", "")) == "agentMessage":
				var text := _extract_agent_text(item)
				if not text.is_empty():
					message_delta.emit(text)
			else:
				_render_item(item, "完成")
		"mcpServer/startupStatus/updated":
			if str(params.get("name", "")) == "godot-mcp":
				var status := str(params.get("status", "unknown"))
				var error := str(params.get("error", ""))
				mcp_status_changed.emit(status + (("：" + error) if not error.is_empty() else ""))
		"error":
			error_message.emit("Codex 错误：%s" % _format_error(params))

func _on_server_request(request_id: Variant, method: String, params: Dictionary) -> void:
	var supported := [
		"item/commandExecution/requestApproval",
		"item/fileChange/requestApproval",
		"item/permissions/requestApproval",
		"item/tool/requestUserInput",
		"mcpServer/elicitation/request",
		"execCommandApproval",
		"applyPatchApproval",
	]
	if not supported.has(method):
		_client.respond_error(request_id, -32601, "Godot AI 管理器不支持该 Codex 请求：%s" % method)
		return
	if _pending_server_request_id != null:
		_client.respond_error(request_id, -32000, "已有另一个审批请求正在等待处理。")
		return
	_pending_server_request_id = request_id
	_pending_server_request_method = method
	_pending_server_request_params = params
	var choices: Array = [
		{"id": "once", "label": "允许一次"},
		{"id": "reject", "label": "拒绝"},
	]
	if method == "item/commandExecution/requestApproval" or method == "item/fileChange/requestApproval" or method == "item/permissions/requestApproval":
		choices.insert(1, {"id": "session", "label": "本会话允许"})
	var needs_text := method == "item/tool/requestUserInput" or method == "mcpServer/elicitation/request"
	approval_requested.emit(
		_approval_title(method),
		_approval_details(method, params),
		choices,
		needs_text,
		"请输入回答；MCP elicitation 可填写 JSON"
	)

func _on_stderr(text: String) -> void:
	log_message.emit("[Codex] %s" % text)

func _on_protocol_error(message: String, raw_line: String) -> void:
	error_message.emit("Codex 通信错误：%s%s" % [message, ("\n" + raw_line) if not raw_line.is_empty() else ""])

func _apply_mcp_status(result: Dictionary) -> void:
	var entries := _as_array(result.get("data", result.get("servers", [])))
	for entry_value in entries:
		var entry := _as_dictionary(entry_value)
		var name := str(entry.get("name", entry.get("serverName", "")))
		if name != "godot-mcp":
			continue
		var status := str(entry.get("status", entry.get("startupStatus", "ready")))
		var error := str(entry.get("error", ""))
		mcp_status_changed.emit(status + (("：" + error) if not error.is_empty() else ""))
		return
	mcp_status_changed.emit("已配置，等待会话连接")

func _render_item(item: Dictionary, status: String) -> void:
	var item_type := str(item.get("type", "item"))
	match item_type:
		"commandExecution":
			tool_event.emit("命令", str(item.get("command", item.get("commands", ""))), status)
		"fileChange":
			tool_event.emit("文件修改", _summarize_file_change(item), status)
		"mcpToolCall":
			var server := str(item.get("server", item.get("serverName", "MCP")))
			var tool := str(item.get("tool", item.get("toolName", item.get("name", "tool"))))
			tool_event.emit("MCP：%s" % server, tool, status)
		"webSearch":
			tool_event.emit("网页搜索", str(item.get("query", "")), status)
		_:
			log_message.emit("Codex 项目事件：%s（%s）" % [item_type, status])

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

func _account_summary() -> String:
	if not signed_in:
		return "未登录"
	if _account.is_empty():
		return "本地或外部提供方"
	var mode := str(_account.get("authMode", _account.get("type", "已登录")))
	var plan := str(_account.get("planType", ""))
	return mode + ((" / " + plan) if not plan.is_empty() and plan != "<null>" else "")

func _approval_title(method: String) -> String:
	match method:
		"item/commandExecution/requestApproval", "execCommandApproval":
			return "Codex 请求执行命令"
		"item/fileChange/requestApproval", "applyPatchApproval":
			return "Codex 请求修改文件"
		"item/permissions/requestApproval":
			return "Codex 请求额外权限"
		"item/tool/requestUserInput":
			return "Codex 需要你的回答"
		"mcpServer/elicitation/request":
			return "Godot MCP Native 需要输入"
		_:
			return method

func _approval_details(method: String, params: Dictionary) -> String:
	if method == "item/commandExecution/requestApproval" or method == "execCommandApproval":
		return "命令：\n%s\n\n工作目录：\n%s\n\n原因：\n%s" % [
			params.get("command", params.get("commands", "")),
			params.get("cwd", project_root),
			params.get("reason", ""),
		]
	if method == "item/fileChange/requestApproval" or method == "applyPatchApproval":
		return "原因：\n%s\n\n当前 Diff：\n%s" % [
			params.get("reason", ""),
			_current_diff if not _current_diff.is_empty() else JSON.stringify(params, "  "),
		]
	if method == "item/tool/requestUserInput":
		var lines: Array[String] = []
		for value in _as_array(params.get("questions", [])):
			var question := _as_dictionary(value)
			lines.append(str(question.get("question", question.get("header", "问题"))))
			for option_value in _as_array(question.get("options", [])):
				var option := _as_dictionary(option_value)
				lines.append("- %s：%s" % [option.get("label", ""), option.get("description", "")])
		return "\n".join(lines)
	return JSON.stringify(params, "  ")

func _summarize_file_change(item: Dictionary) -> String:
	var changes := _as_array(item.get("changes", []))
	if changes.is_empty():
		return str(item.get("path", "待处理文件修改"))
	var lines: Array[String] = []
	for value in changes:
		var change := _as_dictionary(value)
		lines.append("%s %s" % [change.get("kind", "update"), change.get("path", "")])
	return "\n".join(lines)

func _extract_agent_text(item: Dictionary) -> String:
	if item.has("text"):
		return str(item.get("text", ""))
	var parts: Array[String] = []
	for value in _as_array(item.get("content", [])):
		var part := _as_dictionary(value)
		if part.has("text"):
			parts.append(str(part.get("text", "")))
	return "".join(parts)

func _format_error(error: Variant) -> String:
	if error == null:
		return "未知错误"
	if error is Dictionary:
		var dictionary := error as Dictionary
		return str(dictionary.get("message", JSON.stringify(dictionary)))
	return str(error)

func _as_dictionary(value: Variant) -> Dictionary:
	if value is Dictionary:
		return value as Dictionary
	return {}

func _as_array(value: Variant) -> Array:
	if value is Array:
		return value as Array
	return []
