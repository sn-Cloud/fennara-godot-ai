@tool
extends PanelContainer
class_name CodexNativeChatDock

const CLIENT_SCRIPT := preload("res://addons/codex_native_chat/codex_app_server_client.gd")
const CONFIG_MANAGER_SCRIPT := preload("res://addons/codex_native_chat/codex_config_manager.gd")
const SETTINGS_PATH := "user://codex_native_chat.cfg"
const DEFAULT_MCP_ENDPOINT := "http://127.0.0.1:9080/mcp"
const CLIENT_VERSION := "1.0.0"

var _editor_interface: EditorInterface
var _project_root: String = ""
var _client: CodexAppServerClient
var _config_manager: CodexNativeConfigManager
var _settings := ConfigFile.new()

var _initialized: bool = false
var _connecting: bool = false
var _thread_id: String = ""
var _turn_id: String = ""
var _last_thread_id: String = ""
var _queued_prompt: String = ""
var _agent_stream_open: bool = false
var _active_turn: bool = false
var _account: Dictionary = {}
var _requires_openai_auth: bool = true
var _pending_server_request_id: Variant = null
var _pending_server_request_method: String = ""
var _pending_server_request_params: Dictionary = {}
var _request_context: Dictionary = {}
var _current_diff: String = ""

var _codex_path: String = ""
var _mcp_endpoint: String = DEFAULT_MCP_ENDPOINT
var _model: String = ""
var _sandbox_mode: String = "workspace-write"
var _approval_policy: String = "on-request"
var _auto_connect: bool = true

var _codex_status_label: Label
var _account_status_label: Label
var _mcp_status_label: Label
var _connect_button: Button
var _login_button: Button
var _new_button: Button
var _resume_button: Button
var _stop_button: Button
var _settings_button: Button
var _transcript: RichTextLabel
var _diff_view: TextEdit
var _log_view: TextEdit
var _input: TextEdit
var _send_button: Button
var _settings_panel: PanelContainer
var _codex_path_edit: LineEdit
var _mcp_endpoint_edit: LineEdit
var _model_edit: LineEdit
var _sandbox_option: OptionButton
var _approval_option: OptionButton
var _auto_connect_check: CheckBox
var _approval_panel: PanelContainer
var _approval_title: Label
var _approval_details: TextEdit
var _approval_answer: TextEdit
var _approval_once_button: Button
var _approval_session_button: Button
var _approval_reject_button: Button
var _tab_container: TabContainer

func configure(editor_interface: EditorInterface) -> void:
	_editor_interface = editor_interface
	_project_root = ProjectSettings.globalize_path("res://").trim_suffix("/").trim_suffix("\\")
	if is_inside_tree():
		_finish_configuration()

func _ready() -> void:
	_build_ui()
	_load_settings()
	_create_client()
	set_process(true)
	_finish_configuration()

func _process(_delta: float) -> void:
	if _client != null:
		_client.poll()

func shutdown() -> void:
	if _client != null:
		_client.shutdown("plugin_disabled")

func _finish_configuration() -> void:
	if _project_root.is_empty():
		_project_root = ProjectSettings.globalize_path("res://").trim_suffix("/").trim_suffix("\\")
	_update_status_labels()
	if _auto_connect and not _is_headless() and not _connecting and not _initialized:
		call_deferred("connect_codex")

func _create_client() -> void:
	_client = CLIENT_SCRIPT.new() as CodexAppServerClient
	_config_manager = CONFIG_MANAGER_SCRIPT.new() as CodexNativeConfigManager
	_client.started.connect(_on_client_started)
	_client.stopped.connect(_on_client_stopped)
	_client.status_changed.connect(_on_client_status_changed)
	_client.response_received.connect(_on_response_received)
	_client.notification_received.connect(_on_notification_received)
	_client.server_request_received.connect(_on_server_request_received)
	_client.stderr_received.connect(_on_stderr_received)
	_client.protocol_error.connect(_on_protocol_error)

