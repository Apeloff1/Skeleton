"""Input-driven Godot games attached by the existing Forge materialiser.

The old CoreLoop autoload is a deterministic content-table proof. This module
adds a separate visible game scene; starting that scene never wins the game.
Only validated design data is consumed. All executable source is maintained
here, never supplied by a model or downloaded with the generated project.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from skeleton.forge.game_design_spec import gameplay_for_spec

RUNTIME_PATH = "scripts/runtime/playable_game.gd"
SCENE_PATH = "scenes/gameplay.tscn"
SMOKE_PATH = "scripts/runtime/interactive_smoke.gd"
INTERACTIVE_SCHEMA = "skeleton.forge.interactive-game.v1"


PLAYABLE_GD = r'''extends Node2D
## Maintained Forge runtime. JSON is design data, never executable source.
const WORLD: Vector2 = Vector2(1120.0, 720.0)
const ARENA: Rect2 = Rect2(54.0, 166.0, 1012.0, 464.0)
const PALETTES: Dictionary = {
    "moss": ["#101f25", "#1a3438", "#35534e", "#8fe4ba", "#efbc7b", "#ef8580"],
    "neon": ["#101526", "#1c2545", "#39416c", "#93e6f2", "#d6a5ff", "#ff799d"],
    "ember": ["#23181f", "#3b2730", "#704439", "#f7c489", "#eaa88d", "#f38379"],
    "frost": ["#111e30", "#213951", "#3c6074", "#b6eeed", "#b9c6ff", "#f08caa"]
}
var spec: Dictionary = {}
var content: Dictionary = {}
var settings: Dictionary = {}
var genre: String = "top_down_shooter"
var title: String = "A small adventure"
var objective: String = "Clear the encounters and reach the exit"
var palette: Array = []
var player: Vector2 = Vector2(560.0, 410.0)
var velocity: Vector2 = Vector2.ZERO
var aim: Vector2 = Vector2.RIGHT
var aim_target: Vector2 = Vector2(800.0, 410.0)
var pointer_aim: bool = false
var speed: float = 230.0
var hp: float = 100.0
var elapsed: float = 0.0
var phase: String = "playing"
var paused: bool = false
var score: int = 0
var salvage: int = 0
var defeated: int = 0
var wave: int = 1
var wave_count: int = 3
var relics: int = 0
var room: int = 1
var relic_position: Vector2 = Vector2(850.0, 410.0)
var relic_available: bool = false
var relic_taken: bool = false
var exit_position: Vector2 = Vector2(1000.0, 400.0)
var enemies: Array = []
var bullets: Array = []
var pickups: Array = []
var particles: Array = []
var obstacles: Array = []
var shot_timer: float = 0.0
var hurt_timer: float = 0.0
var dash_timer: float = 0.0
var dash_cooldown: float = 0.0
var wave_wait: float = 0.0
var melee_flash: float = 0.0
var shake: float = 0.0
var flash: float = 0.0
var notice: String = ""
var notice_time: float = 0.0
var enemy_scale: float = 1.0
var damage_scale: float = 1.0
var rng: RandomNumberGenerator = RandomNumberGenerator.new()
var seed_value: int = 0
var frames_played: int = 0
var input_frames: int = 0
var shots_fired: int = 0
var jumps: int = 0
var restart_count: int = 0
var platforms: Array = []
var spikes: Array = []
var gems: Array = []
var walkers: Array = []
var checkpoints: Array = []
var checkpoint: Vector2 = Vector2(120.0, 560.0)
var checkpoint_index: int = -1
var grounded: bool = false
var coyote: float = 0.0
var jump_buffer: float = 0.0
var camera_x: float = 0.0
var goal_x: float = 2500.0
var gem_goal: int = 5
var collected: int = 0

func _ready() -> void:
    spec = _read_json("res://data/design_spec.json")
    content = _read_json("res://data/content_bundle.json")
    settings = _read_json("res://data/interactive_runtime.json").get("gameplay", {})
    genre = str(spec.get("genre", "top_down_shooter"))
    title = str(spec.get("title", "A small adventure")).substr(0, 70)
    objective = str(settings.get("objective_label", "Reach the exit")).substr(0, 100)
    speed = clampf(float(settings.get("player_speed", 230)), 120.0, 360.0)
    palette = PALETTES.get(str(settings.get("theme", "moss")), PALETTES["moss"])
    seed_value = str(spec.get("spec_id", "1")).left(8).hex_to_int()
    var difficulty: String = str(settings.get("difficulty", "normal"))
    enemy_scale = 0.78 if difficulty == "easy" else 1.2 if difficulty == "hard" else 1.0
    damage_scale = 0.65 if difficulty == "easy" else 1.35 if difficulty == "hard" else 1.0
    _bind_inputs()
    _reset(false)

func _read_json(path: String) -> Dictionary:
    var file: FileAccess = FileAccess.open(path, FileAccess.READ)
    if file == null:
        return {}
    var parsed: Variant = JSON.parse_string(file.get_as_text())
    return parsed if parsed is Dictionary else {}

func _bind_inputs() -> void:
    var keys: Dictionary = {
        "forge_left": [KEY_A, KEY_LEFT], "forge_right": [KEY_D, KEY_RIGHT],
        "forge_up": [KEY_W, KEY_UP], "forge_down": [KEY_S, KEY_DOWN],
        "forge_jump": [KEY_SPACE, KEY_W, KEY_UP], "forge_fire": [KEY_SPACE, KEY_F],
        "forge_dash": [KEY_SHIFT], "forge_pause": [KEY_ESCAPE, KEY_P],
        "forge_restart": [KEY_R], "forge_interact": [KEY_E, KEY_ENTER]
    }
    for action: String in keys:
        if not InputMap.has_action(action):
            InputMap.add_action(action)
        for key: int in keys[action]:
            var event: InputEventKey = InputEventKey.new()
            event.physical_keycode = key
            if not InputMap.action_has_event(action, event):
                InputMap.action_add_event(action, event)
    var mouse: InputEventMouseButton = InputEventMouseButton.new()
    mouse.button_index = MOUSE_BUTTON_LEFT
    if not InputMap.action_has_event("forge_fire", mouse):
        InputMap.action_add_event("forge_fire", mouse)

func _reset(count_restart: bool = true) -> void:
    if count_restart:
        restart_count += 1
    rng.seed = seed_value
    hp = 100.0
    elapsed = 0.0
    phase = "playing"
    paused = false
    score = 0
    salvage = 0
    defeated = 0
    wave = 1
    room = 1
    relics = 0
    frames_played = 0
    input_frames = 0
    shots_fired = 0
    jumps = 0
    collected = 0
    shot_timer = 0.0
    hurt_timer = 0.0
    dash_timer = 0.0
    dash_cooldown = 0.0
    wave_wait = 0.0
    melee_flash = 0.0
    shake = 0.0
    flash = 0.0
    pointer_aim = false
    aim = Vector2.RIGHT
    velocity = Vector2.ZERO
    player = Vector2(560.0, 410.0)
    bullets.clear()
    pickups.clear()
    particles.clear()
    enemies.clear()
    obstacles.clear()
    wave_count = 3 if str(spec.get("scope", "small")) == "small" else 4
    _say("Follow the signal. Make it back.", 3.5)
    if genre == "platformer":
        _build_platforms()
    else:
        _begin_encounter()
    queue_redraw()

func _say(text: String, seconds: float = 2.0) -> void:
    notice = text
    notice_time = seconds

func _physics_process(delta: float) -> void:
    if Input.is_action_just_pressed("forge_restart"):
        _reset()
    if Input.is_action_just_pressed("forge_pause") and phase == "playing":
        paused = not paused
    if phase != "playing" or paused:
        queue_redraw()
        return
    frames_played += 1
    elapsed += delta
    shot_timer = maxf(0.0, shot_timer - delta)
    hurt_timer = maxf(0.0, hurt_timer - delta)
    dash_timer = maxf(0.0, dash_timer - delta)
    dash_cooldown = maxf(0.0, dash_cooldown - delta)
    melee_flash = maxf(0.0, melee_flash - delta)
    shake = maxf(0.0, shake - delta * 22.0)
    flash = maxf(0.0, flash - delta * 2.0)
    notice_time = maxf(0.0, notice_time - delta)
    var direction: Vector2 = Input.get_vector("forge_left", "forge_right", "forge_up", "forge_down")
    if direction.length_squared() > 0.0 or Input.is_action_pressed("forge_fire") or Input.is_action_pressed("forge_jump"):
        input_frames += 1
    if genre == "platformer":
        _platform_tick(delta, direction.x)
    else:
        _arena_tick(delta, direction)
    _effects_tick(delta)
    if hp <= 0.0 and phase == "playing":
        _finish(false)
    queue_redraw()

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseMotion:
        aim_target = screen_to_world(event.position)
        pointer_aim = true
    if event is InputEventMouseButton and event.pressed:
        aim_target = screen_to_world(event.position)
        pointer_aim = true

func screen_to_world(point: Vector2) -> Vector2:
    var scale_value: float = minf(get_viewport_rect().size.x / WORLD.x, get_viewport_rect().size.y / WORLD.y)
    var margin: Vector2 = (get_viewport_rect().size - WORLD * scale_value) * 0.5
    return (point - margin) / maxf(scale_value, 0.001)

func world_to_screen(point: Vector2) -> Vector2:
    var scale_value: float = minf(get_viewport_rect().size.x / WORLD.x, get_viewport_rect().size.y / WORLD.y)
    return point * scale_value + (get_viewport_rect().size - WORLD * scale_value) * 0.5

func _begin_encounter() -> void:
    enemies.clear()
    bullets.clear()
    obstacles.clear()
    relic_available = false
    relic_taken = false
    var count: int = 3 + wave if genre == "top_down_shooter" else 2 + room
    var stage: int = wave if genre == "top_down_shooter" else room
    if genre == "rpg_roguelike":
        obstacles = [Rect2(330.0, 290.0, 82.0, 76.0), Rect2(700.0, 452.0, 94.0, 72.0)]
        player = Vector2(160.0, 410.0)
    for index: int in range(count):
        var angle: float = float(index) * TAU / float(count) + float(stage) * 0.4
        var position_value: Vector2 = Vector2(560.0, 410.0) + Vector2.from_angle(angle) * 220.0
        if genre == "rpg_roguelike":
            position_value = Vector2(540.0 + float(index % 3) * 150.0, 250.0 + float(index / 3) * 200.0)
        var style: String = str(settings.get("encounter_style", "patrol"))
        var kind: String = "ranged" if style == "ranged" or (index == count - 1 and stage > 1) else style
        var health: float = (24.0 + float(stage) * 5.0) * enemy_scale
        enemies.append({"pos": position_value, "hp": health, "max_hp": health,
            "kind": kind, "cooldown": 0.8 + float(index) * 0.3,
            "angle": angle, "flash": 0.0})
    wave_wait = 0.0
    _say(("Signal wave %d / %d" % [wave, wave_count]) if genre == "top_down_shooter" else ("Chamber %d / %d · recover the relic" % [room, wave_count]), 3.0)

func _arena_tick(delta: float, direction: Vector2) -> void:
    if pointer_aim and aim_target.distance_to(player) > 2.0:
        aim = (aim_target - player).normalized()
    elif direction.length_squared() > 0.0:
        aim = direction.normalized()
    if Input.is_action_just_pressed("forge_dash") and dash_cooldown <= 0.0:
        dash_timer = 0.17
        dash_cooldown = 1.45
        velocity = (direction.normalized() if direction.length_squared() > 0.0 else aim) * speed * 3.5
        _burst(player, _ink(3), 8)
    if dash_timer <= 0.0:
        velocity = velocity.move_toward(direction * speed, delta * 1800.0)
    var next: Vector2 = player + velocity * delta
    next.x = clampf(next.x, ARENA.position.x + 16.0, ARENA.end.x - 16.0)
    next.y = clampf(next.y, ARENA.position.y + 16.0, ARENA.end.y - 16.0)
    for stone: Rect2 in obstacles:
        if stone.grow(14.0).has_point(next):
            var horizontal: Vector2 = Vector2(next.x, player.y)
            next = horizontal if not stone.grow(14.0).has_point(horizontal) else Vector2(player.x, next.y)
            if stone.grow(14.0).has_point(next):
                next = player
    player = next
    if Input.is_action_pressed("forge_fire") and shot_timer <= 0.0:
        _attack()
    for enemy: Dictionary in enemies:
        enemy["cooldown"] = maxf(0.0, float(enemy["cooldown"]) - delta)
        enemy["flash"] = maxf(0.0, float(enemy["flash"]) - delta)
        var to_player: Vector2 = player - Vector2(enemy["pos"])
        var distance: float = to_player.length()
        var movement: Vector2 = to_player.normalized()
        var pace: float = (54.0 + float(wave + room) * 4.0) * enemy_scale
        if str(enemy["kind"]) == "swarm":
            pace *= 1.35
        elif str(enemy["kind"]) == "ranged":
            movement *= -0.45 if distance < 180.0 else 0.7 if distance > 260.0 else 0.0
            if float(enemy["cooldown"]) <= 0.0:
                bullets.append({"pos": Vector2(enemy["pos"]), "vel": to_player.normalized() * 175.0,
                    "life": 3.6, "friendly": false})
                enemy["cooldown"] = 1.6 / enemy_scale
        else:
            movement = (movement + Vector2(-movement.y, movement.x) * 0.32).normalized()
        var candidate: Vector2 = Vector2(enemy["pos"]) + movement * pace * delta
        candidate.x = clampf(candidate.x, ARENA.position.x + 15.0, ARENA.end.x - 15.0)
        candidate.y = clampf(candidate.y, ARENA.position.y + 15.0, ARENA.end.y - 15.0)
        var blocked: bool = false
        for stone: Rect2 in obstacles:
            if stone.grow(12.0).has_point(candidate):
                blocked = true
        if not blocked:
            enemy["pos"] = candidate
        if Vector2(enemy["pos"]).distance_to(player) < 27.0:
            _hurt(9.0 * damage_scale)
    _bullet_tick(delta)
    _pickup_tick()
    for index: int in range(enemies.size() - 1, -1, -1):
        if float(enemies[index]["hp"]) <= 0.0:
            var at: Vector2 = enemies[index]["pos"]
            _burst(at, _ink(5), 11)
            pickups.append({"pos": at, "health": defeated % 4 == 3})
            enemies.remove_at(index)
            defeated += 1
            score += 100
    if enemies.is_empty():
        if genre == "top_down_shooter":
            if wave < wave_count:
                wave_wait += delta
                if wave_wait >= 1.3:
                    wave += 1
                    hp = minf(100.0, hp + 8.0)
                    _begin_encounter()
            elif player.distance_to(exit_position) < 38.0:
                _finish(true)
        else:
            relic_available = not relic_taken
            if relic_available and player.distance_to(relic_position) < 32.0:
                relic_taken = true
                relic_available = false
                relics += 1
                salvage += 15
                _burst(relic_position, _ink(4), 18)
                _say("Relic secured. Take the eastern gate.", 3.0)
            if relic_taken and player.distance_to(exit_position) < 38.0:
                if room >= wave_count:
                    _finish(true)
                else:
                    room += 1
                    hp = minf(100.0, hp + 16.0)
                    _begin_encounter()

func _attack() -> void:
    shots_fired += 1
    shot_timer = 0.14 if genre == "top_down_shooter" else 0.3
    if genre == "top_down_shooter":
        bullets.append({"pos": player + aim * 20.0, "vel": aim * 690.0, "life": 1.45, "friendly": true})
        _burst(player + aim * 21.0, _ink(4), 3)
    else:
        melee_flash = 0.14
        for enemy: Dictionary in enemies:
            var difference: Vector2 = Vector2(enemy["pos"]) - player
            if difference.length() <= 108.0 and (difference.length() < 25.0 or difference.normalized().dot(aim) > 0.15):
                enemy["hp"] = float(enemy["hp"]) - 20.0
                enemy["flash"] = 0.14
                enemy["pos"] = Vector2(enemy["pos"]) + difference.normalized() * 17.0
                _burst(Vector2(enemy["pos"]), _ink(4), 4)

func _bullet_tick(delta: float) -> void:
    for index: int in range(bullets.size() - 1, -1, -1):
        var bullet: Dictionary = bullets[index]
        var old: Vector2 = bullet["pos"]
        bullet["pos"] = old + Vector2(bullet["vel"]) * delta
        bullet["life"] = float(bullet["life"]) - delta
        var remove: bool = float(bullet["life"]) <= 0.0 or not ARENA.grow(8.0).has_point(bullet["pos"])
        for stone: Rect2 in obstacles:
            if stone.grow(3.0).has_point(bullet["pos"]):
                remove = true
        if not remove and bool(bullet["friendly"]):
            for enemy: Dictionary in enemies:
                if Geometry2D.get_closest_point_to_segment(Vector2(enemy["pos"]), old, bullet["pos"]).distance_to(enemy["pos"]) < 17.0:
                    enemy["hp"] = float(enemy["hp"]) - 20.0
                    enemy["flash"] = 0.12
                    _burst(bullet["pos"], _ink(4), 4)
                    remove = true
                    break
        elif not remove and Geometry2D.get_closest_point_to_segment(player, old, bullet["pos"]).distance_to(player) < 15.0:
            _hurt(10.0 * damage_scale)
            remove = true
        if remove:
            bullets.remove_at(index)

func _pickup_tick() -> void:
    for index: int in range(pickups.size() - 1, -1, -1):
        var item: Dictionary = pickups[index]
        if Vector2(item["pos"]).distance_to(player) < 28.0:
            if bool(item["health"]):
                hp = minf(100.0, hp + 18.0)
            else:
                salvage += 10
                score += 25
            _burst(item["pos"], _ink(3), 6)
            pickups.remove_at(index)

func _build_platforms() -> void:
    platforms = [Rect2(0, 592, 440, 100), Rect2(520, 592, 420, 100),
        Rect2(1030, 592, 380, 100), Rect2(1510, 592, 390, 100), Rect2(2010, 592, 620, 100),
        Rect2(285, 520, 140, 20), Rect2(700, 512, 150, 20), Rect2(1200, 520, 150, 20),
        Rect2(1660, 508, 145, 20), Rect2(2190, 520, 170, 20)]
    spikes = [Rect2(735, 573, 48, 19), Rect2(1715, 573, 48, 19), Rect2(2270, 573, 48, 19)]
    gems = []
    for x: float in [235.0, 625.0, 1140.0, 1600.0, 2135.0, 2440.0]:
        gems.append({"pos": Vector2(x, 551.0), "taken": false})
    for at: Vector2 in [Vector2(350, 482), Vector2(775, 474), Vector2(1270, 482), Vector2(1730, 470), Vector2(2260, 482)]:
        gems.append({"pos": at, "taken": false})
    walkers = [{"pos": Vector2(1270, 574), "home": 1270.0, "dir": 1.0, "alive": true},
        {"pos": Vector2(2330, 574), "home": 2330.0, "dir": -1.0, "alive": true}]
    checkpoints = [Vector2(865.0, 560.0), Vector2(1830.0, 560.0)]
    checkpoint_index = -1
    checkpoint = Vector2(120.0, 560.0)
    player = checkpoint
    camera_x = 0.0
    coyote = 0.0
    jump_buffer = 0.0
    grounded = false
    _say("Collect five signal crystals. Reach the far gate.", 4.0)

func _platform_tick(delta: float, horizontal: float) -> void:
    var old: Vector2 = player
    if grounded:
        coyote = 0.1
    else:
        coyote = maxf(0.0, coyote - delta)
    jump_buffer = maxf(0.0, jump_buffer - delta)
    if Input.is_action_just_pressed("forge_jump"):
        jump_buffer = 0.14
    if jump_buffer > 0.0 and coyote > 0.0:
        # Keep every admitted movement speed able to cross the designed gaps;
        # slower characters gain airtime instead of requiring pixel-perfect starts.
        velocity.y = -clampf(455.0 * 230.0 / speed, 455.0, 620.0)
        grounded = false
        coyote = 0.0
        jump_buffer = 0.0
        jumps += 1
        _burst(player + Vector2(0, 15), _ink(2), 6)
    if Input.is_action_just_released("forge_jump") and not Input.is_action_pressed("forge_jump") and velocity.y < -180.0:
        velocity.y *= 0.58
    velocity.x = move_toward(velocity.x, horizontal * speed, delta * (1550.0 if grounded else 950.0))
    velocity.y = minf(700.0, velocity.y + 1120.0 * delta)
    player += velocity * delta
    player.x = clampf(player.x, 18.0, 2610.0)
    grounded = false
    for floor_piece: Rect2 in platforms:
        if velocity.y >= 0.0 and old.y + 15.0 <= floor_piece.position.y + 2.0 and player.y + 15.0 >= floor_piece.position.y and player.x + 11.0 > floor_piece.position.x and player.x - 11.0 < floor_piece.end.x:
            player.y = floor_piece.position.y - 15.0
            velocity.y = 0.0
            grounded = true
    for trap: Rect2 in spikes:
        if trap.grow(9.0).has_point(player):
            _hurt(26.0 * damage_scale)
            velocity.y = -290.0
    for walker: Dictionary in walkers:
        if not bool(walker["alive"]):
            continue
        walker["pos"] = Vector2(walker["pos"]) + Vector2(float(walker["dir"]) * 56.0 * delta * enemy_scale, 0.0)
        if absf(Vector2(walker["pos"]).x - float(walker["home"])) > 78.0:
            walker["dir"] = -float(walker["dir"])
        if Vector2(walker["pos"]).distance_to(player) < 29.0:
            if velocity.y > 0.0 and old.y < Vector2(walker["pos"]).y - 18.0:
                walker["alive"] = false
                velocity.y = -285.0
                defeated += 1
                score += 150
                _burst(walker["pos"], _ink(5), 12)
            else:
                _hurt(19.0 * damage_scale)
    for gem: Dictionary in gems:
        if not bool(gem["taken"]) and Vector2(gem["pos"]).distance_to(player) < 36.0:
            gem["taken"] = true
            collected += 1
            score += 100
            _burst(gem["pos"], _ink(3), 9)
    for index: int in range(checkpoints.size()):
        var checkpoint_area: Rect2 = Rect2(Vector2(checkpoints[index]) - Vector2(25.0, 100.0), Vector2(50.0, 135.0))
        if index > checkpoint_index and checkpoint_area.has_point(player):
            checkpoint_index = index
            checkpoint = checkpoints[index]
            hp = minf(100.0, hp + 12.0)
            _say("Checkpoint restored. Keep the signal alive.", 2.5)
            _burst(checkpoint, _ink(4), 15)
    if player.y > 780.0:
        hurt_timer = 0.0
        _hurt(32.0 * damage_scale)
        if hp > 0.0:
            player = checkpoint
            velocity = Vector2.ZERO
            hurt_timer = 1.0
            _say("Back at your checkpoint. The crystals are safe.", 2.5)
    if player.x > goal_x and player.y < 620.0:
        if collected >= gem_goal:
            _finish(true)
        else:
            _say("The gate needs %d more signal crystals." % [gem_goal - collected])
    camera_x = clampf(player.x - 350.0, 0.0, 2630.0 - WORLD.x + 50.0)

func _hurt(amount: float) -> void:
    if hurt_timer > 0.0 or dash_timer > 0.0 or phase != "playing":
        return
    hp = maxf(0.0, hp - amount)
    hurt_timer = 0.72
    flash = 0.2
    shake = 4.0
    _burst(player, _ink(5), 7)

func _finish(success: bool) -> void:
    if phase != "playing":
        return
    phase = "won" if success else "lost"
    velocity = Vector2.ZERO
    if success:
        score += int(hp) * 10
        _burst(player, _ink(3), 24)
    print("FORGE_GAMEPLAY_RESULT genre=%s outcome=%s input_frames=%d time=%.3f score=%d" % [genre, phase, input_frames, elapsed, score])

func _burst(at: Vector2, color: Color, count: int) -> void:
    for _index: int in range(count):
        if particles.size() >= 180:
            break
        particles.append({"pos": at, "vel": Vector2.from_angle(rng.randf() * TAU) * rng.randf_range(25.0, 115.0),
            "life": rng.randf_range(0.2, 0.5), "color": color})

func _effects_tick(delta: float) -> void:
    for index: int in range(particles.size() - 1, -1, -1):
        var particle: Dictionary = particles[index]
        particle["pos"] = Vector2(particle["pos"]) + Vector2(particle["vel"]) * delta
        particle["life"] = float(particle["life"]) - delta
        if float(particle["life"]) <= 0.0:
            particles.remove_at(index)

func _ink(index: int, alpha: float = 1.0) -> Color:
    var color: Color = Color(str(palette[index]))
    color.a = alpha
    return color

func _text(at: Vector2, text: String, size_value: int, color: Color, width: float = -1.0) -> void:
    draw_string(ThemeDB.fallback_font, at, text, HORIZONTAL_ALIGNMENT_LEFT, width, size_value, color)

func _draw() -> void:
    if palette.is_empty():
        return
    draw_rect(get_viewport_rect(), _ink(0))
    var scale_value: float = minf(get_viewport_rect().size.x / WORLD.x, get_viewport_rect().size.y / WORLD.y)
    var offset: Vector2 = (get_viewport_rect().size - WORLD * scale_value) * 0.5
    draw_set_transform(offset, 0.0, Vector2.ONE * scale_value)
    draw_rect(Rect2(Vector2.ZERO, WORLD), _ink(0))
    _text(Vector2(54, 42), "F O R G E    /    O R I G I N A L   W O R L D", 11, _ink(3, 0.8))
    _text(Vector2(54, 82), title, 30, Color("#f1f2ed"), 850.0)
    _text(Vector2(55, 110), objective, 14, _ink(4), 950.0)
    _text(Vector2(913, 41), "%02d:%02d" % [int(elapsed) / 60, int(elapsed) % 60], 17, _ink(3))
    draw_rect(Rect2(54, 131, 188, 7), _ink(2))
    draw_rect(Rect2(54, 131, 188.0 * hp / 100.0, 7), _ink(3) if hp > 30.0 else _ink(5))
    _text(Vector2(252, 140), "VITALITY  %d" % [int(hp)], 11, _ink(3))
    _text(Vector2(812, 139), "SCORE  %06d" % [score], 13, _ink(4))
    if genre == "platformer":
        _draw_platforms()
    else:
        _draw_arena()
    var player_screen: Vector2 = player - Vector2(camera_x if genre == "platformer" else 0.0, 0.0)
    for particle: Dictionary in particles:
        var point: Vector2 = Vector2(particle["pos"]) - Vector2(camera_x if genre == "platformer" else 0.0, 0.0)
        if point.x > 40.0 and point.x < 1080.0 and point.y > 160.0 and point.y < 640.0:
            draw_circle(point, 2.2, particle["color"])
    draw_circle(player_screen + Vector2(0, 14), 17.0, Color(0, 0, 0, 0.24))
    var player_color: Color = _ink(3)
    if hurt_timer > 0.0 and int(hurt_timer * 22.0) % 2 == 0:
        player_color = Color.WHITE
    draw_circle(player_screen, 13.0, _ink(3, 0.14))
    draw_circle(player_screen, 10.0, player_color)
    draw_circle(player_screen + Vector2(-3, -4), 3.0, Color(1, 1, 1, 0.5))
    if genre != "platformer":
        draw_line(player_screen + aim * 7.0, player_screen + aim * 24.0, _ink(4), 5.0, true)
        if melee_flash > 0.0:
            draw_arc(player_screen, 68.0, aim.angle() - 0.9, aim.angle() + 0.9, 20, _ink(4, 0.75), 7.0, true)
        var cursor: Vector2 = player_screen + aim * 60.0
        draw_arc(cursor, 6.0, 0.0, TAU, 16, _ink(3, 0.6), 1.0, true)
    draw_rect(Rect2(0, 646, WORLD.x, 74), _ink(0))
    draw_line(Vector2(54, 650), Vector2(1066, 650), _ink(2), 1.0)
    var controls: String = "A/D or arrows · Move     Space/W · Jump     R · Restart     Esc · Pause" if genre == "platformer" else "WASD / arrows · Move     Mouse · Aim     Click / Space · Fire     Shift · Dash     R · Restart     Esc · Pause"
    if genre == "rpg_roguelike":
        controls = controls.replace("Fire", "Strike")
    _text(Vector2(54, 681), controls, 12, _ink(3, 0.8))
    _text(Vector2(54, 704), notice if notice_time > 0.0 else "Made from your brief. Played by you.", 12, _ink(4, 0.85))
    if phase != "playing" or paused:
        _draw_overlay()

func _draw_arena() -> void:
    draw_style_box(_panel(_ink(1), _ink(2), 12), ARENA)
    for x: int in range(80, 1060, 40):
        draw_line(Vector2(x, 178), Vector2(x, 620), _ink(2, 0.25), 1.0)
    for y: int in range(190, 630, 40):
        draw_line(Vector2(64, y), Vector2(1054, y), _ink(2, 0.25), 1.0)
    var caption: String = "WAVE  %d / %d     ·     %d HOSTILES" % [wave, wave_count, enemies.size()]
    if genre == "rpg_roguelike":
        caption = "CHAMBER  %d / %d     ·     RELICS  %d     ·     SALVAGE  %d" % [room, wave_count, relics, salvage]
    _text(Vector2(74, 196), caption, 12, _ink(3, 0.75))
    for stone: Rect2 in obstacles:
        draw_style_box(_panel(_ink(2), _ink(3, 0.2), 6), stone)
        draw_line(stone.position + Vector2(9, 10), stone.end - Vector2(9, 10), _ink(0, 0.5), 2.0)
    var exit_open: bool = enemies.is_empty() and (wave >= wave_count if genre == "top_down_shooter" else relic_taken)
    var gate_color: Color = _ink(3 if exit_open else 2)
    draw_circle(exit_position, 34.0, Color(gate_color, 0.08))
    draw_arc(exit_position, 27.0 + sin(elapsed * 3.0) * 2.0, 0.0, TAU, 40, gate_color, 2.0, true)
    draw_arc(exit_position, 17.0, -elapsed, TAU - elapsed - 0.7, 28, gate_color, 2.0, true)
    _text(exit_position + Vector2(-24, 55), "EXIT" if exit_open else "SEALED", 10, gate_color)
    if relic_available:
        _diamond(relic_position + Vector2(0, sin(elapsed * 3.0) * 5.0), 15.0, _ink(4))
        _text(relic_position + Vector2(-22, 37), "RELIC", 10, _ink(4))
    for item: Dictionary in pickups:
        var color: Color = _ink(3 if bool(item["health"]) else 4)
        _diamond(Vector2(item["pos"]), 7.0, color)
    for enemy: Dictionary in enemies:
        var at: Vector2 = enemy["pos"]
        var color: Color = Color.WHITE if float(enemy["flash"]) > 0.0 else _ink(5)
        draw_circle(at + Vector2(0, 11), 16.0, Color(0, 0, 0, 0.2))
        if str(enemy["kind"]) == "ranged":
            _diamond(at, 15.0, color)
            draw_circle(at, 5.0, _ink(0))
        else:
            draw_circle(at, 13.0, color)
            draw_circle(at + Vector2(-4, -2), 2.0, _ink(0))
            draw_circle(at + Vector2(4, -2), 2.0, _ink(0))
        draw_rect(Rect2(at + Vector2(-14, -23), Vector2(28, 3)), _ink(0))
        draw_rect(Rect2(at + Vector2(-14, -23), Vector2(28.0 * maxf(0.0, float(enemy["hp"]) / float(enemy["max_hp"])), 3)), color)
    for bullet: Dictionary in bullets:
        var at: Vector2 = bullet["pos"]
        var vector: Vector2 = Vector2(bullet["vel"]).normalized()
        draw_line(at - vector * 12.0, at, _ink(4 if bool(bullet["friendly"]) else 5), 4.0, true)
        draw_circle(at, 3.0, Color.WHITE if bool(bullet["friendly"]) else _ink(5))

func _draw_platforms() -> void:
    draw_rect(Rect2(54, 166, 1012, 464), _ink(1))
    for layer: int in range(3):
        for index: int in range(10):
            var x: float = float(index) * 180.0 - fmod(camera_x * (0.1 + float(layer) * 0.12), 180.0)
            var height_value: float = 60.0 + float((index * 47 + layer * 29) % 170)
            draw_rect(Rect2(x, 590.0 - height_value, 100, height_value), _ink(2, 0.12 + float(layer) * 0.05))
    _text(Vector2(74, 194), "SIGNAL CRYSTALS  %d / %d     ·     CHECKPOINT  %d / 2" % [collected, gem_goal, checkpoint_index + 1], 12, _ink(3))
    for floor_piece: Rect2 in platforms:
        var visual: Rect2 = Rect2(floor_piece.position - Vector2(camera_x, 0), floor_piece.size)
        draw_style_box(_panel(_ink(2), _ink(3, 0.25), 4), visual)
        draw_line(visual.position, visual.position + Vector2(visual.size.x, 0), _ink(3, 0.5), 3.0)
        for x: int in range(int(visual.position.x) + 14, int(visual.end.x), 36):
            draw_line(Vector2(x, visual.position.y + 10), Vector2(x + 9, visual.position.y + 18), _ink(0, 0.35), 1.0)
    for trap: Rect2 in spikes:
        var at: Vector2 = trap.position - Vector2(camera_x, 0)
        for index: int in range(3):
            var x: float = at.x + float(index) * 16.0
            draw_colored_polygon(PackedVector2Array([Vector2(x, at.y + 19), Vector2(x + 8, at.y), Vector2(x + 16, at.y + 19)]), _ink(5))
    for index: int in range(checkpoints.size()):
        var at: Vector2 = Vector2(checkpoints[index]) - Vector2(camera_x, 0)
        var color: Color = _ink(3 if index <= checkpoint_index else 4)
        draw_line(at + Vector2(0, 31), at - Vector2(0, 34), color, 3.0)
        draw_colored_polygon(PackedVector2Array([at - Vector2(0, 34), at + Vector2(24, -24), at - Vector2(0, 12)]), color)
    for gem: Dictionary in gems:
        if not bool(gem["taken"]):
            _diamond(Vector2(gem["pos"]) - Vector2(camera_x, 0) + Vector2(0, sin(elapsed * 3.5) * 4.0), 10.0, _ink(3))
    for walker: Dictionary in walkers:
        if bool(walker["alive"]):
            var at: Vector2 = Vector2(walker["pos"]) - Vector2(camera_x, 0)
            draw_circle(at, 15.0, _ink(5))
            draw_circle(at + Vector2(-4, -3), 2.0, _ink(0))
            draw_circle(at + Vector2(4, -3), 2.0, _ink(0))
    var gate: Vector2 = Vector2(goal_x - camera_x, 548.0)
    draw_style_box(_panel(_ink(0), _ink(3 if collected >= gem_goal else 2), 15), Rect2(gate - Vector2(22, 45), Vector2(44, 90)))
    draw_arc(gate, 15.0, -elapsed, TAU - elapsed - 0.7, 24, _ink(3 if collected >= gem_goal else 2), 2.0, true)

func _diamond(at: Vector2, radius: float, color: Color) -> void:
    draw_colored_polygon(PackedVector2Array([at + Vector2(0, -radius), at + Vector2(radius * 0.7, 0), at + Vector2(0, radius), at + Vector2(-radius * 0.7, 0)]), color)

func _panel(fill: Color, border: Color, radius: int) -> StyleBoxFlat:
    var box: StyleBoxFlat = StyleBoxFlat.new()
    box.bg_color = fill
    box.border_color = border
    box.set_border_width_all(1)
    box.set_corner_radius_all(radius)
    return box

func _draw_overlay() -> void:
    draw_rect(Rect2(Vector2.ZERO, WORLD), Color(0.02, 0.04, 0.07, 0.78))
    draw_style_box(_panel(_ink(1), _ink(3, 0.5), 18), Rect2(290, 240, 540, 252))
    _text(Vector2(333, 287), "JOURNEY PAUSED" if paused else "SIGNAL RESTORED" if phase == "won" else "THE SIGNAL FADES", 13, _ink(4))
    _text(Vector2(333, 341), "Take a breath." if paused else "You made it back." if phase == "won" else "One more attempt?", 32, Color("#f1f2ed"))
    _text(Vector2(333, 383), "Your world is waiting." if paused else "Score %d   ·   %d:%02d   ·   Vitality %d" % [score, int(elapsed) / 60, int(elapsed) % 60, int(hp)], 16, _ink(3))
    _text(Vector2(333, 443), "Esc / P to resume     ·     R to start again" if paused else "Press R to play again", 15, _ink(4))

func observed_state() -> Dictionary:
    return {"genre": genre, "phase": phase, "paused": paused, "player": player,
        "hp": hp, "elapsed": elapsed, "score": score, "wave": wave, "room": room,
        "relics": relics, "defeated": defeated, "collected": collected,
        "input_frames": input_frames, "shots": shots_fired, "jumps": jumps,
        "restarts": restart_count}
'''


SMOKE_GD = r'''extends SceneTree
## Explicit native acceptance only. Uses the same InputMap and physics path as a player.
var game: Node2D
var hold_jump: int = 0
var capture: String = ""
var last_position: Vector2 = Vector2.ZERO
var movement: float = 0.0
var ticks: int = 0
var initial_restarts: int = 0

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    for arg: String in OS.get_cmdline_user_args():
        if arg.begins_with("--capture="):
            capture = arg.trim_prefix("--capture=")
    change_scene_to_file("res://scenes/gameplay.tscn")
    await process_frame
    await physics_frame
    game = current_scene
    if game == null or str(game.phase) != "playing" or int(game.input_frames) != 0:
        _fail("game did not begin in an unplayed input-required state")
        return
    initial_restarts = int(game.restart_count)
    Input.action_press("forge_pause")
    await physics_frame
    Input.action_release("forge_pause")
    await physics_frame
    if not bool(game.paused):
        _fail("pause input was not handled")
        return
    var paused_time: float = float(game.elapsed)
    for _frame: int in range(6):
        await physics_frame
    if float(game.elapsed) != paused_time:
        _fail("simulation advanced while paused")
        return
    Input.action_press("forge_pause")
    await physics_frame
    Input.action_release("forge_pause")
    await physics_frame
    last_position = game.player
    for frame: int in range(4800):
        ticks = frame
        _drive()
        await physics_frame
        movement += Vector2(game.player).distance_to(last_position)
        last_position = game.player
        if frame == 75 and not capture.is_empty() and DisplayServer.get_name() != "headless":
            await RenderingServer.frame_post_draw
            var image: Image = root.get_texture().get_image()
            if image == null or image.is_empty() or image.save_png(capture) != OK:
                _fail("actual rendered viewport capture failed")
                return
        if str(game.phase) != "playing":
            break
    _release()
    if str(game.phase) != "won":
        _fail("input replay did not win: " + str(game.observed_state()))
        return
    if int(game.input_frames) < 20 or movement < 100.0:
        _fail("replay did not exercise actual movement/input")
        return
    if str(game.genre) == "platformer" and (int(game.jumps) == 0 or int(game.collected) < 5):
        _fail("platformer did not jump and collect the required crystals")
        return
    if str(game.genre) != "platformer" and (int(game.shots_fired) == 0 or int(game.defeated) < 3):
        _fail("combat did not fire/strike and defeat real enemies")
        return
    var receipt: Dictionary = game.observed_state()
    receipt.erase("player")
    receipt["movement_distance"] = snappedf(movement, 0.001)
    receipt["simulated_frames"] = ticks + 1
    if not capture.is_empty() and DisplayServer.get_name() != "headless":
        await RenderingServer.frame_post_draw
        var image: Image = root.get_texture().get_image()
        if image == null or image.is_empty() or image.save_png(capture.get_basename() + "-result.png") != OK:
            _fail("actual rendered result capture failed")
            return
    Input.action_press("forge_restart")
    await physics_frame
    Input.action_release("forge_restart")
    await physics_frame
    if str(game.phase) != "playing" or int(game.restart_count) != initial_restarts + 1 or int(game.defeated) != 0 or int(game.collected) != 0:
        _fail("restart did not restore a fresh live run")
        return
    receipt["pause_verified"] = true
    receipt["restart_verified"] = true
    print("FORGE_INTERACTIVE_OK " + JSON.stringify(receipt))
    quit(0)

func _drive() -> void:
    _release_movement()
    if str(game.genre) == "platformer":
        Input.action_press("forge_right")
        if hold_jump > 0:
            Input.action_press("forge_jump")
            hold_jump -= 1
        else:
            Input.action_release("forge_jump")
        if not bool(game.grounded):
            return
        var x: float = Vector2(game.player).x
        var y: float = Vector2(game.player).y
        var should_jump: bool = false
        for floor_piece: Rect2 in game.platforms:
            if absf(y + 15.0 - floor_piece.position.y) < 4.0 and x >= floor_piece.position.x - 11.0 and x <= floor_piece.end.x + 11.0:
                if floor_piece.size.y > 30.0 and floor_piece.end.x - x < minf(42.0, float(game.speed) * 0.18) and floor_piece.end.x < 2500.0:
                    should_jump = true
        for trap: Rect2 in game.spikes:
            if trap.position.x - x > 0.0 and trap.position.x - x < 72.0:
                should_jump = true
        for walker: Dictionary in game.walkers:
            if bool(walker["alive"]) and Vector2(walker["pos"]).x - x > 0.0 and Vector2(walker["pos"]).x - x < 80.0:
                should_jump = true
        if should_jump and hold_jump == 0:
            hold_jump = 24
            Input.action_press("forge_jump")
        return
    Input.action_press("forge_fire")
    var target: Vector2 = game.exit_position
    if not game.enemies.is_empty():
        var nearest: float = INF
        for enemy: Dictionary in game.enemies:
            var distance: float = Vector2(enemy["pos"]).distance_to(game.player)
            if distance < nearest:
                nearest = distance
                target = enemy["pos"]
        if str(game.genre) == "rpg_roguelike":
            if nearest > 73.0:
                _move_towards(target)
        else:
            var angle: float = float(ticks) * 0.009
            _move_towards(Vector2(560.0, 410.0) + Vector2.from_angle(angle) * 125.0)
    else:
        if str(game.genre) == "rpg_roguelike" and not bool(game.relic_taken):
            target = game.relic_position
        _move_towards(target)
    var event: InputEventMouseMotion = InputEventMouseMotion.new()
    # Input.parse_input_event accepts physical window coordinates, whereas
    # ordinary callbacks receive stretched viewport coordinates. Headless
    # windows may be 64px while the content viewport is 1280px.
    event.position = root.get_final_transform() * game.world_to_screen(target)
    event.global_position = event.position
    Input.parse_input_event(event)

func _move_towards(target: Vector2) -> void:
    var direction: Vector2 = target - Vector2(game.player)
    if direction.x > 10.0:
        Input.action_press("forge_right")
    elif direction.x < -10.0:
        Input.action_press("forge_left")
    if direction.y > 10.0:
        Input.action_press("forge_down")
    elif direction.y < -10.0:
        Input.action_press("forge_up")

func _release_movement() -> void:
    for action: String in ["forge_left", "forge_right", "forge_up", "forge_down"]:
        Input.action_release(action)

func _release() -> void:
    _release_movement()
    for action: String in ["forge_fire", "forge_jump", "forge_pause", "forge_restart"]:
        Input.action_release(action)

func _fail(reason: String) -> void:
    _release()
    push_error("FORGE_INTERACTIVE_FAILED " + reason)
    quit(1)
'''


def runtime_manifest(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Describe generated source and controls without asserting executed acceptance."""
    gameplay = gameplay_for_spec(spec)
    if spec.get("genre") not in {"top_down_shooter", "platformer", "rpg_roguelike"}:
        raise ValueError("interactive Forge runtime requires a supported genre")
    return {
        "schema": INTERACTIVE_SCHEMA,
        "genre": spec["genre"],
        "gameplay": gameplay,
        "main_scene": SCENE_PATH,
        "script": RUNTIME_PATH,
        "smoke_script": SMOKE_PATH,
        "controls": {
            "movement": "WASD or arrow keys", "aim": "mouse; movement direction without mouse",
            "action": "Space/W jumps in platformer; click/Space fires or strikes in arena/chambers",
            "dash": "Shift in arena/chambers", "pause": "Esc or P", "restart": "R",
        },
        "features": ["visible procedural art", "health and objective HUD", "input-driven movement",
                     "enemies and hazards", "collectible rewards", "win and loss", "pause and restart"]
                    + (["gravity and variable jump", "checkpoint recovery"] if spec["genre"] == "platformer"
                       else ["aimed combat", "dash", "encounter progression"]),
        "core_loop_proof": "content-table proof only; separate from live input acceptance",
        "acceptance": "source generated; native playthrough must be executed independently",
        "external_assets": False,
    }


