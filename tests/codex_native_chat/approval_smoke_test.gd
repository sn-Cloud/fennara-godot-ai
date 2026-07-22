extends SceneTree

var _dock: Control
var _suite_complete := false
var _suite_ok := false
var _suite_errors: Array = []

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

	_dock._client.notification_received.connect(_on_notification_received)
	var request_id: int = _dock._client.send_request("mock/approvalSuite/start", {})
	if request_id < 0:
		_fail("Could not start the approval suite.")
		return

	if not await _wait_for_method("item/fileChange/requestApproval"):
		return
	_dock._on_approval_session_pressed()

	if not await _wait_for_method("item/permissions/requestApproval"):
		return
	_dock._on_approval_once_pressed()

	if not await _wait_for_method("item/tool/requestUserInput"):
		return
	_dock._approval_answer.text = "Blue"
	_dock._on_approval_once_pressed()

	if not await _wait_for_method("mcpServer/elicitation/request"):
		return
	_dock._approval_answer.text = "{\"value\":\"ok\"}"
	_dock._on_approval_once_pressed()

	if not await _wait_for_method("item/commandExecution/requestApproval"):
		return
	_dock._on_approval_reject_pressed()

	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _suite_complete:
			break
		await create_timer(0.01).timeout

	if not _suite_complete:
		_fail("The approval suite did not finish.")
		return
	if not _suite_ok:
		_fail("The approval suite reported invalid responses: %s" % _suite_errors)
		return
	if _dock._approval_panel.visible:
		_fail("The approval panel remained visible after the suite completed.")
		return
	if _dock._pending_server_request_id != null:
		_fail("A server approval request remained pending after the suite completed.")
		return

	_dock.shutdown()
	_dock.queue_free()
	print("Codex Native Chat approval workflow smoke test passed.")
	quit(0)

func _wait_for_connection() -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._initialized and not _dock._account.is_empty():
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not initialize before the approval suite.")
	return false

func _wait_for_method(expected_method: String) -> bool:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		if _dock._pending_server_request_method == expected_method and _dock._approval_panel.visible:
			return true
		await create_timer(0.01).timeout
	_fail("The dock did not present approval method %s. Current method: %s" % [
		expected_method,
		_dock._pending_server_request_method,
	])
	return false

func _on_notification_received(method: String, params: Dictionary) -> void:
	if method != "mock/approvalSuiteComplete":
		return
	_suite_complete = true
	_suite_ok = bool(params.get("ok", false))
	_suite_errors = params.get("errors", []) as Array

func _fail(message: String) -> void:
	if _dock != null:
		_dock.shutdown()
	push_error(message)
	quit(1)
