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

ARCHETYPE_CONTENT_VERSION = 4
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
var retry_button: Button = null
var retry_pending: bool = false
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
\t_add_direction(controls, "ui_accept", "USE", Vector2(230.0, -130.0))
\tretry_button = Button.new()
\tretry_button.name = "RetryPrototype"
\tretry_button.text = "Retry challenge"
\tretry_button.focus_mode = Control.FOCUS_NONE
\toverlay.add_child(retry_button)
\tretry_button.position = Vector2(20.0, 102.0)
\tretry_button.custom_minimum_size = Vector2(200.0, 44.0)
\tretry_button.hide()
\tretry_button.pressed.connect(_request_retry)


func _request_retry() -> void:
\tif not finished or retry_pending or bool(player.get("autopilot")):
\t\treturn
\tretry_pending = true
\tif retry_button != null:
\t\tretry_button.disabled = true
\tcall_deferred("_reload_challenge")


func _reload_challenge() -> void:
\t# A portal transition may win the race with retry. Never replace its scene.
\tif not is_inside_tree() or get_tree().current_scene != self:
\t\treturn
\tvar status: Error = get_tree().reload_current_scene()
\tif status != OK:
\t\tretry_pending = false
\t\tif retry_button != null:
\t\t\tretry_button.disabled = false
\t\tif hud_label != null:
\t\t\thud_label.text += "\\nRetry unavailable; return to Forge world."


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
\tif not finished:
\t\tInput.action_press(action)


func _release_action(action: String) -> void:
\tInput.action_release(action)


func _release_controls() -> void:
\tfor action in ["ui_up", "ui_down", "ui_left", "ui_right", "ui_accept"]:
\t\tInput.action_release(action)


func _exit_tree() -> void:
\t_release_controls()


func _nearest_point(points: Array[Vector2], radius: float) -> int:
\tvar selected: int = -1
\tvar best: float = radius * radius
\tfor index in range(points.size()):
\t\tvar distance := player.global_position.distance_squared_to(points[index])
\t\tif distance <= best and (selected < 0 or distance < best):
\t\t\tselected = index
\t\t\tbest = distance
\treturn selected


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
\t_release_controls()
\tplayer.velocity = Vector2.ZERO
\tplayer.set_physics_process(false)
\tif retry_button != null:
\t\tretry_button.show()
\tif hud_label != null:
\t\thud_label.text = ("COMPLETED: " if ok else "FAILED: ") + reason + "\\nRetry challenge or return to Forge world"
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
\tif not finished and hud_label != null:
\t\thud_label.text = "{instruction}\\n" + _hud_status()
'''

_EXTRACTION = '''
## Recover every cache, balance cargo heat and ration finite emergency coolant.
const CACHE_GOAL := 3
var loot: Array[Vector2] = [Vector2(220, 0), Vector2(220, 180), Vector2(0, 180)]
var extract_point := Vector2(-160, 60)
var carried: int = 0
var heat: float = 0.0
var coolant: int = 2
const HEAT_LIMIT := 100.0
const HEAT_PER_SECOND := 6.0
const PICKUP_RADIUS := 12.0
const CARGO_HEAT := 1.5
const COOLANT_RESTORE := 30.0


func _cool_down() -> bool:
	if coolant <= 0 or heat < COOLANT_RESTORE:
		return false
	coolant -= 1
	heat = maxf(0.0, heat - COOLANT_RESTORE)
	return true


func _tick(delta: float) -> void:
	# Carrying recovered cargo increases pressure but never changes the
	# admitted base-world heat model; this is the isolated extraction scene.
	heat += (HEAT_PER_SECOND + CARGO_HEAT * float(carried) / float(CACHE_GOAL)) * delta
	var autopilot := bool(player.get("autopilot"))
	if (autopilot and heat >= maxf(COOLANT_RESTORE, HEAT_LIMIT * 0.55)) or (not autopilot and Input.is_action_just_pressed("ui_accept")):
		_cool_down()
	if heat >= HEAT_LIMIT:
		_finish(false, "heat critical")
		return
	if not loot.is_empty():
		player.set("autopilot_target", loot[0])
		var selected := _nearest_point(loot, PICKUP_RADIUS)
		if selected >= 0:
			loot.remove_at(selected)
			carried += 1
	else:
		player.set("autopilot_target", extract_point)
		if player.global_position.distance_to(extract_point) <= PICKUP_RADIUS and carried == CACHE_GOAL:
			_finish(true, "extracted loot=%d heat=%d coolant=%d" % [carried, int(heat), coolant])


