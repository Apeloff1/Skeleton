extends Node2D

var game_name := "Studio"
var gamefiles := []

func _ready():
	print("%s — GameForge Godot build" % game_name)
	print("gamefiles: ", gamefiles)
	# Headless validation run: boot the engine, then quit cleanly.
	get_tree().quit()
