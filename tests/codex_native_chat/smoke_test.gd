extends SceneTree

func _init() -> void:
	var paths := [
		"res://addons/codex_native_chat/codex_app_server_client.gd",
		"res://addons/codex_native_chat/codex_config_manager.gd",
		"res://addons/codex_native_chat/codex_native_chat_dock.gd",
		"res://addons/codex_native_chat/codex_native_chat.gd",
		"res://addons/codex_native_chat/codex_native_chat_dock.tscn",
	]
	for path in paths:
		var resource := load(path)
		if resource == null:
			push_error("Failed to load %s" % path)
			quit(1)
			return

	var manager_script := load("res://addons/codex_native_chat/codex_config_manager.gd")
	var manager = manager_script.new()
	var test_root := ProjectSettings.globalize_path("res://.config_test")
	DirAccess.make_dir_recursive_absolute(test_root)
	var first := manager.ensure_project_mcp_config(test_root, "http://127.0.0.1:9080/mcp")
	if not bool(first.get("success", false)):
		push_error("MCP config creation failed: %s" % first.get("error", ""))
		quit(1)
		return
	var second := manager.ensure_project_mcp_config(test_root, "http://127.0.0.1:19080/mcp")
	if not bool(second.get("success", false)):
		push_error("MCP config update failed: %s" % second.get("error", ""))
		quit(1)
		return
	var config_path := test_root.path_join(".codex/config.toml")
	var file := FileAccess.open(config_path, FileAccess.READ)
	if file == null:
		push_error("Generated config was not readable.")
		quit(1)
		return
	var content := file.get_as_text()
	file.close()
	if content.count("[mcp_servers.godot-mcp]") != 1 or not content.contains("19080"):
		push_error("Generated MCP table is invalid:\n%s" % content)
		quit(1)
		return
	print("Codex Native Chat smoke tests passed.")
	quit(0)
