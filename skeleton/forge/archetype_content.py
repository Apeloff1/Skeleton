"""Playable per-archetype Godot 4.3 content: scene, player controller, core loop.

Every forge archetype (``extraction``, ``combat_loop``, ``pipeline``) gets a
self-contained playable slice layered onto the emitted project:

- ``scenes/archetypes/<name>/main.tscn`` — playable scene (player + loop);
- ``scripts/archetypes/<name>/player_controller.gd`` — CharacterBody2D
  controller (keyboard via built-in ``ui_*`` actions, autopilot for headless);
- ``scripts/archetypes/<name>/core_loop.gd`` — the archetype's core loop with
  explicit win/lose state.

Headless boots (CI, playtest) run the loop on autopilot and print
``ARCHETYPE_LOOP_COMPLETE <name>`` then quit 0, or ``ARCHETYPE_LOOP_FAILED``
and quit 1 when the frame budget expires — so an E2E test can prove the loop
is actually completable in the real engine, not just statically valid.
Content is additive: no emitted file is overwritten.
"""
from __future__ import annotations

from typing import Dict, Mapping, Tuple

ARCHETYPE_CONTENT_VERSION = 1
COMPLETE_MARKER = "ARCHETYPE_LOOP_COMPLETE"
FAILED_MARKER = "ARCHETYPE_LOOP_FAILED"

_CONTROLLER = '''extends CharacterBody2D
## {name} player controller (Skeleton archetype content v{version}).

@export var speed: float = {speed}
var autopilot: bool = false
var autopilot_target: Vector2 = Vector2.ZERO


func _ready() -> void:
\tautopilot = DisplayServer.get_name() == "headless" or OS.get_cmdline_user_args().has("--autoplay")


func _physics_process(_delta: float) -> void:
\tvar direction := Vector2.ZERO
\tif autopilot:
\t\tvar offset := autopilot_target - global_position
\t\tif offset.length() > 4.0:
\t\t\tdirection = offset.normalized()
\telse:
\t\tdirection = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
\tvelocity = direction * speed
\tmove_and_slide()
'''

_LOOP_HEADER = '''extends Node2D
## {name} core loop (Skeleton archetype content v{version}).

signal loop_completed(archetype: String)
signal loop_failed(archetype: String, reason: String)

const ARCHETYPE := "{name}"
const MAX_FRAMES := {max_frames}
var frames: int = 0
var finished: bool = false
@onready var player: CharacterBody2D = $Player


func _finish(ok: bool, reason: String) -> void:
\tif finished:
\t\treturn
\tfinished = true
\tif ok:
\t\tprint("{complete} ", ARCHETYPE, " ", reason)
\t\tloop_completed.emit(ARCHETYPE)
\telse:
\t\tprint("{failed} ", ARCHETYPE, " ", reason)
\t\tloop_failed.emit(ARCHETYPE, reason)
\tif player.autopilot:
\t\tget_tree().quit(0 if ok else 1)


func _physics_process(delta: float) -> void:
\tif finished:
\t\treturn
\tframes += 1
\tif frames > MAX_FRAMES:
\t\t_finish(false, "frame budget exhausted")
\t\treturn
\t_tick(delta)
'''

_EXTRACTION = '''
## Extraction: grab every loot cache, keep heat below the limit, reach extract.
var loot: Array[Vector2] = [Vector2(220, 0), Vector2(220, 180), Vector2(0, 180)]
var extract_point := Vector2(-160, 60)
var carried: int = 0
var heat: float = 0.0
const HEAT_LIMIT := 100.0
const HEAT_PER_SECOND := 6.0
const PICKUP_RADIUS := 12.0


func _tick(delta: float) -> void:
\theat += HEAT_PER_SECOND * delta
\tif heat >= HEAT_LIMIT:
\t\t_finish(false, "heat critical")
\t\treturn
\tif loot.size() > 0:
\t\tplayer.autopilot_target = loot[0]
\t\tif player.global_position.distance_to(loot[0]) <= PICKUP_RADIUS:
\t\t\tloot.remove_at(0)
\t\t\tcarried += 1
\telse:
\t\tplayer.autopilot_target = extract_point
\t\tif player.global_position.distance_to(extract_point) <= PICKUP_RADIUS:
\t\t\t_finish(true, "extracted loot=%d heat=%d" % [carried, int(heat)])
'''

