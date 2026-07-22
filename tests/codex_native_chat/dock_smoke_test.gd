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

	if not await _wait_for_connection():
		return

	_dock.send_prompt("Implement and verify a Godot feature through Godot MCP Native.")
	if not await _wait_for_approval():
		return

	_dock._on_approval_once_pressed()
	if not await _wait_for_turn_completion():
		return

	var transcript: String = _dock._transcript.get_parsed_text()
	if not transcript.contains("The Godot task was completed and verified through Godot MCP Native."):
		_fail("The streamed Codex response was not rendered in the dock transcript.\n%s" % transcript)
		return
	if not _dock._diff_view.text.contains("player.gd"):
		_fail("The turn diff was not rendered in the Diff tab.")
		return
	if not _dock._mcp_status_label.text.to_lower().contains("ready"):
		_fail("Godot MCP Native status did not become ready: %s" % _dock._mcp_status_label.text)
		return
	if not _dock._account_status_label.text.to_lower().contains("chatgpt"):
		_fail("ChatGPT account status was not rendered: %s" % _dock._account_status_label.text)
		return
	if _dock._active_turn:
		_fail("The dock still reports an active turn after turn/completed.")
		return
	if _dock._approval_panel.visible:
		_fail("The approval panel remained visible after approval was submitted.")
		return

	_dock.shutdown()
	_dock.queue_free()
	print("Codex Native Chat dock workflow smoke test passed.")
	quit(0)

func _wait_for_connection() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._initialized and not _dock._account.is_empty():
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not initialize and read the Codex account.")
	return false

func _wait_for_approval() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._approval_panel.visible and _dock._pending_server_request_id != null:
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not display the command approval request.")
	return false

func _wait_for_turn_completion() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if not _dock._active_turn and _dock._turn_id.is_empty():
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not process turn/completed.")
	return false

func _fail(message: String) -> void:
	if _dock != null:
		_dock.shutdown()
	push_error(message)
	quit(1)
