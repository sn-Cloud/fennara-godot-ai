@tool
extends Node

var _dock: Control
var _client: Object

func _ready() -> void:
	_dock = get_parent() as Control
	set_process(true)

func _process(_delta: float) -> void:
	if _dock == null:
		return
	var current_client: Object = _dock.get("_client")
	if current_client == null:
		return
	if current_client == _client:
		set_process(false)
		return

	_disconnect_client()
	_client = current_client
	_client.response_received.connect(_on_response_received)
	set_process(false)

func _exit_tree() -> void:
	_disconnect_client()

func _disconnect_client() -> void:
	if _client == null:
		return
	if _client.response_received.is_connected(_on_response_received):
		_client.response_received.disconnect(_on_response_received)
	_client = null

func _on_response_received(
	request_id: Variant,
	_method: String,
	_result: Variant,
	_error: Variant
) -> void:
	if _dock == null:
		return
	var request_context: Dictionary = _dock.get("_request_context") as Dictionary
	request_context.erase(str(request_id))
	if request_id is float:
		var numeric_id := float(request_id)
		if is_equal_approx(numeric_id, round(numeric_id)):
			request_context.erase(str(int(round(numeric_id))))
