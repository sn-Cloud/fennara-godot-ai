@tool
extends EditorPlugin

const DOCK_SCENE = preload("res://addons/codex_native_chat/codex_native_chat_dock.tscn")

var dock: Control

func _enter_tree():
	dock = DOCK_SCENE.instantiate()
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, dock)

func _exit_tree():
	if dock:
		remove_control_from_docks(dock)
		dock.queue_free()
