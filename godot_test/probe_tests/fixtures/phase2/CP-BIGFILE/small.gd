extends Node
func _ready():
	var t = OS.get_ticks_msec()
	var s = load("res://x.tscn").instance()
	print(t, s)
