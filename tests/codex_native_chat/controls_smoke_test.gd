extends SceneTree

var _dock: Control

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var dock_scene: PackedScene = load("res://addons/codex_native_chat/codex_native_chat_dock.tscn")
	if dock_scene == null:
		_fail("Codex dock scene could not be loaded.")
		return

	_dock = dock_scene.instantiate()
	root.add_child(_dock)
	await process_frame

	var mock_file := "mock_codex.cmd" if OS.get_name() == "Windows" else "mock_codex.py"
	_dock._codex_path = ProjectSettings.globalize_path("res://" + mock_file)
	_dock._auto_connect = false
	_dock.connect_codex()
	if not await _wait_for_signed_in():
		return

	_dock._on_login_pressed()
	if not await _wait_for_signed_out():
		return
	_dock._on_login_pressed()
	if not await _wait_for_signed_in():
		return

	_dock._mcp_endpoint_edit.text = "http://127.0.0.1:19082/mcp"
	_dock._model_edit.text = "mock-codex-model"
	_dock._select_option_text(_dock._sandbox_option, "read-only")
	_dock._select_option_text(_dock._approval_option, "untrusted")
	_dock._auto_connect_check.button_pressed = false
	_dock._on_save_settings_pressed()

	if _dock._mcp_endpoint != "http://127.0.0.1:19082/mcp":
		_fail("The MCP endpoint setting was not applied.")
		return
	if _dock._model != "mock-codex-model":
		_fail("The model override setting was not applied.")
		return
	if _dock._sandbox_mode != "read-only" or _dock._approval_policy != "untrusted":
		_fail("Sandbox or approval settings were not applied.")
		return
	if _dock._auto_connect:
		_fail("The auto-connect setting was not disabled.")
		return
	if not _generated_config_contains("19082"):
		return

	_dock.send_prompt("Complete a control workflow test.")
	if not await _wait_for_approval():
		return
	_dock._on_approval_once_pressed()
	if not await _wait_for_turn_end():
		return

	var previous_thread_id: String = _dock._last_thread_id
	if previous_thread_id.is_empty():
		_fail("The completed thread was not saved for resume.")
		return

	_dock._on_new_pressed()
	if not _dock._thread_id.is_empty() or not _dock._diff_view.text.is_empty():
		_fail("New Chat did not clear the active thread and diff.")
		return

	_dock._on_resume_pressed()
	if not await _wait_for_thread(previous_thread_id):
		return

	_dock.send_prompt("interrupt-me")
	if not await _wait_for_active_turn():
		return
	_dock._on_stop_pressed()
	if not await _wait_for_turn_end():
		return

	var transcript: String = _dock._transcript.get_parsed_text()
	if not transcript.contains("Turn interrupted"):
		_fail("The interrupted turn was not reported in the transcript.\n%s" % transcript)
		return
	if _dock._stop_button.disabled == false:
		_fail("The Stop button remained enabled after interruption completed.")
		return

	await create_timer(0.05).timeout
	if not _dock._request_context.is_empty():
		_fail("Completed RPC request contexts were not released: %s" % _dock._request_context)
		return

	_dock.shutdown()
	_dock.queue_free()
	print("Codex Native Chat control workflow smoke test passed.")
	quit(0)

func _wait_for_signed_in() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._initialized and not _dock._account.is_empty():
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not reach a signed-in state.")
	return false

func _wait_for_signed_out() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._account.is_empty() and _dock._login_button.text == "Login":
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not complete logout.")
	return false

func _wait_for_approval() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._approval_panel.visible and _dock._pending_server_request_id != null:
			return true
		await create_timer(0.01).timeout
	_fail("The command approval was not displayed.")
	return false

func _wait_for_turn_end() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if not _dock._active_turn and _dock._turn_id.is_empty():
			return true
		await create_timer(0.01).timeout
	_fail("The turn did not finish.")
	return false

func _wait_for_thread(thread_id: String) -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._thread_id == thread_id:
			return true
		await create_timer(0.01).timeout
	_fail("The previous Codex thread was not resumed.")
	return false

func _wait_for_active_turn() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._active_turn and not _dock._turn_id.is_empty():
			return true
		await create_timer(0.01).timeout
	_fail("The interrupt test turn did not start.")
	return false

func _generated_config_contains(expected: String) -> bool:
	var config_path: String = _dock._project_root.path_join(".codex/config.toml")
	var file := FileAccess.open(config_path, FileAccess.READ)
	if file == null:
		_fail("The project Codex configuration could not be read.")
		return false
	var content := file.get_as_text()
	file.close()
	if not content.contains(expected):
		_fail("The saved MCP endpoint was not written to project config.\n%s" % content)
		return false
	return true

func _fail(message: String) -> void:
	if _dock != null:
		_dock.shutdown()
	push_error(message)
	quit(1)
