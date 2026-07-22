@tool
extends PanelContainer
class_name GodotAiManagerDock

const CODEX_BACKEND_SCRIPT := preload("res://addons/godot_ai_manager/codex_backend.gd")
const KIMI_BACKEND_SCRIPT := preload("res://addons/godot_ai_manager/kimi_backend.gd")
const SETTINGS_PATH := "user://godot_ai_manager.cfg"
const DEFAULT_MCP_ENDPOINT := "http://127.0.0.1:9080/mcp"

var _editor_interface: EditorInterface
var _project_root := ""
var _backend: AiAgentBackend
var _backend_id := "codex"
var _settings := ConfigFile.new()
var _stream_open := false
var _last_sessions: Dictionary = {}

var _codex_path := ""
var _kimi_path := ""
var _mcp_endpoint := DEFAULT_MCP_ENDPOINT
var _model_override := ""
var _sandbox_mode := "workspace-write"
var _approval_policy := "on-request"
var _auto_connect := true

var _backend_option: OptionButton
var _backend_status_label: Label
var _account_status_label: Label
var _mcp_status_label: Label
var _connect_button: Button
var _login_button: Button
var _new_button: Button
var _resume_button: Button
var _stop_button: Button
var _settings_button: Button
var _settings_panel: PanelContainer
var _codex_path_edit: LineEdit
var _kimi_path_edit: LineEdit
var _mcp_endpoint_edit: LineEdit
var _model_edit: LineEdit
var _sandbox_option: OptionButton
var _approval_option: OptionButton
var _auto_connect_check: CheckBox
var _transcript: RichTextLabel
var _diff_view: TextEdit
var _log_view: TextEdit
var _input: TextEdit
var _send_button: Button
var _approval_panel: PanelContainer
var _approval_title: Label
var _approval_details: TextEdit
var _approval_text: TextEdit
var _approval_buttons: HBoxContainer

func configure(editor_interface: EditorInterface) -> void:
	_editor_interface = editor_interface
	_project_root = ProjectSettings.globalize_path("res://").trim_suffix("/").trim_suffix("\\")
	if is_inside_tree():
		_finish_configuration()

func _ready() -> void:
	_build_ui()
	_load_settings()
	_create_backend(_backend_id)
	set_process(true)
	_finish_configuration()

func _process(_delta: float) -> void:
	if _backend != null:
		_backend.poll()

func shutdown() -> void:
	if _backend != null:
		_backend.disconnect_backend()
	_backend = null

func active_backend_id() -> String:
	return _backend_id

func active_backend() -> AiAgentBackend:
	return _backend

func select_backend(backend_id: String) -> void:
	if backend_id != "codex" and backend_id != "kimi":
		return
	if _backend_id == backend_id and _backend != null:
		return
	_create_backend(backend_id)

func _finish_configuration() -> void:
	if _project_root.is_empty():
		_project_root = ProjectSettings.globalize_path("res://").trim_suffix("/").trim_suffix("\\")
	_warn_about_legacy_fennara_addon()
	if _auto_connect and not _is_headless() and _backend != null:
		call_deferred("_connect_backend")

func _create_backend(backend_id: String) -> void:
	if _backend != null:
		_backend.disconnect_backend()
	_backend_id = backend_id
	if backend_id == "codex":
		_backend = CODEX_BACKEND_SCRIPT.new() as AiAgentBackend
	else:
		_backend = KIMI_BACKEND_SCRIPT.new() as AiAgentBackend
	_connect_backend_signals()
	_apply_backend_configuration()
	_sync_backend_selector()
	_update_backend_specific_ui()
	_backend_status_label.text = "%s：未连接" % _backend.backend_name()
	_account_status_label.text = "账户：未连接"
	_mcp_status_label.text = "Godot MCP Native：未检查"
	_append_system("已切换到 %s 官方后端。" % _backend.backend_name())
	if _auto_connect and is_inside_tree() and not _is_headless():
		call_deferred("_connect_backend")

