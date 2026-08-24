extends Node

func _ready() -> void:
	Config.ping()
	print("NP_AUTOLOAD_MAIN_OK ", Config.MAGIC)
	get_tree().quit()
