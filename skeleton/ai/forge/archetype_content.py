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

import math
from typing import Dict, Mapping, Optional, Tuple

from skeleton.context.tensor import AXES

ARCHETYPE_CONTENT_VERSION = 3
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
const FLOOR := Color(0.055, 0.075, 0.12, 1.0)
const GRID := Color(0.11, 0.15, 0.22, 1.0)
const PLAYER_COLOR := Color(0.24, 0.85, 0.96, 1.0)
const TARGET_COLOR := Color(0.96, 0.77, 0.23, 1.0)
const GOAL_COLOR := Color(0.34, 0.94, 0.58, 1.0)

var frames: int = 0
var finished: bool = false
var hud_label: Label = null
@onready var player: CharacterBody2D = $Player


func _ready() -> void:
\t# Build an offline-only accessible HUD and pointer/touch D-pad. On headless
\t# Godot qualification the same loop runs without UI or device assumptions.
\tif DisplayServer.get_name() == "headless":
\t\treturn
\tvar overlay := CanvasLayer.new()
\toverlay.name = "ForgeGameplayHUD"
\toverlay.layer = 12
\tadd_child(overlay)
\thud_label = Label.new()
\thud_label.name = "Objectives"
\thud_label.position = Vector2(20.0, 20.0)
\thud_label.add_theme_font_size_override("font_size", 20)
\thud_label.add_theme_color_override("font_color", Color(0.94, 0.97, 1.0))
\thud_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
\thud_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
\thud_label.size = Vector2(maxf(180.0, minf(get_viewport_rect().size.x - 40.0, 660.0)), 110.0)
\toverlay.add_child(hud_label)
\thud_label.text = "{instruction}\\nArrow keys or touch controls to move"
\tvar controls := Control.new()
\tcontrols.name = "TouchControls"
\toverlay.add_child(controls)
\tcontrols.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
\tcontrols.mouse_filter = Control.MOUSE_FILTER_IGNORE
\t_add_direction(controls, "ui_up", "UP", Vector2(90.0, -196.0))
\t_add_direction(controls, "ui_left", "LEFT", Vector2(24.0, -130.0))
\t_add_direction(controls, "ui_down", "DOWN", Vector2(90.0, -130.0))
\t_add_direction(controls, "ui_right", "RIGHT", Vector2(156.0, -130.0))


func _add_direction(controls: Control, action: String, caption: String, offset: Vector2) -> void:
\tvar button := Button.new()
\tbutton.name = "Move" + caption
\tbutton.text = caption
\tbutton.focus_mode = Control.FOCUS_NONE
\tcontrols.add_child(button)
\tbutton.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
\tbutton.offset_left = offset.x
\tbutton.offset_top = offset.y
\tbutton.offset_right = offset.x + 60.0
\tbutton.offset_bottom = offset.y + 60.0
\tbutton.button_down.connect(_press_action.bind(action))
\tbutton.button_up.connect(_release_action.bind(action))


func _press_action(action: String) -> void:
\tInput.action_press(action)


func _release_action(action: String) -> void:
\tInput.action_release(action)


func _exit_tree() -> void:
\tfor action in ["ui_up", "ui_down", "ui_left", "ui_right"]:
\t\tInput.action_release(action)


func _draw() -> void:
\tdraw_rect(Rect2(Vector2(-960.0, -720.0), Vector2(1920.0, 1440.0)), FLOOR)
\tfor i in range(-12, 13):
\t\tdraw_line(Vector2(float(i) * 80.0, -720.0), Vector2(float(i) * 80.0, 720.0), GRID, 1.0)
\tfor j in range(-9, 10):
\t\tdraw_line(Vector2(-960.0, float(j) * 80.0), Vector2(960.0, float(j) * 80.0), GRID, 1.0)
\t_draw_objectives()
\tdraw_circle(player.global_position, 12.0, PLAYER_COLOR)
\tdraw_arc(player.global_position, 16.0, 0.0, TAU, 32, Color(0.0, 0.18, 0.25), 2.0)