func connect_codex() -> void:
	if _client == null or _connecting:
		return
	if _client.is_running() and _initialized:
		_refresh_account()
		_refresh_mcp_status()
		return

	_connecting = true
	_initialized = false
	_connect_button.disabled = true
	_set_codex_status("starting")
	_log("Ensuring project Codex MCP configuration.")
	var config_result := _config_manager.ensure_project_mcp_config(_project_root, _mcp_endpoint)
	if not bool(config_result.get("success", false)):
		_log("MCP configuration failed: %s" % config_result.get("error", "Unknown error"))
	else:
		var action := "updated" if bool(config_result.get("changed", false)) else "verified"
		_log("Project MCP configuration %s: %s" % [action, config_result.get("path", "")])

	var start_result := _client.start(_codex_path)
	if not bool(start_result.get("success", false)):
		_connecting = false
		_connect_button.disabled = false
		_set_codex_status("not connected")
		_append_system("Codex could not start: %s" % start_result.get("error", "Unknown error"))
		return

	var request_id := _client.send_request("initialize", {
		"clientInfo": {
			"name": "godot_codex_native_chat",
			"title": "Godot Codex Native Chat",
			"version": CLIENT_VERSION,
		},
		"capabilities": {
			"experimentalApi": true,
		},
	})
	_request_context[str(request_id)] = "initialize"

func _on_client_started(pid: int, executable: String) -> void:
	_log("Codex app-server started. PID=%s executable=%s" % [pid, executable])
	_set_codex_status("initializing")

func _on_client_stopped(reason: String) -> void:
	_initialized = false
	_connecting = false
	_active_turn = false
	_agent_stream_open = false
	_connect_button.disabled = false
	_set_codex_status("stopped")
	_log("Codex app-server stopped: %s" % reason)

func _on_client_status_changed(status: String) -> void:
	_log("Codex process status: %s" % status)

func _on_response_received(request_id: Variant, method: String, result: Variant, error: Variant) -> void:
	var context := str(_request_context.get(str(request_id), method))
	_request_context.erase(str(request_id))
	if error != null:
		var error_text := _format_error(error)
		_log("RPC %s failed: %s" % [method, error_text])
		if context == "initialize":
			_connecting = false
			_connect_button.disabled = false
			_set_codex_status("protocol error")
		_append_system("Codex request failed (%s): %s" % [method, error_text])
		return

	var result_dict := _as_dictionary(result)
	match context:
		"initialize":
			_initialized = true
			_connecting = false
			_connect_button.disabled = false
			_client.send_notification("initialized", {})
			_set_codex_status("connected")
			_log("Codex app-server handshake completed.")
			_refresh_account()
			_reload_mcp_config()
		"account/read":
			_apply_account_read(result_dict)
		"account/login/start":
			_handle_login_start(result_dict)
		"account/logout":
			_account.clear()
			_requires_openai_auth = true
			_update_account_status()
		"thread/start":
			_apply_thread_result(result_dict, false)
		"thread/resume":
			_apply_thread_result(result_dict, true)
		"turn/start":
			var turn := _as_dictionary(result_dict.get("turn", result_dict))
			_turn_id = str(turn.get("id", _turn_id))
			_active_turn = true
			_update_action_buttons()
		"turn/interrupt":
			_log("Turn interrupt requested.")
		"config/mcpServer/reload":
			_log("Codex MCP configuration reloaded.")
			_refresh_mcp_status()
		"mcpServerStatus/list":
			_apply_mcp_status(result_dict)
		_:
			_log("RPC completed: %s" % method)

func _on_notification_received(method: String, params: Dictionary) -> void:
	match method:
		"account/updated":
			_apply_account_update(params)
		"account/login/completed":
			if bool(params.get("success", false)):
				_append_system("ChatGPT login completed.")
				_refresh_account()
			else:
				_append_system("ChatGPT login failed: %s" % params.get("error", "Unknown error"))
		"thread/started":
			var thread := _as_dictionary(params.get("thread", params))
			if _thread_id.is_empty():
				_thread_id = str(thread.get("id", ""))
		"turn/started":
			var turn := _as_dictionary(params.get("turn", params))
			_turn_id = str(turn.get("id", _turn_id))
			_active_turn = true
			_update_action_buttons()
		"turn/completed":
			_handle_turn_completed(params)
		"turn/diff/updated":
			_current_diff = str(params.get("diff", ""))
			_diff_view.text = _current_diff
		"item/agentMessage/delta":
			_append_agent_delta(str(params.get("delta", "")))
		"item/reasoning/summaryTextDelta":
			_log("Reasoning: %s" % str(params.get("delta", "")))
		"item/commandExecution/outputDelta":
			_log(str(params.get("delta", "")))
		"item/started":
			_render_item_started(_as_dictionary(params.get("item", {})))
		"item/completed":
			_render_item_completed(_as_dictionary(params.get("item", {})))
		"mcpServer/startupStatus/updated":
			_handle_mcp_startup_status(params)
		"thread/tokenUsage/updated":
			_log("Token usage updated.")
		"error":
			_append_system("Codex error: %s" % _format_error(params))
		_:
			if method.begins_with("codex/event/"):
				_log("Event %s" % method)

