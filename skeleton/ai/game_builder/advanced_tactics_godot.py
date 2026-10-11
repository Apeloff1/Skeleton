"""Independent, offline Godot 4 squad tactics game and replay-bound native export.

This adapter actually executes all squad commands, positional enemy AI,
overwatch, authored cover/LOS and mission outcomes in GDScript. Verified Python
sessions only supply an immutable expectation; Godot owns runtime state.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_godot_export import NativeAdvancedGamePackage, AdvancedGodotExportError, _json
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_tactics.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_tactics_proof.v1"
PROOF_FIELDS=("round","active_unit","action_points","units","enemies","obstacles",
              "objective","events","finished","failed","score")

GODOT_TACTICS=r'''
extends Control
## Native Advanced-floor tactical simulation, independent of Python gameplay.
const VERIFY_FLAG: String = "--verify-tactics"
const MAX_ACTIONS: int = 128
const ACTIONS: Array = [
    "north","south","west","east","switch",
    "attack:0","attack:1","guard","overwatch","heal","end_turn"
]
var source: Dictionary = {}
var settings: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var commands: Array = []
var ready_to_play: bool = false
var notice: String = "Original squad game · arrow keys move, 1/2 attack"


func _point(raw: Array) -> Array:
    return [int(raw[0]),int(raw[1])]


func _points(raw: Array) -> Array:
    var output: Array = []
    for point in raw:
        output.append(_point(point))
    return output


func _distance(a: Dictionary,b: Dictionary) -> int:
    return absi(int(a["x"])-int(b["x"]))+absi(int(a["y"])-int(b["y"]))


func _line_clear(x1: int,y1: int,x2: int,y2: int) -> bool:
    var dx: int = absi(x2-x1)
    var dy: int = absi(y2-y1)
    var sx: int = 1 if x1<x2 else -1
    var sy: int = 1 if y1<y2 else -1
    var error: int = dx-dy
    var x: int = x1
    var y: int = y1
    while x!=x2 or y!=y2:
        var doubled: int=2*error
        if doubled > -dy:
            error -= dy
            x += sx
        if doubled < dx:
            error += dx
            y += sy
        if (x!=x2 or y!=y2) and [x,y] in state["obstacles"]:
            return false
    return true


func _error(message: String) -> void:
    push_error("NATIVE_ADVANCED_TACTICS_ERROR: "+message)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String=FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length()>80000:
        _error("missing or oversized original squad source")
        return
    var parsed: Variant=JSON.parse_string(raw)
    if typeof(parsed)!=TYPE_DICTIONARY:
        _error("invalid original squad game JSON")
        return
    source=parsed
    if source.get("schema")!="skeleton.game_builder.godot_advanced_tactics.v1":
        _error("unrecognized native tactics source schema")
        return
    settings=source["settings"]
    layout=source["scene"]["layout"]
    if layout["squad_spawns"].size()!=2 or layout["enemy_spawns"].size()!=2:
        _error("native tactical scene requires two squad members and enemies")
        return
    ready_to_play=true
    _reset()
    get_window().title="Skeleton Original Squad Tactics"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var width: int=int(settings["board_width"])
    var height: int=int(settings["board_height"])
    var hp: int=int(settings["unit_health"])
    var squad: Array=[]
    var enemy: Array=[]
    for i in range(2):
        var p: Array=_point(layout["squad_spawns"][i])
        squad.append({
            "x":p[0],"y":p[1],"hp":hp,"guard":false,
            "overwatch":false,"medkits":2 if i==0 else 1,
        })
        var e: Array=_point(layout["enemy_spawns"][i])
        enemy.append({
            "x":e[0],"y":e[1],"hp":hp,"id":i,
        })
    state={
        "round":1,"active_unit":0,"action_points":int(settings["action_points"]),
        "units":squad,"enemies":enemy,
        "obstacles":_points(layout["obstacles"]),
        "objective":_point(layout["objective"]),
        "events":[],"finished":false,"failed":false,"score":0,
    }
    commands=[]
    notice="Eliminate the two enemies; protect the squad"
    queue_redraw()


func _enemy_round() -> Array:
    var report: Array=[]
    for enemy in state["enemies"]:
        var target: Dictionary={}
        var best: int=2147483647
        var best_y: int=2147483647
        var best_x: int=2147483647
        for squad in state["units"]:
            if int(squad["hp"])<=0:
                continue
            var distance: int=_distance(enemy,squad)
            if (distance<best or (distance==best and
                (int(squad["y"])<best_y or (int(squad["y"])==best_y
                 and int(squad["x"])<best_x)))):
                best=distance
                best_y=int(squad["y"])
                best_x=int(squad["x"])
                target=squad
        if target.is_empty():
            break
        if (best<=2 and _line_clear(int(enemy["x"]),int(enemy["y"]),
                                   int(target["x"]),int(target["y"]))):
            var damage: int=maxi(0,3-(2 if bool(target["guard"]) else 0))
            target["hp"]=maxi(0,int(target["hp"])-damage)
            report.append("enemy_fired")
        else:
            for axis in ["x","y"]:
                var delta: int=(1 if int(target[axis])>int(enemy[axis])
                        else -1 if int(target[axis])<int(enemy[axis]) else 0)
                var point: Array=[int(enemy["x"])+(delta if axis=="x" else 0),
                                  int(enemy["y"])+(delta if axis=="y" else 0)]
                var blocked: bool=point in state["obstacles"]
                for unit in state["units"]:
                    if int(unit["hp"])>0 and [unit["x"],unit["y"]]==point:
                        blocked=true
                for other in state["enemies"]:
                    if other is not enemy and [other["x"],other["y"]]==point:
                        blocked=true
                if delta!=0 and not blocked:
                    enemy[axis]=int(enemy[axis])+delta
                    report.append("enemy_advanced")
                    break
    for unit in state["units"]:
        if int(unit["hp"])>0 and bool(unit["overwatch"]):
            var range_limit: int=int(settings["attack_range"])
            for enemy in state["enemies"]:
                if (_distance(unit,enemy)<=range_limit
                    and _line_clear(int(unit["x"]),int(unit["y"]),
                                    int(enemy["x"]),int(enemy["y"]))):
                    enemy["hp"]=maxi(0,int(enemy["hp"])-2)
                    report.append("overwatch_hit")
                    break
        unit["overwatch"]=false
        unit["guard"]=false
    var alive: Array=[]
    for enemy in state["enemies"]:
        if int(enemy["hp"])>0:
            alive.append(enemy)
    state["enemies"]=alive
    state["round"]=int(state["round"])+1
    state["action_points"]=int(settings["action_points"])
    return report


func _step(action: String) -> bool:
    if (not ready_to_play or bool(state["finished"]) or bool(state["failed"])
        or commands.size()>=MAX_ACTIONS or action not in ACTIONS):
        return false
    var unit: Dictionary=state["units"][int(state["active_unit"])]
    var ap: int=int(state["action_points"])
    var events: Array=[]
    if action=="end_turn":
        events.append_array(_enemy_round())
    elif action=="switch":
        var next_unit: int=1-int(state["active_unit"])
        if int(state["units"][next_unit]["hp"])<=0:
            return false
        state["active_unit"]=next_unit
    elif action in ["north","south","west","east"]:
        if ap<=0:
            return false
        var direction: Array=([0,-1] if action=="north" else [0,1] if action=="south"
                          else [-1,0] if action=="west" else [1,0])
        var x: int=int(unit["x"])+int(direction[0])
        var y: int=int(unit["y"])+int(direction[1])
        if x<0 or x>=int(settings["board_width"]) or y<0 or y>=int(settings["board_height"]):
            return false
        var cell: Array=[x,y]
        var blocked: bool=cell in state["obstacles"]
        for other in state["units"]:
            if other is not unit and int(other["hp"])>0 and [other["x"],other["y"]]==cell:
                blocked=true
        for enemy in state["enemies"]:
            if int(enemy["hp"])>0 and [enemy["x"],enemy["y"]]==cell:
                blocked=true
        if blocked:
            return false
        unit["x"]=x
        unit["y"]=y
        state["action_points"]=ap-1
        events.append("unit_moved")
    elif action.begins_with("attack:"):
        if ap<=0:
            return false
        var id: int=int(action.substr(7))
        var target: Dictionary={}
        for enemy in state["enemies"]:
            if int(enemy["id"])==id:
                target=enemy
                break
        if target.is_empty():
            return false
        if (_distance(unit,target)>int(settings["attack_range"])
            or not _line_clear(int(unit["x"]),int(unit["y"]),
                               int(target["x"]),int(target["y"]))):
            return false
        target["hp"]=maxi(0,int(target["hp"])-4)
        state["action_points"]=ap-1
        events.append("direct_attack")
        if int(target["hp"])==0:
            state["score"]=int(state["score"])+100
            events.append("enemy_defeated")
        var alive: Array=[]
        for enemy in state["enemies"]:
            if int(enemy["hp"])>0:
                alive.append(enemy)
        state["enemies"]=alive
    else:
        if ap<=0:
            return false
        match action:
            "guard":unit["guard"]=true
            "overwatch":unit["overwatch"]=true
            "heal":
                if int(unit["medkits"])<=0:
                    return false
                unit["medkits"]=int(unit["medkits"])-1
                unit["hp"]=mini(int(settings["unit_health"]),int(unit["hp"])+5)
        state["action_points"]=ap-1
        events.append(action)
    if state["enemies"].is_empty():
        state["finished"]=true
        events.append("mission_complete")
    var squad_lost: bool=true
    for member in state["units"]:
        if int(member["hp"])>0:
            squad_lost=false
    if squad_lost:
        state["failed"]=true
        events.append("squad_lost")
    state["events"]=events
    commands.append(action)
    notice=("Mission complete" if bool(state["finished"]) else
            "Squad defeated" if bool(state["failed"]) else
            "Turn %d · %s" % [int(state["round"]),action])
    queue_redraw()
    return true


func _normalize_units(raw: Array,enemy: bool=false) -> Array:
    var out: Array=[]
    for entry in raw:
        var obj: Dictionary=entry.duplicate(true)
        for name in ["x","y","hp"]:
            obj[name]=int(obj[name])
        if enemy:
            obj["id"]=int(obj["id"])
        else:
            obj["medkits"]=int(obj["medkits"])
        out.append(obj)
    return out


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>180000:
        _error("missing or oversized native tactical proof")
        return
    var parsed: Variant=JSON.parse_string(raw)
    if typeof(parsed)!=TYPE_DICTIONARY:
        _error("invalid tactical source proof")
        return
    var proof: Dictionary=parsed
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_tactics_proof.v1"
        or proof.get("scene_digest")!=source["scene"]["digest"]
        or proof.get("settings_digest")!=source.get("settings_digest")):
        _error("source/setting digest mismatch")
        return
    var actions: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if typeof(actions)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY:
        _error("invalid native tactical replay contract")
        return
    if actions.size()>MAX_ACTIONS:
        _error("native tactical replay exceeds capacity")
        return
    for action in actions:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _error("rejected tactical order "+str(action))
            return
    if state.size()!=expected.size() or commands.size()!=actions.size():
        _error("unexpected tactical proof fields or commands")
        return
    for field in state:
        if not expected.has(field):
            _error("missing tactical field "+field)
            return
        var wanted: Variant=expected[field]
        if field=="units":
            wanted=_normalize_units(wanted)
        elif field=="enemies":
            wanted=_normalize_units(wanted,true)
        elif field=="obstacles":
            wanted=_points(wanted)
        elif field=="objective":
            wanted=_point(wanted)
        if state[field]!=wanted:
            _error("tactics divergence "+field+" native="+str(state[field])+
                   " expected="+str(wanted))
            return
    print("NATIVE_ADVANCED_TACTICS_OK "+str(source["scene"]["digest"])+
          " turns="+str(state["round"])+" actions="+str(commands.size())+
          " result="+("won" if bool(state["finished"]) else
                     "lost" if bool(state["failed"]) else "playing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String=""
    match event.keycode:
        KEY_W,KEY_UP:action="north"
        KEY_S,KEY_DOWN:action="south"
        KEY_A,KEY_LEFT:action="west"
        KEY_D,KEY_RIGHT:action="east"
        KEY_TAB:action="switch"
        KEY_1:action="attack:0"
        KEY_2:action="attack:1"
        KEY_G:action="guard"
        KEY_O:action="overwatch"
        KEY_H:action="heal"
        KEY_ENTER,KEY_KP_ENTER:action="end_turn"
        KEY_R:_reset()
    if action!="":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String=""
        match event.button_index:
            JOY_BUTTON_DPAD_UP:action="north"
            JOY_BUTTON_DPAD_DOWN:action="south"
            JOY_BUTTON_DPAD_LEFT:action="west"
            JOY_BUTTON_DPAD_RIGHT:action="east"
            JOY_BUTTON_A:action="attack:0"
            JOY_BUTTON_B:action="attack:1"
            JOY_BUTTON_X:action="overwatch"
            JOY_BUTTON_Y:action="guard"
            JOY_BUTTON_LEFT_SHOULDER:action="switch"
            JOY_BUTTON_RIGHT_SHOULDER:action="heal"
            JOY_BUTTON_START:action="end_turn"
        if action!="":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code==NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#101c2b"))
    if not ready_to_play:
        return
    var width: int=int(settings["board_width"])
    var height: int=int(settings["board_height"])
    var tile: float=maxf(8.0,minf(32.0,minf((size.x-135.0)/float(width),
                                      (size.y-170.0)/float(height))))
    var origin: Vector2=Vector2(18,100)
    _text(Vector2(18,32),"Original Advanced Squad Tactics",23,Color.WHITE)
    _text(Vector2(18,61),"Round %d  AP %d  Active %d  Enemies %d  Score %d" %
        [int(state["round"]),int(state["action_points"]),
         int(state["active_unit"])+1,state["enemies"].size(),int(state["score"])],
        15,Color("#b2e9da"))
    _text(Vector2(18,81),notice,13,Color("#f0d19e"))
    for y in range(height):
        for x in range(width):
            var spot: Array=[x,y]
            var ink: Color=Color("#244457")
            if spot in state["obstacles"]:
                ink=Color("#647987")
            if spot==state["objective"]:
                ink=Color("#bba26e")
            for enemy in state["enemies"]:
                if [enemy["x"],enemy["y"]]==spot:
                    ink=Color("#e4767b")
            for i in range(state["units"].size()):
                var unit: Dictionary=state["units"][i]
                if [unit["x"],unit["y"]]==spot:
                    ink=(Color("#8feac1") if i==int(state["active_unit"])
                         else Color("#6d9bd9"))
            var rect: Rect2=Rect2(origin+Vector2(x,y)*tile,Vector2.ONE*tile)
            draw_rect(rect,ink,true)
            draw_rect(rect,Color("#365e70"),false,1.0)
    _text(Vector2(18,size.y-42),"Arrows move · Tab switch · 1/2 attack · G guard · O overwatch",13,Color.WHITE)
    _text(Vector2(18,size.y-21),"H heal · Enter enemy turn · R reset · Offline original game",12,Color("#b8d7dc"))


func _text(point: Vector2,message: String,font_size: int,color: Color) -> void:
    draw_string(ThemeDB.fallback_font,point,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,color)
'''


def render_tactics_godot_package(session: dict, settings: dict | None = None,
                                 *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("native tactical game export requires trusted human authorization")
    if type(session) is not dict or session.get("editor")!="tactics":
        raise AdvancedGodotExportError("only a reviewed original squad session has this native adapter")
    config=make_editor_document("tactics",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("tactics",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("tactics",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    state=session["state"]
    game={
        "schema":SCHEMA,"editor":"tactics","quality_floor":"advanced",
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
                  "Skeleton Original Advanced Tactics").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_TACTICS.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Native Squad Tactics\n\n"
            "Standalone offline Godot 4.4.1+ game for original squad battles.\n"
            "WASD/arrow movement, Tab swap, 1/2 target enemies, G guard,\n"
            "O overwatch, H heal, Enter enemy round, R restart, gamepad input.\n"
            "godot --headless --path godot -- --verify-tactics\n"
            "independently executes native tactical commands and checks complete\n"
            "source-bound final gameplay state against Python-reviewed proof.\n"
            "No copyright, hardware certification or publication approval implied.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"tactics",
        "native_adapter":"godot4_independent_tactics",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{p:sha256(body).hexdigest() for p,body in sorted(files.items())},
        "godot_executed":False,"native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_TACTICS",
         "render_tactics_godot_package"]
