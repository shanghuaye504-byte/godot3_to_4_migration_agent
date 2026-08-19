extends RefCounted


func describe(project_name: String, count: int) -> String:
	var version: Dictionary = Engine.get_version_info()
	var version_string: String = str(version.get("string", ""))
	return "%s ready | count=%d | %s" % [project_name, count, version_string]
