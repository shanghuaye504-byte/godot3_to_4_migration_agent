@tool
extends EditorPlugin

const SINGLETON_NAME := "DummySingleton"
const SINGLETON_PATH := "res://addons/dummy/dummy_singleton.gd"

func _enable_plugin() -> void:
	add_autoload_singleton(SINGLETON_NAME, SINGLETON_PATH)

func _disable_plugin() -> void:
	remove_autoload_singleton(SINGLETON_NAME)