func _connect_backend_signals() -> void:
	_backend.backend_status_changed.connect(_on_backend_status)
	_backend.account_status_changed.connect(_on_account_status)
	_backend.mcp_status_changed.connect(_on_mcp_status)
	_backend.message_delta.connect(_on_message_delta)
	_backend.message_completed.connect(_on_message_completed)
	_backend.thought_delta.connect(_on_thought_delta)
	_backend.tool_event.connect(_on_tool_event)
	_backend.diff_changed.connect(_on_diff_changed)
	_backend.log_message.connect(_log)
	_backend.error_message.connect(_on_error)
	_backend.session_changed.connect(_on_session_changed)
	_backend.turn_state_changed.connect(_on_turn_state_changed)
	_backend.approval_requested.connect(_on_approval_requested)
	_backend.login_message.connect(_on_login_message)

func _apply_backend_configuration() -> void:
	if _backend == null:
		return
	_backend.configure({
		"project_root": _project_root,
		"executable_path": _codex_path if _backend_id == "codex" else _kimi_path,
		"mcp_endpoint": _mcp_endpoint,
		"model_override": _model_override,
		"sandbox_mode": _sandbox_mode,
		"approval_policy": _approval_policy,
	})

func _connect_backend() -> void:
	if _backend == null:
		return
	_apply_backend_configuration()
	_backend.connect_backend()

func _on_backend_selected(index: int) -> void:
	var id := "codex" if index == 0 else "kimi"
	if id == _backend_id:
		return
	_backend_id = id
	_settings.set_value("general", "backend", _backend_id)
	_settings.save(SETTINGS_PATH)
	_create_backend(_backend_id)

func _on_connect_pressed() -> void:
	_connect_backend()

func _on_login_pressed() -> void:
	if _backend == null:
		return
	if _backend.can_logout() and _backend.signed_in:
		_backend.logout()
	else:
		_backend.login()

func _on_new_pressed() -> void:
	if _backend == null:
		return
	_backend.new_session()
	_diff_view.text = ""
	_stream_open = false
	_append_system("已创建新的 %s 对话。" % _backend.backend_name())

func _on_resume_pressed() -> void:
	if _backend == null:
		return
	var stored := str(_last_sessions.get(_session_key(_backend_id), ""))
	_backend.resume_session(stored)

func _on_stop_pressed() -> void:
	if _backend != null:
		_backend.cancel_turn()

func _on_send_pressed() -> void:
	var prompt := _input.text.strip_edges()
	if prompt.is_empty() or _backend == null:
		return
	_input.clear()
	_append_user(prompt)
	_backend.send_prompt(prompt)

func _on_settings_pressed() -> void:
	_settings_panel.visible = not _settings_panel.visible

func _on_save_settings_pressed() -> void:
	_codex_path = _codex_path_edit.text.strip_edges()
	_kimi_path = _kimi_path_edit.text.strip_edges()
	_mcp_endpoint = _mcp_endpoint_edit.text.strip_edges()
	if _mcp_endpoint.is_empty():
		_mcp_endpoint = DEFAULT_MCP_ENDPOINT
	_model_override = _model_edit.text.strip_edges()
	_sandbox_mode = _sandbox_option.get_item_text(_sandbox_option.selected)
	_approval_policy = _approval_option.get_item_text(_approval_option.selected)
	_auto_connect = _auto_connect_check.button_pressed
	_settings.set_value("general", "backend", _backend_id)
	_settings.set_value("general", "mcp_endpoint", _mcp_endpoint)
	_settings.set_value("general", "model_override", _model_override)
	_settings.set_value("general", "auto_connect", _auto_connect)
	_settings.set_value("codex", "executable_path", _codex_path)
	_settings.set_value("codex", "sandbox_mode", _sandbox_mode)
	_settings.set_value("codex", "approval_policy", _approval_policy)
	_settings.set_value("kimi", "executable_path", _kimi_path)
	_settings.save(SETTINGS_PATH)
	_apply_backend_configuration()
	_settings_panel.visible = false
	_append_system("设置已保存。重新连接后所有后端参数都会生效。")