func _hud_status() -> String:
	return "Caches: %d/%d | Heat: %d%% | Coolant: %d | USE to cool" % [carried, CACHE_GOAL, int(100.0 * heat / HEAT_LIMIT), coolant]


func _draw_objectives() -> void:
	for cache in loot:
		draw_rect(Rect2(cache - Vector2(11.0, 11.0), Vector2(22.0, 22.0)), TARGET_COLOR)
		draw_circle(cache, 17.0, Color(0.9, 0.61, 0.11, 0.35))
	var extraction_color := GOAL_COLOR if loot.is_empty() else Color(0.34, 0.48, 0.41)
	draw_circle(extract_point, 25.0, extraction_color)
	draw_circle(extract_point, 15.0, FLOOR)
'''

_COMBAT = '''
## Combat: select the nearest living enemy, move, attack and survive waves.
const WAVES := 3
const ATTACK_RANGE := 24.0
const ATTACK_DAMAGE := 5
const CONTACT_DAMAGE := 1
const ENEMY_SPEED := 30.0
const ATTACK_INTERVAL := 0.10
const CONTACT_INTERVAL := 0.50
var wave: int = 0
var enemies: Array[Dictionary] = []
var player_hp: int = 100
var kills: int = 0
var attack_cooldown: float = 0.0
var contact_cooldown: float = 0.0
var attack_flash: float = 0.0
var target_index: int = -1


func _spawn_wave() -> void:
\twave += 1
\tfor i in range(wave + 1):
\t\tvar angle := TAU * float(i) / float(wave + 1)
\t\tvar hp := 5 * wave
\t\tenemies.append({"pos": Vector2(cos(angle), sin(angle)) * 160.0, "hp": hp, "max_hp": hp})


func _nearest_enemy() -> int:
\tvar nearest: int = -1
\tvar best_distance: float = INF
\tfor index in range(enemies.size()):
\t\tvar enemy_pos: Vector2 = enemies[index]["pos"]
\t\tvar distance := enemy_pos.distance_squared_to(player.global_position)
\t\tif distance < best_distance:
\t\t\tnearest = index
\t\t\tbest_distance = distance
\treturn nearest


func _tick(delta: float) -> void:
\tattack_cooldown = maxf(0.0, attack_cooldown - delta)
\tcontact_cooldown = maxf(0.0, contact_cooldown - delta)
\tattack_flash = maxf(0.0, attack_flash - delta)
\tif enemies.is_empty():
\t\tif wave >= WAVES:
\t\t\t_finish(true, "waves=%d kills=%d hp=%d" % [wave, kills, player_hp])
\t\t\treturn
\t\t_spawn_wave()
\tvar touching := false
\tfor enemy in enemies:
\t\tvar enemy_pos: Vector2 = enemy["pos"]
\t\tenemy_pos = enemy_pos.move_toward(player.global_position, ENEMY_SPEED * delta)
\t\tenemy["pos"] = enemy_pos
\t\tif enemy_pos.distance_to(player.global_position) < 8.0:
\t\t\ttouching = true
\tif touching and contact_cooldown <= 0.0:
\t\tplayer_hp = maxi(0, player_hp - CONTACT_DAMAGE)
\t\tcontact_cooldown = CONTACT_INTERVAL
\tif player_hp <= 0:
\t\t_finish(false, "player down")
\t\treturn
\ttarget_index = _nearest_enemy()
\tif target_index < 0:
\t\treturn
\tvar target: Dictionary = enemies[target_index]
\tvar target_pos: Vector2 = target["pos"]
\tplayer.set("autopilot_target", target_pos)
\tvar wants_attack: bool = bool(player.get("autopilot")) or Input.is_action_pressed("ui_accept")
\tif wants_attack and attack_cooldown <= 0.0 and target_pos.distance_to(player.global_position) <= ATTACK_RANGE:
\t\tattack_cooldown = ATTACK_INTERVAL
\t\tattack_flash = 0.12
\t\ttarget["hp"] = int(target["hp"]) - ATTACK_DAMAGE
\t\tif int(target["hp"]) <= 0:
\t\t\tenemies.remove_at(target_index)
\t\t\tkills += 1
\t\t\ttarget_index = _nearest_enemy()


func _hud_status() -> String:
\treturn "Wave: %d/%d | Enemies: %d | HP: %d | Kills: %d | Hold Enter or USE to attack" % [wave, WAVES, enemies.size(), player_hp, kills]


