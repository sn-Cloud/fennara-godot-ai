@tool
extends RefCounted
class_name AiCommandResolver

func resolve(
	command_name: String,
	preferred_path: String,
	arguments: PackedStringArray
) -> Dictionary:
	var candidates: Array[String] = []
	var configured := preferred_path.strip_edges()
	if not configured.is_empty():
		candidates.append(configured)
	else:
		candidates.append_array(_find_on_path(command_name))
		candidates.append_array(_common_locations(command_name))

	var seen := {}
	for candidate_value in candidates:
		var candidate := str(candidate_value).strip_edges().replace("\r", "")
		if candidate.is_empty() or seen.has(candidate):
			continue
		seen[candidate] = true
		var result := _build_launch(candidate, arguments)
		if bool(result.get("success", false)):
			return result

	return {
		"success": false,
		"executable": "",
		"arguments": PackedStringArray(),
		"description": command_name,
		"error": "未找到 %s。请安装官方 CLI，或在设置中填写可执行文件路径。" % command_name,
	}

func _build_launch(candidate: String, arguments: PackedStringArray) -> Dictionary:
	var resolved := candidate
	if not resolved.is_absolute_path():
		var on_path := _find_on_path(resolved)
		if not on_path.is_empty():
			resolved = on_path[0]
	if not FileAccess.file_exists(resolved):
		return {"success": false}

	var lower := resolved.to_lower()
	if OS.get_name() == "Windows" and (lower.ends_with(".cmd") or lower.ends_with(".bat")):
		var parts: Array[String] = [_quote_windows(resolved)]
		for argument in arguments:
			parts.append(_quote_windows(str(argument)))
		return {
			"success": true,
			"executable": "cmd.exe",
			"arguments": PackedStringArray(["/D", "/S", "/C", " ".join(parts)]),
			"description": resolved,
			"error": "",
		}

	return {
		"success": true,
		"executable": resolved,
		"arguments": arguments,
		"description": resolved,
		"error": "",
	}

func _find_on_path(command_name: String) -> Array[String]:
	var output: Array = []
	var executable := "where.exe" if OS.get_name() == "Windows" else "which"
	var exit_code := OS.execute(executable, PackedStringArray([command_name]), output, true, false)
	if exit_code != 0 or output.is_empty():
		return []
	var values: Array[String] = []
	for line in str(output[0]).split("\n"):
		var value := str(line).strip_edges().replace("\r", "")
		if not value.is_empty():
			values.append(value)
	return values

func _common_locations(command_name: String) -> Array[String]:
	var values: Array[String] = []
	if OS.get_name() == "Windows":
		var app_data := OS.get_environment("APPDATA")
		var local_app_data := OS.get_environment("LOCALAPPDATA")
		var user_profile := OS.get_environment("USERPROFILE")
		if not app_data.is_empty():
			values.append(app_data.path_join("npm/%s.cmd" % command_name))
		if not local_app_data.is_empty():
			values.append(local_app_data.path_join("Programs/%s/%s.exe" % [command_name.capitalize(), command_name]))
		if not user_profile.is_empty():
			values.append(user_profile.path_join(".local/bin/%s.exe" % command_name))
	else:
		var home := OS.get_environment("HOME")
		if not home.is_empty():
			values.append(home.path_join(".local/bin/%s" % command_name))
			values.append(home.path_join(".npm-global/bin/%s" % command_name))
	return values

func _quote_windows(value: String) -> String:
	return "\"%s\"" % value.replace("\"", "\\\"")
