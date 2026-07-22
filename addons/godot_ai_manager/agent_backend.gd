@tool
extends RefCounted
class_name AiAgentBackend

signal backend_status_changed(status: String)
signal account_status_changed(status: String, signed_in: bool)
signal mcp_status_changed(status: String)
signal message_delta(text: String)
signal message_completed()
signal thought_delta(text: String)
signal tool_event(title: String, details: String, status: String)
signal diff_changed(diff_text: String)
signal log_message(text: String)
signal error_message(text: String)
signal session_changed(session_id: String)
signal turn_state_changed(active: bool)
signal approval_requested(
	title: String,
	details: String,
	choices: Array,
	needs_text: bool,
	text_placeholder: String
)
signal login_message(text: String)

var project_root := ""
var executable_path := ""
var mcp_endpoint := "http://127.0.0.1:9080/mcp"
var model_override := ""
var session_id := ""
var active_turn := false
var signed_in := false

func configure(options: Dictionary) -> void:
	project_root = str(options.get("project_root", project_root))
	executable_path = str(options.get("executable_path", executable_path))
	mcp_endpoint = str(options.get("mcp_endpoint", mcp_endpoint))
	model_override = str(options.get("model_override", model_override))

func backend_id() -> String:
	return "base"

func backend_name() -> String:
	return "AI"

func connect_backend() -> void:
	pass

func disconnect_backend() -> void:
	pass

func poll() -> void:
	pass

func login() -> void:
	pass

func logout() -> void:
	pass

func new_session() -> void:
	session_id = ""
	session_changed.emit(session_id)

func resume_session(_stored_session_id: String) -> void:
	pass

func send_prompt(_prompt: String) -> void:
	pass

func cancel_turn() -> void:
	pass

func resolve_approval(_choice_id: String, _text_value: String, _cancelled: bool) -> void:
	pass

func is_backend_connected() -> bool:
	return false

func can_logout() -> bool:
	return false

func supports_model_override() -> bool:
	return false

func pending_request_count() -> int:
	return 0