func _draw_objectives() -> void:
\tfor index in range(enemies.size()):
\t\tvar enemy: Dictionary = enemies[index]
\t\tvar pos: Vector2 = enemy["pos"]
\t\tdraw_circle(pos, 12.0, Color(0.96, 0.32, 0.37))
\t\tvar shade := TARGET_COLOR if index == target_index else Color(0.55, 0.27, 0.30)
\t\tdraw_arc(pos, 17.0, 0.0, TAU, 24, shade, 2.0)
\t\tvar ratio := clampf(float(enemy["hp"]) / float(enemy["max_hp"]), 0.0, 1.0)
\t\tdraw_rect(Rect2(pos + Vector2(-14.0, -23.0), Vector2(28.0, 4.0)), FLOOR)
\t\tdraw_rect(Rect2(pos + Vector2(-14.0, -23.0), Vector2(28.0 * ratio, 4.0)), GOAL_COLOR)
\tif attack_flash > 0.0:
\t\tdraw_arc(player.global_position, ATTACK_RANGE, 0.0, TAU, 32, TARGET_COLOR, 3.0)
'''


_PIPELINE = '''
## Finite source inventory, physical cargo, timed conversion and verified shipping.
const QUOTA := 4
const RADIUS := 12.0
const CARGO_CAPACITY := 1
const REFINE_SECONDS_PER_UNIT := 0.25
var source := Vector2(200, -80)
var refinery := Vector2(0, 120)
var depot := Vector2(-200, -80)
var stage: String = "to_source"
var source_stock: int = QUOTA
var raw_cargo: int = 0
var refined_cargo: int = 0
var shipped: int = 0
var refine_timer: float = 0.0
var batch_count: int = 0


func _inventory_valid() -> bool:
	return source_stock >= 0 and raw_cargo >= 0 and refined_cargo >= 0 and shipped >= 0 and raw_cargo + refined_cargo <= CARGO_CAPACITY and source_stock + raw_cargo + refined_cargo + shipped == QUOTA


func _tick(delta: float) -> void:
	if not _inventory_valid():
		_finish(false, "cargo ledger mismatch")
		return
	var autopilot := bool(player.get("autopilot"))
	var interact := autopilot or Input.is_action_just_pressed("ui_accept")
	match stage:
		"to_source":
			player.set("autopilot_target", source)
			if interact and player.global_position.distance_to(source) <= RADIUS:
				if raw_cargo != 0 or refined_cargo != 0 or source_stock <= 0:
					_finish(false, "invalid load state")
					return
				raw_cargo = mini(CARGO_CAPACITY, source_stock)
				source_stock -= raw_cargo
				stage = "to_refinery"
		"to_refinery":
			player.set("autopilot_target", refinery)
			if interact and player.global_position.distance_to(refinery) <= RADIUS:
				if raw_cargo <= 0 or refined_cargo != 0:
					_finish(false, "invalid refinery cargo")
					return
				stage = "refining"
				refine_timer = REFINE_SECONDS_PER_UNIT * float(raw_cargo)
		"refining":
			player.set("autopilot_target", refinery)
			if player.global_position.distance_to(refinery) > RADIUS:
				stage = "to_refinery"
				refine_timer = 0.0
			elif autopilot or Input.is_action_pressed("ui_accept"):
				refine_timer = maxf(0.0, refine_timer - delta)
				if refine_timer <= 0.0:
					refined_cargo = raw_cargo
					raw_cargo = 0
					stage = "to_depot"
		"to_depot":
			player.set("autopilot_target", depot)
			if interact and player.global_position.distance_to(depot) <= RADIUS:
				if refined_cargo <= 0 or raw_cargo != 0:
					_finish(false, "invalid shipment cargo")
					return
				shipped += refined_cargo
				refined_cargo = 0
				batch_count += 1
				stage = "to_source"
		_:
			_finish(false, "unknown production stage")
			return
	if not _inventory_valid():
		_finish(false, "cargo ledger mismatch")
		return
	if shipped == QUOTA and source_stock == 0 and raw_cargo == 0 and refined_cargo == 0:
		_finish(true, "shipped=%d batches=%d" % [shipped, batch_count])


func _hud_status() -> String:
	return "Shipped: %d/%d | Stock: %d | Cargo: %d raw / %d refined | %s | USE load / refine / ship (%.1f s)" % [shipped, QUOTA, source_stock, raw_cargo, refined_cargo, stage, refine_timer]