func _finish(ok: bool, reason: String) -> void:
\tif finished:
\t\treturn
\tfinished = true
\tif hud_label != null:
\t\thud_label.text = ("COMPLETED: " if ok else "FAILED: ") + reason + "\\nReturn to Forge world using the top button"
\tqueue_redraw()
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
\tqueue_redraw()
\tif hud_label != null:
\t\thud_label.text = "{instruction}\\n" + _hud_status()
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


func _hud_status() -> String:
\treturn "Caches: %d/3 | Heat: %d%% | Reach green extraction" % [carried, int(heat)]


func _draw_objectives() -> void:
\tfor cache in loot:
\t\tdraw_rect(Rect2(cache - Vector2(11.0, 11.0), Vector2(22.0, 22.0)), TARGET_COLOR)
\t\tdraw_circle(cache, 17.0, Color(0.9, 0.61, 0.11, 0.35))
\tdraw_circle(extract_point, 25.0, GOAL_COLOR)
\tdraw_circle(extract_point, 15.0, FLOOR)
'''

_COMBAT = '''
## Combat loop: survive and clear three escalating waves.
const WAVES := 3
const ATTACK_RANGE := 24.0
const ATTACK_DAMAGE := 5
const CONTACT_DAMAGE := 1
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
\t\t\tplayer_hp -= CONTACT_DAMAGE
\tif player_hp <= 0:
\t\t_finish(false, "player down")
\t\treturn
\tif target["pos"].distance_to(player.global_position) <= ATTACK_RANGE and frames % 6 == 0:
\t\ttarget["hp"] -= ATTACK_DAMAGE
\t\tif target["hp"] <= 0:
\t\t\tenemies.remove_at(0)
\t\t\tkills += 1


func _hud_status() -> String:
\treturn "Wave: %d/%d | Enemies: %d | HP: %d | Kills: %d" % [wave, WAVES, enemies.size(), player_hp, kills]


func _draw_objectives() -> void:
\tfor enemy in enemies:
\t\tvar pos: Vector2 = enemy["pos"]
\t\tdraw_circle(pos, 12.0, Color(0.96, 0.32, 0.37))
\t\tdraw_arc(pos, 17.0, 0.0, TAU, 24, TARGET_COLOR, 2.0)
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


func _hud_status() -> String:
\treturn "Shipments: %d/%d | Step: %s | Yellow source / blue refinery / green depot" % [shipped, QUOTA, stage]


func _draw_objectives() -> void:
\tdraw_rect(Rect2(source - Vector2(18.0, 18.0), Vector2(36.0, 36.0)), TARGET_COLOR)
\tdraw_circle(refinery, 22.0, Color(0.32, 0.61, 1.0))
\tdraw_circle(depot, 22.0, GOAL_COLOR)
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

_INSTRUCTIONS = {
    "extraction": "Collect three golden caches, then reach the green extraction point",
    "combat_loop": "Clear three enemy waves by approaching red targets",
    "pipeline": "Ship four loads through the source, refinery and depot",
}

# name -> (loop body, controller speed, frame budget)
_SPECS: Dict[str, Tuple[str, float, int]] = {
    "extraction": (_EXTRACTION, 260.0, 1800),
    "combat_loop": (_COMBAT, 240.0, 3600),
    "pipeline": (_PIPELINE, 320.0, 3600),
}


def content_archetypes() -> Tuple[str, ...]:
    return tuple(sorted(_SPECS))