func _on_backend_status(status: String) -> void:
	_backend_status_label.text = "%s：%s" % [_backend.backend_name(), status]

func _on_account_status(status: String, signed_in: bool) -> void:
	_account_status_label.text = "账户：%s" % status
	_login_button.text = "退出" if signed_in and _backend.can_logout() else "登录"
	_update_buttons()

func _on_mcp_status(status: String) -> void:
	_mcp_status_label.text = "Godot MCP Native：%s" % status

func _on_message_delta(text: String) -> void:
	if text.is_empty():
		return
	if not _stream_open:
		_transcript.append_text("[b]%s[/b]\n" % _escape_bbcode(_backend.backend_name()))
		_stream_open = true
	_transcript.append_text(_escape_bbcode(text))

func _on_message_completed() -> void:
	if _stream_open:
		_transcript.append_text("\n\n")
	_stream_open = false

func _on_thought_delta(text: String) -> void:
	if not text.is_empty():
		_log("[%s 思考摘要] %s" % [_backend.backend_name(), text])

func _on_tool_event(title: String, details: String, status: String) -> void:
	_transcript.append_text("[color=#8ab4f8][b]%s · %s[/b][/color]\n%s\n\n" % [
		_escape_bbcode(title),
		_escape_bbcode(status),
		_escape_bbcode(details),
	])

func _on_diff_changed(diff_text: String) -> void:
	_diff_view.text = diff_text

func _on_error(text: String) -> void:
	_append_system("错误：%s" % text)
	_log("错误：%s" % text)

func _on_login_message(text: String) -> void:
	_append_system(text)
	_log(text)

func _on_session_changed(session_id: String) -> void:
	if not session_id.is_empty():
		_last_sessions[_session_key(_backend_id)] = session_id
		_settings.set_value("sessions", _session_key(_backend_id), session_id)
		_settings.save(SETTINGS_PATH)
	_update_buttons()

func _on_turn_state_changed(_active: bool) -> void:
	_update_buttons()

func _on_approval_requested(
	title: String,
	details: String,
	choices: Array,
	needs_text: bool,
	text_placeholder: String
) -> void:
	_approval_title.text = title
	_approval_details.text = details
	_approval_text.visible = needs_text
	_approval_text.placeholder_text = text_placeholder
	_approval_text.text = ""
	for child in _approval_buttons.get_children():
		child.queue_free()
	for choice_value in choices:
		var choice := choice_value as Dictionary
		var button := Button.new()
		button.text = str(choice.get("label", choice.get("id", "选择")))
		var choice_id := str(choice.get("id", ""))
		button.pressed.connect(_resolve_approval.bind(choice_id, false))
		_approval_buttons.add_child(button)
	if needs_text:
		var submit := Button.new()
		submit.text = "提交输入"
		submit.pressed.connect(_resolve_approval.bind("answer", false))
		_approval_buttons.add_child(submit)
	var cancel := Button.new()
	cancel.text = "取消"
	cancel.pressed.connect(_resolve_approval.bind("reject", true))
	_approval_buttons.add_child(cancel)
	_approval_panel.visible = true

func _resolve_approval(choice_id: String, cancelled: bool) -> void:
	if _backend == null:
		return
	_backend.resolve_approval(choice_id, _approval_text.text, cancelled)
	_approval_panel.visible = false

func _update_buttons() -> void:
	if _backend == null or _send_button == null:
		return
	var active := _backend.active_turn
	_send_button.disabled = active
	_stop_button.disabled = not active
	_new_button.disabled = active
	_resume_button.disabled = active or str(_last_sessions.get(_session_key(_backend_id), "")).is_empty()
	_login_button.disabled = active