func _draw_objectives() -> void:
	var active_source := TARGET_COLOR if stage == "to_source" else Color(0.58, 0.46, 0.26)
	var active_refinery := Color(0.32, 0.61, 1.0) if stage == "to_refinery" or stage == "refining" else Color(0.24, 0.34, 0.52)
	var active_depot := GOAL_COLOR if stage == "to_depot" else Color(0.25, 0.43, 0.31)
	draw_rect(Rect2(source - Vector2(18.0, 18.0), Vector2(36.0, 36.0)), active_source)
	draw_circle(refinery, 22.0, active_refinery)
	draw_circle(depot, 22.0, active_depot)
	if raw_cargo + refined_cargo > 0:
		draw_arc(player.global_position, 24.0, 0.0, TAU, 32, active_refinery if raw_cargo > 0 else GOAL_COLOR, 3.0)
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
    "extraction": "Recover all caches; use finite coolant before heat becomes critical",
    "combat_loop": "Move near enemies; hold Enter or USE to attack and survive the waves",
    "pipeline": "USE to load ore, hold USE at refinery, then USE at depot to ship",
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

_RACING_CONTROLLER = '''extends CharacterBody2D
## {name} acceleration and finite boost controller v{version}.
@export var speed: float = {speed}
const ACCELERATION := 1800.0
const BRAKE_ACCELERATION := 2400.0
const BOOST_SCALE := 1.35
const BOOST_DRAIN := 30.0
const BOOST_RECHARGE := 12.5
var autopilot: bool = false
var autopilot_target: Vector2 = Vector2.ZERO
var boost_charge: float = 100.0
var boosting: bool = false

func _ready() -> void:
	autopilot = DisplayServer.get_name() == "headless" or OS.get_cmdline_user_args().has("--autoplay")

func _physics_process(delta: float) -> void:
	var desired := Vector2.ZERO
	boosting = false
	if autopilot:
		var offset := autopilot_target - global_position
		var distance := offset.length()
		if distance > 4.0:
			var arrival_speed := minf(speed, sqrt(2.0 * BRAKE_ACCELERATION * distance))
			desired = offset.normalized() * arrival_speed
	else:
		var direction := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
		boosting = direction.length_squared() > 0.0 and Input.is_action_pressed("ui_accept") and boost_charge >= BOOST_DRAIN * delta
		desired = direction * speed * (BOOST_SCALE if boosting else 1.0)
	if boosting:
		boost_charge = maxf(0.0, boost_charge - BOOST_DRAIN * delta)
	else:
		boost_charge = minf(100.0, boost_charge + BOOST_RECHARGE * delta)
	var acceleration := ACCELERATION if desired.length_squared() > velocity.length_squared() else BRAKE_ACCELERATION
	velocity = velocity.move_toward(desired, acceleration * delta)
	move_and_slide()
'''

# Use the existing visual grid, live progress, headless isolation and D-pad.
# Expanded interactions also need a dedicated pointer/touch USE action.
_EXPANDED_LOOP_HEADER = _LOOP_HEADER


_PUZZLE = '''
## Spatial switch-order puzzle. Press ui_accept within a target's ring.
var switches: Array[Vector2] = [
	Vector2(180, 0), Vector2(180, 150),
	Vector2(-40, 150), Vector2(-180, -20)
]
var next_switch: int = 0
var mistakes: int = 0
var clue_until: int = 120
const MAX_MISTAKES := 5
const SHOW_ACTIVE_SWITCH := true
const USE_RADIUS := 18.0

func _draw_objectives() -> void:
	for index in range(switches.size()):
		var solved := index < next_switch
		var hinted := index == next_switch and (SHOW_ACTIVE_SWITCH or frames <= clue_until)
		var shade := Color(0.20, 0.90, 0.58) if hinted else Color(0.4, 0.4, 0.4)
		if solved:
			shade = Color(0.25, 0.60, 0.95)
		draw_circle(switches[index], 14.0, shade)
		draw_arc(switches[index], USE_RADIUS, 0.0, TAU, 24, shade, 2.0)


func _near_switch() -> int:
	var nearest: int = -1
	var best: float = USE_RADIUS
	for index in range(switches.size()):
		var distance := player.global_position.distance_to(switches[index])
		if distance <= best:
			nearest = index
			best = distance
	return nearest


func _tick(_delta: float) -> void:
	if next_switch >= switches.size():
		_finish(true, "switches=%d mistakes=%d" % [next_switch, mistakes])
		return
	var target: Vector2 = switches[next_switch]
	player.set("autopilot_target", target)
	var autopilot := bool(player.get("autopilot"))
	if not autopilot and not Input.is_action_just_pressed("ui_accept"):
		return
	var selected := _near_switch()
	if selected < 0 or selected < next_switch:
		return
	if selected == next_switch:
		next_switch += 1
		clue_until = frames + 90
	else:
		mistakes += 1
		clue_until = frames + 120
		if mistakes >= MAX_MISTAKES:
			_finish(false, "too many incorrect switches")
	queue_redraw()


func _hud_status() -> String:
	if SHOW_ACTIVE_SWITCH or frames <= clue_until:
		return "Switch %d/%d | Green = next | Errors %d/%d" % [next_switch, switches.size(), mistakes, MAX_MISTAKES]
	return "Switches remaining: %d | Remember the green clue | Errors %d/%d" % [switches.size() - next_switch, mistakes, MAX_MISTAKES]
'''

