"""Original offline Godot 4 tower defense with independent wave simulation.

This native adapter directly executes the original Python reference's bounded
rules in GDScript and verifies final source-bound gameplay state. Authored
build slots/wave count are respected; zero executable outside dependencies.
"""
from __future__ import annotations

from hashlib import sha256
from .advanced_godot_export import NativeAdvancedGamePackage, AdvancedGodotExportError, _json
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_tower_defense.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_tower_defense_proof.v1"
PROOF_FIELDS=(
    "tick","credits","base_hp","towers","enemies","spawned","defeated",
    "escaped","waves_completed","priority","events","finished","failed",
    "seed","lane_length","allowed_slots","wave_limit",
)

GODOT_DEFENSE=r'''
extends Control
## Asset-free offline Godot 4 original lane defense. No Python runtime here.
const PROOF_FLAG: String="--verify-defense"
const MAX_ACTIONS: int=128
const ACTIONS: Array=[
    "tick","tick:4",
    "build:0","build:1","build:2",
    "upgrade:0","upgrade:1","upgrade:2",
    "sell:0","sell:1","sell:2",
    "priority:first","priority:strong"
]
var source: Dictionary={}
var config: Dictionary={}
var layout: Dictionary={}
var state: Dictionary={}
var commands: Array=[]
var ready_to_play: bool=false
var notice: String="Original Tower Defense: build, defend, upgrade and survive"


func _fail(message: String) -> void:
    push_error("NATIVE_ADVANCED_DEFENSE_ERROR: "+message)
    if PROOF_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String=FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length()>80000:
        _fail("missing or oversized original source")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid authored defense JSON")
        return
    source=decoded
    if source.get("schema")!="skeleton.game_builder.godot_advanced_tower_defense.v1":
        _fail("unknown native tower-defense source contract")
        return
    config=source["settings"]
    layout=source["scene"]["layout"]
    if (int(layout["waves"])<1 or int(layout["waves"])>12
        or layout["build_slots"].is_empty() or layout["build_slots"].size()>3):
        _fail("authored tower configuration outside bounded rules")
        return
    ready_to_play=true
    _reset()
    get_window().title="Skeleton Original Advanced Tower Defense"
    if PROOF_FLAG in OS.get_cmdline_user_args():
        _verify()


func _numbers(raw: Array) -> Array:
    var result: Array=[]
    for item in raw:
        result.append(int(item))
    return result


func _reset() -> void:
    state={
        "tick":0,"credits":int(config["starting_credits"]),"base_hp":20,
        "towers":[],"enemies":[],"spawned":0,"defeated":0,"escaped":0,
        "waves_completed":0,"priority":"first","events":[],
        "finished":false,"failed":false,
        "seed":int(source["scene"]["seed"]),
        "lane_length":int(config["lane_length"]),
        "allowed_slots":_numbers(layout["build_slots"]),
        "wave_limit":int(layout["waves"]),
    }
    commands=[]
    notice="Build towers (1–3); Space advances time; B selects target policy"
    queue_redraw()


func _tick() -> Array:
    state["tick"]=int(state["tick"])+1
    var events: Array=[]
    var wave_size: int=int(config["wave_size"])
    var limit: int=wave_size*int(state["wave_limit"])
    if int(state["spawned"])<limit and int(state["tick"])%2==1:
        var ident: int=int(state["spawned"])
        state["enemies"].append({
            "id":ident,"x":0,"hp":3+int(ident/wave_size)*2,
            "armor":ident%3==0,"slow":0,
        })
        state["spawned"]=ident+1
        events.append("enemy_spawned")
    for enemy in state["enemies"]:
        enemy["x"]=int(enemy["x"])+(1 if int(enemy["slow"])==0 else 0)
        enemy["slow"]=maxi(0,int(enemy["slow"])-1)
    for tower in state["towers"]:
        var chosen: Dictionary={}
        var strongest: int=-2147483647
        var best_id: int=2147483647
        for enemy in state["enemies"]:
            var position: int=int(tower["slot"])*maxi(1,int(int(config["lane_length"])/3))+2
            if absi(int(enemy["x"])-position)>int(config["tower_range"]):
                continue
            var score: int=(int(enemy["hp"]) if state["priority"]=="strong"
                            else int(enemy["x"]))
            if score>strongest or (score==strongest and int(enemy["id"])<best_id):
                strongest=score
                best_id=int(enemy["id"])
                chosen=enemy
        if chosen.is_empty():
            continue
        var damage: int=int(config["tower_damage"])*int(tower["level"])
        if bool(chosen["armor"]):
            damage=maxi(1,damage-1)
        chosen["hp"]=int(chosen["hp"])-damage
        if int(tower["level"])>=2:
            chosen["slow"]=1
        events.append("tower_fired")
    var survivors: Array=[]
    for enemy in state["enemies"]:
        if int(enemy["hp"])<=0:
            state["defeated"]=int(state["defeated"])+1
            state["credits"]=int(state["credits"])+5
            events.append("enemy_defeated")
        elif int(enemy["x"])>=int(config["lane_length"]):
            state["escaped"]=int(state["escaped"])+1
            state["base_hp"]=maxi(0,int(state["base_hp"])-2)
            events.append("enemy_escaped")
        else:
            survivors.append(enemy)
    state["enemies"]=survivors
    var resolved: int=mini(int(state["wave_limit"]),
        int((int(state["defeated"])+int(state["escaped"]))/wave_size))
    if resolved>int(state["waves_completed"]):
        state["waves_completed"]=resolved
        events.append("wave_resolved")
    if int(state["spawned"])==limit and state["enemies"].is_empty():
        state["waves_completed"]=int(state["wave_limit"])
        state["finished"]=true
        events.append("authored_waves_resolved")
    if int(state["base_hp"])==0:
        state["failed"]=true
        state["finished"]=false
        events.append("base_destroyed")
    return events


func _step(action: String) -> bool:
    if (not ready_to_play or bool(state["finished"]) or bool(state["failed"])
        or commands.size()>=MAX_ACTIONS or action not in ACTIONS):
        return false
    var events: Array=[]
    if action in ["tick","tick:4"]:
        for i in range(4 if action=="tick:4" else 1):
            if bool(state["finished"]) or bool(state["failed"]):
                break
            events.append_array(_tick())
    elif action.begins_with("build:"):
        var slot: int=int(action.substr(6))
        if slot not in state["allowed_slots"] or int(state["credits"])<20:
            return false
        for tower in state["towers"]:
            if int(tower["slot"])==slot:
                return false
        state["credits"]=int(state["credits"])-20
        state["towers"].append({"slot":slot,"level":1})
        events.append("tower_constructed")
    elif action.begins_with("upgrade:"):
        var slot: int=int(action.substr(8))
        var found: Dictionary={}
        for tower in state["towers"]:
            if int(tower["slot"])==slot:
                found=tower
                break
        if found.is_empty() or int(found["level"])>=3:
            return false
        var price: int=15*int(found["level"])
        if int(state["credits"])<price:
            return false
        state["credits"]=int(state["credits"])-price
        found["level"]=int(found["level"])+1
        events.append("tower_upgraded")
    elif action.begins_with("sell:"):
        var slot: int=int(action.substr(5))
        var found: Dictionary={}
        for tower in state["towers"]:
            if int(tower["slot"])==slot:
                found=tower
                break
        if found.is_empty():
            return false
        state["credits"]=int(state["credits"])+10*int(found["level"])
        state["towers"].erase(found)
        events.append("tower_sold")
    elif action.begins_with("priority:"):
        state["priority"]=action.substr(9)
        events.append("target_priority_changed")
    state["events"]=events
    commands.append(action)
    notice=("Game won" if bool(state["finished"])
            else "Base lost" if bool(state["failed"])
            else "Tick %d · %s" % [int(state["tick"]),action])
    queue_redraw()
    return true


func _normalize_towers(raw: Array) -> Array:
    var output: Array=[]
    for tower in raw:
        output.append({"slot":int(tower["slot"]),"level":int(tower["level"])})
    return output


func _normalize_enemies(raw: Array) -> Array:
    var output: Array=[]
    for enemy in raw:
        output.append({
            "id":int(enemy["id"]),"x":int(enemy["x"]),"hp":int(enemy["hp"]),
            "armor":bool(enemy["armor"]),"slow":int(enemy["slow"]),
        })
    return output


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>180000:
        _fail("missing or oversized original proof")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid replay proof")
        return
    var proof: Dictionary=decoded
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_tower_defense_proof.v1"
        or proof.get("scene_digest")!=source["scene"]["digest"]
        or proof.get("settings_digest")!=source.get("settings_digest")):
        _fail("unapproved source/proof mismatch")
        return
    var actions: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if typeof(actions)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY:
        _fail("invalid native game transcript")
        return
    if actions.size()>MAX_ACTIONS:
        _fail("native proof command budget exceeded")
        return
    for action in actions:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _fail("rejected tower order "+str(action))
            return
    if state.size()!=expected.size() or commands.size()!=actions.size():
        _fail("final state or command schema mismatch")
        return
    for field in state:
        if not expected.has(field):
            _fail("missing native tower state "+field)
            return
        var wanted: Variant=expected[field]
        if field=="towers":
            wanted=_normalize_towers(wanted)
        elif field=="enemies":
            wanted=_normalize_enemies(wanted)
        elif field=="allowed_slots":
            wanted=_numbers(wanted)
        if state[field]!=wanted:
            _fail("tower defense divergence "+field+" native="+str(state[field])
                  +" python="+str(wanted))
            return
    print("NATIVE_ADVANCED_DEFENSE_OK "+str(source["scene"]["digest"])+
          " actions="+str(commands.size())+
          " waves="+str(state["waves_completed"])+
          " result="+("won" if bool(state["finished"]) else
                     "lost" if bool(state["failed"]) else "playing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String=""
    match event.keycode:
        KEY_SPACE: action="tick"
        KEY_ENTER,KEY_KP_ENTER: action="tick:4"
        KEY_1: action="build:0"
        KEY_2: action="build:1"
        KEY_3: action="build:2"
        KEY_Q: action="upgrade:0"
        KEY_W: action="upgrade:1"
        KEY_E: action="upgrade:2"
        KEY_Z: action="sell:0"
        KEY_X: action="sell:1"
        KEY_C: action="sell:2"
        KEY_F: action="priority:first"
        KEY_S: action="priority:strong"
        KEY_R: _reset()
    if action!="":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String=""
        match event.button_index:
            JOY_BUTTON_A: action="tick"
            JOY_BUTTON_B: action="tick:4"
            JOY_BUTTON_DPAD_LEFT: action="build:0"
            JOY_BUTTON_DPAD_UP: action="build:1"
            JOY_BUTTON_DPAD_RIGHT: action="build:2"
            JOY_BUTTON_X: action="upgrade:0"
            JOY_BUTTON_Y: action="upgrade:1"
            JOY_BUTTON_LEFT_SHOULDER: action="priority:first"
            JOY_BUTTON_RIGHT_SHOULDER: action="priority:strong"
            JOY_BUTTON_START: _reset()
        if action!="":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code==NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#101b2b"))
    if not ready_to_play:
        return
    _text(Vector2(18,29),"Original Tower Defense · Advanced",22,Color.WHITE)
    _text(Vector2(18,55),"Base %d HP  ·  Credits %d  ·  Wave %d/%d  ·  Tick %d" %
        [int(state["base_hp"]),int(state["credits"]),int(state["waves_completed"]),
         int(state["wave_limit"]),int(state["tick"])],
        15,Color("#b1ebd8"))
    _text(Vector2(18,76),"Priority "+str(state["priority"])+
        " ·  Kills "+str(state["defeated"])+" · Escapes "+str(state["escaped"]),
        13,Color("#ebd5a4"))
    var length: int=int(state["lane_length"])
    var scale: float=maxf(5.0,minf(26.0,(size.x-40.0)/float(length+1)))
    var start: Vector2=Vector2(18,140)
    for i in range(length+1):
        var spot: Vector2=start+Vector2(float(i)*scale,0)
        draw_rect(Rect2(spot,Vector2(scale-2.0,25.0)),Color("#285065"),true)
        if i==length:
            draw_rect(Rect2(spot,Vector2(scale-2.0,25.0)),Color("#db767a"),true)
    for slot in state["allowed_slots"]:
        var position: int=int(slot)*maxi(1,int(length/3))+2
        var at: Vector2=start+Vector2(float(position)*scale,-36)
        var level: int=0
        for tower in state["towers"]:
            if int(tower["slot"])==int(slot):
                level=int(tower["level"])
        draw_rect(Rect2(at,Vector2(scale-3.0,26.0)),
                  Color("#8de1b3") if level>0 else Color("#8395b2"),true)
        _text(at+Vector2(1,-5),"T"+str(slot)+":"+str(level),12,Color.WHITE)
    for enemy in state["enemies"]:
        var px: float=start.x+float(int(enemy["x"]))*scale+scale/2.0
        draw_circle(Vector2(px,start.y+12.0),maxf(3.0,scale*0.30),
                    Color("#ed907d"))
    _text(Vector2(18,210),notice,14,Color("#f2d9ac"))
    _text(Vector2(18,244),"1–3 build  ·  Q/W/E upgrade  ·  Z/X/C sell",13,Color.WHITE)
    _text(Vector2(18,268),"Space tick  ·  Enter four ticks  ·  F/S priority  ·  R restart",
          13,Color("#bedbdd"))


func _text(at: Vector2,message: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_defense_godot_package(session: dict, settings: dict | None = None,
                                 *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("tower defense native export requires explicit operator authorization")
    if type(session) is not dict or session.get("editor")!="tower_defense":
        raise AdvancedGodotExportError("only original verified tower defense sessions have a native Godot adapter")
    config=make_editor_document("tower_defense",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("tower_defense",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("tower_defense",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    state=session["state"]
    game={
        "schema":SCHEMA,"editor":"tower_defense","quality_floor":"advanced",
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
                   "Skeleton Original Advanced Tower Defense").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_DEFENSE.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Native Tower Defense\n\n"
            "Standalone offline Godot 4.4.1+ authored defense game.\n"
            "1–3 build, Q/W/E upgrade, Z/X/C sell, F/S set targeting,\n"
            "Space advances a tick, Enter advances four; R restarts.\n"
            "Godot native replay: --headless --path godot -- --verify-defense\n"
            "Native simulation independently executes reviewed action transcripts\n"
            "and compares the complete gameplay state with Python verified proof.\n"
            "Distribution, licensed assets and hardware certification not approved.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"tower_defense",
        "native_adapter":"godot4_independent_tower_defense",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{path:sha256(raw).hexdigest() for path,raw in sorted(files.items())},
        "godot_executed":False,"native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_DEFENSE",
         "render_defense_godot_package"]