func _on_server_request_received(request_id: Variant, method: String, params: Dictionary) -> void:
	var supported_methods := [
		"item/commandExecution/requestApproval",
		"item/fileChange/requestApproval",
		"item/permissions/requestApproval",
		"item/tool/requestUserInput",
		"mcpServer/elicitation/request",
		"execCommandApproval",
		"applyPatchApproval",
	]
	if supported_methods.has(method):
		_show_server_request(request_id, method, params)
		return
	_client.respond_error(request_id, -32601, "Godot Codex Native Chat does not implement server request: %s" % method)
	_log("Rejected unsupported server request: %s" % method)

func _on_stderr_received(text: String) -> void:
	_log("[app-server] %s" % text)

func _on_protocol_error(message: String, raw_line: String) -> void:
	_log("Protocol error: %s %s" % [message, raw_line])

func _refresh_account() -> void:
	if not _initialized:
		return
	var request_id := _client.send_request("account/read", {"refreshToken": false})
	_request_context[str(request_id)] = "account/read"

func _reload_mcp_config() -> void:
	if not _initialized:
		return
	var request_id := _client.send_request("config/mcpServer/reload", {})
	_request_context[str(request_id)] = "config/mcpServer/reload"

func _refresh_mcp_status() -> void:
	if not _initialized:
		return
	var params := {}
	if not _thread_id.is_empty():
		params["threadId"] = _thread_id
	var request_id := _client.send_request("mcpServerStatus/list", params)
	_request_context[str(request_id)] = "mcpServerStatus/list"
	_set_mcp_status("checking")

func _on_connect_pressed() -> void:
	connect_codex()

func _on_login_pressed() -> void:
	if not _initialized:
		connect_codex()
		_append_system("Connect to Codex first, then press Login again.")
		return

	if not _account.is_empty():
		var request_id := _client.send_request("account/logout", {})
		_request_context[str(request_id)] = "account/logout"
		return

	var request_id := _client.send_request("account/login/start", {
		"type": "chatgpt",
		"useHostedLoginSuccessPage": true,
		"appBrand": "codex",
	})
	_request_context[str(request_id)] = "account/login/start"
	_set_account_status("opening login")

func _handle_login_start(result: Dictionary) -> void:
	var auth_url := str(result.get("authUrl", result.get("authorization_url", "")))
	if auth_url.is_empty():
		_append_system("Codex started login but did not return an authorization URL.")
		return
	OS.shell_open(auth_url)
	_append_system("The ChatGPT login page was opened in your browser.")

func _on_new_pressed() -> void:
	if _active_turn:
		_append_system("Stop the active turn before starting a new chat.")
		return
	_thread_id = ""
	_turn_id = ""
	_current_diff = ""
	_diff_view.text = ""
	_transcript.clear()
	_append_system("New Codex chat. The next message will create a new thread.")
	_update_action_buttons()

func _on_resume_pressed() -> void:
	if not _initialized:
		connect_codex()
		return
	if _last_thread_id.is_empty():
		_append_system("No previous Codex thread is stored for this project.")
		return
	var request_id := _client.send_request("thread/resume", {"threadId": _last_thread_id})
	_request_context[str(request_id)] = "thread/resume"
	_set_codex_status("resuming")

func _on_stop_pressed() -> void:
	if not _active_turn or _thread_id.is_empty() or _turn_id.is_empty():
		return
	var request_id := _client.send_request("turn/interrupt", {
		"threadId": _thread_id,
		"turnId": _turn_id,
	})
	_request_context[str(request_id)] = "turn/interrupt"
	_stop_button.disabled = true

func _on_send_pressed() -> void:
	var prompt := _input.text.strip_edges()
	if prompt.is_empty():
		return
	_input.clear()
	send_prompt(prompt)

func send_prompt(prompt: String) -> void:
	if not _initialized:
		_queued_prompt = prompt
		connect_codex()
		_append_system("Message queued while Codex connects.")
		return
	if _active_turn:
		_append_system("Codex is still working. Stop the current turn before sending another message.")
		return
	if _requires_openai_auth and _account.is_empty():
		_queued_prompt = prompt
		_append_system("ChatGPT login is required. Press Login, then the queued message will be sent after login.")
		return

	_append_user(prompt)
	if _thread_id.is_empty():
		_queued_prompt = prompt
		_start_thread()
	else:
		_start_turn(prompt)

