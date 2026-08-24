extends Node
func f() -> void:
	Config.ping()
	var v := Vector2(1, 2)
	v.not_a_vector_method()
