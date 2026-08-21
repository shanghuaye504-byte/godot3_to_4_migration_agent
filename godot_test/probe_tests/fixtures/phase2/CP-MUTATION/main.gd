extends CharacterBody2D

@export var speed := 100
@onready var label := $Label
@onready var sprite: Sprite2D = $Sprite2D

signal done

func _ready() -> void:
	var packed := preload("res://child.tscn")
	var node := packed.instantiate()
	add_child(node)
	var extra := Sprite2D.new()
	node.add_sibling(extra)
	var dist := position.distance_to(Vector2(speed, 0.0))
	var ticks := Time.get_ticks_msec()
	label.text = str(ticks)
	sprite.visible = false
	done.connect(_on_done)
	velocity = Vector2.UP * speed
	move_and_slide()
	var tw := create_tween()
	tw.tween_property(self, "position", Vector2.ZERO, 0.1)
	await get_tree().process_frame
	done.emit()
	print("CP_MUTATION_BASE_OK ", ticks, dist)
	get_tree().quit()

func _on_done() -> void:
	pass
