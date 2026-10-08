"""Generate editable Godot 4 projects from original game-builder blueprints.

Godot output uses primitive geometry and built-in CharacterBody2D and
StaticBody2D physics. No external assets, scripts, plugins, or downloaded
research code are embedded in exported projects.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import json

from .game_knowledge_design import GameBlueprint
from .game_playable_builder import compile_scene_entities, compile_tile_collision


_MAIN_SCENE = '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://main.gd" id="1_main"]

[node name="Main" type="Node2D"]
script = ExtResource("1_main")
'''

_PLAYER = '''
extends CharacterBody2D

var move_speed := 145.0
var jump_speed := 480.0
var gravity := 800.0
var acceleration := 1024.0
var friction := 832.0
var facing := 1
var jump_buffer := 0.0
var coyote := 0.0

func _physics_process(delta):
    var direction = Input.get_axis("move_left", "move_right")
    var target = direction * move_speed
    velocity.x = move_toward(velocity.x, target, (acceleration if direction else friction) * delta)
    if is_on_floor():
        coyote = 0.10
    else:
        coyote = maxf(0.0, coyote - delta)
    if Input.is_action_just_pressed("jump"):
        jump_buffer = 0.12
    jump_buffer = maxf(0.0, jump_buffer - delta)
    if jump_buffer > 0.0 and coyote > 0.0:
        velocity.y = -jump_speed
        jump_buffer = 0.0
        coyote = 0.0
    velocity.y = minf(650.0, velocity.y + gravity * delta)
    move_and_slide()

func _draw():
    draw_rect(Rect2(Vector2(-11, -14), Vector2(22, 28)), Color("#7cc5ff"))
    draw_rect(Rect2(Vector2(4, -7), Vector2(4, 5)), Color("#132638"))
'''

_MAIN_SCRIPT = '''
extends Node2D

const TILE := 32.0
var data: Dictionary = {}
var solids: Array = []
var pickups: Array = []
var foes: Array = []
var player
var spawn: Vector2
var goal: Rect2
var score := 0
var lives := 3
var paused := false
var won := false
var invincible := 0.0
var hud: Label

func _ready():
    var raw = FileAccess.get_file_as_string("res://level.json")
    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid original level configuration")
        return
    data = parsed
    _install_actions()
    var physics = data["physics"]
    lives = int(physics["max_lives"])
    for y in range(data["height"]):
        for x in range(data["width"]):
            if data["collision"][y][x] == 1:
                _solid(Vector2(x * TILE, y * TILE))
    for entity in data["entities"]:
        var pos = Vector2(float(entity["x"]), float(entity["y"]))
        match entity["type"]:
            "player":
                spawn = pos + Vector2(16, 16)
            "goal":
                goal = Rect2(pos + Vector2(8, 2), Vector2(16, 30))
            "collectible":
                pickups.append({"pos": pos + Vector2(8, 8), "active":true})
            "enemy":
                foes.append({"pos":pos + Vector2(4,6),
                    "home":pos.x+4.0,"dir":1.0,"active":true})
    player = CharacterBody2D.new()
    player.set_script(load("res://player.gd"))
    player.position = spawn
    var col = CollisionShape2D.new()
    var shape = RectangleShape2D.new()
    shape.size = Vector2(22, 28)
    col.shape = shape
    player.add_child(col)
    add_child(player)
    player.move_speed = float(physics["move_speed"]) * TILE
    player.jump_speed = float(physics["jump_speed"]) * TILE
    player.gravity = float(physics["gravity"]) * TILE
    player.acceleration = float(physics["acceleration"]) * TILE
    player.friction = float(physics["friction"]) * TILE
    var camera = Camera2D.new()
    camera.enabled = true
    camera.position_smoothing_enabled = true
    camera.position_smoothing_speed = 9.0
    player.add_child(camera)
    var layer = CanvasLayer.new()
    add_child(layer)
    hud = Label.new()
    hud.position = Vector2(16, 12)
    hud.add_theme_font_size_override("font_size", 21)
    layer.add_child(hud)
    _update_hud()
    queue_redraw()

func _install_actions():
    var bindings = {
        "move_left": [KEY_A, KEY_LEFT],
        "move_right": [KEY_D, KEY_RIGHT],
        "jump": [KEY_SPACE, KEY_W, KEY_UP],
        "restart": [KEY_R],
        "pause": [KEY_P],
    }
    for action in bindings:
        if not InputMap.has_action(action):
            InputMap.add_action(action)
        for key in bindings[action]:
            var ev = InputEventKey.new()
            ev.physical_keycode = key
            InputMap.action_add_event(action, ev)

func _solid(pos: Vector2):
    var body = StaticBody2D.new()
    body.position = pos + Vector2(16, 16)
    var shape = RectangleShape2D.new()
    shape.size = Vector2(32, 32)
    var collision = CollisionShape2D.new()
    collision.shape = shape
    body.add_child(collision)
    add_child(body)

func _unhandled_input(event):
    if event.is_action_pressed("pause"):
        paused = not paused
        if is_instance_valid(player):
            player.set_physics_process(not paused)
    if event.is_action_pressed("restart"):
        get_tree().reload_current_scene()

func _physics_process(delta):
    if not is_instance_valid(player) or paused or won:
        return
    if not player.is_inside_tree():
        return
    invincible = maxf(0.0, invincible - delta)
    var player_box = Rect2(player.position - Vector2(11,14), Vector2(22,28))
    for item in pickups:
        if item["active"] and player_box.intersects(Rect2(item["pos"], Vector2(16,16))):
            item["active"] = false
            score += 10
    for foe in foes:
        if not foe["active"]:
            continue
        var pos: Vector2 = foe["pos"]
        var direction: float = foe["dir"]
        var proposal = pos + Vector2(direction * 42.0 * delta, 0)
        var next_cell = Vector2i(int((proposal.x + (20 if direction>0 else 0))/TILE),
            int((proposal.y+30)/TILE))
        if absf(proposal.x - float(foe["home"])) > 64.0 or not _is_floor(next_cell):
            foe["dir"] = -direction
        else:
            foe["pos"] = proposal
        var hitbox = Rect2(foe["pos"], Vector2(24,26))
        if hitbox.intersects(player_box) and invincible<=0.0:
            if player.velocity.y>0 and player.position.y<foe["pos"].y:
                foe["active"] = false
                score += 100
                player.velocity.y = -220
            else:
                _damage()
    if player.position.y > float(data["height"])*TILE+TILE:
        _damage()
    if player_box.intersects(goal):
        won = true
        score += 250
    _update_hud()
    queue_redraw()

func _is_floor(cell: Vector2i) -> bool:
    if cell.x < 0 or cell.x >= int(data["width"]) or cell.y < 0 or cell.y >= int(data["height"]):
        return false
    return data["collision"][cell.y][cell.x] == 1

func _damage():
    if invincible>0.0 or lives<=0:
        return
    lives-=1
    player.position = spawn
    player.velocity = Vector2.ZERO
    invincible = 1.5
    if lives<=0:
        paused = true
        player.set_physics_process(false)

func _update_hud():
    var status = "  |  P: Pause  R: Restart"
    if won:
        status = "  |  Level Complete! Press R"
    elif lives<=0:
        status = "  |  Game Over! Press R"
    elif paused:
        status = "  |  Paused"
    hud.text = "Score: %s  Lives: %s%s" % [score, lives, status]

func _draw():
    if data.is_empty():
        return
    draw_rect(Rect2(0,0,float(data["width"])*TILE,
        float(data["height"])*TILE), Color("#0b1423"))
    for y in range(data["height"]):
        for x in range(data["width"]):
            if data["collision"][y][x] == 1:
                draw_rect(Rect2(x*TILE,y*TILE,TILE,TILE), Color("#344765"))
                draw_rect(Rect2(x*TILE,y*TILE,TILE,4), Color("#78b1c8"))
    for item in pickups:
        if item["active"]:
            draw_circle(item["pos"]+Vector2(8,8),8,Color("#f8ca55"))
    for foe in foes:
        if foe["active"]:
            draw_rect(Rect2(foe["pos"], Vector2(24,26)), Color("#e66d77"))
    draw_rect(goal, Color("#7ce4b2"))
'''


@dataclass(frozen=True)
class GodotProject:
    files: tuple[tuple[str,bytes], ...]
    fingerprint: str


def compile_godot_project(blueprint: GameBlueprint) -> GodotProject:
    """Produce an editable Godot 4 project with playable native mechanics."""
    collision=compile_tile_collision(blueprint)
    entities=compile_scene_entities(blueprint)
    scene={
        "schema":"skeleton.original.godot_game.v1",
        "width":blueprint.width,"height":blueprint.height,
        "collision":collision,"entities":entities,
        "physics":blueprint.physics_dict(),
        "blueprint":blueprint.fingerprint,
        "knowledge_refs":blueprint.source_evidence,
    }
    safe_title=blueprint.title.replace('"', "").replace("\n"," ")
    project=(
        'config_version=5\n\n'
        '[application]\n'
        f'config/name="{safe_title}"\n'
        'run/main_scene="res://main.tscn"\n\n'
        '[display]\nwindow/size/viewport_width=960\n'
        'window/size/viewport_height=540\n\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        'renderer/rendering_method.mobile="gl_compatibility"\n'
    ).encode()
    files=(
        ("project.godot",project),
        ("main.tscn",_MAIN_SCENE.encode()),
        ("main.gd",_MAIN_SCRIPT.encode()),
        ("player.gd",_PLAYER.encode()),
        ("level.json",json.dumps(scene,sort_keys=True,indent=2).encode()),
        ("README.md",(
            "# Original game project\nOpen project.godot with Godot 4.\n"
            "Arrow keys or A/D move, Space/W jumps, P pauses, R restarts.\n"
            "All graphics are drawn procedurally; no third-party game assets.\n"
            f"Blueprint: {blueprint.fingerprint}\n"
        ).encode()),
    )
    digest=sha256(b"".join(
        path.encode()+b"\0"+content for path,content in files
    )).hexdigest()
    return GodotProject(files,digest)


def export_godot_game_archive(blueprint: GameBlueprint) -> bytes:
    project=compile_godot_project(blueprint)
    output=BytesIO()
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for path,content in project.files:
            info=ZipInfo(path,date_time=(2026,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o644<<16
            archive.writestr(info,content)
    return output.getvalue()