_COMBAT = '''
## Combat loop: survive and clear three escalating waves.
const WAVES := 3
const ATTACK_RANGE := 24.0
const ATTACK_DAMAGE := 5
var wave: int = 0
var enemies: Array[Dictionary] = []
var player_hp: int = 100
var kills: int = 0


func _spawn_wave() -> void:
\twave += 1
\tfor i in range(wave + 1):
\t\tvar angle := TAU * float(i) / float(wave + 1)
\t\tenemies.append({"pos": Vector2(cos(angle), sin(angle)) * 160.0, "hp": 5 * wave})


func _tick(_delta: float) -> void:
\tif enemies.is_empty():
\t\tif wave >= WAVES:
\t\t\t_finish(true, "waves=%d kills=%d hp=%d" % [wave, kills, player_hp])
\t\t\treturn
\t\t_spawn_wave()
\tvar target: Dictionary = enemies[0]
\tplayer.autopilot_target = target["pos"]
\tfor enemy in enemies:
\t\tenemy["pos"] = enemy["pos"].move_toward(player.global_position, 0.5)
\t\tif enemy["pos"].distance_to(player.global_position) < 8.0 and frames % 30 == 0:
\t\t\tplayer_hp -= 1
\tif player_hp <= 0:
\t\t_finish(false, "player down")
\t\treturn
\tif target["pos"].distance_to(player.global_position) <= ATTACK_RANGE and frames % 6 == 0:
\t\ttarget["hp"] -= ATTACK_DAMAGE
\t\tif target["hp"] <= 0:
\t\t\tenemies.remove_at(0)
\t\t\tkills += 1
'''

_PIPELINE = '''
## Pipeline: haul raw ore source -> refinery -> depot until the quota ships.
const QUOTA := 4
const RADIUS := 12.0
var source := Vector2(200, -80)
var refinery := Vector2(0, 120)
var depot := Vector2(-200, -80)
var stage: String = "to_source"
var shipped: int = 0
var refine_timer: float = 0.0


func _tick(delta: float) -> void:
\tmatch stage:
\t\t"to_source":
\t\t\tplayer.autopilot_target = source
\t\t\tif player.global_position.distance_to(source) <= RADIUS:
\t\t\t\tstage = "to_refinery"
\t\t"to_refinery":
\t\t\tplayer.autopilot_target = refinery
\t\t\tif player.global_position.distance_to(refinery) <= RADIUS:
\t\t\t\tstage = "refining"
\t\t\t\trefine_timer = 0.25
\t\t"refining":
\t\t\trefine_timer -= delta
\t\t\tif refine_timer <= 0.0:
\t\t\t\tstage = "to_depot"
\t\t"to_depot":
\t\t\tplayer.autopilot_target = depot
\t\t\tif player.global_position.distance_to(depot) <= RADIUS:
\t\t\t\tshipped += 1
\t\t\t\tstage = "to_source"
\tif shipped >= QUOTA:
\t\t_finish(true, "shipped=%d" % shipped)
'''

_SCENE = '''[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://scripts/archetypes/{name}/core_loop.gd" id="1_loop"]
[ext_resource type="Script" path="res://scripts/archetypes/{name}/player_controller.gd" id="2_player"]

[sub_resource type="CircleShape2D" id="CircleShape2D_player"]
radius = 6.0

[node name="{title}" type="Node2D"]
script = ExtResource("1_loop")

[node name="Player" type="CharacterBody2D" parent="."]
motion_mode = 1
script = ExtResource("2_player")

[node name="Shape" type="CollisionShape2D" parent="Player"]
shape = SubResource("CircleShape2D_player")

[node name="Camera" type="Camera2D" parent="Player"]
'''

# name -> (loop body, controller speed, frame budget)
_SPECS: Dict[str, Tuple[str, float, int]] = {
    "extraction": (_EXTRACTION, 260.0, 1800),
    "combat_loop": (_COMBAT, 240.0, 3600),
    "pipeline": (_PIPELINE, 320.0, 3600),
}


def content_archetypes() -> Tuple[str, ...]:
    return tuple(sorted(_SPECS))


def archetype_files(name: str) -> Dict[str, str]:
    """Return the playable file set for ``name`` (raises KeyError if unknown)."""
    if type(name) is not str or name not in _SPECS:
        raise KeyError("unsupported original playable archetype")
    body, speed, max_frames = _SPECS[name]
    fmt = {"name": name, "version": ARCHETYPE_CONTENT_VERSION}
    title = "".join(part.capitalize() for part in name.split("_")) + "Main"
    return {
        f"scenes/archetypes/{name}/main.tscn": _SCENE.format(name=name, title=title),
        f"scripts/archetypes/{name}/player_controller.gd": _CONTROLLER.format(speed=speed, **fmt),
        f"scripts/archetypes/{name}/core_loop.gd": _LOOP_HEADER.format(
            max_frames=max_frames, complete=COMPLETE_MARKER, failed=FAILED_MARKER, **fmt
        ) + body,
    }


def attach_archetype_content(files: Mapping[str, str], name: str) -> Dict[str, str]:
    """Layer ``name``'s playable slice onto an emitted project (additive only).

    Unknown archetypes (e.g. composed ``auto``/``vision`` blueprints) fall back
    to the canonical ``extraction`` slice so every forged game stays playable.
    """
    if type(name) is not str or len(name) > 128 or not isinstance(files, Mapping):
        raise ValueError("invalid bounded project source or archetype")
    if len(files) > 4096:
        raise ValueError("playable project input file budget exceeded")
    if any(type(path) is not str or type(body) is not str or len(body) > 4*1024*1024
           for path, body in files.items()):
        raise ValueError("playable project file identity or source is invalid")
    key = name if name in _SPECS else "extraction"
    out = dict(files)
    for path, body in archetype_files(key).items():
        if path in out and out[path] != body:
            raise ValueError("playable archetype output collides with existing source: " + path)
        out[path] = body
    return out
