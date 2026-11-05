extends RigidBody3D
class_name FixtureBall

const GAME := preload("res://scripts/game.gd")

@export var push: float = 1.0


func _ready() -> void:
	# Stay deterministic in headless runs.
	sleeping = false


func _physics_process(_delta: float) -> void:
	if push > 0.0:
		apply_central_force(Vector3.FORWARD * push)
