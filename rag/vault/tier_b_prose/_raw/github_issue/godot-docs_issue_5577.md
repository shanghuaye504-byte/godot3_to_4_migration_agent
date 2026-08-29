# body by SimonImming

**Godot version:**
Godot Engine v4.0.alpha1.official [31a7ddbf8]


**Issue description:**
The Step by Step tutorial uses a deprecated syntax for connecting signals. This is the code used in the documentation:
```
func _ready():
    var timer = get_node("Timer")
    timer.connect("timeout", self, "_on_Timer_timeout")
```

This code does not work in Godot 4 and produces the following error message:
```
Invalid argument for "connect()" function: argument 2 should be Callable but is res://Sprite2D.gd.
Invalid argument for "connect()" function: argument 3 should be Array but is String.
```

The correct code according to the [Class Reference](https://docs.godotengine.org/en/latest/classes/class_object.html#class-object-method-connect) would be:
```
func _ready():
	var timer = get_node("Timer")
	timer.timeout.connect(_on_Timer_timeout)
```

This code has also been tested in Godot 4 with the tutorial files from the step by step tutorial and works as expected.


**URL to the documentation page:**
[https://docs.godotengine.org/en/latest/getting_started/step_by_step/signals.html](https://docs.godotengine.org/en/latest/getting_started/step_by_step/signals.html)