def attach_playable(files: Mapping[str, str], spec: Mapping[str, Any]) -> dict[str, str]:
    """Attach one live scene to the existing Godot project and preserve its scaffold."""
    manifest = runtime_manifest(spec)
    project = files.get("project.godot", "")
    if not isinstance(project, str) or "config_version=5" not in project:
        raise ValueError("interactive Forge runtime requires an emitted Godot 4 project")
    project, replaced = re.subn(
        r'^run/main_scene="[^"\n]+"\s*$',
        f'run/main_scene="res://{SCENE_PATH}"', project, count=1, flags=re.MULTILINE,
    )
    if replaced != 1:
        raise ValueError("interactive Forge runtime requires exactly one main scene")
    out = dict(files)
    # Keep the canonical design-spec bytes and digest intact. Validated legacy
    # defaults travel in the explicitly derived interactive manifest below.
    out["project.godot"] = project
    out[RUNTIME_PATH] = PLAYABLE_GD
    out[SMOKE_PATH] = SMOKE_GD
    out[SCENE_PATH] = (
        '[gd_scene load_steps=2 format=3]\n'
        f'[ext_resource type="Script" path="res://{RUNTIME_PATH}" id="1"]\n'
        '[node name="ForgePlayableGame" type="Node2D"]\n'
        'script = ExtResource("1")\n'
    )
    out["data/interactive_runtime.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    out["PLAY.md"] = (
        "# Play your original Forge game\n\n"
        "Open project.godot in Godot 4.4+ and press F6 on scenes/gameplay.tscn, or run `godot --path .`.\n\n"
        "- Arena: WASD/arrows move; mouse aims; click/Space fires; Shift dashes. Clear every wave, then enter the eastern exit.\n"
        "- Relic chambers: the same controls; click/Space strikes. Defeat guards, collect each relic and take its gate.\n"
        "- Platformer: A/D/arrows run; Space/W jumps. Collect five crystals, cross the gaps and reach the far gate. Checkpoint flags preserve progress after a fall.\n"
        "- Esc/P pauses; R restarts. Your vitality, objectives and result remain visible.\n\n"
        "The CoreLoop startup line proves content-table consistency. It does not prove a human played the game.\n"
        "Execute the maintained input replay separately: `godot --headless --fixed-fps 60 --path . --script res://scripts/runtime/interactive_smoke.gd`.\n"
        "That replay drives the ordinary input/physics path, checks a real win, pause and restart, and prints FORGE_INTERACTIVE_OK only after success.\n"
        "Rendering, export templates, controller hardware and production release require their own qualification. No external art, audio, model call or network is required by this game.\n"
    )
    return out


__all__ = ["attach_playable", "runtime_manifest", "RUNTIME_PATH", "SCENE_PATH", "SMOKE_PATH", "PLAYABLE_GD", "SMOKE_GD", "INTERACTIVE_SCHEMA"]
