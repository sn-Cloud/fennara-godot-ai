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
var _stdio_thread: Thread
var _stderr_thread: Thread
var _stdio_thread_started := false
var _stderr_thread_started := false
var _io_stop := false
var _queue_mutex := Mutex.new()
var _outgoing_lines: Array[String] = []
var _stdout_lines: Array[String] = []
var _stderr_lines: Array[String] = []
var _protocol_errors: Array[Dictionary] = []
var _next_request_id: int = 1
var _pending_methods: Dictionary = {}
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
	_pending_methods.clear()
	_next_request_id = 1
	_io_stop = false
	_clear_queues()

	if not _running:
		shutdown("invalid_pipe")
		status_changed.emit("failed")
		return {
			"success": false,
			"pid": -1,
			"executable": executable,
			"error": "Codex process started without a usable stdio pipe.",
		}

	var thread_result := _start_io_threads()
	if thread_result != OK:
		shutdown("io_thread_failed")
		status_changed.emit("failed")
		return {
			"success": false,
			"pid": -1,
			"executable": executable,
			"error": "Could not start Codex pipe I/O thread (error %s)." % thread_result,
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
	var had_process := old_pid > 0
	_running = false
	_pid = -1
	_io_stop = true

	_wait_for_io_threads()

	if old_pid > 0 and OS.is_process_running(old_pid):
		OS.kill(old_pid)

	if _stdio != null:
		_stdio.close()
	if _stderr != null:
		_stderr.close()

	_drain_queues()
	_stdio = null
	_stderr = null
	_pending_methods.clear()
	_clear_queues()

	if had_process:
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

	_drain_queues()
	if _pid > 0 and not OS.is_process_running(_pid):
		shutdown("process_exited")

func _start_io_threads() -> Error:
	_stdio_thread = Thread.new()
	var stdio_error := _stdio_thread.start(_stdio_io_loop)
	if stdio_error != OK:
		_stdio_thread = null
		return stdio_error
	_stdio_thread_started = true

	if _stderr != null:
		_stderr_thread = Thread.new()
		var stderr_error := _stderr_thread.start(_stderr_io_loop)
		if stderr_error != OK:
			_io_stop = true
			_stdio_thread.wait_to_finish()
			_stdio_thread_started = false
			_stdio_thread = null
			_stderr_thread = null
			return stderr_error
		_stderr_thread_started = true
	return OK

func _wait_for_io_threads() -> void:
	if _stdio_thread != null and _stdio_thread_started:
		_stdio_thread.wait_to_finish()
	_stdio_thread_started = false
	_stdio_thread = null

	if _stderr_thread != null and _stderr_thread_started:
		_stderr_thread.wait_to_finish()
	_stderr_thread_started = false
	_stderr_thread = null

func _stdio_io_loop() -> void:
	var buffer := PackedByteArray()
	while not _io_stop and _stdio != null and _stdio.is_open():
		var did_work := _flush_outgoing_on_io_thread()
		var pipe_ended := false

		for _byte_index in range(4096):
			var byte := _stdio.get_8()
			var read_error := _stdio.get_error()
			if read_error == OK:
				did_work = true
				buffer.append(byte)
				if byte == 10:
					_enqueue_stdout_line(buffer.get_string_from_utf8().strip_edges())
					buffer.clear()
				continue
			if read_error == ERR_BUSY or read_error == ERR_FILE_CANT_READ:
				break
			if read_error != ERR_FILE_EOF:
				_enqueue_protocol_error("Codex stdout pipe read failed (error %s)." % read_error, "")
			pipe_ended = true
			break

		if pipe_ended:
			break
		if not did_work:
			OS.delay_usec(1000)

	if not buffer.is_empty():
		_enqueue_stdout_line(buffer.get_string_from_utf8().strip_edges())

func _stderr_io_loop() -> void:
	var buffer := PackedByteArray()
	while not _io_stop and _stderr != null and _stderr.is_open():
		var did_work := false
		var pipe_ended := false

		for _byte_index in range(4096):
			var byte := _stderr.get_8()
			var read_error := _stderr.get_error()
			if read_error == OK:
				did_work = true
				buffer.append(byte)
				if byte == 10:
					_enqueue_stderr_line(buffer.get_string_from_utf8().strip_edges())
					buffer.clear()
				continue
			if read_error == ERR_BUSY or read_error == ERR_FILE_CANT_READ:
				break
			if read_error != ERR_FILE_EOF:
				_enqueue_protocol_error("Codex stderr pipe read failed (error %s)." % read_error, "")
			pipe_ended = true
			break

		if pipe_ended:
			break
		if not did_work:
			OS.delay_usec(1000)

	if not buffer.is_empty():
		_enqueue_stderr_line(buffer.get_string_from_utf8().strip_edges())

func _flush_outgoing_on_io_thread() -> bool:
	var batch := _take_outgoing_lines()
	if batch.is_empty():
		return false

	for index in range(batch.size()):
		var line := batch[index]
		var stored := _stdio.store_line(line)
		_stdio.flush()
		var write_error := _stdio.get_error()
		if stored and (write_error == OK or write_error == ERR_BUSY):
			continue
		if write_error == ERR_BUSY:
			_requeue_outgoing_front(batch, index)
			return index > 0
		_enqueue_protocol_error("Codex stdin pipe write failed (error %s)." % write_error, line)
		return index > 0
	return true

func _take_outgoing_lines() -> Array[String]:
	var batch: Array[String] = []
	_queue_mutex.lock()
	batch.assign(_outgoing_lines)
	_outgoing_lines.clear()
	_queue_mutex.unlock()
	return batch

func _requeue_outgoing_front(lines: Array[String], start_index: int) -> void:
	_queue_mutex.lock()
	for index in range(lines.size() - 1, start_index - 1, -1):
		_outgoing_lines.push_front(lines[index])
	_queue_mutex.unlock()

func _enqueue_stdout_line(line: String) -> void:
	if line.is_empty():
		return
	_queue_mutex.lock()
	_stdout_lines.append(line)
	_queue_mutex.unlock()

func _enqueue_stderr_line(line: String) -> void:
	if line.is_empty():
		return
	_queue_mutex.lock()
	_stderr_lines.append(line)
	_queue_mutex.unlock()

func _enqueue_protocol_error(message: String, raw_line: String) -> void:
	_queue_mutex.lock()
	_protocol_errors.append({
		"message": message,
		"raw_line": raw_line,
	})
	_queue_mutex.unlock()

func _drain_queues() -> void:
	var stdout_batch: Array[String] = []
	var stderr_batch: Array[String] = []
	var error_batch: Array[Dictionary] = []
	_queue_mutex.lock()
	stdout_batch.assign(_stdout_lines)
	stderr_batch.assign(_stderr_lines)
	error_batch.assign(_protocol_errors)
	_stdout_lines.clear()
	_stderr_lines.clear()
	_protocol_errors.clear()
	_queue_mutex.unlock()

	for line in stdout_batch:
		_parse_message(line)
	for line in stderr_batch:
		stderr_received.emit(line)
	for error_value in error_batch:
		protocol_error.emit(
			str(error_value.get("message", "Pipe error")),
			str(error_value.get("raw_line", ""))
		)

func _clear_queues() -> void:
	_queue_mutex.lock()
	_outgoing_lines.clear()
	_stdout_lines.clear()
	_stderr_lines.clear()
	_protocol_errors.clear()
	_queue_mutex.unlock()

func _write_message(message: Dictionary) -> void:
	var serialized := JSON.stringify(message)
	_queue_mutex.lock()
	_outgoing_lines.append(serialized)
	_queue_mutex.unlock()

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
