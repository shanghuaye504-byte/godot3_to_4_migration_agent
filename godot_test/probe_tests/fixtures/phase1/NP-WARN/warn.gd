extends Node

signal never_emitted

var member := 1

func _ready() -> void:
	var unused := 42
	var member := 2
	var d := 7 / 2
	var f: float = 1.0
	var i: int = f
	print(d, i, member)

func untyped(p):
	return p
