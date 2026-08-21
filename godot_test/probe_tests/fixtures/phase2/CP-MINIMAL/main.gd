extends Node

func _ready():
	var t = OS.get_ticks_msec()
	var c = load("res://child.tscn").instance()
	add_child(c)
	print("CP_MINIMAL_OK ", t)
	get_tree().quit()
