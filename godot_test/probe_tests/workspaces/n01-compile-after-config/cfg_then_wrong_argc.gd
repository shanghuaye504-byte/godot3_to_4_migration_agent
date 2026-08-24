extends Node
func f() -> void:
	Config.ping()
	var n: Node = Node.new()
	n.queue_free(1, 2, 3)
