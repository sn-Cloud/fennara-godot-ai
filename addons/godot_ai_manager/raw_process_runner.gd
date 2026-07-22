@tool
extends RefCounted
class_name RawProcessRunner

signal started(pid: int, description: String)
signal stdout_received(text: String)
signal stderr_received(text: String)
signal stopped(reason: String)
signal process_error(message: String)

var _pid := -1
var _stdout: FileAccess
var _stderr: FileAccess
var _stdout_thread: Thread
var _stderr_thread: Thread
var _stdout_started := false
var _stderr_started := false
var _stop := false
var _mutex := Mutex.new()
var _stdout_lines: Array[String] = []
var _stderr_lines: Array[String] = []
var _errors: Array[String] = []
var _running := false

func start_command(
	executable: String,
	arguments: PackedStringArray,
	description: String
) -> Dictionary:
	shutdown("restart")
	var process := OS.execute_with_pipe(executable, arguments, false)
	if process.is_empty():
		return {
			"success": false,
			"error": "无法启动进程：%s" % description,
		}
	_pid = int(process.get("pid", -1))
	_stdout = process.get("stdio") as FileAccess
	_stderr = process.get("stderr") as FileAccess
	_running = _pid > 0 and _stdout != null
	_stop = false
	_clear_queues()
	if not _running:
		shutdown("invalid_pipe")
		return {
			"success": false,
			"error": "登录进程没有提供可用管道。",
		}
	var thread_error := _start_threads()
	if thread_error != OK:
		shutdown("thread_failed")
		return {
			"success": false,
			"error": "无法启动登录输出线程，错误码：%s" % thread_error,
		}
	started.emit(_pid, description)
	return {
		"success": true,
		"error": "",
	}

func is_running() -> bool:
	return _running and _pid > 0 and OS.is_process_running(_pid)

func poll() -> void:
	if not _running:
		return
	_drain()
	if _pid > 0 and not OS.is_process_running(_pid):
		shutdown("process_exited")

func shutdown(reason: String = "shutdown") -> void:
	var old_pid := _pid
	var had_process := old_pid > 0
	_running = false
	_pid = -1
	_stop = true
	_wait_threads()
	if old_pid > 0 and OS.is_process_running(old_pid):
		OS.kill(old_pid)
	if _stdout != null:
		_stdout.close()
	if _stderr != null:
		_stderr.close()
	_drain()
	_stdout = null
	_stderr = null
	_clear_queues()
	if had_process:
		stopped.emit(reason)

func _start_threads() -> Error:
	_stdout_thread = Thread.new()
	var stdout_error := _stdout_thread.start(_stdout_loop)
	if stdout_error != OK:
		_stdout_thread = null
		return stdout_error
	_stdout_started = true
	if _stderr != null:
		_stderr_thread = Thread.new()
		var stderr_error := _stderr_thread.start(_stderr_loop)
		if stderr_error != OK:
			_stop = true
			_stdout_thread.wait_to_finish()
			_stdout_thread = null
			_stdout_started = false
			_stderr_thread = null
			return stderr_error
		_stderr_started = true
	return OK

func _wait_threads() -> void:
	if _stdout_thread != null and _stdout_started:
		_stdout_thread.wait_to_finish()
	_stdout_thread = null
	_stdout_started = false
	if _stderr_thread != null and _stderr_started:
		_stderr_thread.wait_to_finish()
	_stderr_thread = null
	_stderr_started = false

func _stdout_loop() -> void:
	_read_loop(_stdout, true)

func _stderr_loop() -> void:
	_read_loop(_stderr, false)

func _read_loop(pipe: FileAccess, is_stdout: bool) -> void:
	var buffer := PackedByteArray()
	while not _stop and pipe != null and pipe.is_open():
		var did_work := false
		var ended := false
		for _index in range(4096):
			var byte := pipe.get_8()
			var read_error := pipe.get_error()
			if read_error == OK:
				did_work = true
				buffer.append(byte)
				if byte == 10:
					_enqueue_line(buffer.get_string_from_utf8().strip_edges(), is_stdout)
					buffer.clear()
				continue
			if read_error == ERR_BUSY or read_error == ERR_FILE_CANT_READ:
				break
			if read_error != ERR_FILE_EOF:
				_enqueue_error("登录进程管道读取失败，错误码：%s" % read_error)
			ended = true
			break
		if ended:
			break
		if not did_work:
			OS.delay_usec(1000)
	if not buffer.is_empty():
		_enqueue_line(buffer.get_string_from_utf8().strip_edges(), is_stdout)

func _enqueue_line(line: String, is_stdout: bool) -> void:
	if line.is_empty():
		return
	_mutex.lock()
	if is_stdout:
		_stdout_lines.append(line)
	else:
		_stderr_lines.append(line)
	_mutex.unlock()

func _enqueue_error(message: String) -> void:
	_mutex.lock()
	_errors.append(message)
	_mutex.unlock()

func _drain() -> void:
	var stdout_batch: Array[String] = []
	var stderr_batch: Array[String] = []
	var error_batch: Array[String] = []
	_mutex.lock()
	stdout_batch.assign(_stdout_lines)
	stderr_batch.assign(_stderr_lines)
	error_batch.assign(_errors)
	_stdout_lines.clear()
	_stderr_lines.clear()
	_errors.clear()
	_mutex.unlock()
	for line in stdout_batch:
		stdout_received.emit(line)
	for line in stderr_batch:
		stderr_received.emit(line)
	for message in error_batch:
		process_error.emit(message)

func _clear_queues() -> void:
	_mutex.lock()
	_stdout_lines.clear()
	_stderr_lines.clear()
	_errors.clear()
	_mutex.unlock()
