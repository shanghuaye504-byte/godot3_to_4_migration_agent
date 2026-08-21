extends Node

func _ready() -> void:
	DummySingleton.ping()
	print("NP_ADDON_MAIN_OK")
	get_tree().quit()