func _update_backend_specific_ui() -> void:
	if _backend == null or _model_edit == null:
		return
	_model_edit.editable = _backend.supports_model_override()
	_login_button.text = "登录"
	if _backend_id == "kimi":
		_login_button.tooltip_text = "使用官方 kimi login 设备码流程。Kimi ACP 不提供退出方法。"
	else:
		_login_button.tooltip_text = "使用官方 Codex app-server 的 ChatGPT 登录或退出接口。"
	_update_buttons()

func _load_settings() -> void:
	_settings.load(SETTINGS_PATH)
	_backend_id = str(_settings.get_value("general", "backend", "codex"))
	if _backend_id != "codex" and _backend_id != "kimi":
		_backend_id = "codex"
	_mcp_endpoint = str(_settings.get_value("general", "mcp_endpoint", DEFAULT_MCP_ENDPOINT))
	_model_override = str(_settings.get_value("general", "model_override", ""))
	_auto_connect = bool(_settings.get_value("general", "auto_connect", true))
	_codex_path = str(_settings.get_value("codex", "executable_path", ""))
	_sandbox_mode = str(_settings.get_value("codex", "sandbox_mode", "workspace-write"))
	_approval_policy = str(_settings.get_value("codex", "approval_policy", "on-request"))
	_kimi_path = str(_settings.get_value("kimi", "executable_path", ""))
	_last_sessions[_session_key("codex")] = str(_settings.get_value("sessions", _session_key("codex"), ""))
	_last_sessions[_session_key("kimi")] = str(_settings.get_value("sessions", _session_key("kimi"), ""))
	_sync_settings_ui()

func _sync_settings_ui() -> void:
	if _codex_path_edit == null:
		return
	_codex_path_edit.text = _codex_path
	_kimi_path_edit.text = _kimi_path
	_mcp_endpoint_edit.text = _mcp_endpoint
	_model_edit.text = _model_override
	_auto_connect_check.button_pressed = _auto_connect
	_select_option_text(_sandbox_option, _sandbox_mode)
	_select_option_text(_approval_option, _approval_policy)
	_sync_backend_selector()

func _sync_backend_selector() -> void:
	if _backend_option == null:
		return
	_backend_option.select(0 if _backend_id == "codex" else 1)

func _session_key(backend_id: String) -> String:
	return "%s_%s" % [backend_id, _project_root.sha256_text().substr(0, 16)]

func _warn_about_legacy_fennara_addon() -> void:
	if DirAccess.dir_exists_absolute(_project_root.path_join("addons/fennara")):
		_append_system("警告：当前项目仍包含 `addons/fennara/`。本插件不会加载它；为避免 MCP 冲突，请在确认不再使用后手动停用或移除旧 Fennara 插件。")