_RACING = '''
## Complete full ordered checkpoint circuits before the deadline.
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
var lap_started_at: float = 0.0
var sector_started_at: float = 0.0
var last_sector: float = 0.0
var last_lap: float = 0.0
var best_lap: float = 0.0
var lap_times: Array[float] = []
var started: bool = false

func _draw_objectives() -> void:
	for idx in range(course.size()):
		var end: Vector2 = course[(idx + 1) % course.size()]
		draw_line(course[idx], end, Color(0.32, 0.4, 0.7), 7.0)
		var shade := Color(0.2, 0.96, 0.35) if idx == waypoint else Color(0.86, 0.77, 0.28)
		draw_circle(course[idx], LAP_RADIUS, shade)
		if idx == waypoint:
			draw_arc(course[idx], LAP_RADIUS + 8.0, 0.0, TAU, 32, shade, 2.0)
	if bool(player.get("boosting")):
		draw_arc(player.global_position, 24.0, 0.0, TAU, 32, Color(0.39, 0.78, 1.0), 3.0)

func _tick(delta: float) -> void:
	elapsed += delta
	if elapsed >= TIME_LIMIT:
		_finish(false, "checkpoint time limit")
		return
	player.set("autopilot_target", course[waypoint])
	if player.global_position.distance_to(course[waypoint]) <= LAP_RADIUS:
		if not started:
			started = true
			lap_started_at = elapsed
			sector_started_at = elapsed
			waypoint = 1
			return
		last_sector = elapsed - sector_started_at
		sector_started_at = elapsed
		if waypoint == 0:
			laps += 1
			last_lap = elapsed - lap_started_at
			lap_started_at = elapsed
			lap_times.append(last_lap)
			if best_lap <= 0.0 or last_lap < best_lap:
				best_lap = last_lap
			if laps >= GOAL_LAPS:
				_finish(true, "laps=%d time=%.1f best=%.2f" % [laps, elapsed, best_lap])
				return
		waypoint = (waypoint + 1) % course.size()
		queue_redraw()

func _hud_status() -> String:
	return "Lap %d/%d | Gate %d/%d | Time %.1f/%.1f s | Best %.2f | Sector %.2f | Boost %d%% (hold USE)" % [mini(laps + 1, GOAL_LAPS), GOAL_LAPS, waypoint + 1, course.size(), elapsed, TIME_LIMIT, best_lap, last_sector, int(player.get("boost_charge"))]
'''