def _admit_axes(raw: Optional[Mapping[str, float]]) -> Dict[str, float]:
    """No implicit defaults: only *explicit* operator overrides change loops."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or len(raw) > len(AXES):
        raise ValueError("playable mechanics require at most ten creator axes")
    for axis, value in raw.items():
        if type(axis) is not str or axis not in AXES:
            raise ValueError("unknown playable creator axis")
        if type(value) not in (float, int) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("playable creator axes must be finite unit-interval values")
    return {axis: float(raw[axis]) for axis in AXES if axis in raw}


def _swap_constant(script: str, before: str, after: str) -> str:
    """Fail when canonical generated script templates change unexpectedly."""
    if script.count(before) != 1:
        raise RuntimeError("playable tuning template drift: " + before[:100])
    return script.replace(before, after)


def _number(value: float) -> str:
    return f"{value:.2f}"


def archetype_files(
    name: str, *, operator_axes: Optional[Mapping[str, float]] = None,
) -> Dict[str, str]:
    """Deterministic Godot playable slice with optional *mechanical* knobs.

    Tempo controls movement in all three archetypes. Risk adjusts extraction
    heat and the pipeline time budget; lethality changes combat contact damage;
    scarcity changes extraction heat budget; agency changes interaction range;
    grind controls combat wave count and pipeline delivery quota. Remaining
    creative-only axes stay in the tensor/blueprint, never falsely advertised
    as live native gameplay settings.
    """
    if type(name) is not str or name not in _SPECS:
        raise KeyError("unsupported original playable archetype")
    axes = _admit_axes(operator_axes)
    body, speed, max_frames = _SPECS[name]
    if "tempo" in axes:
        speed = round(speed * (0.75 + 0.5 * axes["tempo"]), 2)
    if name == "extraction":
        if "risk" in axes:
            body = _swap_constant(
                body, "const HEAT_PER_SECOND := 6.0",
                "const HEAT_PER_SECOND := " + _number(3.0 + 7.0 * axes["risk"]),
            )
        if "scarcity" in axes:
            body = _swap_constant(
                body, "const HEAT_LIMIT := 100.0",
                "const HEAT_LIMIT := " + _number(120.0 - 50.0 * axes["scarcity"]),
            )
        if "agency" in axes:
            body = _swap_constant(
                body, "const PICKUP_RADIUS := 12.0",
                "const PICKUP_RADIUS := " + _number(8.0 + 12.0 * axes["agency"]),
            )
    elif name == "combat_loop":
        if "lethality" in axes:
            body = _swap_constant(
                body, "const CONTACT_DAMAGE := 1",
                "const CONTACT_DAMAGE := " + str(1 + int(4.0 * axes["lethality"] + 0.5)),
            )
        if "grind" in axes:
            body = _swap_constant(
                body, "const WAVES := 3",
                "const WAVES := " + str(2 + int(3.0 * axes["grind"] + 0.5)),
            )
        if "agency" in axes:
            body = _swap_constant(
                body, "const ATTACK_RANGE := 24.0",
                "const ATTACK_RANGE := " + _number(16.0 + 24.0 * axes["agency"]),
            )
    elif name == "pipeline":
        if "grind" in axes:
            body = _swap_constant(
                body, "const QUOTA := 4",
                "const QUOTA := " + str(2 + int(6.0 * axes["grind"] + 0.5)),
            )
        if "agency" in axes:
            body = _swap_constant(
                body, "const RADIUS := 12.0",
                "const RADIUS := " + _number(8.0 + 12.0 * axes["agency"]),
            )
        if "risk" in axes:
            # High risk shortens the completion window but never removes
            # enough time for a low-end machine to finish the 4-load demo.
            max_frames = round(max_frames * (1.5 - 0.5 * axes["risk"]))

    fmt = {"name": name, "version": ARCHETYPE_CONTENT_VERSION}
    title = "".join(part.capitalize() for part in name.split("_")) + "Main"
    return {
        f"scenes/archetypes/{name}/main.tscn": _SCENE.format(name=name, title=title),
        f"scripts/archetypes/{name}/player_controller.gd": _CONTROLLER.format(speed=speed, **fmt),
        f"scripts/archetypes/{name}/core_loop.gd": _LOOP_HEADER.format(
            max_frames=max_frames, complete=COMPLETE_MARKER, failed=FAILED_MARKER,
            instruction=_INSTRUCTIONS[name], **fmt
        ) + body,
    }


def verify_archetype_content(
    files: Mapping[str, str], name: str, *, operator_axes: Optional[Mapping[str, float]] = None,
) -> bool:
    """Source-verification after all independent Godot/quest file writers."""
    return isinstance(files, Mapping) and all(
        files.get(path) == body
        for path, body in archetype_files(name, operator_axes=operator_axes).items()
    )


def attach_archetype_content(
    files: Mapping[str, str], name: str, *,
    operator_axes: Optional[Mapping[str, float]] = None,
) -> Dict[str, str]:
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
    for path, body in archetype_files(key, operator_axes=operator_axes).items():
        if path in out and out[path] != body:
            raise ValueError("playable archetype output collides with existing source: " + path)
        out[path] = body
    return out
