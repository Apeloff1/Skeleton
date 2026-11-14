"""Playable per-archetype Godot 4.3 content: scene, player controller, core loop.

Eight original, self-contained 2D mini-games ship as authored source
(``combat_loop``, ``crafting``, ``extraction``, ``pipeline``, ``puzzle``,
``racing``, ``stealth``, ``survival``). Each one is layered onto the emitted
project as:

- ``scenes/archetypes/<name>/main.tscn`` — playable scene (player + loop);
- ``scripts/archetypes/<name>/player_controller.gd`` — CharacterBody2D
  controller (keyboard via built-in ``ui_*`` actions, touchscreen D-pad,
  autopilot for headless);
- ``scripts/archetypes/<name>/core_loop.gd`` — the archetype's core loop with
  explicit win/lose state, an accessible HUD and a pointer D-pad.

Headless boots (CI, playtest) run the loop on autopilot and print
``ARCHETYPE_LOOP_COMPLETE <name>`` then quit 0, or ``ARCHETYPE_LOOP_FAILED``
and quit 1 when the frame budget expires — so an E2E test can prove the loop
is actually completable in the real engine, not just statically valid.
Content is additive: no emitted file is overwritten.

Two bounded knob contracts exist and are mutually exclusive per call:

- ``operator_axes`` — the creator-axes mechanics v3 contract (tempo, risk,
  scarcity, lethality, grind, agency on the original three loops);
- ``tuning`` — the sparse cockpit contract in
  :mod:`skeleton.forge.playable_tuning`, which writes an auditable
  ``data/playable_tuning.json`` receipt and covers all eight loops.

The 158-genre catalog is a design vocabulary; only these eight are playable.
"""
from __future__ import annotations

import math
from typing import Dict, Mapping, Optional, Tuple

from skeleton.context.tensor import AXES

ARCHETYPE_CONTENT_VERSION = 4
COMPLETE_MARKER = "ARCHETYPE_LOOP_COMPLETE"
FAILED_MARKER = "ARCHETYPE_LOOP_FAILED"