func _start_thread() -> void:
	var developer_instructions := "You are running inside the Godot editor. Work only in the current Godot project unless the user explicitly asks otherwise. Prefer the configured Godot MCP Native server named godot-mcp for scene, node, editor, debugger, runtime, screenshot, import, and resource operations. Use normal filesystem and shell tools for source files, Git, and build commands. Verify meaningful changes through Godot before reporting completion."
	var params := {
		"cwd": _project_root,
		"approvalPolicy": _approval_policy,
		"sandbox": _sandbox_mode,
		"developerInstructions": developer_instructions,
		"sessionStartSource": "startup",
	}
	if not _model.is_empty():
		params["model"] = _model
	var request_id := _client.send_request("thread/start", params)
	_request_context[str(request_id)] = "thread/start"
	_set_codex_status("starting thread")

func _start_turn(prompt: String) -> void:
	var params := {
		"threadId": _thread_id,
		"input": [{
			"type": "text",
			"text": prompt,
			"text_elements": [],
		}],
		"cwd": _project_root,
		"approvalPolicy": _approval_policy,
	}
	if not _model.is_empty():
		params["model"] = _model
	var request_id := _client.send_request("turn/start", params)
	_request_context[str(request_id)] = "turn/start"
	_active_turn = true
	_agent_stream_open = false
	_update_action_buttons()
	_set_codex_status("working")

func _apply_thread_result(result: Dictionary, resumed: bool) -> void:
	var thread := _as_dictionary(result.get("thread", result))
	_thread_id = str(thread.get("id", ""))
	if _thread_id.is_empty():
		_append_system("Codex returned a thread without an ID.")
		return
	_last_thread_id = _thread_id
	_settings.set_value("session", _project_session_key(), _last_thread_id)
	_settings.save(SETTINGS_PATH)
	_set_codex_status("connected")
	if resumed:
		_append_system("Resumed Codex thread %s." % _thread_id)
		_refresh_mcp_status()
		return
	_refresh_mcp_status()
	if not _queued_prompt.is_empty():
		var prompt := _queued_prompt
		_queued_prompt = ""
		_start_turn(prompt)

func _handle_turn_completed(params: Dictionary) -> void:
	var turn := _as_dictionary(params.get("turn", params))
	var status := str(turn.get("status", "completed"))
	if _agent_stream_open:
		_transcript.append_text("\n\n")
	_agent_stream_open = false
	_active_turn = false
	_turn_id = ""
	_set_codex_status("connected")
	_update_action_buttons()
	if status == "failed":
		var error := turn.get("error", {})
		_append_system("Turn failed: %s" % _format_error(error))
	elif status == "interrupted":
		_append_system("Turn interrupted.")

func _render_item_started(item: Dictionary) -> void:
	var item_type := str(item.get("type", "item"))
	match item_type:
		"commandExecution":
			var command := item.get("command", item.get("commands", ""))
			_append_tool("Command", str(command))
		"fileChange":
			_append_tool("File change", _summarize_file_change(item))
		"mcpToolCall":
			var server := str(item.get("server", item.get("serverName", "MCP")))
			var tool := str(item.get("tool", item.get("toolName", item.get("name", "tool"))))
			_append_tool("MCP %s" % server, tool)
		"webSearch":
			_append_tool("Web search", str(item.get("query", "")))
		"reasoning":
			_log("Codex reasoning item started.")
		"agentMessage", "userMessage":
			pass
		_:
			_log("Item started: %s" % item_type)

func _render_item_completed(item: Dictionary) -> void:
	var item_type := str(item.get("type", "item"))
	if item_type == "agentMessage" and not _agent_stream_open:
		var text := _extract_agent_message(item)
		if not text.is_empty():
			_append_agent_delta(text)
			_transcript.append_text("\n\n")
			_agent_stream_open = false
	elif item_type == "commandExecution":
		var status := str(item.get("status", "completed"))
		_append_tool("Command result", status)
	elif item_type == "mcpToolCall":
		var status := str(item.get("status", "completed"))
		_append_tool("MCP result", status)

func _append_user(text: String) -> void:
	_transcript.append_text("[b]You[/b]\n%s\n\n" % _escape_bbcode(text))

func _append_system(text: String) -> void:
	_transcript.append_text("[color=gray][i]%s[/i][/color]\n\n" % _escape_bbcode(text))

