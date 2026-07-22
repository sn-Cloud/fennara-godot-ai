@tool
extends RefCounted
class_name CodexAppServerClient

signal started(pid: int, executable: String)
signal stopped(exit_reason: String)
signal status_changed(status: String)
signal response_received(request_id: Variant, method: String, result: Variant, error: Variant)
signal notification_received(method: String, params: Dictionary)
signal server_request_received(request_id: Variant, method: String, params: Dictionary)
signal stderr_received(text: String)
signal protocol_error(message: String, raw_line: String)

var _pid: int = -1
var _stdio: FileAccess
var _stderr: FileAccess
var _next_request_id: int = 1
var _pending_methods: Dictionary = {}
var _stdout_buffer: String = ""
var _stderr_buffer: String = ""
var _running: bool = false
var _launch_description: String = ""

func is_running() -> bool:
	return _running and _pid > 0 and OS.is_process_running(_pid)

func start(preferred_path: String = "") -> Dictionary:
	if is_running():
		return {
			"success": true,
			"pid": _pid,
			"executable": _launch_description,
			"error": "",
		}

	shutdown("restart")
	var launch := _resolve_launch(preferred_path)
	if not bool(launch.get("success", false)):
		status_changed.emit("not_found")
		return launch

	var executable := str(launch.get("executable", ""))
	var arguments := launch.get("arguments", PackedStringArray()) as PackedStringArray
	var process := OS.execute_with_pipe(executable, arguments, false)
	if process.is_empty():
		var error_message := "Failed to start Codex app-server with %s." % executable
		status_changed.emit("failed")
		return {
			"success": false,
			"pid": -1,
			"executable": executable,
			"error": error_message,
		}

	_pid = int(process.get("pid", -1))
	_stdio = process.get("stdio") as FileAccess
	_stderr = process.get("stderr") as FileAccess
	_running = _pid > 0 and _stdio != null
	_launch_description = str(launch.get("description", executable))
	_stdout_buffer = ""
	_stderr_buffer = ""
	_pending_methods.clear()
	_next_request_id = 1

	if not _running:
		shutdown("invalid_pipe")
		status_changed.emit("failed")
		return {
			"success": false,
			"pid": -1,
			"executable": executable,
			"error": "Codex process started without a usable stdio pipe.",
		}

	status_changed.emit("running")
	started.emit(_pid, _launch_description)
	return {
		"success": true,
		"pid": _pid,
		"executable": _launch_description,
		"error": "",
	}

func shutdown(reason: String = "shutdown") -> void:
	var old_pid := _pid
	_running = false
	_pid = -1
	_pending_methods.clear()
	_stdout_buffer = ""
	_stderr_buffer = ""

	if _stdio != null:
		_stdio.close()
		_stdio = null
	if _stderr != null:
		_stderr.close()
		_stderr = null

	if old_pid > 0 and OS.is_process_running(old_pid):
		OS.kill(old_pid)

	if old_pid > 0:
		status_changed.emit("stopped")
		stopped.emit(reason)

func send_request(method: String, params: Dictionary = {}) -> int:
	if not is_running():
		protocol_error.emit("Cannot send %s because Codex app-server is not running." % method, "")
		return -1

	var request_id := _next_request_id
	_next_request_id += 1
	_pending_methods[str(request_id)] = method
	_write_message({
		"id": request_id,
		"method": method,
		"params": params,
	})
	return request_id

func send_notification(method: String, params: Dictionary = {}) -> void:
	if not is_running():
		return
	_write_message({
		"method": method,
		"params": params,
	})

func respond(request_id: Variant, result: Variant) -> void:
	if not is_running():
		return
	_write_message({
		"id": request_id,
		"result": result,
	})

func respond_error(request_id: Variant, code: int, message: String, data: Variant = null) -> void:
	if not is_running():
		return
	var error_payload := {
		"code": code,
		"message": message,
	}
	if data != null:
		error_payload["data"] = data
	_write_message({
		"id": request_id,
		"error": error_payload,
	})

func poll() -> void:
	if not _running:
		return

	_drain_pipe(_stdio, false)
	_drain_pipe(_stderr, true)

	if _pid > 0 and not OS.is_process_running(_pid):
		shutdown("process_exited")

func _drain_pipe(pipe: FileAccess, is_stderr: bool) -> void:
	if pipe == null:
		return

	for _iteration in range(32):
		var bytes := pipe.get_buffer(65536)
		if bytes.is_empty():
			break
		var text := bytes.get_string_from_utf8()
		if text.is_empty():
			continue
		if is_stderr:
			_stderr_buffer += text
			_flush_stderr_lines()
		else:
			_stdout_buffer += text
			_flush_stdout_lines()

func _flush_stdout_lines() -> void:
	while true:
		var newline_index := _stdout_buffer.find("\n")
		if newline_index < 0:
			return
		var line := _stdout_buffer.substr(0, newline_index).strip_edges()
		_stdout_buffer = _stdout_buffer.substr(newline_index + 1)
		if not line.is_empty():
			_parse_message(line)

