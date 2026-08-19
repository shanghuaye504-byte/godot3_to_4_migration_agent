extends Node2D

const CounterScript := preload("res://counter.gd")
const Ping := preload("res://ping.gd")

@onready var status_label: Label = $StatusLabel
@onready var counter: CounterScript = $Counter


func _ready() -> void:
	var ping := Ping.new()
	var count: int = counter.increment()
	status_label.text = ping.describe("CleanControl", count)