func _build_ui() -> void:
	custom_minimum_size = Vector2(450, 520)
	var root := VBoxContainer.new()
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(root)

	var backend_row := HBoxContainer.new()
	root.add_child(backend_row)
	var backend_label := Label.new()
	backend_label.text = "官方 AI 后端"
	backend_row.add_child(backend_label)
	_backend_option = OptionButton.new()
	_backend_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_backend_option.add_item("Codex（ChatGPT／Codex 会员）")
	_backend_option.add_item("Kimi Code（Kimi 会员）")
	_backend_option.item_selected.connect(_on_backend_selected)
	backend_row.add_child(_backend_option)

	var status_box := VBoxContainer.new()
	root.add_child(status_box)
	_backend_status_label = Label.new()
	_account_status_label = Label.new()
	_mcp_status_label = Label.new()
	status_box.add_child(_backend_status_label)
	status_box.add_child(_account_status_label)
	status_box.add_child(_mcp_status_label)

	var toolbar := HBoxContainer.new()
	root.add_child(toolbar)
	_connect_button = _make_button("连接", _on_connect_pressed)
	_login_button = _make_button("登录", _on_login_pressed)
	_new_button = _make_button("新对话", _on_new_pressed)
	_resume_button = _make_button("恢复", _on_resume_pressed)
	_stop_button = _make_button("停止", _on_stop_pressed)
	_settings_button = _make_button("设置", _on_settings_pressed)
	for button in [_connect_button, _login_button, _new_button, _resume_button, _stop_button, _settings_button]:
		toolbar.add_child(button)

	_settings_panel = PanelContainer.new()
	_settings_panel.visible = false
	root.add_child(_settings_panel)
	var settings_box := VBoxContainer.new()
	_settings_panel.add_child(settings_box)
	_codex_path_edit = _labeled_line_edit(settings_box, "Codex 可执行文件", "留空则自动查找 codex.exe / codex.cmd / codex")
	_kimi_path_edit = _labeled_line_edit(settings_box, "Kimi 可执行文件", "留空则自动查找 kimi.exe / kimi.cmd / kimi")
	_mcp_endpoint_edit = _labeled_line_edit(settings_box, "Godot MCP Native 地址", DEFAULT_MCP_ENDPOINT)
	_model_edit = _labeled_line_edit(settings_box, "模型覆盖", "留空则使用当前后端官方默认模型")
	_sandbox_option = _labeled_option(settings_box, "Codex 沙箱", ["workspace-write", "read-only", "danger-full-access"])
	_approval_option = _labeled_option(settings_box, "Codex 审批策略", ["on-request", "untrusted", "never"])
	_auto_connect_check = CheckBox.new()
	_auto_connect_check.text = "打开 Dock 后自动连接当前后端"
	settings_box.add_child(_auto_connect_check)
	settings_box.add_child(_make_button("保存设置", _on_save_settings_pressed))

	var tabs := TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(tabs)
	_transcript = RichTextLabel.new()
	_transcript.name = "对话"
	_transcript.bbcode_enabled = true
	_transcript.scroll_following = true
	_transcript.selection_enabled = true
	_transcript.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tabs.add_child(_transcript)
	_diff_view = TextEdit.new()
	_diff_view.name = "Diff"
	_diff_view.editable = false
	_diff_view.wrap_mode = TextEdit.LINE_WRAPPING_NONE
	tabs.add_child(_diff_view)
	_log_view = TextEdit.new()
	_log_view.name = "日志"
	_log_view.editable = false
	_log_view.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	tabs.add_child(_log_view)

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
	_approval_text = TextEdit.new()
	_approval_text.custom_minimum_size = Vector2(0, 70)
	approval_box.add_child(_approval_text)
	_approval_buttons = HBoxContainer.new()
	approval_box.add_child(_approval_buttons)

	_input = TextEdit.new()
	_input.placeholder_text = "让当前官方 AI 后端处理这个 Godot 项目……"
	_input.custom_minimum_size = Vector2(0, 90)
	root.add_child(_input)
	_send_button = _make_button("发送", _on_send_pressed)
	root.add_child(_send_button)
	_append_system("Godot AI 管理器已加载。Godot 编辑器能力只由独立安装的 Godot MCP Native 提供。")

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

func _append_user(text: String) -> void:
	_transcript.append_text("[b]你[/b]\n%s\n\n" % _escape_bbcode(text))

func _append_system(text: String) -> void:
	if _transcript == null:
		return
	_transcript.append_text("[color=gray][i]%s[/i][/color]\n\n" % _escape_bbcode(text))

func _log(text: String) -> void:
	if _log_view == null:
		return
	_log_view.text += "[%s] %s\n" % [Time.get_time_string_from_system(), text]
	_log_view.scroll_vertical = _log_view.get_line_count()

func _escape_bbcode(text: String) -> String:
	return text.replace("[", "[lb]")

func _is_headless() -> bool:
	return DisplayServer.get_name() == "headless" or OS.has_environment("CI")