_CONTROLLER = '''extends CharacterBody2D
## {name} player controller (Skeleton archetype content v{version}).

@export var speed: float = {speed}
var autopilot: bool = false
var autopilot_target: Vector2 = Vector2.ZERO
var _touch_controls: Array[Button] = []


func _ready() -> void:
\tautopilot = DisplayServer.get_name() == "headless" or OS.get_cmdline_user_args().has("--autoplay")
\tif not autopilot and DisplayServer.is_touchscreen_available():
\t\t_install_touch_controls()


func _install_touch_controls() -> void:
\tvar layer := CanvasLayer.new()
\tlayer.layer = 8
\tadd_child(layer)
\tvar panel := Control.new()
\tpanel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
\tpanel.mouse_filter = Control.MOUSE_FILTER_PASS
\tlayer.add_child(panel)
\t_touch_controls.append(_make_touch_button(panel, "UP", "ui_up"))
\t_touch_controls.append(_make_touch_button(panel, "LEFT", "ui_left"))
\t_touch_controls.append(_make_touch_button(panel, "DOWN", "ui_down"))
\t_touch_controls.append(_make_touch_button(panel, "RIGHT", "ui_right"))
\t_touch_controls.append(_make_touch_button(panel, "USE", "ui_accept"))
\t_layout_touch_controls()
\tget_viewport().size_changed.connect(_layout_touch_controls)


func _make_touch_button(panel: Control, title: String, action: String) -> Button:
\tvar button := Button.new()
\tbutton.text = title
\tbutton.focus_mode = Control.FOCUS_NONE
\tbutton.custom_minimum_size = Vector2(64, 64)
\tbutton.size = Vector2(64, 64)
\tbutton.modulate = Color(1.0, 1.0, 1.0, 0.75)
\tbutton.button_down.connect(_set_touch_action.bind(action, true))
\tbutton.button_up.connect(_set_touch_action.bind(action, false))
\tpanel.add_child(button)
\treturn button


func _layout_touch_controls() -> void:
\tif _touch_controls.size() != 5:
\t\treturn
\tvar viewport_size := get_viewport().get_visible_rect().size
\tvar bottom := maxf(165.0, viewport_size.y - 86.0)
\t_touch_controls[0].position = Vector2(90, bottom - 72.0)
\t_touch_controls[1].position = Vector2(22, bottom)
\t_touch_controls[2].position = Vector2(90, bottom)
\t_touch_controls[3].position = Vector2(158, bottom)
\t_touch_controls[4].position = Vector2(maxf(250.0, viewport_size.x - 94.0), bottom)


func _set_touch_action(action: String, pressed: bool) -> void:
\tif pressed:
\t\tInput.action_press(action)
\telse:
\t\tInput.action_release(action)


func _exit_tree() -> void:
\tfor action in ["ui_up", "ui_left", "ui_down", "ui_right", "ui_accept"]:
\t\tInput.action_release(action)


func _draw() -> void:
\tdraw_circle(Vector2.ZERO, 9.0, Color(0.95, 0.85, 0.35))
\tdraw_arc(Vector2.ZERO, 11.0, 0.0, TAU, 20, Color(0.25, 0.45, 0.95), 2.0)


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
var _status: Label = null
@onready var player: CharacterBody2D = $Player


func _ready() -> void:
\t# Build an offline-only accessible HUD. On headless Godot qualification
\t# the same loop runs on autopilot without UI or device assumptions.
\tif DisplayServer.get_name() == "headless":
\t\treturn
\tvar overlay := CanvasLayer.new()
\toverlay.name = "ForgeGameplayHUD"
\toverlay.layer = 12
\tadd_child(overlay)
\t_status = Label.new()
\t_status.name = "Objectives"
\t_status.position = Vector2(20.0, 20.0)
\t_status.add_theme_font_size_override("font_size", 20)
\t_status.add_theme_color_override("font_color", Color(0.94, 0.97, 1.0))
\t_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
\t_status.mouse_filter = Control.MOUSE_FILTER_IGNORE
\t_status.size = Vector2(maxf(180.0, minf(get_viewport_rect().size.x - 40.0, 660.0)), 110.0)
\toverlay.add_child(_status)
\t_status.text = "{instruction}\\n" + _hud_status()
\t# Touchscreens get the player controller's D-pad (with USE); pointer-only
\t# devices get this one, so a single device never shows two pads.
\tif DisplayServer.is_touchscreen_available():
\t\treturn
\tvar controls := Control.new()
\tcontrols.name = "TouchControls"
\toverlay.add_child(controls)
\tcontrols.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
\tcontrols.mouse_filter = Control.MOUSE_FILTER_IGNORE
\t_add_direction(controls, "ui_up", "UP", Vector2(90.0, -196.0))
\t_add_direction(controls, "ui_left", "LEFT", Vector2(24.0, -130.0))
\t_add_direction(controls, "ui_down", "DOWN", Vector2(90.0, -130.0))
\t_add_direction(controls, "ui_right", "RIGHT", Vector2(156.0, -130.0))
\t_add_direction(controls, "ui_accept", "USE", Vector2(240.0, -130.0))


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
\tfor action in ["ui_up", "ui_down", "ui_left", "ui_right", "ui_accept"]:
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


func _hud_status() -> String:
\treturn _objective_text() + " | arrows: move | Enter: interact"


func _finish(ok: bool, reason: String) -> void:
\tif finished:
\t\treturn
\tfinished = true
\tif is_instance_valid(_status):
\t\t_status.text = ("COMPLETED: " if ok else "FAILED: ") + reason
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
\tif not finished and is_instance_valid(_status):
\t\t_status.text = "{instruction}\\n" + _hud_status()
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


func _draw_objectives() -> void:
\tfor location in loot:
\t\tdraw_circle(location, 12.0, Color(0.3, 0.8, 1.0))
\tdraw_circle(extract_point, 20.0, Color(0.25, 0.92, 0.45))


func _tick(delta: float) -> void:
\theat += HEAT_PER_SECOND * delta
\tif heat >= HEAT_LIMIT:
\t\t_finish(false, "heat critical")
\t\treturn
\tif loot.size() > 0:
\t\tplayer.set("autopilot_target", loot[0])
\t\tif player.global_position.distance_to(loot[0]) <= PICKUP_RADIUS:
\t\t\tif bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
\t\t\t\tloot.remove_at(0)
\t\t\t\tcarried += 1
\t\t\t\tqueue_redraw()
\telse:
\t\tplayer.set("autopilot_target", extract_point)
\t\tif player.global_position.distance_to(extract_point) <= PICKUP_RADIUS:
\t\t\t_finish(true, "extracted loot=%d heat=%d" % [carried, int(heat)])


func _objective_text() -> String:
	return "Recover loot %d/3 | Heat %d/100 | Reach the extraction point" % [carried, int(heat)]
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


func _draw_objectives() -> void:
\tfor enemy in enemies:
\t\tdraw_circle(enemy["pos"], 12.0, Color(0.96, 0.3, 0.28))


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
\t\tif not (bool(player.get("autopilot")) or Input.is_action_pressed("ui_accept")):
\t\t\treturn
\t\ttarget["hp"] -= ATTACK_DAMAGE
\t\tif target["hp"] <= 0:
\t\t\tenemies.remove_at(0)
\t\t\tkills += 1
\tqueue_redraw()


func _objective_text() -> String:
	return "Wave %d/%d | HP %d | Kills %d | Hold Enter to attack nearby enemies" % [wave, WAVES, player_hp, kills]
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


func _draw_objectives() -> void:
\tdraw_circle(source, 15.0, Color(0.37, 0.72, 0.98))
\tdraw_circle(refinery, 19.0, Color(0.99, 0.69, 0.30))
\tdraw_circle(depot, 19.0, Color(0.33, 0.92, 0.45))


func _tick(delta: float) -> void:
\tmatch stage:
\t\t"to_source":
\t\t\tplayer.set("autopilot_target", source)
\t\t\tif player.global_position.distance_to(source) <= RADIUS:
\t\t\t\tif bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
\t\t\t\t\tstage = "to_refinery"
\t\t"to_refinery":
\t\t\tplayer.set("autopilot_target", refinery)
\t\t\tif player.global_position.distance_to(refinery) <= RADIUS:
\t\t\t\tif bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
\t\t\t\t\tstage = "refining"
\t\t\t\t\trefine_timer = 0.25
\t\t"refining":
\t\t\trefine_timer -= delta
\t\t\tif refine_timer <= 0.0:
\t\t\t\tstage = "to_depot"
\t\t"to_depot":
\t\t\tplayer.set("autopilot_target", depot)
\t\t\tif player.global_position.distance_to(depot) <= RADIUS:
\t\t\t\tif bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept"):
\t\t\t\t\tshipped += 1
\t\t\t\t\tstage = "to_source"
\tif shipped >= QUOTA:
\t\t_finish(true, "shipped=%d" % shipped)


func _objective_text() -> String:
	return "Shipped %d/%d | Current stage: %s" % [shipped, QUOTA, stage]
'''

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