func _flush_stderr_lines() -> void:
	while true:
		var newline_index := _stderr_buffer.find("\n")
		if newline_index < 0:
			return
		var line := _stderr_buffer.substr(0, newline_index).strip_edges()
		_stderr_buffer = _stderr_buffer.substr(newline_index + 1)
		if not line.is_empty():
			stderr_received.emit(line)

func _write_message(message: Dictionary) -> void:
	if _stdio == null:
		return
	var payload := (JSON.stringify(message) + "\n").to_utf8_buffer()
	_stdio.store_buffer(payload)
	_stdio.flush()
	var write_error := _stdio.get_error()
	if write_error != OK and write_error != ERR_BUSY:
		protocol_error.emit("Failed to write to Codex app-server pipe (error %s)." % write_error, JSON.stringify(message))

func _parse_message(line: String) -> void:
	var parsed := JSON.parse_string(line)
	if not parsed is Dictionary:
		protocol_error.emit("Codex app-server emitted invalid JSON.", line)
		return

	var message := parsed as Dictionary
	if message.has("method") and message.has("id"):
		server_request_received.emit(
			message.get("id"),
			str(message.get("method", "")),
			_as_dictionary(message.get("params", {}))
		)
		return

	if message.has("method"):
		notification_received.emit(
			str(message.get("method", "")),
			_as_dictionary(message.get("params", {}))
		)
		return

	if message.has("id"):
		var request_id: Variant = message.get("id")
		var method := str(_pending_methods.get(str(request_id), ""))
		_pending_methods.erase(str(request_id))
		response_received.emit(
			request_id,
			method,
			message.get("result"),
			message.get("error")
		)
		return

	protocol_error.emit("Codex app-server emitted an unrecognized message.", line)

func _resolve_launch(preferred_path: String) -> Dictionary:
	var candidate := preferred_path.strip_edges()
	if not candidate.is_empty():
		var explicit := _launch_for_candidate(candidate)
		if bool(explicit.get("success", false)):
			return explicit
		return {
			"success": false,
			"pid": -1,
			"executable": candidate,
			"error": "Configured Codex executable was not found: %s" % candidate,
		}

	var candidates: Array[String] = []
	if OS.get_name() == "Windows":
		candidates.append_array(_command_search("where.exe", PackedStringArray(["codex.exe"])))
		candidates.append_array(_command_search("where.exe", PackedStringArray(["codex.cmd"])))
		candidates.append_array(_command_search("where.exe", PackedStringArray(["codex"])))
		var user_profile := OS.get_environment("USERPROFILE")
		var local_app_data := OS.get_environment("LOCALAPPDATA")
		var app_data := OS.get_environment("APPDATA")
		if not user_profile.is_empty():
			candidates.append(user_profile.path_join(".codex/bin/codex.exe"))
		if not local_app_data.is_empty():
			candidates.append(local_app_data.path_join("Programs/Codex/codex.exe"))
			candidates.append(local_app_data.path_join("OpenAI/Codex/codex.exe"))
		if not app_data.is_empty():
			candidates.append(app_data.path_join("npm/codex.cmd"))
	else:
		candidates.append_array(_command_search("which", PackedStringArray(["codex"])))
		var home := OS.get_environment("HOME")
		if not home.is_empty():
			candidates.append(home.path_join(".local/bin/codex"))
			candidates.append(home.path_join(".codex/bin/codex"))

	var seen: Dictionary = {}
	for candidate_path in candidates:
		var normalized := candidate_path.strip_edges().replace("\r", "")
		if normalized.is_empty() or seen.has(normalized):
			continue
		seen[normalized] = true
		var launch := _launch_for_candidate(normalized)
		if bool(launch.get("success", false)):
			return launch

	return {
		"success": false,
		"pid": -1,
		"executable": "",
		"error": "Codex CLI was not found. Install Codex or set its executable path in Settings.",
	}

func _launch_for_candidate(candidate: String) -> Dictionary:
	var path := candidate
	if not path.is_absolute_path():
		var found := _command_search("where.exe" if OS.get_name() == "Windows" else "which", PackedStringArray([path]))
		if not found.is_empty():
			path = found[0]

	if not FileAccess.file_exists(path):
		return {"success": false}

	if OS.get_name() == "Windows" and (path.to_lower().ends_with(".cmd") or path.to_lower().ends_with(".bat")):
		var command_line := "\"%s\" app-server --stdio" % path.replace("\"", "\\\"")
		return {
			"success": true,
			"executable": "cmd.exe",
			"arguments": PackedStringArray(["/D", "/S", "/C", command_line]),
			"description": path,
		}

	return {
		"success": true,
		"executable": path,
		"arguments": PackedStringArray(["app-server", "--stdio"]),
		"description": path,
	}

func _command_search(command: String, arguments: PackedStringArray) -> Array[String]:
	var output: Array = []
	var exit_code := OS.execute(command, arguments, output, true, false)
	if exit_code != 0 or output.is_empty():
		return []
	var values: Array[String] = []
	for line in str(output[0]).split("\n"):
		var value := str(line).strip_edges().replace("\r", "")
		if not value.is_empty():
			values.append(value)
	return values

func _as_dictionary(value: Variant) -> Dictionary:
	if value is Dictionary:
		return value as Dictionary
	return {}