_SURVIVAL = '''
## Collect essentials, manage a finite water reserve and cross exposed terrain.
var supplies: Array[Vector2] = [
	Vector2(160, 80), Vector2(90, 220), Vector2(-160, 180)
]
var shelter := Vector2(-220, -120)
var hot_zones: Array[Vector2] = [Vector2(180, -180), Vector2(-240, 0)]
var collected: int = 0
var water_reserve: int = 0
var hydration: float = 75.0
const DRAIN_PER_SECOND := 2.0
const EXPOSURE_DRAIN := 3.0
const EXPOSURE_RADIUS := 70.0
const WATER_PER_SUPPLY := 1
const DRINK_RESTORE := 24.0
const PICKUP_RADIUS := 19.0
var exposed: bool = false


func _draw_objectives() -> void:
	for zone in hot_zones:
		draw_circle(zone, EXPOSURE_RADIUS, Color(0.95, 0.49, 0.12, 0.13))
		draw_arc(zone, EXPOSURE_RADIUS, 0.0, TAU, 40, Color(0.95, 0.49, 0.12), 2.0)
	for location in supplies:
		draw_circle(location, 11.0, Color(0.25, 0.72, 0.98))
	var shelter_color := Color(0.38, 0.9, 0.36) if supplies.is_empty() else Color(0.35, 0.45, 0.43)
	draw_circle(shelter, 21.0, shelter_color)


func _drink() -> bool:
	if water_reserve <= 0 or hydration >= 100.0:
		return false
	water_reserve -= 1
	hydration = minf(100.0, hydration + DRINK_RESTORE)
	return true


func _tick(delta: float) -> void:
	exposed = _nearest_point(hot_zones, EXPOSURE_RADIUS) >= 0
	hydration = maxf(0.0, hydration - (DRAIN_PER_SECOND + (EXPOSURE_DRAIN if exposed else 0.0)) * delta)
	var autopilot := bool(player.get("autopilot"))
	var use_pressed := Input.is_action_just_pressed("ui_accept")
	if not supplies.is_empty():
		player.set("autopilot_target", supplies[0])
		var selected := _nearest_point(supplies, PICKUP_RADIUS)
		if selected >= 0 and (autopilot or use_pressed):
			supplies.remove_at(selected)
			collected += 1
			water_reserve += WATER_PER_SUPPLY
			use_pressed = false
			queue_redraw()
	else:
		player.set("autopilot_target", shelter)
	# A manual interaction gathers OR drinks, never both. Autoplay follows
	# the same finite inventory and can use reserves at the low-water threshold.
	if (autopilot and hydration <= 55.0) or (not autopilot and use_pressed):
		_drink()
	if hydration <= 0.0:
		_finish(false, "dehydrated")
		return
	if supplies.is_empty() and player.global_position.distance_to(shelter) <= PICKUP_RADIUS:
		_finish(true, "supplies=%d hydration=%d reserve=%d" % [collected, int(hydration), water_reserve])


func _hud_status() -> String:
	return "Supplies %d/3 | Hydration %d | Water %d | %s | USE gather / drink" % [collected, int(hydration), water_reserve, "EXPOSED" if exposed else "Safe terrain"]
'''

