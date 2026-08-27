"""Godot materialiser — turn a compiled era pack + blueprint into project files.

Produces a dict of relative path → text. No Godot binary required; the
godot_engine pipeline can later import/check these files.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _gd_recipes(recipes: List[dict]) -> str:
    lines = []
    for r in recipes:
        parts = ", ".join(f'"{p}"' for p in r.get("parts") or [])
        lines.append(
            '	{"id": "%s", "family": "%s", "parts": [%s], "damage": %s, "heat": %s, "rpm": %s}'
            % (r.get("id"), r.get("family"), parts, r.get("damage"), r.get("heat"), r.get("rpm"))
        )
    return "var known_recipes: Array = [\n" + ",\n".join(lines) + "\n]\n"


def emit_godot(
    pack: Dict[str, Any],
    *,
    title: str = "FORGE-RUN",
    build_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
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
    plan = build_plan or {}
    hw = pack.get("hardware") or {}
    vw, vh = (hw.get("viewport") or [1280, 720])[:2]
    files: Dict[str, str] = {}
    files["project.godot"] = (
        '; Engine configuration file.\n'
        'config_version=5\n\n'
        '[application]\n'
        f'config/name="{title}"\n'
        'run/main_scene="res://scenes/levels/run_level.tscn"\n'
        'config/features=PackedStringArray("4.3")\n\n'
        '[display]\n'
        f'window/size/viewport_width={int(vw)}\n'
        f'window/size/viewport_height={int(vh)}\n'
        f'window/stretch/mode="{"viewport" if hw.get("pixel_snap") else "canvas_items"}"\n\n'
        '[autoload]\n'
        'EventBus="*res://scripts/autoloads/event_bus.gd"\n'
        'HeatSystem="*res://scripts/autoloads/heat_system.gd"\n'
        'ForgeManager="*res://scripts/autoloads/forge_manager.gd"\n'
        'GameState="*res://scripts/autoloads/game_state.gd"\n'
        'Jeeves="*res://scripts/autoloads/jeeves.gd"\n'
        'InputBind="*res://scripts/autoloads/input_bind.gd"\n'
        f'\n; era={era} generation={hw.get("key", "modern")}\n'
    )
    files["scripts/autoloads/event_bus.gd"] = (
        "extends Node\n"
        "signal heat_changed(current: float, max_heat: float)\n"
        "signal heat_critical()\n"
        "signal advice_issued(text: String, priority: int)\n"
        "signal run_ended(success: bool)\n"
        "signal data_core_picked(core: Dictionary)\n"
        "signal room_entered(room_id: String)\n"
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
    armed = bool(plan.get("spawn_weapon"))
    files["scripts/autoloads/game_state.gd"] = (
        "extends Node\n"
        "enum RunPhase { IDLE, RUNNING, EXTRACTING, FAILED, SUCCESS }\n"
        "var phase: RunPhase = RunPhase.IDLE\n"
        "var player_alive: bool = true\n"
        f"var collapse_max: float = {collapse}\n"
        "var collapse_timer: float = collapse_max\n"
        "var data_cores_held: Array = []\n"
        f"var spawn_weapon: bool = {str(armed).lower()}\n"
        f"var current_room: String = \"r00\"\n"
        f"var generation: String = \"{hw.get('key') or 'modern'}\"\n\n"
        "func start_run() -> void:\n"
        "	phase = RunPhase.RUNNING\n"
        "	player_alive = true\n"
        "	collapse_timer = collapse_max\n"
        "	data_cores_held.clear()\n\n"
        "func enter_room(rid: String) -> void:\n"
        "	current_room = rid\n"
        "	EventBus.room_entered.emit(rid)\n\n"
        "func _process(delta: float) -> void:\n"
        "	if phase != RunPhase.RUNNING:\n"
        "		return\n"
        "	collapse_timer -= delta\n"
        "	if collapse_timer <= 0.0:\n"
        "		phase = RunPhase.FAILED\n"
        "		player_alive = false\n"
        "		EventBus.run_ended.emit(false)\n"
    )
    briefing = (plan.get("briefing") or "Jeeves online.").replace('"', "'")
    files["scripts/autoloads/jeeves.gd"] = (
        "extends Node\n"
        "## Jeeves — tactical AI (era-weighted) + builder briefing\n"
        f"const W_HEAT_RISING := {float(jeeves.get('heat_rising', 0.65))}\n"
        f"const W_HEAT_CRITICAL := {float(jeeves.get('heat_critical', 0.92))}\n"
        f"const W_CD_NORMAL := {float(jeeves.get('advice_cooldown_normal', 4.5))}\n"
        f'const BRIEFING := "{briefing}"\n'
        "var _cd: float = 0.0\n"
        "var _briefed: bool = false\n\n"
        "func _process(delta: float) -> void:\n"
        "	if not _briefed:\n"
        "		EventBus.advice_issued.emit(BRIEFING, 1)\n"
        "		_briefed = true\n"
        "		_cd = W_CD_NORMAL\n"
        "		return\n"
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
    files["scripts/autoloads/input_bind.gd"] = (
        "extends Node\n"
        "## Binds WASD/arrows/shift/space so empty project.godot events still play.\n"
        "func _ready() -> void:\n"
        "	_add(\"move_left\", KEY_A)\n"
        "	_add(\"move_left\", KEY_LEFT)\n"
        "	_add(\"move_right\", KEY_D)\n"
        "	_add(\"move_right\", KEY_RIGHT)\n"
        "	_add(\"move_up\", KEY_W)\n"
        "	_add(\"move_up\", KEY_UP)\n"
        "	_add(\"move_down\", KEY_S)\n"
        "	_add(\"move_down\", KEY_DOWN)\n"
        "	_add(\"sprint\", KEY_SHIFT)\n"
        "	_add(\"fire\", KEY_SPACE)\n\n"
        "func _add(action: String, keycode: int) -> void:\n"
        "	if not InputMap.has_action(action):\n"
        "		InputMap.add_action(action)\n"
        "	var ev := InputEventKey.new()\n"
        "	ev.keycode = keycode\n"
        "	InputMap.action_add_event(action, ev)\n"
    )
    files["scripts/player/player_controller.gd"] = (
        "extends CharacterBody2D\n"
        f"@export var speed: float = {speed}\n"
        f"@export var sprint_multiplier: float = {sprint_m}\n"
        "@export var acceleration: float = 1200.0\n"
        "@export var friction: float = 900.0\n"
        "@export var fire_family: String = \"kinetic\"\n\n"
        "func _ready() -> void:\n"
        "	add_to_group(\"player\")\n"
        "	GameState.start_run()\n\n"
        "func _physics_process(delta: float) -> void:\n"
        "	var dir := Input.get_vector(\"move_left\", \"move_right\", \"move_up\", \"move_down\")\n"
        "	var sprinting := Input.is_action_pressed(\"sprint\")\n"
        "	var v := speed * (sprint_multiplier if sprinting else 1.0)\n"
        "	if dir != Vector2.ZERO:\n"
        "		velocity = velocity.move_toward(dir * v, acceleration * delta)\n"
        "	else:\n"
        "		velocity = velocity.move_toward(Vector2.ZERO, friction * delta)\n"
        "	if sprinting:\n"
        "		HeatSystem.add_sprint_heat(delta)\n"
        "	if Input.is_action_just_pressed(\"fire\"):\n"
        "		HeatSystem.add_weapon_heat(fire_family)\n"
        "		_try_hit()\n"
        "	move_and_slide()\n\n"
        "func _try_hit() -> void:\n"
        "	for n in get_tree().get_nodes_in_group(\"enemy\"):\n"
        "		if n.global_position.distance_to(global_position) < 96.0 and n.has_method(\"take_damage\"):\n"
        "			n.take_damage(18.0)\n"
        "			break\n"
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
        "	add_to_group(\"enemy\")\n"
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
        "	$Room.text = \"ROOM %s\" % GameState.current_room\n"
        "	$Gen.text = GameState.generation\n"
    )
    files["export_presets.cfg"] = (
        "[preset.0]\nname=\"Linux/X11\"\nplatform=\"Linux/X11\"\nrunnable=true\n"
        "export_path=\"builds/linux/game.x86_64\"\n\n"
        "[preset.1]\nname=\"Windows Desktop\"\nplatform=\"Windows Desktop\"\nrunnable=true\n"
        "export_path=\"builds/windows/game.exe\"\n\n"
        "[preset.2]\nname=\"Web\"\nplatform=\"Web\"\nrunnable=false\n"
        "export_path=\"builds/web/index.html\"\n"
    )
    files["scripts/extract/extract_zone.gd"] = (
        "extends Area2D\n"
        "func _ready() -> void:\n"
        "	body_entered.connect(_on_body_entered)\n\n"
        "func _on_body_entered(body: Node) -> void:\n"
        "	if body.is_in_group(\"player\"):\n"
        "		GameState.phase = GameState.RunPhase.SUCCESS\n"
        "		EventBus.run_ended.emit(true)\n"
    )
    files["scripts/world/heat_zone.gd"] = (
        "extends Area2D\n"
        "func _ready() -> void:\n"
        "	add_to_group(\"heat_zone\")\n\n"
        "func _process(delta: float) -> void:\n"
        "	for b in get_overlapping_bodies():\n"
        "		if b.is_in_group(\"player\"):\n"
        "			HeatSystem.add_sprint_heat(delta)\n"
    )
    files["scenes/player.tscn"] = (
        "[gd_scene load_steps=3 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://scripts/player/player_controller.gd\" id=\"1\"]\n"
        "[sub_resource type=\"RectangleShape2D\" id=\"body\"]\n"
        "size = Vector2(24, 32)\n"
        "[node name=\"Player\" type=\"CharacterBody2D\"]\n"
        "script = ExtResource(\"1\")\n"
        "[node name=\"Body\" type=\"CollisionShape2D\" parent=\".\"]\n"
        "shape = SubResource(\"body\")\n"
        "[node name=\"Cam\" type=\"Camera2D\" parent=\".\"]\n"
        "position_smoothing_enabled = true\n"
    )
    files["scenes/enemy.tscn"] = (
        "[gd_scene load_steps=3 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://scripts/combat/enemy.gd\" id=\"1\"]\n"
        "[sub_resource type=\"RectangleShape2D\" id=\"body\"]\n"
        "size = Vector2(28, 28)\n"
        "[node name=\"Enemy\" type=\"CharacterBody2D\" groups=[\"enemy\"]]\n"
        "script = ExtResource(\"1\")\n"
        "[node name=\"Body\" type=\"CollisionShape2D\" parent=\".\"]\n"
        "shape = SubResource(\"body\")\n"
    )
    files["scenes/extract.tscn"] = (
        "[gd_scene load_steps=3 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://scripts/extract/extract_zone.gd\" id=\"1\"]\n"
        "[sub_resource type=\"RectangleShape2D\" id=\"zone\"]\n"
        "size = Vector2(80, 80)\n"
        "[node name=\"Extract\" type=\"Area2D\"]\n"
        "script = ExtResource(\"1\")\n"
        "[node name=\"Body\" type=\"CollisionShape2D\" parent=\".\"]\n"
        "shape = SubResource(\"zone\")\n"
    )
    files["scenes/heat_zone.tscn"] = (
        "[gd_scene load_steps=3 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://scripts/world/heat_zone.gd\" id=\"1\"]\n"
        "[sub_resource type=\"RectangleShape2D\" id=\"zone\"]\n"
        "size = Vector2(200, 200)\n"
        "[node name=\"HeatZone\" type=\"Area2D\"]\n"
        "script = ExtResource(\"1\")\n"
        "[node name=\"Body\" type=\"CollisionShape2D\" parent=\".\"]\n"
        "shape = SubResource(\"zone\")\n"
    )
    files["scripts/world/door.gd"] = (
        "extends Area2D\n"
        "@export var dest_room: String = \"\"\n"
        "@export var dest_x: float = 0.0\n"
        "@export var dest_y: float = 0.0\n"
        "var _lock: float = 0.0\n\n"
        "func _ready() -> void:\n"
        "	body_entered.connect(_on)\n\n"
        "func _process(delta: float) -> void:\n"
        "	_lock = max(0.0, _lock - delta)\n\n"
        "func _on(body: Node) -> void:\n"
        "	if _lock > 0.0:\n"
        "		return\n"
        "	if body.is_in_group(\"player\") and dest_room != \"\":\n"
        "		var root := get_tree().current_scene\n"
        "		var room := root.get_node_or_null(\"Room_\" + dest_room)\n"
        "		if room:\n"
        "			_lock = 0.45\n"
        "			body.global_position = room.global_position + Vector2(dest_x, dest_y)\n"
        "			GameState.enter_room(dest_room)\n"
    )
    files["scenes/door.tscn"] = (
        "[gd_scene load_steps=3 format=3]\n"
        "[ext_resource type=\"Script\" path=\"res://scripts/world/door.gd\" id=\"1\"]\n"
        "[sub_resource type=\"RectangleShape2D\" id=\"zone\"]\n"
        "size = Vector2(48, 48)\n"
        "[node name=\"Door\" type=\"Area2D\"]\n"
        "script = ExtResource(\"1\")\n"
        "[node name=\"Body\" type=\"CollisionShape2D\" parent=\".\"]\n"
        "shape = SubResource(\"zone\")\n"
    )
    files["project.godot"] += (
        "\n[input]\n"
        "move_left={\"deadzone\": 0.5, \"events\": []}\n"
        "move_right={\"deadzone\": 0.5, \"events\": []}\n"
        "move_up={\"deadzone\": 0.5, \"events\": []}\n"
        "move_down={\"deadzone\": 0.5, \"events\": []}\n"
        "sprint={\"deadzone\": 0.5, \"events\": []}\n"
        "fire={\"deadzone\": 0.5, \"events\": []}\n"
    )
    from skeleton.forge.world import generate_rooms, assert_connected, assert_occupancy
    graph = generate_rooms(pack, seed=str(plan.get("seed") or pack.get("era")), plan=plan)
    assert_connected(graph)
    assert_occupancy(graph)
    files["data/rooms.json"] = json.dumps(graph, indent=2)
    files["data/build_plan.json"] = json.dumps(plan, indent=2)
    files["data/hardware.json"] = json.dumps(hw, indent=2)
    files["scenes/levels/run_level.tscn"] = _level_tscn(graph, hw)
    files["scripts/world/world_map.gd"] = _world_map_gd(plan, graph)
    return files


def _world_map_gd(plan: Dict[str, Any], graph: Optional[Dict[str, Any]] = None) -> str:
    era = (plan.get("era") or (graph or {}).get("era") or "extraction_now")
    seed = plan.get("seed") or (graph or {}).get("seed") or era
    n = int((graph or {}).get("count") or 0)
    rooms = (graph or {}).get("rooms") or []
    edges = (graph or {}).get("edges") or []
    room_lits = []
    for r in rooms:
        room_lits.append(
            '{"id": "%s", "kind": "%s", "x": %s, "y": %s}'
            % (r["id"], r["kind"], r.get("x", 0), r.get("y", 0))
        )
    edge_lits = ['{"from": "%s", "to": "%s"}' % (e["from"], e["to"]) for e in edges]
    rooms_s = ", ".join(room_lits) or ""
    edges_s = ", ".join(edge_lits) or ""
    return (
        "extends Node2D\n"
        "## WorldMap — instanced room graph (Jeeves BuildPlan)\n"
        f'const ERA := "{era}"\n'
        f'const SEED := "{seed}"\n'
        f"const ROOM_COUNT := {n}\n"
        f"var rooms: Array = [{rooms_s}]\n"
        f"var edges: Array = [{edges_s}]\n\n"
        "func _ready() -> void:\n"
        "	if rooms.size() > 0:\n"
        "		GameState.current_room = rooms[0].id\n"
        "		EventBus.room_entered.emit(rooms[0].id)\n"
    )


def _level_tscn(graph: Dict[str, Any], hardware: Optional[Dict[str, Any]] = None) -> str:
    """Instance every room + occupant + live doors. Floors tinted by generation palette."""
    from skeleton.forge.hardware import hex_to_color
    pal = (hardware or {}).get("palette") or ["#1a1a2e", "#16213e", "#0f3460", "#533483"]
    lines = [
        "[gd_scene load_steps=8 format=3]",
        '[ext_resource type="Script" path="res://scripts/world/world_map.gd" id="1"]',
        '[ext_resource type="Script" path="res://scripts/ui/hud.gd" id="2"]',
        '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="3"]',
        '[ext_resource type="PackedScene" path="res://scenes/enemy.tscn" id="4"]',
        '[ext_resource type="PackedScene" path="res://scenes/extract.tscn" id="5"]',
        '[ext_resource type="PackedScene" path="res://scenes/heat_zone.tscn" id="6"]',
        '[ext_resource type="PackedScene" path="res://scenes/door.tscn" id="7"]',
        '[node name="RunLevel" type="Node2D"]',
        'script = ExtResource("1")',
    ]
    enemy_i = 0
    for i, room in enumerate(graph["rooms"]):
        rid = room["id"]
        hx = pal[i % len(pal)]
        r, g, b = hex_to_color(hx)
        lines.append(f'[node name="Room_{rid}" type="Node2D" parent="."]')
        lines.append(f'position = Vector2({int(room.get("x", 0))}, {int(room.get("y", 0))})')
        lines.append(f'[node name="Floor" type="ColorRect" parent="Room_{rid}"]')
        lines.append("offset_left = -320.0")
        lines.append("offset_top = -180.0")
        lines.append("offset_right = 320.0")
        lines.append("offset_bottom = 180.0")
        lines.append(f"color = Color({r:.4f}, {g:.4f}, {b:.4f}, 1)")
        ox = 0
        for occ in room.get("occupants") or []:
            kind = occ.get("kind")
            if kind == "player":
                lines.append(f'[node name="Player" parent="Room_{rid}" instance=ExtResource("3")]')
                lines.append("position = Vector2(0, 0)")
            elif kind == "enemy":
                enemy_i += 1
                tier = occ.get("tier") or "trash"
                name = f"Enemy_{rid}_{enemy_i}"
                lines.append(f'[node name="{name}" parent="Room_{rid}" instance=ExtResource("4")]')
                lines.append(f"position = Vector2({ox}, 0)")
                lines.append(f'tier = "{tier}"')
                ox += 36
            elif kind == "extract":
                lines.append(f'[node name="Extract" parent="Room_{rid}" instance=ExtResource("5")]')
                lines.append("position = Vector2(0, 0)")
            elif kind == "heat":
                lines.append(f'[node name="HeatZone" parent="Room_{rid}" instance=ExtResource("6")]')
                lines.append("position = Vector2(0, 0)")
            elif kind == "loot":
                lines.append(f'[node name="Loot" type="Marker2D" parent="Room_{rid}"]')
                lines.append("position = Vector2(0, 0)")
    for d in graph.get("doors") or []:
        a, b = d["from"], d["to"]
        lines.append(f'[node name="Door_{a}_{b}" parent="Room_{a}" instance=ExtResource("7")]')
        lines.append(f'position = Vector2({int(d.get("x", 0))}, {int(d.get("y", 0))})')
        lines.append(f'dest_room = "{b}"')
        lines.append(f'dest_x = {float(d.get("dest_x", 0))}')
        lines.append(f'dest_y = {float(d.get("dest_y", 0))}')
    lines.extend([
        '[node name="HUD" type="CanvasLayer" parent="."]',
        'script = ExtResource("2")',
        '[node name="Heat" type="Label" parent="HUD"]',
        "offset_right = 400.0",
        "offset_bottom = 24.0",
        '[node name="Collapse" type="Label" parent="HUD"]',
        "offset_top = 28.0",
        "offset_right = 400.0",
        "offset_bottom = 52.0",
        '[node name="Room" type="Label" parent="HUD"]',
        "offset_top = 56.0",
        "offset_right = 400.0",
        "offset_bottom = 80.0",
        '[node name="Gen" type="Label" parent="HUD"]',
        "offset_top = 84.0",
        "offset_right = 400.0",
        "offset_bottom = 108.0",
    ])
    return "\n".join(lines) + "\n"
