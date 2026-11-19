"""Five additional self-contained Godot 4 sidecar gameplay loops.

This module supplies real authored movement/objective/failure mechanics for
puzzle, racing, survival, stealth and crafting. All are offline native
GDScript bodies compatible with archetype_content's common controller,
canvas HUD, touch D-pad, deterministic headless autopilot and source pinning.

These prototypes are not AAA production games, an emulator, or a substitute
for physically compiled Godot execution evidence.
"""
from __future__ import annotations

from typing import Final

_PUZZLE = r'''
## Spatial puzzle: activate four pressure pads in the announced sequence.
## Wrong pads reset progress, while mystery controls how much guidance appears.
const PRESS_RADIUS := 17.0
const SHOW_SWITCH_HINTS := true
var switches: Array[Vector2] = [
	Vector2(-180.0, -120.0), Vector2(180.0, -120.0),
	Vector2(-180.0, 120.0), Vector2(180.0, 120.0)
]
var sequence: Array[int] = [2, 0, 3, 1]
var solved: int = 0
var wrong_activations: int = 0
var release_gate: int = 0


func _tick(_delta: float) -> void:
	if solved >= sequence.size():
		_finish(true, "four pads activated; mistakes=%d" % wrong_activations)
		return
	var correct: int = sequence[solved]
	player.autopilot_target = switches[correct]
	if frames < release_gate:
		return
	for i in range(switches.size()):
		if player.global_position.distance_to(switches[i]) > PRESS_RADIUS:
			continue
		if i == correct:
			solved += 1
		else:
			wrong_activations += 1
			solved = 0
		release_gate = frames + 18
		break


func _hud_status() -> String:
	var clue := ("Next pad: %d" % (sequence[solved] + 1)) if SHOW_SWITCH_HINTS and solved < sequence.size() else "Observe the pad order"
	return "Switches: %d/4 | Mistakes: %d | %s" % [solved, wrong_activations, clue]


func _draw_objectives() -> void:
	for i in range(switches.size()):
		var pos: Vector2 = switches[i]
		var active := solved < sequence.size() and i == sequence[solved]
		var tint: Color = GOAL_COLOR if active and SHOW_SWITCH_HINTS else TARGET_COLOR
		draw_rect(Rect2(pos - Vector2(19, 19), Vector2(38, 38)), tint)
		draw_string(ThemeDB.fallback_font, pos + Vector2(-6, 5), str(i + 1))
'''

_RACING = r'''
## Race checkpoints and laps; progress requires driving through ALL gates.
## Risk adjusts the checkpoint timer, progression depth adjusts race laps.
const RACE_LAPS := 3
const CHECKPOINT_LIMIT := 30.0
const CHECKPOINT_RADIUS := 20.0
var checkpoints: Array[Vector2] = [
	Vector2(180, -120), Vector2(220, 120),
	Vector2(-200, 140), Vector2(-220, -120)
]
var gate: int = 0
var lap: int = 0
var checkpoint_seconds: float = CHECKPOINT_LIMIT
var race_seconds: float = 0.0


func _tick(delta: float) -> void:
	checkpoint_seconds -= delta
	race_seconds += delta
	if checkpoint_seconds <= 0:
		_finish(false, "checkpoint time expired")
		return
	player.autopilot_target = checkpoints[gate]
	if player.global_position.distance_to(checkpoints[gate]) <= CHECKPOINT_RADIUS:
		gate += 1
		checkpoint_seconds = CHECKPOINT_LIMIT
		if gate >= checkpoints.size():
			gate = 0
			lap += 1
			if lap >= RACE_LAPS:
				_finish(true, "laps=%d time=%.1fs" % [lap, race_seconds])


func _hud_status() -> String:
	return "Lap: %d/%d | Gate: %d/4 | Gate time: %.1fs" % [
		lap + 1, RACE_LAPS, gate + 1, checkpoint_seconds
	]


func _draw_objectives() -> void:
	for i in range(checkpoints.size()):
		var point: Vector2 = checkpoints[i]
		var tint: Color = GOAL_COLOR if i == gate else TARGET_COLOR
		draw_arc(point, 24.0, 0.0, TAU, 32, tint, 4.0)
		draw_line(point - Vector2(25, 0), point + Vector2(25, 0), tint, 2.0)
'''