func _append_tool(title: String, details: String) -> void:
	_transcript.append_text("[color=#8ab4f8][b]%s[/b][/color]\n%s\n\n" % [
		_escape_bbcode(title),
		_escape_bbcode(details),
	])

func _append_agent_delta(delta: String) -> void:
	if delta.is_empty():
		return
	if not _agent_stream_open:
		_transcript.append_text("[b]Codex[/b]\n")
		_agent_stream_open = true
	_transcript.append_text(_escape_bbcode(delta))

func _show_server_request(request_id: Variant, method: String, params: Dictionary) -> void:
	if _pending_server_request_id != null:
		_client.respond_error(request_id, -32000, "Another approval is already being reviewed.")
		return
	_pending_server_request_id = request_id
	_pending_server_request_method = method
	_pending_server_request_params = params
	_approval_title.text = _approval_title_for_method(method)
	_approval_details.text = _approval_details_for_method(method, params)
	_approval_answer.text = ""
	_approval_answer.visible = method == "item/tool/requestUserInput" or method == "mcpServer/elicitation/request"
	_approval_once_button.text = "Submit" if _approval_answer.visible else "Allow once"
	_approval_session_button.visible = method == "item/commandExecution/requestApproval" or method == "item/fileChange/requestApproval" or method == "item/permissions/requestApproval"
	_approval_panel.visible = true
	_append_system("Codex is waiting for approval: %s" % _approval_title.text)

func _on_approval_once_pressed() -> void:
	_resolve_server_request(false, false)

func _on_approval_session_pressed() -> void:
	_resolve_server_request(true, false)

func _on_approval_reject_pressed() -> void:
	_resolve_server_request(false, true)

func _resolve_server_request(for_session: bool, rejected: bool) -> void:
	if _pending_server_request_id == null:
		return
	var request_id: Variant = _pending_server_request_id
	var method := _pending_server_request_method
	var params := _pending_server_request_params
	var answer := _approval_answer.text.strip_edges()

	match method:
		"item/commandExecution/requestApproval", "item/fileChange/requestApproval":
			_client.respond(request_id, {
				"decision": "decline" if rejected else ("acceptForSession" if for_session else "accept"),
			})
		"item/permissions/requestApproval":
			_client.respond(request_id, {
				"permissions": {} if rejected else _as_dictionary(params.get("permissions", {})),
				"scope": "session" if for_session else "turn",
				"strictAutoReview": false,
			})
		"item/tool/requestUserInput":
			if rejected:
				_client.respond_error(request_id, -32000, "User declined the input request.")
			else:
				var answers := {}
				for question_value in _as_array(params.get("questions", [])):
					var question := _as_dictionary(question_value)
					answers[str(question.get("id", "question"))] = {"answers": [answer]}
				_client.respond(request_id, {"answers": answers})
		"mcpServer/elicitation/request":
			if rejected:
				_client.respond(request_id, {"action": "decline", "content": null, "_meta": null})
			else:
				var content: Variant = {}
				if not answer.is_empty():
					var parsed := JSON.parse_string(answer)
					content = parsed if parsed != null else {"value": answer}
				_client.respond(request_id, {"action": "accept", "content": content, "_meta": null})
		"execCommandApproval", "applyPatchApproval":
			_client.respond(request_id, {"decision": "denied" if rejected else "approved"})
		_:
			_client.respond_error(request_id, -32601, "Unsupported approval method: %s" % method)

	_log("Approval resolved: %s rejected=%s session=%s" % [method, rejected, for_session])
	_pending_server_request_id = null
	_pending_server_request_method = ""
	_pending_server_request_params = {}
	_approval_panel.visible = false

func _apply_account_read(result: Dictionary) -> void:
	_requires_openai_auth = bool(result.get("requiresOpenaiAuth", true))
	_account = _as_dictionary(result.get("account", {}))
	_update_account_status()
	if not _account.is_empty() and not _queued_prompt.is_empty():
		var prompt := _queued_prompt
		_queued_prompt = ""
		send_prompt(prompt)

func _apply_account_update(params: Dictionary) -> void:
	var auth_mode := params.get("authMode")
	if auth_mode == null:
		_account.clear()
	else:
		_account = {
			"authMode": auth_mode,
			"planType": params.get("planType"),
		}
	_update_account_status()
	if not _account.is_empty() and not _queued_prompt.is_empty():
		var prompt := _queued_prompt
		_queued_prompt = ""
		send_prompt(prompt)

