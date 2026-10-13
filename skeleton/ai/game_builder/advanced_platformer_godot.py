"""Offline Godot 4 advanced platformer, independently executed against Python.

Native state transitions are authored in GDScript, *not* replayed from Python
snapshots. Packaging, manifest and source reviews reuse the proved puzzle
exporter's fixed-path secure source contract.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_godot_export import (
    NativeAdvancedGamePackage, AdvancedGodotExportError, _json,
)
from .dual_runtime_export import _PROJECT, _EXPORT_PRESETS, _SCENE
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_platformer.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_platformer_proof.v1"
PROOF_FIELDS=("tick","x","y","vy","air_jumps","health","checkpoint",
              "dash_cooldown","crystals","spikes","collectibles",
              "checkpoints","exit_x","events","finished","failed")

GODOT_PLATFORMER=r'''
extends Control
## Original native platformer: deterministic integer motions, hazards and exit.
const VERIFY_FLAG: String = "--verify-platformer"
const MAX_COMMANDS: int = 128
const ACTIONS: Array = [
    "left","right","jump","jump_left","jump_right",
    "wait","dash_left","dash_right"
]
var rules: Dictionary = {}
var world: Dictionary = {}
var layout: Dictionary = {}
var ready_to_play: bool = false
var tick: int = 0
var x: int = 0
var y: int = 0
var vy: int = 0
var air_jumps: int = 0
var health: int = 5
var checkpoint: int = 0
var dash_cooldown: int = 0
var crystals: Array = []
var spikes: Array = []
var collectibles: Array = []
var checkpoints: Array = []
var exit_x: int = 0
var events: Array = []
var finished: bool = false
var failed: bool = false
var actions: Array = []
var notice: String = "Original platformer · WASD or arrows; space to jump"


func _numbers(source: Array) -> Array:
    var result: Array = []
    for value in source:
        result.append(int(value))
    return result


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length() > 80000:
        _native_error("missing or oversized authored platformer")
        return
    var incoming: Variant = JSON.parse_string(raw)
    if typeof(incoming) != TYPE_DICTIONARY:
        _native_error("invalid original platformer JSON")
        return
    world = incoming
    if str(world.get("schema","")) != "skeleton.game_builder.godot_advanced_platformer.v1":
        _native_error("unknown native game schema")
        return
    rules = world["settings"]
    layout = world["scene"]["layout"]
    if int(rules["level_width"]) < 16 or int(rules["level_width"]) > 1024:
        _native_error("unbounded native platform width")
        return
    ready_to_play = true
    _reset()
    get_window().title = "Skeleton Original Platformer"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify_proof()


func _native_error(reason: String) -> void:
    push_error("NATIVE_ADVANCED_PLATFORMER_ERROR: " + reason)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _reset() -> void:
    tick = 0
    x = int(layout["spawn_x"])
    y = 0
    vy = 0
    air_jumps = 0
    health = 5
    checkpoint = x
    dash_cooldown = 0
    crystals = []
    spikes = _numbers(layout["hazards"])
    collectibles = _numbers(layout["collectibles"])
    checkpoints = _numbers(layout["checkpoints"])
    exit_x = int(layout["exit_x"])
    events = []
    finished = false
    failed = false
    actions = []
    notice = "Find every crystal and reach the exit"
    queue_redraw()


func _step(action: String, record: bool = true) -> bool:
    if not ready_to_play or finished or failed or actions.size() >= MAX_COMMANDS:
        return false
    if action not in ACTIONS:
        return false
    # Validate cooldown before any state mutation; rejected moves are atomic.
    var dash: bool = action.begins_with("dash")
    if dash and dash_cooldown > 0:
        return false
    tick += 1
    events = []
    var grounded: bool = y == 0
    var jumping: bool = action.begins_with("jump")
    if jumping and (grounded or (bool(rules["double_jump"]) and air_jumps < 2)):
        vy = int(rules["jump_impulse"])
        air_jumps += 1
        events.append("jump")
    var direction: int = 0
    if action in ["left","jump_left","dash_left"]:
        direction = -1
    elif action in ["right","jump_right","dash_right"]:
        direction = 1
    var speed: int = int(rules["run_speed"]) * (2 if dash else 1)
    var old_x: int = x
    var next_x: int = clampi(old_x + direction * speed,0,int(rules["level_width"])-1)
    var old_y: int = y
    y = maxi(0,old_y + vy)
    vy = maxi(-int(rules["gravity"])*3,vy-int(rules["gravity"]))
    if y == 0:
        vy = 0
        air_jumps = 0
    x = next_x
    if dash:
        dash_cooldown = 3
        events.append("dash")
    elif dash_cooldown > 0:
        dash_cooldown -= 1
    var low: int = mini(old_x,next_x)
    var high: int = maxi(old_x,next_x)
    for crystal in collectibles:
        if int(crystal) >= low and int(crystal) <= high and crystal not in crystals:
            crystals.append(crystal)
            events.append("crystal_collected")
    crystals.sort()
    for mark in checkpoints:
        if int(mark) >= low and int(mark) <= high and int(mark) > checkpoint:
            checkpoint = int(mark)
            events.append("checkpoint_activated")
    var exposed: bool = old_y <= 2 and y <= 2 and not dash
    var hit: bool = false
    if exposed:
        for hazard in spikes:
            if int(hazard) >= low and int(hazard) <= high:
                hit = true
                break
    if hit:
        health -= 1
        x = checkpoint
        y = 0
        vy = 0
        air_jumps = 0
        events.append("hazard_respawn")
    if health <= 0:
        health = 0
        failed = true
        events.append("run_failed")
    if x >= exit_x and crystals.size() == collectibles.size() and not failed:
        finished = true
        events.append("exit_unlocked")
    elif x >= exit_x:
        events.append("exit_locked")
    if record:
        actions.append(action)
    if failed:
        notice = "Run failed · press R to restart"
    elif finished:
        notice = "Original game complete!"
    elif hit:
        notice = "Hazard hit; checkpoint respawn"
    else:
        notice = action + " · " + str(crystals.size()) + "/" + str(collectibles.size()) + " crystals"
    queue_redraw()
    return true


func _snapshot() -> Dictionary:
    return {
        "tick":tick, "x":x,"y":y,"vy":vy,"air_jumps":air_jumps,
        "health":health,"checkpoint":checkpoint,
        "dash_cooldown":dash_cooldown,"crystals":crystals.duplicate(true),
        "spikes":spikes.duplicate(true),"collectibles":collectibles.duplicate(true),
        "checkpoints":checkpoints.duplicate(true),"exit_x":exit_x,
        "events":events.duplicate(true),"finished":finished,"failed":failed
    }


func _verify_proof() -> void:
    var raw: String = FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length() > 150000:
        _native_error("missing or oversized Python proof")
        return
    var incoming: Variant = JSON.parse_string(raw)
    if typeof(incoming) != TYPE_DICTIONARY:
        _native_error("invalid Python proof JSON")
        return
    var proof: Dictionary = incoming
    if (proof.get("schema") != "skeleton.game_builder.godot_advanced_platformer_proof.v1"
        or proof.get("settings_digest") != world.get("settings_digest")
        or proof.get("scene_digest") != world["scene"]["digest"]):
        _native_error("native source/proof configuration mismatch")
        return
    var commands: Variant = proof.get("actions")
    var expected: Variant = proof.get("expected")
    if typeof(commands) != TYPE_ARRAY or typeof(expected) != TYPE_DICTIONARY:
        _native_error("invalid action transcript or final state")
        return
    if commands.size() > MAX_COMMANDS:
        _native_error("bounded native replay action limit exceeded")
        return
    for action in commands:
        if typeof(action) != TYPE_STRING or not _step(action):
            _native_error("replay action rejected " + str(action))
            return
    var native: Dictionary = _snapshot()
    for field in native:
        if not expected.has(field):
            _native_error("missing expected proof field " + field)
            return
        var actual: Variant = native[field]
        var intended: Variant = expected[field]
        if field in ["crystals","spikes","collectibles","checkpoints"]:
            intended = _numbers(intended)
        if actual != intended:
            _native_error("divergent " + field + " native=" + str(actual) +
                          " python=" + str(intended))
            return
    if native.size() != expected.size() or actions.size() != commands.size():
        _native_error("mismatched proof schema or action count")
        return
    print("NATIVE_ADVANCED_PLATFORMER_OK " + str(world["scene"]["digest"]) +
          " actions=" + str(actions.size()) +
          " outcome=" + ("failed" if failed else "won" if finished else "playing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String = ""
    match event.keycode:
        KEY_LEFT, KEY_A: action = "left"
        KEY_RIGHT, KEY_D: action = "right"
        KEY_SPACE, KEY_UP, KEY_W: action = "jump"
        KEY_Q: action = "jump_left"
        KEY_E: action = "jump_right"
        KEY_Z: action = "dash_left"
        KEY_X: action = "dash_right"
        KEY_R: _reset()
    if action != "":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String = ""
        match event.button_index:
            JOY_BUTTON_DPAD_LEFT: action = "left"
            JOY_BUTTON_DPAD_RIGHT: action = "right"
            JOY_BUTTON_A: action = "jump"
            JOY_BUTTON_X: action = "dash_left"
            JOY_BUTTON_Y: action = "dash_right"
            JOY_BUTTON_START: _reset()
        if action != "":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code == NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#101c2b"),true)
    if not ready_to_play:
        return
    var w: float = size.x
    var h: float = size.y
    var base: float = h * 0.78
    var cell: float = maxf(6.0,minf(30.0,(w-80.0)/float(int(rules["level_width"]))))
    var camera_left: int = maxi(0,x - int((w-90.0)/cell/2.0))
    var visible: int = int((w-40.0)/cell)+1
    _text(Vector2(18,31),"Original platformer · Advanced native",22,Color.WHITE)
    _text(Vector2(18,61),"HP %d   Crystals %d/%d   Tick %d   Checkpoint %d" %
        [health,crystals.size(),collectibles.size(),tick,checkpoint],15,Color("#b9ebe0"))
    _text(Vector2(18,84),notice,14,Color("#f3d39d"))
    for tile in range(camera_left,mini(int(rules["level_width"]),camera_left+visible)):
        var x0: float = 18.0 + float(tile-camera_left)*cell
        draw_rect(Rect2(Vector2(x0,base),Vector2(cell,cell)),Color("#275269"),true)
        draw_rect(Rect2(Vector2(x0,base),Vector2(cell,cell)),Color("#436a75"),false)
        if tile in spikes:
            draw_rect(Rect2(Vector2(x0+cell*0.32,base+cell*0.2),
                     Vector2(cell*0.35,cell*0.6)),Color("#ee7a81"),true)
        if tile in collectibles and tile not in crystals:
            draw_circle(Vector2(x0+cell/2.0,base-cell*0.40),
                        cell*0.23,Color("#80edca"))
        if tile in checkpoints:
            draw_rect(Rect2(Vector2(x0+cell*0.43,base-cell*0.75),
                      Vector2(cell*0.14,cell*0.74)),Color("#ecc987"),true)
        if tile == exit_x:
            draw_rect(Rect2(Vector2(x0+cell*0.2,base-cell),
                      Vector2(cell*0.6,cell)),Color("#6fb5d7"),true)
    var px: float = 18.0 + float(x-camera_left)*cell+cell/2.0
    var py: float = base-cell*0.15-float(y)*cell*0.14
    draw_circle(Vector2(px,py),maxf(3.0,cell*0.33),Color("#f6f2e6"))
    _text(Vector2(18,h-30),"Arrow/A,D: run · Space: jump · Q/E: jump+move · Z/X: dash · R: reset",
          13,Color("#b7d5d5"))


func _text(point: Vector2,message: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,point,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_platformer_godot_package(session: dict, settings: dict | None = None,
                                    *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("original platformer native export requires explicit authorization")
    if type(session) is not dict or session.get("editor")!="platformer":
        raise AdvancedGodotExportError("only a verified original platformer session can use this adapter")
    config=make_editor_document("platformer",settings)
    verify_advanced_session(session,config["settings"])
    original=(
        validate_advanced_scene(session["scene"],config["settings"])
        if session.get("scene") is not None
        else make_advanced_scene("platformer",config["settings"],seed=session["seed"])
    )
    if session.get("scene") is None:
        session=run_advanced_session("platformer",config["settings"],
                                     session["actions"],seed=session["seed"],scene=original)
    state=session["state"]
    game={
        "schema":SCHEMA,"editor":"platformer",
        "quality_floor":"advanced","settings":config["settings"],
        "settings_digest":config["digest"],"scene":original,
        "native_parity_verified":False,"external_assets_executed":False,
    }
    proof={
        "schema":PROOF_SCHEMA,"scene_digest":original["digest"],
        "settings_digest":config["digest"],"actions":session["actions"],
        "expected":{field:state[field] for field in PROOF_FIELDS},
        "python_session_digest":session["digest"],
        "verified_by_python_replay":True,
    }
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                        "Skeleton Original Advanced Platformer").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_PLATFORMER.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Godot 4 Platformer\n\n"
            "Native GDScript play controls and rendered scene, entirely offline.\n"
            "Godot 4.4.1+ project: godot/project.godot. Arrow/A,D to run, Space/W to jump,\n"
            "Q/E for jump+move, Z/X for dash, gamepad controls, R to restart.\n"
            "godot --headless --path godot -- --verify-platformer independently\n"
            "replays real native transitions and compares every field to the\n"
            "Python-verified source proof. No production certification or rights\n"
            "approval is inferred solely from native source export.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"platformer","native_adapter":"godot4_independent_platformer",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":original["digest"],
        "files":{p:sha256(b).hexdigest() for p,b in sorted(files.items())},
        "godot_executed":False,"native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","GODOT_PLATFORMER","PROOF_FIELDS",
         "render_platformer_godot_package"]