_SURVIVAL = r'''
## Survival requires collecting hydration before reaching safe shelter.
## Scarcity changes real hydration depletion; exhausted players lose.
const HYDRATION_DRAIN := 2.0
const SUPPLY_RADIUS := 16.0
var hydration: float = 70.0
var supplies: Array[Vector2] = [
	Vector2(180, 0), Vector2(210, 160), Vector2(-180, 160)
]
var gathered: int = 0
var shelter: Vector2 = Vector2(-230, -130)


func _tick(delta: float) -> void:
	hydration -= HYDRATION_DRAIN * delta
	if hydration <= 0.0:
		_finish(false, "hydration exhausted")
		return
	if not supplies.is_empty():
		player.autopilot_target = supplies[0]
		if player.global_position.distance_to(supplies[0]) <= SUPPLY_RADIUS:
			supplies.remove_at(0)
			gathered += 1
			hydration = minf(100.0, hydration + 16.0)
	else:
		player.autopilot_target = shelter
		if player.global_position.distance_to(shelter) <= SUPPLY_RADIUS:
			_finish(true, "supplies=%d hydration=%d" % [gathered, int(hydration)])


func _hud_status() -> String:
	return "Supply crates: %d/3 | Hydration: %d%% | Reach shelter" % [gathered, int(hydration)]


func _draw_objectives() -> void:
	for pos in supplies:
		draw_circle(pos, 14.0, Color(0.26, 0.63, 0.98))
		draw_arc(pos, 20.0, 0.0, TAU, 26, TARGET_COLOR, 2.0)
	draw_rect(Rect2(shelter - Vector2(23, 23), Vector2(46, 46)), GOAL_COLOR)
'''

_STEALTH = r'''
## Recover three intelligence caches while avoiding patrolling guard zones.
## Risk controls physical detection radius. Mystery hides/reveals the zones.
const GUARD_DETECTION_RADIUS := 24.0
const SHOW_GUARD_ZONES := true
const ALERT_LIMIT := 100.0
var intel: Array[Vector2] = [
	Vector2(-240, -170), Vector2(-240, 180), Vector2(220, 180)
]
var guards: Array[Vector2] = [
	Vector2(-60, -60), Vector2(100, 30)
]
var guard_phase: float = 0.0
var alert: float = 0.0
var collected: int = 0
var safe_exit := Vector2(260, -170)


func _tick(delta: float) -> void:
	guard_phase += delta
	var route_target: Vector2 = intel[0] if not intel.is_empty() else safe_exit
	player.autopilot_target = route_target
	for i in range(guards.size()):
		var guard_pos: Vector2 = guards[i] + Vector2(
			sin(guard_phase + float(i) * 1.7) * 30.0,
			cos(guard_phase * 0.7 + float(i)) * 40.0
		)
		if guard_pos.distance_to(player.global_position) < GUARD_DETECTION_RADIUS:
			alert += delta * 70.0
	if alert >= ALERT_LIMIT:
		_finish(false, "guard alarm triggered")
		return
	if not intel.is_empty() and player.global_position.distance_to(intel[0]) <= 17.0:
		intel.remove_at(0)
		collected += 1
	elif intel.is_empty() and player.global_position.distance_to(safe_exit) <= 17.0:
		_finish(true, "intel=%d alert=%d" % [collected, int(alert)])
	alert = maxf(0.0, alert - delta * 5.0)


func _hud_status() -> String:
	return "Intel: %d/3 | Suspicion: %d%% | Reach the extraction route" % [
		collected, int(alert)
	]


func _draw_objectives() -> void:
	for point in intel:
		draw_rect(Rect2(point - Vector2(12, 12), Vector2(24, 24)), TARGET_COLOR)
	draw_circle(safe_exit, 20.0, GOAL_COLOR)
	for i in range(guards.size()):
		var pos: Vector2 = guards[i] + Vector2(
			sin(guard_phase + float(i) * 1.7) * 30.0,
			cos(guard_phase * 0.7 + float(i)) * 40.0
		)
		draw_circle(pos, 12.0, Color(0.95, 0.22, 0.28))
		if SHOW_GUARD_ZONES:
			draw_arc(pos, GUARD_DETECTION_RADIUS, 0.0, TAU, 48, Color(1.0, 0.28, 0.3, 0.45), 2.0)
'''