func _apply_mcp_status(result: Dictionary) -> void:
	var entries := _as_array(result.get("data", result.get("servers", [])))
	var found := false
	var summary := "configured"
	for entry_value in entries:
		var entry := _as_dictionary(entry_value)
		var name := str(entry.get("name", entry.get("serverName", "")))
		if name != "godot-mcp":
			continue
		found = true
		summary = str(entry.get("status", entry.get("startupStatus", "ready")))
		var error := str(entry.get("error", ""))
		if not error.is_empty():
			summary += ": " + error
		break
	_set_mcp_status(summary if found else "configured; waiting for thread")

func _handle_mcp_startup_status(params: Dictionary) -> void:
	if str(params.get("name", "")) != "godot-mcp":
		return
	var status := str(params.get("status", "unknown"))
	var error := str(params.get("error", ""))
	_set_mcp_status(status + ((": " + error) if not error.is_empty() else ""))

func _update_account_status() -> void:
	if _account.is_empty():
		_set_account_status("not signed in" if _requires_openai_auth else "local provider")
		_login_button.text = "Login"
		return
	var mode := str(_account.get("authMode", _account.get("type", "signed in")))
	var plan := str(_account.get("planType", ""))
	_set_account_status(mode + ((" / " + plan) if not plan.is_empty() and plan != "<null>" else ""))
	_login_button.text = "Logout"

func _update_status_labels() -> void:
	_update_account_status()
	_update_action_buttons()

func _update_action_buttons() -> void:
	if _send_button == null:
		return
	_send_button.disabled = _active_turn
	_stop_button.disabled = not _active_turn
	_new_button.disabled = _active_turn
	_resume_button.disabled = _active_turn or _last_thread_id.is_empty()

func _set_codex_status(value: String) -> void:
	if _codex_status_label != null:
		_codex_status_label.text = "Codex: %s" % value

func _set_account_status(value: String) -> void:
	if _account_status_label != null:
		_account_status_label.text = "Account: %s" % value

func _set_mcp_status(value: String) -> void:
	if _mcp_status_label != null:
		_mcp_status_label.text = "Godot MCP Native: %s" % value

func _on_settings_pressed() -> void:
	_settings_panel.visible = not _settings_panel.visible

func _on_save_settings_pressed() -> void:
	_codex_path = _codex_path_edit.text.strip_edges()
	_mcp_endpoint = _mcp_endpoint_edit.text.strip_edges()
	if _mcp_endpoint.is_empty():
		_mcp_endpoint = DEFAULT_MCP_ENDPOINT
	_model = _model_edit.text.strip_edges()
	_sandbox_mode = _sandbox_option.get_item_text(_sandbox_option.selected)
	_approval_policy = _approval_option.get_item_text(_approval_option.selected)
	_auto_connect = _auto_connect_check.button_pressed
	_settings.set_value("connection", "codex_path", _codex_path)
	_settings.set_value("connection", "mcp_endpoint", _mcp_endpoint)
	_settings.set_value("codex", "model", _model)
	_settings.set_value("codex", "sandbox", _sandbox_mode)
	_settings.set_value("codex", "approval_policy", _approval_policy)
	_settings.set_value("connection", "auto_connect", _auto_connect)
	_settings.save(SETTINGS_PATH)
	var result := _config_manager.ensure_project_mcp_config(_project_root, _mcp_endpoint)
	_append_system("Settings saved. MCP config: %s" % ("updated" if bool(result.get("changed", false)) else "unchanged"))
	_settings_panel.visible = false
	if _initialized:
		_reload_mcp_config()

func _load_settings() -> void:
	_settings.load(SETTINGS_PATH)
	_codex_path = str(_settings.get_value("connection", "codex_path", ""))
	_mcp_endpoint = str(_settings.get_value("connection", "mcp_endpoint", DEFAULT_MCP_ENDPOINT))
	_model = str(_settings.get_value("codex", "model", ""))
	_sandbox_mode = str(_settings.get_value("codex", "sandbox", "workspace-write"))
	_approval_policy = str(_settings.get_value("codex", "approval_policy", "on-request"))
	_auto_connect = bool(_settings.get_value("connection", "auto_connect", true))
	_last_thread_id = str(_settings.get_value("session", _project_session_key(), ""))
	_sync_settings_ui()