_STEALTH = '''
## Recover intel while managing progressive detection from moving sentries.
var patrols: Array[Vector2] = [
	Vector2(90, -120), Vector2(260, -80),
	Vector2(40, 320), Vector2(-240, 170)
]
var objectives: Array[Vector2] = [
	Vector2(160, 20), Vector2(260, 170), Vector2(-20, 200)
]
var exit_point := Vector2(-180, 50)
var intel: int = 0
var patrol_time: float = 0.0
var alert: float = 0.0
var exposed: bool = false
const DETECTION_RADIUS := 64.0
const SHOW_GUARD_ZONES := true
const USE_RADIUS := 18.0
const PATROL_AMPLITUDE := 14.0
const PATROL_FREQUENCY := 0.85
const ALERT_RISE := 0.95
const ALERT_DECAY := 0.48
const PROXIMITY_RADIUS := 12.0


func _guard_position(index: int) -> Vector2:
	var phase := patrol_time * PATROL_FREQUENCY + float(index) * 1.570796
	return patrols[index] + Vector2(cos(phase), sin(phase)) * PATROL_AMPLITUDE


func _draw_objectives() -> void:
	for index in range(patrols.size()):
		var guard := _guard_position(index)
		if SHOW_GUARD_ZONES:
			draw_circle(guard, DETECTION_RADIUS, Color(0.9, 0.22, 0.24, 0.16))
		draw_circle(guard, 9.0, Color(0.96, 0.26, 0.24))
		draw_arc(guard, PROXIMITY_RADIUS, 0.0, TAU, 24, Color(0.96, 0.26, 0.24), 2.0)
	for intel_point in objectives:
		draw_circle(intel_point, 11.0, Color(0.25, 0.82, 0.98))
	var exit_color := Color(0.25, 0.88, 0.32) if objectives.is_empty() else Color(0.35, 0.45, 0.43)
	draw_circle(exit_point, 20.0, exit_color)


func _tick(delta: float) -> void:
	patrol_time += delta
	exposed = false
	var pressure: float = 0.0
	for index in range(patrols.size()):
		var distance := player.global_position.distance_to(_guard_position(index))
		if distance < PROXIMITY_RADIUS:
			_finish(false, "intercepted by patrol")
			return
		if distance < DETECTION_RADIUS:
			exposed = true
			pressure = maxf(pressure, 1.0 - distance / DETECTION_RADIUS)
	if exposed:
		alert = minf(1.0, alert + ALERT_RISE * (0.35 + pressure) * delta)
	else:
		alert = maxf(0.0, alert - ALERT_DECAY * delta)
	if alert >= 1.0:
		_finish(false, "spotted by patrol")
		return
	if not objectives.is_empty():
		player.set("autopilot_target", objectives[0])
		var selected := _nearest_point(objectives, USE_RADIUS)
		if selected >= 0 and (bool(player.get("autopilot")) or Input.is_action_just_pressed("ui_accept")):
			objectives.remove_at(selected)
			intel += 1
			queue_redraw()
	else:
		player.set("autopilot_target", exit_point)
		if player.global_position.distance_to(exit_point) <= USE_RADIUS and not exposed:
			_finish(true, "intel=%d alert=%d" % [intel, int(alert * 100.0)])


func _hud_status() -> String:
	return "Intel %d/3 | Alert %d%% | %s | USE to retrieve" % [intel, int(alert * 100.0), "EXPOSED" if exposed else "Unseen"]
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
var assembly_progress: float = 0.0
const ASSEMBLY_SECONDS := 1.2
const USE_RADIUS := 19.0

func _draw_objectives() -> void:
	for deposit in materials:
		draw_circle(deposit, 11.0, Color(0.48, 0.79, 0.99))
	draw_circle(workshop, 22.0, Color(0.98, 0.68, 0.27))
	draw_circle(delivery, 23.0, Color(0.33, 0.9, 0.48))

func _tick(delta: float) -> void:
	var autopilot := bool(player.get("autopilot"))
	if materials.size() > 0:
		player.set("autopilot_target", materials[0])
		var selected := _nearest_point(materials, USE_RADIUS)
		if selected >= 0 and (autopilot or Input.is_action_just_pressed("ui_accept")):
			materials.remove_at(selected)
			collected += 1
	elif not crafted:
		player.set("autopilot_target", workshop)
		if player.global_position.distance_to(workshop) > USE_RADIUS:
			assembly_progress = 0.0
		elif autopilot or Input.is_action_pressed("ui_accept"):
			assembly_progress = minf(ASSEMBLY_SECONDS, assembly_progress + delta)
			if assembly_progress >= ASSEMBLY_SECONDS:
				crafted = collected == 3
				if not crafted:
					_finish(false, "missing crafting materials")
		else:
			assembly_progress = maxf(0.0, assembly_progress - delta)
	else:
		player.set("autopilot_target", delivery)
		if player.global_position.distance_to(delivery) <= USE_RADIUS:
			_finish(true, "crafted item delivered from %d materials" % collected)


func _hud_status() -> String:
	return "Materials %d/3 | Assembly %d%% | %s" % [collected, int(100.0 * assembly_progress / ASSEMBLY_SECONDS), "Deliver to green" if crafted else "Hold Enter or USE at workshop"]
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
    controller = _RACING_CONTROLLER if name == "racing" else _EXPANDED_CONTROLLER
    player = controller.format(speed=speed, **fmt)
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
    return {axis: round(float(raw[axis]), 4) for axis in AXES if axis in raw}


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
    if type(name) is not str or name not in content_archetypes():
        raise KeyError("unsupported original playable archetype")
    axes = _admit_axes(operator_axes)
    if name in _EXPANDED_SPECS:
        return _expanded_files(name, axes)
    from skeleton.forge.playable_tuning import SCHEMA, SOURCE_PATH, tuning_source

    body, speed, max_frames = _SPECS[name]
    applied: dict[str, float] = {}
    used: set[str] = set()

    def apply_constant(axis: str, effect: str, old: str, constant: str,
                       value: float, *, integral: bool = False) -> None:
        nonlocal body
        literal = str(int(value)) if integral else _number(value)
        body = _swap_constant(body, old, f"const {constant} := {literal}")
        applied[effect] = float(literal)
        used.add(axis)

    if "tempo" in axes:
        speed = round(speed * (0.75 + 0.5 * axes["tempo"]), 2)
        applied["player.speed"] = speed
        used.add("tempo")
    if name == "extraction":
        if "grind" in axes:
            count = 2 + int(4.0 * axes["grind"] + 0.5)
            points = ((220, 0), (220, 180), (0, 180), (-180, 180), (-240, -80), (60, -180))
            apply_constant("grind", "extraction.caches_required", "const CACHE_GOAL := 3",
                           "CACHE_GOAL", count, integral=True)
            body = _swap_constant(
                body, "Vector2(220, 0), Vector2(220, 180), Vector2(0, 180)",
                ", ".join(f"Vector2({x}, {y})" for x, y in points[:count]),
            )
        if "risk" in axes:
            apply_constant("risk", "extraction.heat_per_second", "const HEAT_PER_SECOND := 6.0",
                           "HEAT_PER_SECOND", 3.0 + 7.0 * axes["risk"])
        if "scarcity" in axes:
            apply_constant("scarcity", "extraction.heat_limit", "const HEAT_LIMIT := 100.0",
                           "HEAT_LIMIT", 120.0 - 50.0 * axes["scarcity"])
        if "agency" in axes:
            apply_constant("agency", "extraction.pickup_radius", "const PICKUP_RADIUS := 12.0",
                           "PICKUP_RADIUS", 8.0 + 12.0 * axes["agency"])
    elif name == "combat_loop":
        if "lethality" in axes:
            apply_constant("lethality", "combat_loop.contact_damage", "const CONTACT_DAMAGE := 1",
                           "CONTACT_DAMAGE", 1 + int(4.0 * axes["lethality"] + 0.5), integral=True)
        if "grind" in axes:
            apply_constant("grind", "combat_loop.waves", "const WAVES := 3",
                           "WAVES", 2 + int(3.0 * axes["grind"] + 0.5), integral=True)
        if "agency" in axes:
            apply_constant("agency", "combat_loop.attack_range", "const ATTACK_RANGE := 24.0",
                           "ATTACK_RANGE", 16.0 + 24.0 * axes["agency"])
    elif name == "pipeline":
        if "scarcity" in axes:
            apply_constant("scarcity", "pipeline.cargo_capacity", "const CARGO_CAPACITY := 1",
                           "CARGO_CAPACITY", 3 - int(2.0 * axes["scarcity"] + 0.5), integral=True)
        if "grind" in axes:
            apply_constant("grind", "pipeline.shipment_quota", "const QUOTA := 4",
                           "QUOTA", 2 + int(6.0 * axes["grind"] + 0.5), integral=True)
        if "agency" in axes:
            apply_constant("agency", "pipeline.interaction_radius", "const RADIUS := 12.0",
                           "RADIUS", 8.0 + 12.0 * axes["agency"])
        if "risk" in axes:
            max_frames = round(max_frames * (1.5 - 0.5 * axes["risk"]))
            applied["pipeline.frame_budget"] = float(max_frames)
            used.add("risk")

    fmt = {"name": name, "version": ARCHETYPE_CONTENT_VERSION}
    title = "".join(part.capitalize() for part in name.split("_")) + "Main"
    emitted = {
        f"scenes/archetypes/{name}/main.tscn": _SCENE.format(name=name, title=title),
        f"scripts/archetypes/{name}/player_controller.gd": _CONTROLLER.format(speed=speed, **fmt),
        f"scripts/archetypes/{name}/core_loop.gd": _LOOP_HEADER.format(
            max_frames=max_frames, complete=COMPLETE_MARKER, failed=FAILED_MARKER,
            instruction=_INSTRUCTIONS[name], **fmt
        ) + body,
    }
    # No implicit tuning artifact for an untouched baseline. All explicit
    # edits, even unmapped creative-only axes, receive honest typed evidence.
    if axes:
        emitted[SOURCE_PATH] = tuning_source({
            "schema": SCHEMA, "mode": name, "axes": dict(sorted(axes.items())),
            "applied": dict(sorted(applied.items())), "mapped_axes": sorted(used),
            "unmapped_axes": sorted(set(axes) - used),
        })
    return emitted


def verify_archetype_content(
    files: Mapping[str, str], name: str, *, operator_axes: Optional[Mapping[str, float]] = None,
) -> bool:
    """Source-verification after all independent Godot/quest file writers."""
    from skeleton.forge.playable_tuning import SOURCE_PATH

    if not isinstance(files, Mapping):
        return False
    expected = archetype_files(name, operator_axes=operator_axes)
    receipt_paths = [path for path in files
                     if isinstance(path, str) and path.casefold() == SOURCE_PATH.casefold()]
    if receipt_paths != ([SOURCE_PATH] if SOURCE_PATH in expected else []):
        return False
    return all(files.get(path) == body for path, body in expected.items())


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
    from skeleton.forge.playable_tuning import SOURCE_PATH

    key = name if name in content_archetypes() else "extraction"
    expected = archetype_files(key, operator_axes=operator_axes)
    for path in files:
        if path.casefold() == SOURCE_PATH.casefold() and (
            path != SOURCE_PATH or SOURCE_PATH not in expected or files[path] != expected[SOURCE_PATH]
        ):
            raise ValueError("playable tuning receipt collides with existing source: " + path)
    out = dict(files)
    for path, body in expected.items():
        if path in out and out[path] != body:
            raise ValueError("playable archetype output collides with existing source: " + path)
        out[path] = body
    return out