_CRAFTING = r'''
## Craft supply packs from real resources, then deliver to the market.
## Progress only increments after gathering both components at the bench.
const REQUIRED_DELIVERIES := 2
const CONTACT_RADIUS := 16.0
var wood := Vector2(-170, -120)
var ore := Vector2(180, -120)
var bench := Vector2(0, 150)
var market := Vector2(230, 160)
var stage: String = "gather_wood"
var completed: int = 0
var wood_count: int = 0
var ore_count: int = 0
var packed: bool = false


func _tick(_delta: float) -> void:
	match stage:
		"gather_wood":
			player.autopilot_target = wood
			if player.global_position.distance_to(wood) <= CONTACT_RADIUS:
				wood_count += 1
				stage = "gather_ore"
		"gather_ore":
			player.autopilot_target = ore
			if player.global_position.distance_to(ore) <= CONTACT_RADIUS:
				ore_count += 1
				stage = "craft"
		"craft":
			player.autopilot_target = bench
			if player.global_position.distance_to(bench) <= CONTACT_RADIUS:
				if wood_count > 0 and ore_count > 0:
					wood_count -= 1
					ore_count -= 1
					packed = true
					stage = "deliver"
		"deliver":
			player.autopilot_target = market
			if packed and player.global_position.distance_to(market) <= CONTACT_RADIUS:
				packed = false
				completed += 1
				stage = "gather_wood"
	if completed >= REQUIRED_DELIVERIES:
		_finish(true, "delivered crafted packs=%d" % completed)


func _hud_status() -> String:
	return "Crafted packs: %d/%d | Wood: %d | Ore: %d | Task: %s" % [
		completed, REQUIRED_DELIVERIES, wood_count, ore_count, stage
	]


func _draw_objectives() -> void:
	draw_rect(Rect2(wood - Vector2(18, 18), Vector2(36, 36)), Color(0.64, 0.38, 0.18))
	draw_rect(Rect2(ore - Vector2(18, 18), Vector2(36, 36)), TARGET_COLOR)
	draw_circle(bench, 23.0, Color(0.4, 0.68, 0.97))
	draw_circle(market, 23.0, GOAL_COLOR)
'''

EXTRA_ARCHETYPE_SPECS: Final[dict[str, tuple[str, float, int, str]]] = {
    "puzzle": (
        _PUZZLE, 270.0, 2500,
        "Activate four pressure pads in sequence to unlock the exit",
    ),
    "racing": (
        _RACING, 350.0, 3500,
        "Race four checkpoints over three complete laps before each timer expires",
    ),
    "survival": (
        _SURVIVAL, 290.0, 2500,
        "Gather water supplies, manage hydration and reach the shelter",
    ),
    "stealth": (
        _STEALTH, 290.0, 3100,
        "Avoid patrolling guards, collect three intel caches and escape",
    ),
    "crafting": (
        _CRAFTING, 320.0, 3100,
        "Gather wood and ore, craft supply packs and complete two deliveries",
    ),
}

__all__ = ["EXTRA_ARCHETYPE_SPECS"]