func _sync_settings_ui() -> void:
	if _codex_path_edit == null:
		return
	_codex_path_edit.text = _codex_path
	_mcp_endpoint_edit.text = _mcp_endpoint
	_model_edit.text = _model
	_select_option_text(_sandbox_option, _sandbox_mode)
	_select_option_text(_approval_option, _approval_policy)
	_auto_connect_check.button_pressed = _auto_connect
	_update_action_buttons()

func _build_ui() -> void:
	custom_minimum_size = Vector2(420, 420)
	var root := VBoxContainer.new()
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(root)

	var status_box := VBoxContainer.new()
	root.add_child(status_box)
	_codex_status_label = Label.new()
	_account_status_label = Label.new()
	_mcp_status_label = Label.new()
	status_box.add_child(_codex_status_label)
	status_box.add_child(_account_status_label)
	status_box.add_child(_mcp_status_label)

	var toolbar := HBoxContainer.new()
	root.add_child(toolbar)
	_connect_button = _make_button("Connect", _on_connect_pressed)
	_login_button = _make_button("Login", _on_login_pressed)
	_new_button = _make_button("New", _on_new_pressed)
	_resume_button = _make_button("Resume", _on_resume_pressed)
	_stop_button = _make_button("Stop", _on_stop_pressed)
	_settings_button = _make_button("Settings", _on_settings_pressed)
	for button in [_connect_button, _login_button, _new_button, _resume_button, _stop_button, _settings_button]:
		toolbar.add_child(button)

	_settings_panel = PanelContainer.new()
	_settings_panel.visible = false
	root.add_child(_settings_panel)
	var settings_box := VBoxContainer.new()
	_settings_panel.add_child(settings_box)
	_codex_path_edit = _labeled_line_edit(settings_box, "Codex executable", "Auto-detect when empty")
	_mcp_endpoint_edit = _labeled_line_edit(settings_box, "Godot MCP Native endpoint", DEFAULT_MCP_ENDPOINT)
	_model_edit = _labeled_line_edit(settings_box, "Model override", "Use Codex default when empty")
	_sandbox_option = _labeled_option(settings_box, "Sandbox", ["workspace-write", "read-only", "danger-full-access"])
	_approval_option = _labeled_option(settings_box, "Approval policy", ["on-request", "untrusted", "never"])
	_auto_connect_check = CheckBox.new()
	_auto_connect_check.text = "Connect automatically when the dock opens"
	settings_box.add_child(_auto_connect_check)
	settings_box.add_child(_make_button("Save settings", _on_save_settings_pressed))

	_tab_container = TabContainer.new()
	_tab_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(_tab_container)

	_transcript = RichTextLabel.new()
	_transcript.name = "Chat"
	_transcript.bbcode_enabled = true
	_transcript.scroll_following = true
	_transcript.selection_enabled = true
	_transcript.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tab_container.add_child(_transcript)

	_diff_view = TextEdit.new()
	_diff_view.name = "Diff"
	_diff_view.editable = false
	_diff_view.wrap_mode = TextEdit.LINE_WRAPPING_NONE
	_tab_container.add_child(_diff_view)

	_log_view = TextEdit.new()
	_log_view.name = "Logs"
	_log_view.editable = false
	_log_view.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_tab_container.add_child(_log_view)

	_approval_panel = PanelContainer.new()
	_approval_panel.visible = false
	root.add_child(_approval_panel)
	var approval_box := VBoxContainer.new()
	_approval_panel.add_child(approval_box)
	_approval_title = Label.new()
	_approval_title.add_theme_font_size_override("font_size", 16)
	approval_box.add_child(_approval_title)
	_approval_details = TextEdit.new()
	_approval_details.editable = false
	_approval_details.custom_minimum_size = Vector2(0, 130)
	approval_box.add_child(_approval_details)
	_approval_answer = TextEdit.new()
	_approval_answer.placeholder_text = "Enter the requested answer or JSON content."
	_approval_answer.custom_minimum_size = Vector2(0, 70)
	approval_box.add_child(_approval_answer)
	var approval_buttons := HBoxContainer.new()
	approval_box.add_child(approval_buttons)
	_approval_once_button = _make_button("Allow once", _on_approval_once_pressed)
	_approval_session_button = _make_button("Allow session", _on_approval_session_pressed)
	_approval_reject_button = _make_button("Reject", _on_approval_reject_pressed)
	approval_buttons.add_child(_approval_once_button)
	approval_buttons.add_child(_approval_session_button)
	approval_buttons.add_child(_approval_reject_button)

	_input = TextEdit.new()
	_input.placeholder_text = "Ask Codex to work on the current Godot project..."
	_input.custom_minimum_size = Vector2(0, 90)
	root.add_child(_input)
	_send_button = _make_button("Send", _on_send_pressed)
	root.add_child(_send_button)

	_append_system("Godot Codex Native Chat is ready. Codex and Godot MCP Native will be detected automatically.")

