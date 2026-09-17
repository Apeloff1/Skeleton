"""Godot 4 scripts for NEXUS-EXTRACT. Text only. Numbers from data/spec.json."""

from __future__ import annotations

from typing import Any

from skeleton.game.layouts import campus


PLAYER_GD = '''extends CharacterBody2D
class_name NexusPlayer

@export var speed: float = 180.0
@export var heat_gain_on_move: int = 1
@export var extract_once: bool = true

var extracted: int = 0

func _physics_process(_delta: float) -> void:
    var input_vector := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    velocity = input_vector * speed
    move_and_slide()
    if input_vector != Vector2.ZERO and has_node("/root/Heat"):
        get_node("/root/Heat").add_heat(heat_gain_on_move)

func try_extract() -> bool:
    if extract_once and extracted >= 1:
        return false
    if not has_node("/root/Extract"):
        return false
    var ok: bool = get_node("/root/Extract").pull()
    if ok:
        extracted += 1
    return ok
'''

HEAT_GD = '''extends Node
class_name NexusHeat

@export var heat: int = 0
@export var sleep: int = 0
@export var period: int = 4
@export var tokens: int = 0

var _tick: int = 0

func add_heat(amount: int) -> void:
    heat = clamp(heat + amount, 0, 100)
    sleep = clamp(sleep - 1, 0, 100)

func rest() -> void:
    heat = clamp(heat - 5, 0, 100)
    sleep = clamp(sleep + 8, 0, 100)

func dream() -> bool:
    if sleep < 8:
        return false
    sleep -= 8
    heat = clamp(heat - 2, 0, 100)
    return true

func pulse() -> void:
    _tick += 1
    if _tick % period == 0:
        tokens += 1
'''

EXTRACT_GD = '''extends Node
class_name NexusExtract

@export var extract_count: int = 0
@export var warp_count: int = 0
@export var heat_need: int = 12

func pull() -> bool:
    if warp_count >= 1:
        return false
    if not has_node("/root/Heat"):
        return false
    var heat_node = get_node("/root/Heat")
    if heat_node.heat < heat_need:
        return false
    heat_node.heat -= heat_need
    extract_count += 1
    warp_count += 1
    return true
'''

FORGE_GD = '''extends Node
class_name NexusForge

@export var mass0: float = 1.0
@export var mass: float = 1.0
const CLIP := 1.1

func clip_grow() -> float:
    var proposed: float = mass * CLIP
    if proposed > mass0 * CLIP and mass <= mass0:
        mass = mass0 * CLIP
    else:
        mass = min(proposed, mass * CLIP)
    return mass
'''

JEEVES_GD = '''extends Node
class_name NexusJeeves

@export var organ: String = "jeeves"
var last_plan: Dictionary = {}

func load_spec(path: String = "res://data/spec.json") -> Dictionary:
    if not FileAccess.file_exists(path):
        return {}
    var file := FileAccess.open(path, FileAccess.READ)
    var parsed: Variant = JSON.parse_string(file.get_as_text())
    file.close()
    if typeof(parsed) != TYPE_DICTIONARY:
        return {}
    last_plan = parsed
    return last_plan
'''

STALKER_GD = '''extends CharacterBody2D
class_name NexusStalker

@export var speed: float = 120.0
@export var mood: String = "patrol"
var waypoint: Vector2 = Vector2.ZERO

func set_target(point: Vector2) -> void:
    waypoint = point

func _physics_process(_delta: float) -> void:
    if mood == "idle":
        velocity = Vector2.ZERO
        return
    var delta_vec := waypoint - global_position
    if delta_vec.length() < 4.0:
        velocity = Vector2.ZERO
        return
    velocity = delta_vec.normalized() * speed
    move_and_slide()
'''

DOOR_GD = '''extends Area2D
class_name NexusDoor

@export var target_room: String = "r1"
@export var locked: bool = false

signal crossed(room_id)

func _on_body_entered(body: Node) -> void:
    if locked:
        return
    if body is NexusPlayer:
        crossed.emit(target_room)
'''

WORLD_GD = '''extends Node2D
class_name NexusWorld

@export var seed: int = 8847291
@export var rooms: int = 5

func _ready() -> void:
    if has_node("/root/Jeeves"):
        get_node("/root/Jeeves").load_spec()
'''


class GodotScriptsError(ValueError):
    """Godot script pack contract violation."""


def pack(seed: int = 8847291) -> dict[str, Any]:
    kinds = ["spawn", "scavenge", "heat", "forge", "extract"]
    space = campus(seed, kinds)
    files = {
        "player.gd": PLAYER_GD,
        "heat/heat.gd": HEAT_GD,
        "extract/extract.gd": EXTRACT_GD,
        "forge/forge.gd": FORGE_GD,
        "jeeves/jeeves.gd": JEEVES_GD,
        "stalker.gd": STALKER_GD,
        "door.gd": DOOR_GD,
        "world.gd": WORLD_GD,
    }
    return {
        "kind": "godot_scripts",
        "seed": int(seed),
        "files": sorted(files),
        "n": len(files),
        "campus": space["n"],
        "width_px": space["width_px"],
        "godot_binary": 0,
        "contents": files,
        "stored_prose": 0,
    }
