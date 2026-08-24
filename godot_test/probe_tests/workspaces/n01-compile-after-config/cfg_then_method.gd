extends Node
func f() -> void:
	Config.ping()
	var n: Node = Node.new()
	n.no_such_method()