func _make_button(text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.pressed.connect(callback)
	return button

func _labeled_line_edit(parent: VBoxContainer, title: String, placeholder: String) -> LineEdit:
	var label := Label.new()
	label.text = title
	parent.add_child(label)
	var edit := LineEdit.new()
	edit.placeholder_text = placeholder
	parent.add_child(edit)
	return edit

func _labeled_option(parent: VBoxContainer, title: String, values: Array[String]) -> OptionButton:
	var label := Label.new()
	label.text = title
	parent.add_child(label)
	var option := OptionButton.new()
	for value in values:
		option.add_item(value)
	parent.add_child(option)
	return option

func _select_option_text(option: OptionButton, value: String) -> void:
	for index in range(option.item_count):
		if option.get_item_text(index) == value:
			option.select(index)
			return

func _approval_title_for_method(method: String) -> String:
	match method:
		"item/commandExecution/requestApproval", "execCommandApproval":
			return "Command execution approval"
		"item/fileChange/requestApproval", "applyPatchApproval":
			return "File change approval"
		"item/permissions/requestApproval":
			return "Additional permission request"
		"item/tool/requestUserInput":
			return "Codex needs input"
		"mcpServer/elicitation/request":
			return "MCP tool needs input"
		_:
			return method

func _approval_details_for_method(method: String, params: Dictionary) -> String:
	if method == "item/commandExecution/requestApproval" or method == "execCommandApproval":
		return "Command:\n%s\n\nWorking directory:\n%s\n\nReason:\n%s" % [
			params.get("command", params.get("commands", "")),
			params.get("cwd", _project_root),
			params.get("reason", ""),
		]
	if method == "item/fileChange/requestApproval" or method == "applyPatchApproval":
		return "Reason:\n%s\n\nCurrent turn diff:\n%s" % [
			params.get("reason", ""),
			_current_diff if not _current_diff.is_empty() else JSON.stringify(params, "  "),
		]
	if method == "item/tool/requestUserInput":
		var lines: Array[String] = []
		for value in _as_array(params.get("questions", [])):
			var question := _as_dictionary(value)
			lines.append(str(question.get("question", question.get("header", "Question"))))
			var options := _as_array(question.get("options", []))
			if not options.is_empty():
				for option_value in options:
					var option := _as_dictionary(option_value)
					lines.append("- %s: %s" % [option.get("label", ""), option.get("description", "")])
		return "\n".join(lines)
	return JSON.stringify(params, "  ")

func _summarize_file_change(item: Dictionary) -> String:
	var changes := _as_array(item.get("changes", []))
	if changes.is_empty():
		return str(item.get("path", "Pending file changes"))
	var lines: Array[String] = []
	for value in changes:
		var change := _as_dictionary(value)
		lines.append("%s %s" % [change.get("kind", "update"), change.get("path", "")])
	return "\n".join(lines)

func _extract_agent_message(item: Dictionary) -> String:
	if item.has("text"):
		return str(item.get("text", ""))
	var content := _as_array(item.get("content", []))
	var parts: Array[String] = []
	for value in content:
		var part := _as_dictionary(value)
		if part.has("text"):
			parts.append(str(part.get("text", "")))
	return "".join(parts)

func _format_error(error: Variant) -> String:
	if error == null:
		return "Unknown error"
	if error is Dictionary:
		var dictionary := error as Dictionary
		return str(dictionary.get("message", JSON.stringify(dictionary)))
	return str(error)

func _log(text: String) -> void:
	if _log_view == null:
		return
	var timestamp := Time.get_time_string_from_system()
	_log_view.text += "[%s] %s\n" % [timestamp, text]
	_log_view.scroll_vertical = int(_log_view.get_line_count())

func _escape_bbcode(text: String) -> String:
	return text.replace("[", "[lb]")

func _as_dictionary(value: Variant) -> Dictionary:
	if value is Dictionary:
		return value as Dictionary
	return {}

func _as_array(value: Variant) -> Array:
	if value is Array:
		return value as Array
	return []

func _project_session_key() -> String:
	return _project_root.sha256_text().substr(0, 16)

func _is_headless() -> bool:
	return DisplayServer.get_name() == "headless" or OS.has_environment("CI")
