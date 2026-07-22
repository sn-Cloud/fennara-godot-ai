@tool
extends EditorPlugin

const DOCK_SCENE := preload("res://addons/godot_ai_manager/godot_ai_manager_dock.tscn")

var _dock: GodotAiManagerDock

func _enter_tree() -> void:
	_dock = DOCK_SCENE.instantiate() as GodotAiManagerDock
	_dock.configure(get_editor_interface())
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _dock)

func _exit_tree() -> void:
	if _dock == null:
		return
	_dock.shutdown()
	remove_control_from_docks(_dock)
	_dock.queue_free()
	_dock = null
