@tool
extends EditorPlugin

const DOCK_SCENE := preload("res://addons/codex_native_chat/codex_native_chat_dock.tscn")

var _dock: CodexNativeChatDock

func _enter_tree() -> void:
	_dock = DOCK_SCENE.instantiate() as CodexNativeChatDock
	_dock.configure(get_editor_interface())
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _dock)

func _exit_tree() -> void:
	if _dock == null:
		return
	_dock.shutdown()
	remove_control_from_docks(_dock)
	_dock.queue_free()
	_dock = null
