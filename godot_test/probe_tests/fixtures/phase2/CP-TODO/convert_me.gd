extends KinematicBody2D

var vel = Vector2()

func _physics_process(delta):
	move_and_slide_with_snap(vel, Vector2.DOWN * 8, Vector2.UP, true, 4, 0.785398, false)
	var a = preload("res://x.tscn").instance()
	var pk = load("res://y.tscn")
	var b = pk.instance()
	var c = get_node("Holder").scene.instance()
	yield(get_tree(), "idle_frame")
	var t = Tween.new()
	add_child(t)
	t.interpolate_property(self, "position", position, Vector2.ZERO, 1.0)
	t.start()
	print(a, b, c, OS.get_ticks_msec())
