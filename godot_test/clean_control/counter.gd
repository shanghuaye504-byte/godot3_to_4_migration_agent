extends Node

var value: int = 0


func increment() -> int:
	value += 1
	return value


func get_value() -> int:
	return value
