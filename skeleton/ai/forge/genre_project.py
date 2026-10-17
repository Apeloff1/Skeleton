"""Attach a headless-playable genre runtime to an emitted Godot project.

``execute_core_loop`` and ``CORE_LOOP_GD`` implement the same rules. The
GDScript copy runs inside Godot and prints ``CORE_LOOP_OK``. The Python copy
is the oracle the repair loop and the golden tests check first.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

CORE_LOOP_PATH = "scripts/autoloads/core_loop.gd"
DESIGN_SPEC_PATH = "data/design_spec.json"
CONTENT_PATH = "data/content_bundle.json"
MARKER_PREFIX = "CORE_LOOP_OK"

# Keep this script aligned with execute_core_loop. Godot JSON numbers may
# arrive as floats; every value is coerced before arithmetic.
CORE_LOOP_GD = """extends Node

func _ready() -> void:
	var spec = _load("res://data/design_spec.json")
	var content = _load("res://data/content_bundle.json")
	var genre = str(spec.get("genre", ""))
	var marker = _marker(genre, content)
	print("CORE_LOOP_OK genre=%s marker=%s" % [genre, marker])

func _load(path: String):
	if not FileAccess.file_exists(path):
		return {}
	var file = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed

func _marker(genre: String, content: Dictionary) -> String:
	var player_hp = int(content.get("player_hp", 100))
	var economy = content.get("economy", {})
	if typeof(economy) != TYPE_DICTIONARY:
		economy = {}
	var gold = int(economy.get("starting_balance", 0))
	if genre == "platformer":
		var reach = float(content.get("jump_reach", 1))
		var x = 0.0
		var steps = content.get("platforms", [])
		if typeof(steps) != TYPE_ARRAY:
			return "stuck"
		for step in steps:
			if typeof(step) != TYPE_DICTIONARY:
				return "stuck"
			var gap = float(step.get("gap", 1))
			if gap > reach:
				return "stuck"
			x += gap
		if x < float(content.get("goal_x", 1)):
			return "short"
		return "goal:%s" % str(int(x))
	var cleared = 0
	var encounters = content.get("encounters", [])
	if typeof(encounters) != TYPE_ARRAY:
		return "dead"
	for enc in encounters:
		if typeof(enc) != TYPE_DICTIONARY:
			return "dead"
		var hp = int(enc.get("hp", 1))
		var dealt = int(enc.get("player_damage", 1))
		var taken = int(enc.get("enemy_damage", 0))
		if dealt < 1:
			return "dead"
		while hp > 0 and player_hp > 0:
			hp -= dealt
			player_hp -= taken
		if player_hp <= 0:
			return "dead"
		cleared += 1
		gold += int(enc.get("loot", 0))
	var sink = int(economy.get("sink_cost", 0))
	if gold < sink:
		return "broke"
	gold -= sink
	if genre == "top_down_shooter":
		return "cleared:%s:gold:%s" % [str(cleared), str(gold)]
	var hooks = content.get("narrative", [])
	if typeof(hooks) != TYPE_ARRAY or hooks.is_empty():
		return "no-hook"
	var hook = hooks[0]
	if typeof(hook) != TYPE_DICTIONARY:
		return "no-hook"
	var levels = content.get("levels", [])
	var count = 0
	if typeof(levels) == TYPE_ARRAY:
		count = levels.size()
	return "rooms:%s:hook:%s" % [str(count), str(hook.get("id", ""))]
"""


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def execute_core_loop(content: Mapping[str, Any], genre: str) -> str:
    """Run the genre core loop and return its marker (no ``CORE_LOOP_OK`` prefix)."""
    if not isinstance(content, Mapping):
        raise ValueError("content bundle must be a mapping")
    player_hp = _as_int(content.get("player_hp"), 100)
    economy = content.get("economy") if isinstance(content.get("economy"), Mapping) else {}
    gold = _as_int(economy.get("starting_balance"), 0)
    if genre == "platformer":
        reach = _as_float(content.get("jump_reach"), 1.0)
        x = 0.0
        steps = content.get("platforms")
        if not isinstance(steps, list):
            return "stuck"
        for step in steps:
            if not isinstance(step, Mapping):
                return "stuck"
            gap = _as_float(step.get("gap"), 1.0)
            if gap > reach:
                return "stuck"
            x += gap
        if x < _as_float(content.get("goal_x"), 1.0):
            return "short"
        return f"goal:{int(x)}"
    cleared = 0
    encounters = content.get("encounters")
    if not isinstance(encounters, list):
        return "dead"
    for enc in encounters:
        if not isinstance(enc, Mapping):
            return "dead"
        hp = _as_int(enc.get("hp"), 1)
        dealt = _as_int(enc.get("player_damage"), 1)
        taken = _as_int(enc.get("enemy_damage"), 0)
        if dealt < 1:
            return "dead"
        while hp > 0 and player_hp > 0:
            hp -= dealt
            player_hp -= taken
        if player_hp <= 0:
            return "dead"
        cleared += 1
        gold += _as_int(enc.get("loot"), 0)
    sink = _as_int(economy.get("sink_cost"), 0)
    if gold < sink:
        return "broke"
    gold -= sink
    if genre == "top_down_shooter":
        return f"cleared:{cleared}:gold:{gold}"
    hooks = content.get("narrative")
    if not isinstance(hooks, list) or not hooks or not isinstance(hooks[0], Mapping):
        return "no-hook"
    levels = content.get("levels")
    count = len(levels) if isinstance(levels, list) else 0
    return f"rooms:{count}:hook:{hooks[0].get('id', '')}"


def loop_succeeded(marker: str) -> bool:
    return isinstance(marker, str) and (
        marker.startswith("goal:") or marker.startswith("cleared:") or marker.startswith("rooms:")
    )


def proof_line(genre: str, marker: str) -> str:
    return f"{MARKER_PREFIX} genre={genre} marker={marker}"


def _dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def register_core_loop(project_godot: str) -> str:
    if not isinstance(project_godot, str) or "config_version=5" not in project_godot:
        raise ValueError("project.godot must be a Godot 4 project file")
    line = f'CoreLoop="*res://{CORE_LOOP_PATH}"\n'
    if 'CoreLoop="*' in project_godot:
        return project_godot
    needle = 'InputBind="*res://scripts/autoloads/input_bind.gd"\n'
    if needle in project_godot:
        return project_godot.replace(needle, needle + line, 1)
    if "[autoload]\n" in project_godot:
        return project_godot.replace("[autoload]\n", "[autoload]\n" + line, 1)
    raise ValueError("project.godot has no autoload section")


def attach_genre(files: Mapping[str, str], spec: Mapping[str, Any], content: Mapping[str, Any]) -> dict[str, str]:
    """Return a new file map with the design spec, content bundle, and core loop."""
    if not isinstance(files, Mapping) or "project.godot" not in files:
        raise ValueError("emitted Godot files are required")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in files.items()):
        raise ValueError("files must map paths to source")
    out = dict(files)
    out["project.godot"] = register_core_loop(out["project.godot"])
    out[DESIGN_SPEC_PATH] = _dump(dict(spec))
    out[CONTENT_PATH] = _dump(dict(content))
    out[CORE_LOOP_PATH] = CORE_LOOP_GD
    return out
