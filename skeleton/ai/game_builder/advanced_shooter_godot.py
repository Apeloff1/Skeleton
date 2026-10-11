"""Playable offline Godot 4 original arena shooter with independent combat replay.

Original integer-grid gameplay, authored cover/LOS, deterministic hostile AI,
finite weapons and healing, and score/extraction proof. Native state is never
copied from the expected Python outcome; the game independently executes.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_godot_export import (
    AdvancedGodotExportError, NativeAdvancedGamePackage, _json,
)
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_shooter.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_shooter_proof.v1"
PROOF_FIELDS=(
    "tick","width","height","player","hp","max_hp","ammo","magazine",
    "dashes","dodge_limit","medkits","covered","cover","spawns",
    "extraction","pickups","enemies","enemy_total","spawned","defeated",
    "wave","damage_taken","score","events","finished","failed",
)

GODOT_SHOOTER=r'''
extends Control
## Independent original Godot arena shooter. Python receipt is proof, not AI.
const VERIFY_FLAG: String = "--verify-shooter"
const MAX_ACTIONS: int = 128
const ACTIONS: Array = [
    "north","south","west","east","dash:north","dash:south",
    "dash:west","dash:east","fire","reload","cover","medkit",
    "extract","wait"
]
var source: Dictionary = {}
var rules: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var history: Array = []
var ready_to_play: bool = false
var notice: String = "Original arena: arrows move, F fires, R reloads"


func _point(raw: Array) -> Array:
    return [int(raw[0]),int(raw[1])]


func _points(raw: Array) -> Array:
    var result: Array = []
    for point in raw:
        result.append(_point(point))
    return result


func _distance(a: Array,b: Array) -> int:
    return absi(int(a[0])-int(b[0]))+absi(int(a[1])-int(b[1]))


func _valid(point: Array) -> bool:
    return (int(point[0]) >= 0 and int(point[0]) < int(state["width"])
        and int(point[1]) >= 0 and int(point[1]) < int(state["height"]))


func _next(point: Array,direction: String) -> Array:
    var delta: Array = [0,0]
    match direction:
        "north": delta=[0,-1]
        "south": delta=[0,1]
        "west": delta=[-1,0]
        "east": delta=[1,0]
    return [int(point[0])+int(delta[0]),int(point[1])+int(delta[1])]


func _visible(start: Array,destination: Array) -> bool:
    # True Bresenham grid LOS; authored cover blocks bullet paths AND movement.
    var x: int = int(start[0])
    var y: int = int(start[1])
    var tx: int = int(destination[0])
    var ty: int = int(destination[1])
    var dx: int = absi(tx-x)
    var dy: int = absi(ty-y)
    var sx: int = 1 if x < tx else -1
    var sy: int = 1 if y < ty else -1
    var err: int = dx-dy
    while [x,y] != destination:
        var twice: int = 2*err
        if twice > -dy:
            err -= dy
            x += sx
        if twice < dx:
            err += dx
            y += sy
        if [x,y] != destination and [x,y] in state["cover"]:
            return false
    return true


func _error(message: String) -> void:
    push_error("NATIVE_ADVANCED_SHOOTER_ERROR: "+message)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length()>80000:
        _error("missing or oversized original combat source")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed)!=TYPE_DICTIONARY:
        _error("invalid authored arena JSON")
        return
    source=parsed
    if source.get("schema")!="skeleton.game_builder.godot_advanced_shooter.v1":
        _error("invalid native shooter contract")
        return
    rules=source["settings"]
    layout=source["scene"]["layout"]
    if (int(layout["width"])<8 or int(layout["width"])>30
        or int(layout["height"])<6 or int(layout["height"])>20
        or layout["enemy_spawns"].size()!=3):
        _error("original arena violates bounded geometry")
        return
    ready_to_play=true
    _reset()
    get_window().title="Skeleton Original Advanced Arena"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _spawn_wave(seed: int) -> void:
    if not state["enemies"].is_empty() or int(state["spawned"])>=int(state["enemy_total"]):
        return
    state["wave"]=int(state["wave"])+1
    var count: int=mini(3,int(state["enemy_total"])-int(state["spawned"]))
    for _index in range(count):
        var ident: int=int(state["spawned"])
        var spawn_index: int=(ident+seed)%state["spawns"].size()
        var pos: Array=state["spawns"][spawn_index].duplicate(true)
        state["enemies"].append({
            "id":ident,"pos":pos,"hp":4+int(ident/3),
            "armor":1 if ident%4==3 else 0,
            "behavior":"flank" if ident%3==2 else "advance",
        })
        state["spawned"]=int(state["spawned"])+1


func _reset() -> void:
    var health: int=int(rules["player_health"])
    var rounds: int=int(rules["enemy_count"])
    var ammo: int=int(rules["ammo"])
    var dodges: int=int(rules["dodge_charges"])
    state={
        "tick":0,"width":int(layout["width"]),"height":int(layout["height"]),
        "player":_point(layout["player_spawn"]),
        "hp":health,"max_hp":health,"ammo":ammo,"magazine":ammo,
        "dashes":dodges,"dodge_limit":dodges,"medkits":1,"covered":false,
        "cover":_points(layout["cover"]),"spawns":_points(layout["enemy_spawns"]),
        "extraction":_point(layout["extraction"]),"pickups":_points(layout["medkits"]),
        "enemies":[],"enemy_total":rounds,"spawned":0,"defeated":0,
        "wave":0,"damage_taken":0,"score":0,"events":[],
        "finished":false,"failed":false,
    }
    history=[]
    _spawn_wave(int(source["scene"]["seed"]))
    # The authored-scene adapter explicitly repositions initial wave enemies
    # in creation order, distinct from subsequent wave seed offsets.
    for i in range(state["enemies"].size()):
        state["enemies"][i]["pos"] = state["spawns"][i % state["spawns"].size()].duplicate(true)
    notice="Clear every enemy wave, then reach the extraction marker"
    queue_redraw()


func _step(action: String) -> bool:
    if (not ready_to_play or bool(state["finished"]) or bool(state["failed"])
        or history.size()>=MAX_ACTIONS or action not in ACTIONS):
        return false
    # Invalid actions must be rejected before advancing tick or enemies.
    if action.begins_with("dash:") and int(state["dashes"])<=0:
        return false
    if action=="fire":
        if int(state["ammo"])<=0:
            return false
        var possible: Array=[]
        for enemy in state["enemies"]:
            if (_distance(state["player"],enemy["pos"])<=8
                and _visible(state["player"],enemy["pos"])):
                possible.append(enemy)
        if possible.is_empty():
            return false
    if action=="reload" and int(state["ammo"])==int(state["magazine"]):
        return false
    if action=="medkit" and (int(state["medkits"])<=0
        or int(state["hp"])==int(state["max_hp"])):
        return false
    if action=="extract" and (not state["enemies"].is_empty()
        or int(state["spawned"])<int(state["enemy_total"])
        or state["player"]!=state["extraction"]):
        return false

    state["tick"]=int(state["tick"])+1
    var events: Array=[]
    var dodging: bool=false
    if action in ["north","south","east","west"] or action.begins_with("dash:"):
        dodging=action.begins_with("dash:")
        var direction: String=action.split(":")[-1]
        var steps: int=2 if dodging else 1
        for _i in range(steps):
            var dest: Array=_next(state["player"],direction)
            var occupied: bool=false
            for enemy in state["enemies"]:
                if enemy["pos"]==dest:
                    occupied=true
                    break
            if not _valid(dest) or dest in state["cover"] or occupied:
                break
            state["player"]=dest
        if dodging:
            state["dashes"]=int(state["dashes"])-1
            events.append("evasive_movement")
        else:
            events.append("arena_movement")
    elif action=="fire":
        var target: Dictionary={}
        var best_dist: int=2147483647
        var best_id: int=2147483647
        for enemy in state["enemies"]:
            var dist: int=_distance(state["player"],enemy["pos"])
            if dist<=8 and _visible(state["player"],enemy["pos"]):
                if dist<best_dist or (dist==best_dist and int(enemy["id"])<best_id):
                    target=enemy
                    best_dist=dist
                    best_id=int(enemy["id"])
        state["ammo"]=int(state["ammo"])-1
        target["hp"]=int(target["hp"])-maxi(1,
            int(rules["weapon_damage"])-int(target["armor"]))
        events.append("weapon_hit")
        if int(target["hp"])<=0:
            state["enemies"].erase(target)
            state["defeated"]=int(state["defeated"])+1
            state["score"]=int(state["score"])+100
            events.append("enemy_defeated")
    elif action=="reload":
        state["ammo"]=int(state["magazine"])
        events.append("magazine_reloaded")
    elif action=="cover":
        state["covered"]=true
        events.append("cover_stance")
    elif action=="medkit":
        state["medkits"]=int(state["medkits"])-1
        state["hp"]=mini(int(state["max_hp"]),int(state["hp"])+6)
        events.append("medkit_used")
    elif action=="extract":
        state["finished"]=true
        events.append("mission_extracted")
        state["events"]=events
        history.append(action)
        queue_redraw()
        return true
    else:
        events.append("arena_wait")

    var retained: Array=[]
    for pickup in state["pickups"]:
        if pickup==state["player"]:
            state["medkits"]=mini(3,int(state["medkits"])+1)
            events.append("medical_supply_collected")
        else:
            retained.append(pickup)
    state["pickups"]=retained
    if state["enemies"].is_empty() and int(state["spawned"])<int(state["enemy_total"]):
        _spawn_wave(int(state["wave"]))
        events.append("enemy_reinforcement_wave")

    var occupied: Array=[]
    for enemy in state["enemies"]:
        occupied.append(enemy["pos"].duplicate(true))
    for enemy in state["enemies"]:
        if int(state["hp"])<=0:
            break
        if (_distance(enemy["pos"],state["player"])<=3
            and _visible(enemy["pos"],state["player"])):
            var damage: int=0 if dodging else maxi(0,2-
                (1 if bool(state["covered"]) else 0))
            state["hp"]=maxi(0,int(state["hp"])-damage)
            state["damage_taken"]=int(state["damage_taken"])+damage
            if damage>0:
                events.append("enemy_fire")
        else:
            var direction_x: String="east" if int(state["player"][0])>int(enemy["pos"][0]) else "west"
            var direction_y: String="south" if int(state["player"][1])>int(enemy["pos"][1]) else "north"
            for direction in [direction_x,direction_y]:
                var dest: Array=_next(enemy["pos"],direction)
                if (dest==state["player"] or not _valid(dest)
                    or dest in state["cover"] or dest in occupied):
                    continue
                occupied.erase(enemy["pos"])
                enemy["pos"]=dest
                occupied.append(dest)
                events.append("enemy_patrolled")
                break
    if not bool(state["finished"]) and int(state["hp"])==0:
        state["failed"]=true
        events.append("player_defeated")
    state["covered"]=false
    state["events"]=events
    history.append(action)
    notice=("Mission complete" if bool(state["finished"])
        else "Combat failed" if bool(state["failed"])
        else "Wave %d · %s" % [int(state["wave"]),action])
    queue_redraw()
    return true


func _normalized_expected(field: String, raw: Variant) -> Variant:
    if field in ["player","extraction"]:
        return _point(raw)
    if field in ["cover","spawns","pickups"]:
        return _points(raw)
    if field=="enemies":
        var result: Array=[]
        for enemy in raw:
            var parsed: Dictionary=enemy.duplicate(true)
            parsed["pos"]=_point(parsed["pos"])
            result.append(parsed)
        return result
    return raw


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>180000:
        _error("missing or oversized verified game proof")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _error("invalid native replay proof")
        return
    var proof: Dictionary=decoded
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_shooter_proof.v1"
        or proof.get("scene_digest")!=source["scene"]["digest"]
        or proof.get("settings_digest")!=source.get("settings_digest")):
        _error("authored scene/settings/contract mismatch")
        return
    var commands: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if typeof(commands)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY:
        _error("invalid bounded native replay input")
        return
    if commands.size()>MAX_ACTIONS:
        _error("native replay command budget exceeded")
        return
    for action in commands:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _error("gameplay action rejected: "+str(action))
            return
    if state.size()!=expected.size() or history.size()!=commands.size():
        _error("replay output field count mismatch")
        return
    for field in state:
        var wanted: Variant=_normalized_expected(field,expected.get(field))
        if not expected.has(field) or state[field]!=wanted:
            _error("shooter state divergence "+field+" native="+str(state[field])+
                   " expected="+str(wanted))
            return
    print("NATIVE_ADVANCED_SHOOTER_OK "+str(source["scene"]["digest"])+
          " actions="+str(history.size())+
          " outcome="+("won" if bool(state["finished"])
                       else "lost" if bool(state["failed"]) else "playing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var selected: String=""
    match event.keycode:
        KEY_W,KEY_UP: selected="north"
        KEY_S,KEY_DOWN: selected="south"
        KEY_A,KEY_LEFT: selected="west"
        KEY_D,KEY_RIGHT: selected="east"
        KEY_SPACE,KEY_F: selected="fire"
        KEY_R: selected="reload"
        KEY_C: selected="cover"
        KEY_H: selected="medkit"
        KEY_SHIFT: selected="dash:east"
        KEY_ENTER,KEY_KP_ENTER: selected="extract"
        KEY_BACKSPACE: _reset()
    if selected!="":
        _step(selected)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var selected: String=""
        match event.button_index:
            JOY_BUTTON_DPAD_UP: selected="north"
            JOY_BUTTON_DPAD_DOWN: selected="south"
            JOY_BUTTON_DPAD_LEFT: selected="west"
            JOY_BUTTON_DPAD_RIGHT: selected="east"
            JOY_BUTTON_A: selected="fire"
            JOY_BUTTON_B: selected="reload"
            JOY_BUTTON_X: selected="cover"
            JOY_BUTTON_Y: selected="medkit"
            JOY_BUTTON_RIGHT_SHOULDER: selected="dash:east"
            JOY_BUTTON_START: selected="extract"
        if selected!="":
            _step(selected)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code==NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#101c2b"),true)
    if not ready_to_play:
        return
    var tilesize: float=maxf(9.0,minf(31.0,
        minf((size.x-215.0)/float(int(state["width"])),
             (size.y-125.0)/float(int(state["height"])))))
    var offset: Vector2=Vector2(14.0,74.0)
    _text(Vector2(14,26),"Original Advanced Arena · Godot 4",22,Color.WHITE)
    _text(Vector2(14,48),"Wave %d · HP %d/%d · Ammo %d/%d · Dodges %d" %
        [int(state["wave"]),int(state["hp"]),int(state["max_hp"]),
         int(state["ammo"]),int(state["magazine"]),int(state["dashes"])],
        15,Color("#b6ecdc"))
    for y in range(int(state["height"])):
        for x in range(int(state["width"])):
            var point: Array=[x,y]
            var rect: Rect2=Rect2(offset+Vector2(x,y)*tilesize,Vector2.ONE*tilesize)
            var color: Color=Color("#224459")
            if point in state["cover"]:
                color=Color("#637989")
            elif point in state["pickups"]:
                color=Color("#ecc87e")
            elif point==state["extraction"]:
                color=Color("#718ee4")
            for enemy in state["enemies"]:
                if enemy["pos"]==point:
                    color=Color("#ee817d")
            if point==state["player"]:
                color=Color("#83e4af")
            draw_rect(rect,color,true)
            draw_rect(rect,Color("#365e70"),false,1.0)
    var right: float=offset.x+tilesize*float(int(state["width"]))+12.0
    _text(Vector2(right,97),"Enemies "+str(state["enemies"].size()),14,Color.WHITE)
    _text(Vector2(right,119),"Defeated "+str(state["defeated"]),14,Color.WHITE)
    _text(Vector2(right,141),"Medkits "+str(state["medkits"]),14,Color.WHITE)
    _text(Vector2(right,163),"Score "+str(state["score"]),14,Color.WHITE)
    _text(Vector2(14,size.y-35),notice,13,Color("#e7d7b3"))
    _text(Vector2(14,size.y-14),"WASD move · F fire · R reload · H heal · C cover · Enter extract",
          12,Color("#b3d5d8"))


func _text(at: Vector2,label: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,label,
        HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_shooter_godot_package(session: dict, settings: dict | None = None,
                                 *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("authored arena native export requires human authorization")
    if type(session) is not dict or session.get("editor")!="shooter":
        raise AdvancedGodotExportError("only reviewed original shooter sessions use this native adapter")
    config=make_editor_document("shooter",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("shooter",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("shooter",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    state=session["state"]
    game={
        "schema":SCHEMA,"editor":"shooter","quality_floor":"advanced",
        "settings":config["settings"],"settings_digest":config["digest"],
        "scene":scene,"native_parity_verified":False,
        "external_assets_executed":False,
    }
    proof={
        "schema":PROOF_SCHEMA,"scene_digest":scene["digest"],
        "settings_digest":config["digest"],
        "actions":list(session["actions"]),
        "expected":{name:state[name] for name in PROOF_FIELDS},
        "python_session_digest":session["digest"],
        "verified_by_python_replay":True,
    }
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
            "Skeleton Original Advanced Arena").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_SHOOTER.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original advanced arena shooter · Godot 4\n\n"
            "Independent offline GDScript engine, authored terrain and spawn system.\n"
            "WASD/arrows move; F/Space fires; R reloads; C cover; H heals;\n"
            "Enter extracts; Shift evades; Backspace resets. Gamepad supported.\n"
            "Run: godot --headless --path godot -- --verify-shooter\n"
            "Native mode independently replays Python-validated commands and\n"
            "compares all original arena combat state and events; no gameplay\n"
            "source file in this bundle is fetched or executed from the web.\n"
            "Retail publication, hardware and rights certification are unapproved.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"shooter",
        "native_adapter":"godot4_independent_shooter",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{path:sha256(data).hexdigest() for path,data in sorted(files.items())},
        "godot_executed":False,
        "native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_SHOOTER",
         "render_shooter_godot_package"]