func _objective_text() -> String:
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


func _objective_text() -> String:
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


func _objective_text() -> String:
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


func _objective_text() -> String:
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


func _objective_text() -> String:
	return "Materials %d/3 | Crafted %s | Press Enter to work" % [collected, "yes" if crafted else "no"]
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
    "extraction": "Collect three loot caches with Enter, then reach the green extraction point",
    "combat_loop": "Clear three enemy waves: approach red targets and hold Enter to attack",
    "pipeline": "Ship four loads through the source, refinery and depot (Enter at each)",
    "puzzle": "Activate the switches in order: step into the bright ring and press Enter",
    "racing": "Drive three ordered laps through the checkpoints before the clock runs out",
    "survival": "Gather three supplies before you dehydrate, then reach the shelter",
    "stealth": "Retrieve three intel drops without entering a red guard zone, then exit",
    "crafting": "Collect three materials, assemble them at the workshop, deliver the item",
}

# name -> (loop body, controller speed, frame budget)
_SPECS: Dict[str, Tuple[str, float, int]] = {
    "extraction": (_EXTRACTION, 260.0, 1800),
    "combat_loop": (_COMBAT, 240.0, 3600),
    "pipeline": (_PIPELINE, 320.0, 3600),
    "puzzle": (_PUZZLE, 300.0, 1800),
    "racing": (_RACING, 420.0, 3600),
    "survival": (_SURVIVAL, 280.0, 3600),
    "stealth": (_STEALTH, 250.0, 3600),
    "crafting": (_CRAFTING, 320.0, 3600),
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


# Creator-axes mechanics v3: which axes really change native source per mode.
MECHANICS_AXES: Dict[str, frozenset] = {
    name: frozenset({"tempo"}) for name in _SPECS
}
MECHANICS_AXES.update({
    "extraction": frozenset({"tempo", "risk", "scarcity", "agency"}),
    "combat_loop": frozenset({"tempo", "lethality", "grind", "agency"}),
    "pipeline": frozenset({"tempo", "risk", "grind", "agency"}),
})


def _apply_operator_axes(
    name: str, body: str, speed: float, max_frames: int, axes: Mapping[str, float],
) -> Tuple[str, float, int]:
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
    return body, speed, max_frames


def archetype_files(
    name: str, *,
    operator_axes: Optional[Mapping[str, float]] = None,
    tuning: Optional[Mapping[str, float]] = None,
) -> Dict[str, str]:
    """Deterministic Godot playable slice with optional *mechanical* knobs.

    ``operator_axes`` (creator-axes mechanics v3): tempo controls movement in
    every mode; risk/scarcity/agency tune extraction heat and pickup range,
    lethality/grind/agency tune combat damage, waves and reach, grind/agency/
    risk tune the pipeline quota, radius and time budget.

    ``tuning`` (cockpit tuning v1, :mod:`skeleton.forge.playable_tuning`)
    covers all eight modes and emits ``data/playable_tuning.json``.

    The two contracts are mutually exclusive. Remaining creative-only axes
    stay in the tensor/blueprint, never falsely advertised as live settings.
    """
    if type(name) is not str or name not in _SPECS:
        raise KeyError("unsupported original playable archetype")
    if operator_axes is not None and tuning is not None:
        raise ValueError("choose operator_axes or tuning, not both")
    axes = _admit_axes(operator_axes)
    body, speed, max_frames = _SPECS[name]
    body, speed, max_frames = _apply_operator_axes(name, body, speed, max_frames, axes)

    fmt = {"name": name, "version": ARCHETYPE_CONTENT_VERSION}
    title = "".join(part.capitalize() for part in name.split("_")) + "Main"
    player = _CONTROLLER.format(speed=speed, **fmt)
    loop = _LOOP_HEADER.format(
        max_frames=max_frames, complete=COMPLETE_MARKER, failed=FAILED_MARKER,
        instruction=_INSTRUCTIONS[name], **fmt
    ) + body
    receipt = None
    if tuning is not None:
        from skeleton.forge.playable_tuning import compile_playable_tuning
        player, loop, receipt = compile_playable_tuning(
            name, tuning, speed=speed, player=player, loop=loop,
        )
    emitted = {
        f"scenes/archetypes/{name}/main.tscn": _SCENE.format(name=name, title=title),
        f"scripts/archetypes/{name}/player_controller.gd": player,
        f"scripts/archetypes/{name}/core_loop.gd": loop,
    }
    if receipt is not None:
        from skeleton.forge.playable_tuning import SOURCE_PATH, tuning_source
        emitted[SOURCE_PATH] = tuning_source(receipt)
    return emitted


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
    key = name if name in _SPECS else "extraction"
    out = dict(files)
    for path, body in archetype_files(key, operator_axes=operator_axes, tuning=tuning).items():
        if path in out and out[path] != body:
            raise ValueError("playable archetype output collides with existing source: " + path)
        out[path] = body
    return out


PLAYABLE_LAUNCHER_PATH = "scripts/autoloads/playable_hub.gd"
_LAUNCHER_SCRIPT = '''extends CanvasLayer
## Opt-in in-game launcher for an actual additional 2D playable genre.
## Switching scenes restarts the active room world, not quest custody.

const ORIGINAL_WORLD := "res://scenes/levels/run_level.tscn"
const BONUS_SCENE := "res://scenes/archetypes/__MODE__/main.tscn"
var _button: Button


func _ready() -> void:
	if DisplayServer.get_name() == "headless":
		return
	layer = 7
	_button = Button.new()
	_button.text = "World / __MODE__ mini-game"
	_button.tooltip_text = "Switching scenes restarts the world, but saved quest snapshots remain stored in the QuestRuntime autoload"
	_button.custom_minimum_size = Vector2(188, 40)
	add_child(_button)
	_button.pressed.connect(_switch_scene)
	get_viewport().size_changed.connect(_layout_button)
	_layout_button()


func _layout_button() -> void:
	if not is_instance_valid(_button):
		return
	var width := get_viewport().get_visible_rect().size.x
	_button.position = Vector2(maxf(14.0, width - 220.0), 14.0)


func _switch_scene() -> void:
	var current := get_tree().current_scene
	if current == null:
		return
	var target := ORIGINAL_WORLD if current.scene_file_path == BONUS_SCENE else BONUS_SCENE
	var result := get_tree().change_scene_to_file(target)
	if result != OK:
		push_warning("Playable scene is unavailable")
'''


def attach_playable_launcher(files: Mapping[str, str], name: str) -> Dict[str, str]:
    """Make an opt-in bonus Godot mini-game reachable without overwriting main.

    All scene names come from the fixed authored prototype registry. The menu
    is source-bound and never follows a game-file or user-supplied path.
    """
    if type(name) is not str or name not in _SPECS or not isinstance(files, Mapping):
        raise ValueError("unregistered playable launcher mode or project")
    project = files.get("project.godot")
    source = f"scenes/archetypes/{name}/main.tscn"
    if type(project) is not str or project.count("[autoload]\n") != 1:
        raise ValueError("canonical Godot autoload block is missing")
    if source not in files or PLAYABLE_LAUNCHER_PATH in files:
        raise ValueError("bonus game scene is missing or launcher path collides")
    if "PlayableHub=" in project:
        raise ValueError("PlayableHub autoload is already registered")
    launcher = _LAUNCHER_SCRIPT.replace("__MODE__", name)
    out = dict(files)
    out[PLAYABLE_LAUNCHER_PATH] = launcher
    out["project.godot"] = project.replace(
        "[autoload]\n",
        '[autoload]\nPlayableHub="*res://scripts/autoloads/playable_hub.gd"\n',
        1,
    )
    return out
