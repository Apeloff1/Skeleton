"""Godot materialiser — turn a compiled era pack + blueprint into project files.

Produces a dict of relative path → text. No Godot binary required; the
godot_engine pipeline can later import/check these files.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _gd_recipes(recipes: List[dict]) -> str:
    lines = []
    for r in recipes:
        parts = ", ".join(f'"{p}"' for p in r.get("parts") or [])
        lines.append(
            '	{"id": "%s", "family": "%s", "parts": [%s], "damage": %s, "heat": %s, "rpm": %s}'
            % (r.get("id"), r.get("family"), parts, r.get("damage"), r.get("heat"), r.get("rpm"))
        )
    return "var known_recipes: Array = [\n" + ",\n".join(lines) + "\n]\n"


def emit_godot(pack: Dict[str, Any], *, title: str = "FORGE-RUN") -> Dict[str, str]:
    heat = pack.get("heat") or {}
    player = pack.get("player") or {}
    jeeves = pack.get("jeeves") or {}
    session = pack.get("session") or {}
    era = pack.get("era", "extraction_now")
    mh = float(heat.get("max_heat") or 100)
    cool = float(heat.get("passive_cool") or 7.5)
    crit = float(heat.get("critical_ratio") or 0.78)
    kin = float(heat.get("kinetic_heat") or 6.2)
    ene = float(heat.get("energy_heat") or 11.5)
    sprint = float(heat.get("sprint_heat_per_sec") or 11.0)
    speed = float(player.get("speed") or 180)
    sprint_m = float(player.get("sprint_multiplier") or 1.4)
    collapse = float(session.get("collapse_max") or 300)
    files: Dict[str, str] = {}
    files["project.godot"] = (
        '; Engine configuration file.\n'
        'config_version=5\n\n'
        '[application]\n'
        f'config/name="{title}"\n'
        'run/main_scene="res://scenes/levels/run_level.tscn"\n'
        'config/features=PackedStringArray("4.3")\n\n'
        '[autoload]\n'
        'EventBus="*res://scripts/autoloads/event_bus.gd"\n'
        'HeatSystem="*res://scripts/autoloads/heat_system.gd"\n'
        'ForgeManager="*res://scripts/autoloads/forge_manager.gd"\n'
        'GameState="*res://scripts/autoloads/game_state.gd"\n'
        'Jeeves="*res://scripts/autoloads/jeeves.gd"\n'
        f'\n; era={era}\n'
    )
    files["scripts/autoloads/event_bus.gd"] = (
        "extends Node\n"
        "signal heat_changed(current: float, max_heat: float)\n"
        "signal heat_critical()\n"
        "signal advice_issued(text: String, priority: int)\n"
        "signal run_ended(success: bool)\n"
        "signal data_core_picked(core: Dictionary)\n"
    )
    files["scripts/autoloads/heat_system.gd"] = (
        "extends Node\n"
        "## HeatSystem — thermal budget (era-compiled)\n"
        "var current_heat: float = 0.0\n"
        f"var max_heat: float = {mh}\n"
        f"var passive_cool: float = {cool}\n\n"
        "func _process(delta: float) -> void:\n"
        "	if current_heat > 0.0:\n"
        "		current_heat = max(0.0, current_heat - passive_cool * delta)\n"
        "		EventBus.heat_changed.emit(current_heat, max_heat)\n"
        f"		if current_heat / max(max_heat, 0.001) >= {crit}:\n"
        "			EventBus.heat_critical.emit()\n\n"
        "func add_weapon_heat(family: String) -> void:\n"
        f"	var amt := {kin}\n"
        "	if family == \"energy\":\n"
        f"		amt = {ene}\n"
        "	current_heat = min(max_heat * 1.15, current_heat + amt)\n\n"
        "func add_sprint_heat(delta: float) -> void:\n"
        f"	current_heat = min(max_heat * 1.15, current_heat + {sprint} * delta)\n\n"
        "func reset() -> void:\n"
        "	current_heat = 0.0\n"
    )
    files["scripts/autoloads/forge_manager.gd"] = (
        "extends Node\n"
        "## ForgeManager — modular weapon assembly\n"
        "var inventory: Array = []\n"
        "var current_weapon: Dictionary = {}\n"
        + _gd_recipes(pack.get("recipes") or [])
        + "\nfunc scavenge(comp: Dictionary) -> void:\n"
        "	inventory.append(comp)\n\n"
        "func can_assemble(recipe_id: String) -> bool:\n"
        "	for r in known_recipes:\n"
        "		if r.id == recipe_id:\n"
        "			return true\n"
        "	return false\n"
    )
    files["scripts/autoloads/game_state.gd"] = (
        "extends Node\n"
        "enum RunPhase { IDLE, RUNNING, EXTRACTING, FAILED, SUCCESS }\n"
        "var phase: RunPhase = RunPhase.IDLE\n"
        "var player_alive: bool = true\n"
        f"var collapse_max: float = {collapse}\n"
        "var collapse_timer: float = collapse_max\n"
        "var data_cores_held: Array = []\n\n"
        "func start_run() -> void:\n"
        "	phase = RunPhase.RUNNING\n"
        "	player_alive = true\n"
        "	collapse_timer = collapse_max\n"
        "	data_cores_held.clear()\n\n"
        "func _process(delta: float) -> void:\n"
        "	if phase != RunPhase.RUNNING:\n"
        "		return\n"
        "	collapse_timer -= delta\n"
        "	if collapse_timer <= 0.0:\n"
        "		phase = RunPhase.FAILED\n"
        "		player_alive = false\n"
        "		EventBus.run_ended.emit(false)\n"
    )
    files["scripts/autoloads/jeeves.gd"] = (
        "extends Node\n"
        "## Jeeves — tactical AI (era-weighted)\n"
        f"const W_HEAT_RISING := {float(jeeves.get('heat_rising', 0.65))}\n"
        f"const W_HEAT_CRITICAL := {float(jeeves.get('heat_critical', 0.92))}\n"
        f"const W_CD_NORMAL := {float(jeeves.get('advice_cooldown_normal', 4.5))}\n"
        "var _cd: float = 0.0\n\n"
        "func _process(delta: float) -> void:\n"
        "	_cd = max(0.0, _cd - delta)\n"
        "	if _cd > 0.0:\n"
        "		return\n"
        "	var ratio := 0.0\n"
        "	if HeatSystem.max_heat > 0.0:\n"
        "		ratio = HeatSystem.current_heat / HeatSystem.max_heat\n"
        "	if ratio >= W_HEAT_CRITICAL:\n"
        "		EventBus.advice_issued.emit(\"Heat critical — vent or swap to kinetic.\", 3)\n"
        "		_cd = W_CD_NORMAL * 0.4\n"
        "	elif ratio >= W_HEAT_RISING:\n"
        "		EventBus.advice_issued.emit(\"Heat rising. Watch the sprint tax.\", 2)\n"
        "		_cd = W_CD_NORMAL\n"
    )
    files["scripts/player/player_controller.gd"] = (
        "extends CharacterBody2D\n"
        f"@export var speed: float = {speed}\n"
        f"@export var sprint_multiplier: float = {sprint_m}\n\n"
        "func _physics_process(delta: float) -> void:\n"
        "	var dir := Input.get_vector(\"ui_left\", \"ui_right\", \"ui_up\", \"ui_down\")\n"
        "	var sprinting := Input.is_action_pressed(\"ui_select\")\n"
        "	var v := speed * (sprint_multiplier if sprinting else 1.0)\n"
        "	velocity = dir * v\n"
        "	if sprinting:\n"
        "		HeatSystem.add_sprint_heat(delta)\n"
        "	move_and_slide()\n"
    )
    enemies = pack.get("enemies") or []
    def _hp(eid, default):
        for e in enemies:
            if e.get("id") == eid:
                return float(e.get("hp") or default)
        return float(default)
    trash_hp, elite_hp, boss_hp = _hp("trash", 100), _hp("elite", 400), _hp("boss", 5000)
    files["scripts/combat/enemy.gd"] = (
        "extends CharacterBody2D\n"
        "class_name ForgeEnemy\n"
        "@export_enum(\"trash\", \"elite\", \"boss\") var tier: String = \"trash\"\n"
        f"var hp_table := {{\"trash\": {trash_hp}, \"elite\": {elite_hp}, \"boss\": {boss_hp}}}\n"
        "var hp: float = 0.0\n\n"
        "func _ready() -> void:\n"
        "	hp = hp_table.get(tier, hp_table[\"trash\"])\n\n"
        "func take_damage(amount: float) -> void:\n"
        "	hp -= amount\n"
        "	if hp <= 0.0:\n"
        "		queue_free()\n"
    )
    files["scripts/ui/hud.gd"] = (
        "extends CanvasLayer\n"
        "func _process(_delta: float) -> void:\n"
        "	$Heat.text = \"HEAT %.0f / %.0f\" % [HeatSystem.current_heat, HeatSystem.max_heat]\n"
        "	$Collapse.text = \"COLLAPSE %.0f\" % GameState.collapse_timer\n"
    )
    files["export_presets.cfg"] = (
        "[preset.0]\nname=\"Linux/X11\"\nplatform=\"Linux/X11\"\nrunnable=true\n"
        "export_path=\"builds/linux/game.x86_64\"\n\n"
        "[preset.1]\nname=\"Windows Desktop\"\nplatform=\"Windows Desktop\"\nrunnable=true\n"
        "export_path=\"builds/windows/game.exe\"\n\n"
        "[preset.2]\nname=\"Web\"\nplatform=\"Web\"\nrunnable=false\n"
        "export_path=\"builds/web/index.html\"\n"
    )
    files["scenes/levels/run_level.tscn"] = (
        "[gd_scene load_steps=2 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://scripts/ui/hud.gd\" id=\"1\"]\n"
        "[node name=\"RunLevel\" type=\"Node2D\"]\n"
        "[node name=\"PlayerSpawn\" type=\"Marker2D\" parent=\".\"]\n"
        "position = Vector2(640, 360)\n"
        "[node name=\"HUD\" type=\"CanvasLayer\" parent=\".\"]\n"
        "script = ExtResource(\"1\")\n"
        "[node name=\"Heat\" type=\"Label\" parent=\"HUD\"]\n"
        "offset_right = 400.0\n"
        "offset_bottom = 24.0\n"
        "[node name=\"Collapse\" type=\"Label\" parent=\"HUD\"]\n"
        "offset_top = 28.0\n"
        "offset_right = 400.0\n"
        "offset_bottom = 52.0\n"
    )
    # input map — keep move/sprint off ui_* so the export is a real project
    files["project.godot"] += (
        "\n[input]\n"
        "move_left={\"deadzone\": 0.5, \"events\": []}\n"
        "move_right={\"deadzone\": 0.5, \"events\": []}\n"
        "move_up={\"deadzone\": 0.5, \"events\": []}\n"
        "move_down={\"deadzone\": 0.5, \"events\": []}\n"
        "sprint={\"deadzone\": 0.5, \"events\": []}\n"
        "fire={\"deadzone\": 0.5, \"events\": []}\n"
    )
    return files
