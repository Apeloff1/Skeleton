"""Five distinct offline-only, native Godot mini-game loops.

These are actual GDScript loop bodies, not delegated labels to extraction.
They are composed with the bounded source-attested Godot scene and controller,
which are independently imported and played by the native qualification gate.
No model inference, external service, downloadable asset or credential is used.
"""
from __future__ import annotations

from typing import Final

# Each script shares the canonical Node2D completion/failure contract.
ORIGINAL_NATIVE_MODES: Final[tuple[str, ...]] = (
    "puzzle", "racing", "survival", "stealth", "crafting",
)

MODE_BODIES: Final[dict[str, str]] = {
    "puzzle": '''
## Ordered three-switch circuit: one input at a time, exactly sequenced.
const HINTS_VISIBLE := true
const SWITCH_RADIUS := 15.0
var switches: Array[Vector2] = [Vector2(180, 0), Vector2(180, 150), Vector2(-50, 150)]
var active_switch: int = 0

func _tick(_delta: float) -> void:
	if active_switch >= switches.size():
		_finish(true, "circuit restored in sequence")
		return
	player.autopilot_target = switches[active_switch]
	if player.global_position.distance_to(switches[active_switch]) <= SWITCH_RADIUS:
		active_switch += 1
		if active_switch == switches.size():
			_finish(true, "switches=%d" % active_switch)

func _hud_status() -> String:
	if HINTS_VISIBLE and active_switch < switches.size():
		return "Circuit: %d/%d | Next switch: %d" % [active_switch, switches.size(), active_switch + 1]
	return "Circuit: %d/%d | Follow the illuminated switch" % [active_switch, switches.size()]

func _draw_objectives() -> void:
	for i in range(switches.size()):
		var color: Color = GOAL_COLOR if i < active_switch else TARGET_COLOR if i == active_switch else GRID
		draw_rect(Rect2(switches[i] - Vector2(14, 14), Vector2(28, 28)), color)
''',
    "racing": '''
## Ordered checkpoints and completed laps; time pressure is an actual loss.
const LAP_COUNT := 3
const TIME_LIMIT := 65.0
const CHECKPOINT_RADIUS := 20.0
var checkpoints: Array[Vector2] = [
	Vector2(220, 0), Vector2(220, 180), Vector2(-40, 180), Vector2(-40, 0)
]
var next_checkpoint: int = 0
var completed_laps: int = 0
var elapsed: float = 0.0

func _tick(delta: float) -> void:
	elapsed += delta
	if elapsed >= TIME_LIMIT:
		_finish(false, "checkpoint time limit expired")
		return
	player.autopilot_target = checkpoints[next_checkpoint]
	if player.global_position.distance_to(checkpoints[next_checkpoint]) <= CHECKPOINT_RADIUS:
		next_checkpoint += 1
		if next_checkpoint == checkpoints.size():
			next_checkpoint = 0
			completed_laps += 1
			if completed_laps >= LAP_COUNT:
				_finish(true, "laps=%d time=%.1fs" % [completed_laps, elapsed])

func _hud_status() -> String:
	return "Lap %d/%d | Checkpoint %d/%d | %.1fs left" % [
		completed_laps, LAP_COUNT, next_checkpoint + 1, checkpoints.size(), maxf(0.0, TIME_LIMIT - elapsed)
	]

func _draw_objectives() -> void:
	for i in range(checkpoints.size()):
		var color: Color = GOAL_COLOR if i == next_checkpoint else TARGET_COLOR
		draw_circle(checkpoints[i], 18.0, color)
		draw_circle(checkpoints[i], 10.0, FLOOR)
''',
    "survival": '''
## Collect water before shelter; running out of hydration loses the run.
const HYDRATION_DRAIN := 1.5
const PICKUP_RADIUS := 17.0
var hydration: float = 80.0
var canteens: Array[Vector2] = [Vector2(150, 0), Vector2(160, 150), Vector2(-80, 150)]
var shelter: Vector2 = Vector2(-200, 0)
var collected: int = 0

func _tick(delta: float) -> void:
	hydration -= HYDRATION_DRAIN * delta
	if hydration <= 0.0:
		_finish(false, "dehydration")
		return
	if not canteens.is_empty():
		player.autopilot_target = canteens[0]
		if player.global_position.distance_to(canteens[0]) <= PICKUP_RADIUS:
			canteens.remove_at(0)
			hydration = minf(100.0, hydration + 18.0)
			collected += 1
	else:
		player.autopilot_target = shelter
		if player.global_position.distance_to(shelter) <= PICKUP_RADIUS:
			_finish(true, "shelter reached water=%d hydration=%d" % [collected, int(hydration)])

func _hud_status() -> String:
	return "Hydration: %d%% | Water found: %d/3 | Reach green shelter" % [int(hydration), collected]

func _draw_objectives() -> void:
	for canteen in canteens:
		draw_circle(canteen, 16.0, Color(0.31, 0.67, 1.0))
	draw_rect(Rect2(shelter - Vector2(20, 20), Vector2(40, 40)), GOAL_COLOR)
''',
    "stealth": '''
## Recover intel and exfiltrate without entering any guard detection zone.
const GUARD_RADIUS := 36.0
const SHOW_GUARD_ZONES := true
const INTERACT_RADIUS := 16.0
var guards: Array[Vector2] = [Vector2(130, -60), Vector2(160, 140)]
var intel: Vector2 = Vector2(-200, 100)
var extraction: Vector2 = Vector2(-110, 230)
var has_intel: bool = false

func _tick(_delta: float) -> void:
	for guard in guards:
		if player.global_position.distance_to(guard) < GUARD_RADIUS:
			_finish(false, "detected by security patrol")
			return
	if not has_intel:
		player.autopilot_target = intel
		if player.global_position.distance_to(intel) <= INTERACT_RADIUS:
			has_intel = true
	else:
		player.autopilot_target = extraction
		if player.global_position.distance_to(extraction) <= INTERACT_RADIUS:
			_finish(true, "intel secured and extracted")

func _hud_status() -> String:
	return "Intel: %s | Avoid patrol detection and reach green exit" % ["secured" if has_intel else "unrecovered"]

func _draw_objectives() -> void:
	for guard in guards:
		draw_circle(guard, 12.0, Color(0.96, 0.3, 0.34))
		if SHOW_GUARD_ZONES:
			draw_arc(guard, GUARD_RADIUS, 0.0, TAU, 32, TARGET_COLOR, 2.0)
	if not has_intel:
		draw_rect(Rect2(intel - Vector2(12, 12), Vector2(24, 24)), TARGET_COLOR)
	draw_circle(extraction, 24.0, GOAL_COLOR)
''',
    "crafting": '''
## Collect two distinct materials, craft at the station, deliver the result.
const PICKUP_RADIUS := 17.0
const CRAFT_DURATION := 0.65
var materials: Array[Vector2] = [Vector2(175, 0), Vector2(175, 150)]
var workshop: Vector2 = Vector2(0, 170)
var customer: Vector2 = Vector2(-180, 60)
var gathered: int = 0
var crafting_time: float = 0.0
var crafted: bool = false

func _tick(delta: float) -> void:
	if not materials.is_empty():
		player.autopilot_target = materials[0]
		if player.global_position.distance_to(materials[0]) <= PICKUP_RADIUS:
			materials.remove_at(0)
			gathered += 1
	elif not crafted:
		player.autopilot_target = workshop
		if player.global_position.distance_to(workshop) <= PICKUP_RADIUS:
			crafting_time += delta
			if crafting_time >= CRAFT_DURATION:
				crafted = true
	else:
		player.autopilot_target = customer
		if player.global_position.distance_to(customer) <= PICKUP_RADIUS:
			_finish(true, "crafted and delivered from %d materials" % gathered)

func _hud_status() -> String:
	var stage: String = "collect" if gathered < 2 else "craft" if not crafted else "deliver"
	return "Materials %d/2 | Stage: %s | Yellow parts, blue station, green customer" % [gathered, stage]

func _draw_objectives() -> void:
	for item in materials:
		draw_rect(Rect2(item - Vector2(11, 11), Vector2(22, 22)), TARGET_COLOR)
	draw_circle(workshop, 20.0, Color(0.30, 0.58, 0.98))
	draw_circle(customer, 20.0, GOAL_COLOR)
''',
}

MODE_INSTRUCTIONS: Final[dict[str, str]] = {
    "puzzle": "Activate the glowing circuit switches in sequence",
    "racing": "Complete three laps through checkpoints before the clock expires",
    "survival": "Collect water and reach shelter before hydration runs out",
    "stealth": "Recover intel while avoiding patrol sensors, then extract",
    "crafting": "Gather two parts, craft at the workshop, deliver to the customer",
}

MODE_SPEEDS: Final[dict[str, float]] = {
    "puzzle": 240.0,
    "racing": 340.0,
    "survival": 240.0,
    "stealth": 240.0,
    "crafting": 280.0,
}

MODE_FRAME_BUDGETS: Final[dict[str, int]] = {
    "puzzle": 2100,
    "racing": 4500,
    "survival": 3000,
    "stealth": 2600,
    "crafting": 3000,
}
