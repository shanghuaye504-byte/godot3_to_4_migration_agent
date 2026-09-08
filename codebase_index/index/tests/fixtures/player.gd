class_name Player
extends CharacterBody2D

signal died

const MAX_HP := 100
var hp := MAX_HP

func take_damage(amount: int) -> void:
	hp -= amount
	if hp <= 0:
		_die()

func _die() -> void:
	died.emit()
	queue_free()
