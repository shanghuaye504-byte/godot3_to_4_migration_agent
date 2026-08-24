extends Node
func f() -> void:
	Config.ping()
	print(Config.MAGIC)
	Config.ping()
	var n: Node = Node.new()
	n.no_such_method()
	n.queue_free(1, 2)
	DoesNotExist.boom()
