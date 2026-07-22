@tool
extends RefCounted
class_name JsonRpcProcessClient

signal started(pid: int, description: String)
signal stopped(reason: String)
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
var _running := false
var _description := ""
var _include_jsonrpc := false

func is_running() -> bool:
	return _running and _pid > 0 and OS.is_process_running(_pid)

func start_command(
	executable: String,
	arguments: PackedStringArray,
	description: String,
	include_jsonrpc: bool
) -> Dictionary:
	if is_running():
		return {
			"success": true,
			"pid": _pid,
			"description": _description,
			"error": "",
		}

	shutdown("restart")
	var process := OS.execute_with_pipe(executable, arguments, false)
	if process.is_empty():
		return {
			"success": false,
			"pid": -1,
			"description": description,
			"error": "无法启动进程：%s" % description,
		}

	_pid = int(process.get("pid", -1))
	_stdio = process.get("stdio") as FileAccess
	_stderr = process.get("stderr") as FileAccess
	_description = description
	_include_jsonrpc = include_jsonrpc
	_running = _pid > 0 and _stdio != null
	_pending_methods.clear()
	_next_request_id = 1
	_io_stop = false
	_clear_queues()

	if not _running:
		shutdown("invalid_pipe")
		return {
			"success": false,
			"pid": -1,
			"description": description,
			"error": "进程没有提供可用的标准输入输出管道。",
		}

	var thread_error := _start_io_threads()
	if thread_error != OK:
		shutdown("io_thread_failed")
		return {
			"success": false,
			"pid": -1,
			"description": description,
			"error": "无法启动进程通信线程，错误码：%s" % thread_error,
		}

	started.emit(_pid, _description)
	return {
		"success": true,
		"pid": _pid,
		"description": _description,
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
		stopped.emit(reason)

func send_request(method: String, params: Dictionary = {}) -> int:
	if not is_running():
		protocol_error.emit("进程未运行，无法发送请求：%s" % method, "")
		return -1

	var request_id := _next_request_id
	_next_request_id += 1
	_pending_methods[_request_id_key(request_id)] = method
	var message := {
		"id": request_id,
		"method": method,
		"params": params,
	}
	if _include_jsonrpc:
		message["jsonrpc"] = "2.0"
	_write_message(message)
	return request_id

func send_notification(method: String, params: Dictionary = {}) -> void:
	if not is_running():
		return
	var message := {
		"method": method,
		"params": params,
	}
	if _include_jsonrpc:
		message["jsonrpc"] = "2.0"
	_write_message(message)

func respond(request_id: Variant, result: Variant) -> void:
	if not is_running():
		return
	var message := {
		"id": request_id,
		"result": result,
	}
	if _include_jsonrpc:
		message["jsonrpc"] = "2.0"
	_write_message(message)

func respond_error(
	request_id: Variant,
	code: int,
	message_text: String,
	data: Variant = null
) -> void:
	if not is_running():
		return
	var error_payload := {
		"code": code,
		"message": message_text,
	}
	if data != null:
		error_payload["data"] = data
	var message := {
		"id": request_id,
		"error": error_payload,
	}
	if _include_jsonrpc:
		message["jsonrpc"] = "2.0"
	_write_message(message)

func poll() -> void:
	if not _running:
		return
	_drain_queues()
	if _pid > 0 and not OS.is_process_running(_pid):
		shutdown("process_exited")

func pending_request_count() -> int:
	return _pending_methods.size()

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
				_enqueue_protocol_error("标准输出读取失败，错误码：%s" % read_error, "")
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
				_enqueue_protocol_error("标准错误读取失败，错误码：%s" % read_error, "")
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
		var payload := (line + "\n").to_utf8_buffer()
		var stored := _stdio.store_buffer(payload)
		var write_error := _stdio.get_error()
		if stored and (write_error == OK or write_error == ERR_BUSY):
			continue
		if write_error == ERR_BUSY:
			_requeue_outgoing_front(batch, index)
			return index > 0
		_enqueue_protocol_error("标准输入写入失败，错误码：%s" % write_error, line)
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
			str(error_value.get("message", "管道错误")),
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
		protocol_error.emit("子进程输出了无效 JSON。", line)
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
		var request_key := _request_id_key(request_id)
		var method := str(_pending_methods.get(request_key, ""))
		_pending_methods.erase(request_key)
		response_received.emit(
			request_id,
			method,
			message.get("result"),
			message.get("error")
		)
		return

	protocol_error.emit("子进程输出了无法识别的 JSON-RPC 消息。", line)

func _request_id_key(value: Variant) -> String:
	if value is int:
		return str(value)
	if value is float:
		var numeric := float(value)
		if is_equal_approx(numeric, round(numeric)):
			return str(int(round(numeric)))
	return str(value)

func _as_dictionary(value: Variant) -> Dictionary:
	if value is Dictionary:
		return value as Dictionary
	return {}
