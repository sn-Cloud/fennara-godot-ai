@tool
extends RefCounted
class_name CodexGodotMcpConfigManager

const GODOT_MCP_SECTION := "[mcp_servers.godot-mcp]"

func ensure_config(project_root: String, endpoint: String) -> Dictionary:
	var codex_dir := project_root.path_join(".codex")
	var config_path := codex_dir.path_join("config.toml")
	var make_error := DirAccess.make_dir_recursive_absolute(codex_dir)
	if make_error != OK and make_error != ERR_ALREADY_EXISTS:
		return _result(false, false, config_path, "无法创建 %s，错误码：%s" % [codex_dir, make_error], false)

	var original := ""
	if FileAccess.file_exists(config_path):
		var read_file := FileAccess.open(config_path, FileAccess.READ)
		if read_file == null:
			return _result(false, false, config_path, "无法读取 %s。" % config_path, false)
		original = read_file.get_as_text()
		read_file.close()

	var block := "%s\nurl = \"%s\"\nenabled = true\nstartup_timeout_sec = 20" % [
		GODOT_MCP_SECTION,
		_escape_toml(endpoint),
	]
	var updated := _replace_table(original, GODOT_MCP_SECTION, block)
	var legacy_found := _contains_fennara_mcp(original)
	if updated == original:
		return _result(true, false, config_path, "", legacy_found)

	var write_file := FileAccess.open(config_path, FileAccess.WRITE)
	if write_file == null:
		return _result(false, false, config_path, "无法写入 %s。" % config_path, legacy_found)
	write_file.store_string(updated)
	var write_error := write_file.get_error()
	write_file.close()
	if write_error != OK:
		return _result(false, false, config_path, "写入 %s 失败，错误码：%s" % [config_path, write_error], legacy_found)
	return _result(true, true, config_path, "", legacy_found)

func _replace_table(source: String, section: String, replacement: String) -> String:
	var lines := source.split("\n", true)
	var output: Array[String] = []
	var skipping := false
	var replaced := false
	for raw_line in lines:
		var line := str(raw_line)
		var stripped := line.strip_edges()
		if stripped == section:
			if not replaced:
				for replacement_line in replacement.split("\n"):
					output.append(str(replacement_line))
			replaced = true
			skipping = true
			continue
		if skipping and stripped.begins_with("[") and stripped.ends_with("]"):
			skipping = false
		if not skipping:
			output.append(line)

	if not replaced:
		while not output.is_empty() and output.back().strip_edges().is_empty():
			output.pop_back()
		if not output.is_empty():
			output.append("")
		for replacement_line in replacement.split("\n"):
			output.append(str(replacement_line))
	return "\n".join(output).strip_edges() + "\n"

func _contains_fennara_mcp(source: String) -> bool:
	var lower := source.to_lower()
	return lower.contains("mcp_servers.fennara") or lower.contains("fennara-mcp") or lower.contains("127.0.0.1:41287")

func _escape_toml(value: String) -> String:
	return value.replace("\\", "\\\\").replace("\"", "\\\"")

func _result(
	success: bool,
	changed: bool,
	path: String,
	error: String,
	legacy_found: bool
) -> Dictionary:
	return {
		"success": success,
		"changed": changed,
		"path": path,
		"error": error,
		"legacy_fennara_mcp_found": legacy_found,
	}
