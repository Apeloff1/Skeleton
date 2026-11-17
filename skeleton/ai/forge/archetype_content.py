"""Playable per-archetype Godot 4.3 content: scene, player controller, core loop.

Eight admitted playable modes get a
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
\tif bool(player.get("autopilot")):
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
\t\tplayer.set("autopilot_target", loot[0])
\t\tif player.global_position.distance_to(loot[0]) <= PICKUP_RADIUS:
\t\t\tloot.remove_at(0)
\t\t\tcarried += 1
\telse:
\t\tplayer.set("autopilot_target", extract_point)
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
\tplayer.set("autopilot_target", target["pos"])
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
\t\t\tplayer.set("autopilot_target", source)
\t\t\tif player.global_position.distance_to(source) <= RADIUS:
\t\t\t\tstage = "to_refinery"
\t\t"to_refinery":
\t\t\tplayer.set("autopilot_target", refinery)
\t\t\tif player.global_position.distance_to(refinery) <= RADIUS:
\t\t\t\tstage = "refining"
\t\t\t\trefine_timer = 0.25
\t\t"refining":
\t\t\trefine_timer -= delta
\t\t\tif refine_timer <= 0.0:
\t\t\t\tstage = "to_depot"
\t\t"to_depot":
\t\t\tplayer.set("autopilot_target", depot)
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


# Expanded modes share one HUD and one input owner. The movement controller
# remains the canonical deterministic CharacterBody2D implementation.
_EXPANDED_CONTROLLER = _CONTROLLER

# Use the existing visual grid, live progress, headless isolation and D-pad.
# Expanded interactions also need a dedicated pointer/touch USE action.
_EXPANDED_LOOP_HEADER = (
    _LOOP_HEADER
    .replace(
        '\t_add_direction(controls, "ui_right", "RIGHT", Vector2(156.0, -130.0))',
        '\t_add_direction(controls, "ui_right", "RIGHT", Vector2(156.0, -130.0))\n'
        '\t_add_direction(controls, "ui_accept", "USE", Vector2(230.0, -130.0))',
    )
    .replace(
        '["ui_up", "ui_down", "ui_left", "ui_right"]',
        '["ui_up", "ui_down", "ui_left", "ui_right", "ui_accept"]',
    )
    .replace(
        'if hud_label != null:\n\t\thud_label.text = "{instruction}\\n" + _hud_status()',
        'if not finished and hud_label != null:\n\t\thud_label.text = "{instruction}\\n" + _hud_status()',
    )
)


_PUZZLE = '''
## Spatial switch-order puzzle. Press ui_accept within a target's ring.
var switches: Array[Vector2] = [
	Vector2(180, 0), Vector2(180, 150),
	Vector2(-40, 150), Vector2(-180, -20)
]
var next_switch: int = 0
const SHOW_ACTIVE_SWITCH := true
const USE_RADIUS := 18.0

func _draw_objectives() -> void:
	for index in range(switches.size()):
		var shade := Color(0.20, 0.90, 0.58) if SHOW_ACTIVE_SWITCH and index == next_switch else Color(0.4, 0.4, 0.4)
		draw_circle(switches[index], 14.0, shade)
		draw_arc(switches[index], USE_RADIUS, 0.0, TAU, 24, shade, 2.0)

func _tick(_delta: float) -> void:
	if next_switch >= switches.size():
		_finish(true, "switches=%d" % next_switch)
		return
	var target: Vector2 = switches[next_switch]
	player.set("autopilot_target", target)
	if player.global_position.distance_to(target) <= USE_RADIUS:
		if bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
			next_switch += 1
			queue_redraw()


func _hud_status() -> String:
	return ("Switch %d/%d | Move into the bright ring and press Enter" % [next_switch, switches.size()]) if SHOW_ACTIVE_SWITCH else ("Switches remaining: %d | Discover the correct order" % (switches.size() - next_switch))
'''

_RACING = '''
## 2D checkpoint time trial. Complete three ordered laps before the clock.
var course: Array[Vector2] = [
	Vector2(210, -90), Vector2(290, 130), Vector2(40, 230),
	Vector2(-240, 110), Vector2(-180, -150)
]
const GOAL_LAPS := 3
const LAP_RADIUS := 24.0
const TIME_LIMIT := 45.0
var waypoint: int = 0
var laps: int = 0
var elapsed: float = 0.0

func _draw_objectives() -> void:
	for idx in range(course.size()):
		var end: Vector2 = course[(idx + 1) % course.size()]
		draw_line(course[idx], end, Color(0.32, 0.4, 0.7), 7.0)
		var shade := Color(0.2, 0.96, 0.35) if idx == waypoint else Color(0.86, 0.77, 0.28)
		draw_circle(course[idx], LAP_RADIUS, shade)

func _tick(delta: float) -> void:
	elapsed += delta
	if elapsed >= TIME_LIMIT:
		_finish(false, "checkpoint time limit")
		return
	player.set("autopilot_target", course[waypoint])
	if player.global_position.distance_to(course[waypoint]) <= LAP_RADIUS:
		waypoint += 1
		if waypoint >= course.size():
			waypoint = 0
			laps += 1
			if laps >= GOAL_LAPS:
				_finish(true, "laps=%d time=%.1f" % [laps, elapsed])
		queue_redraw()


func _hud_status() -> String:
	return "Lap %d/%d | Checkpoint %d/%d | Time %.1f/%.1f s" % [laps, GOAL_LAPS, waypoint + 1, course.size(), elapsed, TIME_LIMIT]
'''

_SURVIVAL = '''
## Survive thirst, scavenge essentials and reach a safe shelter.
var supplies: Array[Vector2] = [
	Vector2(160, 80), Vector2(90, 220), Vector2(-160, 180)
]
var shelter := Vector2(-220, -120)
var collected: int = 0
var hydration: float = 75.0
const DRAIN_PER_SECOND := 2.0
const PICKUP_RADIUS := 19.0

func _draw_objectives() -> void:
	for location in supplies:
		draw_circle(location, 11.0, Color(0.25, 0.72, 0.98))
	draw_circle(shelter, 21.0, Color(0.38, 0.9, 0.36))

func _tick(delta: float) -> void:
	hydration -= DRAIN_PER_SECOND * delta
	if hydration <= 0.0:
		_finish(false, "dehydrated")
		return
	if supplies.size() > 0:
		player.set("autopilot_target", supplies[0])
		if player.global_position.distance_to(supplies[0]) <= PICKUP_RADIUS:
			if bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
				supplies.remove_at(0)
				collected += 1
				hydration = min(100.0, hydration + 12.0)
				queue_redraw()
	else:
		player.set("autopilot_target", shelter)
		if player.global_position.distance_to(shelter) <= PICKUP_RADIUS:
			_finish(true, "supplies=%d hydration=%d" % [collected, int(hydration)])


func _hud_status() -> String:
	return "Supplies %d/3 | Hydration %d | Press Enter to gather" % [collected, int(hydration)]
'''

_STEALTH = '''
## Recover intel and reach extraction without crossing guard vision radii.
var patrols: Array[Vector2] = [
	Vector2(90, -120), Vector2(260, -80),
	Vector2(40, 320), Vector2(-240, 170)
]
var objectives: Array[Vector2] = [
	Vector2(160, 20), Vector2(260, 170), Vector2(-20, 200)
]
var exit_point := Vector2(-180, 50)
var intel: int = 0
const DETECTION_RADIUS := 64.0
const SHOW_GUARD_ZONES := true
const USE_RADIUS := 18.0

func _draw_objectives() -> void:
	for guard in patrols:
		if SHOW_GUARD_ZONES:
			draw_circle(guard, DETECTION_RADIUS, Color(0.9, 0.22, 0.24, 0.16))
		draw_circle(guard, 9.0, Color(0.96, 0.26, 0.24))
	for intel_point in objectives:
		draw_circle(intel_point, 11.0, Color(0.25, 0.82, 0.98))
	draw_circle(exit_point, 20.0, Color(0.25, 0.88, 0.32))

func _tick(_delta: float) -> void:
	for guard in patrols:
		if player.global_position.distance_to(guard) < DETECTION_RADIUS:
			_finish(false, "spotted by patrol")
			return
	if objectives.size() > 0:
		player.set("autopilot_target", objectives[0])
		if player.global_position.distance_to(objectives[0]) <= USE_RADIUS:
			if bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
				objectives.remove_at(0)
				intel += 1
				queue_redraw()
	else:
		player.set("autopilot_target", exit_point)
		if player.global_position.distance_to(exit_point) <= USE_RADIUS:
			_finish(true, "intel=%d undetected" % intel)


func _hud_status() -> String:
	return "Intel %d/3 | Avoid red guard zones | Press Enter to retrieve" % [intel]
'''

_CRAFTING = '''
## Collect mineral parts, assemble them at a workshop, deliver the item.
var materials: Array[Vector2] = [
	Vector2(160, -80), Vector2(240, 170), Vector2(-80, 210)
]
var workshop := Vector2(-170, 130)
var delivery := Vector2(-180, -140)
var collected: int = 0
var crafted: bool = false
const USE_RADIUS := 19.0

func _draw_objectives() -> void:
	for deposit in materials:
		draw_circle(deposit, 11.0, Color(0.48, 0.79, 0.99))
	draw_circle(workshop, 22.0, Color(0.98, 0.68, 0.27))
	draw_circle(delivery, 23.0, Color(0.33, 0.9, 0.48))

func _tick(_delta: float) -> void:
	if materials.size() > 0:
		player.set("autopilot_target", materials[0])
		if player.global_position.distance_to(materials[0]) <= USE_RADIUS:
			if bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
				materials.remove_at(0)
				collected += 1
				queue_redraw()
	elif not crafted:
		player.set("autopilot_target", workshop)
		if player.global_position.distance_to(workshop) <= USE_RADIUS:
			if bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
				crafted = collected == 3
				if not crafted:
					_finish(false, "missing crafting materials")
	else:
		player.set("autopilot_target", delivery)
		if player.global_position.distance_to(delivery) <= USE_RADIUS:
			_finish(true, "crafted item delivered from %d materials" % collected)


func _hud_status() -> String:
	return "Materials %d/3 | Crafted %s | Press Enter to work" % [collected, "yes" if crafted else "no"]
'''

# Historical extra modes use their original interaction-aware controller
# and native loop templates, while the three newer portal/HUD slices above
# keep their exact source and established mechanical mapping.
_EXPANDED_SPECS: Dict[str, Tuple[str, float, int]] = {
    "puzzle": (_PUZZLE, 300.0, 1800),
    "racing": (_RACING, 420.0, 3600),
    "survival": (_SURVIVAL, 280.0, 3600),
    "stealth": (_STEALTH, 250.0, 3600),
    "crafting": (_CRAFTING, 320.0, 3600),
}


def content_archetypes() -> Tuple[str, ...]:
    return tuple(sorted(set(_SPECS) | set(_EXPANDED_SPECS)))


def _expanded_files(name: str, axes: Mapping[str, float]) -> Dict[str, str]:
    from skeleton.forge.playable_tuning import SOURCE_PATH, compile_playable_tuning, tuning_source

    body, speed, max_frames = _EXPANDED_SPECS[name]
    fmt = {"name": name, "version": ARCHETYPE_CONTENT_VERSION}
    title = "".join(part.capitalize() for part in name.split("_")) + "Main"
    player = _EXPANDED_CONTROLLER.format(speed=speed, **fmt)
    loop = _EXPANDED_LOOP_HEADER.format(
        max_frames=max_frames, complete=COMPLETE_MARKER, failed=FAILED_MARKER,
        instruction=name.capitalize() + " | arrows or touch to move | Enter or USE to interact", **fmt
    ) + body
    player, loop, receipt = compile_playable_tuning(name, axes or None, speed=speed, player=player, loop=loop)
    emitted = {
        f"scenes/archetypes/{name}/main.tscn": _SCENE.format(name=name, title=title),
        f"scripts/archetypes/{name}/player_controller.gd": player,
        f"scripts/archetypes/{name}/core_loop.gd": loop,
    }
    if receipt is not None:
        emitted[SOURCE_PATH] = tuning_source(receipt)
    return emitted



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
    tuning: Optional[Mapping[str, float]] = None,
) -> Dict[str, str]:
    """Compile one of eight original gameplay loops and its sparse native edits.

    The historical tuning keyword is admitted solely as a compatibility alias.
    Callers cannot combine it with the authoritative operator_axes input, and
    no user-provided source, path, expression or arbitrary GDScript is executed.
    Every nonempty tuning now emits one exact source-bound receipt.
    """
    if type(name) is not str or name not in content_archetypes():
        raise KeyError("unsupported original playable archetype")
    if operator_axes is not None and tuning is not None:
        raise ValueError("conflicting playable tuning authorities")
    axes = _admit_axes(tuning if tuning is not None else operator_axes)
    if name in _EXPANDED_SPECS:
        return _expanded_files(name, axes)

    from skeleton.forge.playable_tuning import (
        SOURCE_PATH, compile_playable_tuning, tuning_source,
    )
    body, speed, max_frames = _SPECS[name]
    fmt = {"name": name, "version": ARCHETYPE_CONTENT_VERSION}
    title = "".join(part.capitalize() for part in name.split("_")) + "Main"
    player = _CONTROLLER.format(speed=speed, **fmt)
    loop = _LOOP_HEADER.format(
        max_frames=max_frames, complete=COMPLETE_MARKER, failed=FAILED_MARKER,
        instruction=_INSTRUCTIONS[name], **fmt,
    ) + body
    player, loop, receipt = compile_playable_tuning(
        name, axes or None, speed=speed, player=player, loop=loop,
    )
    result = {
        f"scenes/archetypes/{name}/main.tscn": _SCENE.format(
            name=name, title=title,
        ),
        f"scripts/archetypes/{name}/player_controller.gd": player,
        f"scripts/archetypes/{name}/core_loop.gd": loop,
    }
    if receipt is not None:
        result[SOURCE_PATH] = tuning_source(receipt)
    return result

def verify_archetype_content(
    files: Mapping[str, str], name: str, *,
    operator_axes: Optional[Mapping[str, float]] = None,
    tuning: Optional[Mapping[str, float]] = None,
) -> bool:
    """Source-verification after all independent Godot/quest file writers."""
    return isinstance(files, Mapping) and all(
        files.get(path) == body
        for path, body in archetype_files(
            name, operator_axes=operator_axes, tuning=tuning,
        ).items()
    )


def attach_archetype_content(
    files: Mapping[str, str], name: str, *,
    operator_axes: Optional[Mapping[str, float]] = None,
    tuning: Optional[Mapping[str, float]] = None,
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
    key = name if name in content_archetypes() else "extraction"
    out = dict(files)
    for path, body in archetype_files(
        key, operator_axes=operator_axes, tuning=tuning,
    ).items():
        if path in out and out[path] != body:
            raise ValueError("playable archetype output collides with existing source: " + path)
        out[path] = body
    return out
