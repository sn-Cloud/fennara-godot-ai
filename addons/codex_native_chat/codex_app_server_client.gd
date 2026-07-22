@tool
extends RefCounted
class_name CodexAppServerClient

signal notification_received(method: String, params: Dictionary)
signal response_received(request_id: int, method: String, result: Variant, error: Variant)
signal server_request_received(request_id: Variant, method: String, params: Dictionary)
signal output_received(text: String)
signal status_changed(status: String)

var _process: int = -1
var _stdout: FileAccess
var _stderr: FileAccess
var _request_id := 1
var _pending_methods: Dictionary = {}

func start(codex_path: String = "codex") -> bool:
	if _process != -1:
		return true

	var args := PackedStringArray(["app-server", "--stdio"])
	var result := OS.execute_with_pipe(codex_path, args)
	if result.is_empty():
		status_changed.emit("failed")
		return false

	_process = int(result.get("pid", -1))
	_stdout = result.get("stdio")
	_stderr = result.get("stderr")
	status_changed.emit("running")
	return true

func shutdown() -> void:
	if _process != -1:
		OS.kill(_process)
	_process = -1

func send(method: String, params: Dictionary = {}) -> int:
	var id := _request_id
	_request_id += 1
	_pending_methods[id] = method
	_write_json({"jsonrpc":"2.0", "id":id, "method":method, "params":params})
	return id

func notify(method: String, params: Dictionary = {}) -> void:
	_write_json({"jsonrpc":"2.0", "method":method, "params":params})

func poll() -> void:
	if _stdout == null:
		return
	while _stdout.get_position() < _stdout.get_length():
		_parse_message(_stdout.get_line())

func _write_json(message: Dictionary) -> void:
	if _stdout == null:
		return
	_stdout.store_line(JSON.stringify(message))

func _parse_message(line: String) -> void:
	var data = JSON.parse_string(line)
	if not data is Dictionary:
		return
	if data.has("method") and data.has("id"):
		server_request_received.emit(data.id, data.method, data.get("params", {}))
	elif data.has("method"):
		notification_received.emit(data.method, data.get("params", {}))
	elif data.has("id"):
		var method := str(_pending_methods.get(data.id, ""))
		response_received.emit(data.id, method, data.get("result"), data.get("error"))

func _notification(_delta: float) -> void:
	poll()
