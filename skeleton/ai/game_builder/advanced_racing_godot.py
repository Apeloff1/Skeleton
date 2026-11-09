"""Offline original Godot 4 racing simulator with independent fixed-step parity.

Actual GDScript game logic models acceleration, braking, steering, nitro,
weather/grip, tires, engine damage, pits, track hazards, fuel and lap results.
No Python runtime, external assets or network in generated game.
"""
from __future__ import annotations
from hashlib import sha256

from .advanced_godot_export import NativeAdvancedGamePackage, AdvancedGodotExportError, _json
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_racing.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_racing_proof.v1"
PROOF_FIELDS=("tick","distance","position","lap","laps","track_length",
              "speed","lane","fuel","fuel_capacity","tire_condition",
              "engine_integrity","boost_charges","pit_stops","pit_crews",
              "weather","corners","track_obstacle","events","finished",
              "failed","championship_points")

GODOT_RACING=r'''
extends Control
## Native independent original circuit racer, deterministic authored physics.
const VERIFY_FLAG: String = "--verify-racing"
const MAX_ACTIONS: int = 128
const ACTIONS: Array = [
    "accelerate","brake","coast","steer_left","steer_right","boost","pit"
]
var authored: Dictionary = {}
var config: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var commands: Array = []
var ready_to_play: bool = false
var announcement: String = "Original Circuit · Accelerate, steer and race"


func _integers(raw: Array) -> Array:
    var values: Array = []
    for item in raw:
        values.append(int(item))
    return values


func _error(message: String) -> void:
    push_error("NATIVE_ADVANCED_RACING_ERROR: "+message)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var json_text: String=FileAccess.get_file_as_string("res://game.json")
    if json_text.is_empty() or json_text.length()>80000:
        _error("missing or oversized original circuit source")
        return
    var decoded: Variant=JSON.parse_string(json_text)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _error("invalid original race source")
        return
    authored=decoded
    if authored.get("schema")!="skeleton.game_builder.godot_advanced_racing.v1":
        _error("unknown native circuit contract")
        return
    config=authored["settings"]
    layout=authored["scene"]["layout"]
    if (int(config["track_length"])<20 or int(config["track_length"])>50000
        or int(config["laps"])<1 or int(config["laps"])>50
        or layout["corners"].size()>24
        or str(layout["weather"]) not in ["dry","wet","storm"]):
        _error("invalid bounded circuit geometry or weather")
        return
    ready_to_play=true
    _reset()
    get_window().title="Skeleton Original Advanced Circuit Racing"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var track_length: int=int(config["track_length"])
    var laps: int=int(config["laps"])
    var tank: int=maxi(20,int(track_length*laps/5))
    state={
        "tick":0,"distance":0,"position":0,"lap":0,"laps":laps,
        "track_length":track_length,"speed":0,
        "lane":int(layout["starting_lane"]),"fuel":tank,
        "fuel_capacity":tank,"tire_condition":100,"engine_integrity":100,
        "boost_charges":3,"pit_stops":0,"pit_crews":3,
        "weather":str(layout["weather"]),
        "corners":_integers(layout["corners"]),
        "track_obstacle":int(layout["track_obstacle"]),
        "events":[],"finished":false,"failed":false,
        "championship_points":0,
    }
    commands=[]
    announcement="Find your racing line, protect your tires and finish"
    queue_redraw()


func _step(action: String) -> bool:
    if (not ready_to_play or bool(state["finished"]) or bool(state["failed"])
        or commands.size()>=MAX_ACTIONS or action not in ACTIONS):
        return false
    # All rejected actions are rejected before the authoritative state mutates.
    if action=="boost" and int(state["boost_charges"])<=0:
        return false
    if action=="pit" and (
        int(state["position"])>mini(10,int(int(config["track_length"])/5))
        or int(state["speed"])>maxi(3,int(config["brake_force"]))
        or int(state["pit_crews"])<=0):
        return false
    state["tick"]=int(state["tick"])+1
    var events: Array=[]
    var weather: String=str(state["weather"])
    var top_speed: int=int(config["max_speed"])
    var grip: int=top_speed
    if weather=="wet":
        grip-=maxi(1,int(top_speed/4))
    elif weather=="storm":
        grip-=maxi(2,int(top_speed/3))
    grip=maxi(2,grip)
    var position_before: int=int(state["position"])
    if action=="pit":
        state["pit_crews"]=int(state["pit_crews"])-1
        state["pit_stops"]=int(state["pit_stops"])+1
        state["fuel"]=int(state["fuel_capacity"])
        state["tire_condition"]=100
        state["engine_integrity"]=mini(100,int(state["engine_integrity"])+30)
        state["speed"]=0
        events.append("pit_service")
        state["events"]=events
        commands.append(action)
        announcement="Pit service completed"
        queue_redraw()
        return true
    match action:
        "accelerate":
            state["speed"]=mini(top_speed,
                int(state["speed"])+int(config["acceleration"]))
        "brake":
            state["speed"]=maxi(0,
                int(state["speed"])-int(config["brake_force"]))
        "coast":
            state["speed"]=maxi(0,int(state["speed"])-1)
        "steer_left","steer_right":
            var direction: int=-1 if action=="steer_left" else 1
            state["lane"]=clampi(int(state["lane"])+direction,-1,1)
            state["speed"]=maxi(0,int(state["speed"])-1)
            events.append("lane_changed")
        "boost":
            state["boost_charges"]=int(state["boost_charges"])-1
            state["speed"]=mini(top_speed,
                int(state["speed"])+int(config["acceleration"])*2)
            events.append("boost_consumed")
    if int(state["fuel"])<=0:
        state["speed"]=0
        events.append("fuel_empty")
    else:
        state["fuel"]=maxi(0,int(state["fuel"])-1-int(int(state["speed"])/15))
    if int(state["tire_condition"])<25 or int(state["engine_integrity"])<30:
        state["speed"]=mini(int(state["speed"]),maxi(1,int(grip/2)))
        events.append("mechanical_limp_mode")
    var distance_before: int=int(state["distance"])
    var distance_after: int=mini(int(config["track_length"])*int(config["laps"]),
        distance_before+int(state["speed"]))
    var lap_before: int=int(distance_before/int(config["track_length"]))
    var lap_after: int=int(distance_after/int(config["track_length"]))
    for lap in range(lap_before,lap_after+1):
        var segment_start: int=maxi(distance_before,lap*int(config["track_length"]))
        var segment_end: int=mini(distance_after,(lap+1)*int(config["track_length"]))
        for corner in state["corners"]:
            var absolute: int=lap*int(config["track_length"])+int(corner)
            if (segment_start<=absolute and absolute<=segment_end
                and int(state["speed"])>grip):
                state["tire_condition"]=maxi(0,int(state["tire_condition"])-12)
                state["engine_integrity"]=maxi(0,int(state["engine_integrity"])-6)
                events.append("corner_understeer_damage")
        var obstruction: int=lap*int(config["track_length"])+int(state["track_obstacle"])
        if segment_start<=obstruction and obstruction<=segment_end and int(state["lane"])==0:
            state["engine_integrity"]=maxi(0,int(state["engine_integrity"])-12)
            events.append("centerline_obstacle_hit")
    state["tire_condition"]=maxi(0,int(state["tire_condition"])-1)
    state["distance"]=distance_after
    state["position"]=distance_after%int(config["track_length"])
    state["lap"]=mini(int(config["laps"]),int(distance_after/int(config["track_length"])))
    if lap_after>lap_before:
        events.append("lap_completed")
    if int(state["engine_integrity"])==0:
        state["failed"]=true
        events.append("engine_destroyed")
    if distance_after>=int(config["track_length"])*int(config["laps"]) and not bool(state["failed"]):
        state["finished"]=true
        state["championship_points"]=maxi(1,1000-int(state["tick"])*4
                                      -(100-int(state["engine_integrity"]))*3)
        events.append("race_completed")
    state["events"]=events
    commands.append(action)
    announcement=("Race won!" if bool(state["finished"])
        else "Engine destroyed" if bool(state["failed"])
        else "Lap %d · %s" % [int(state["lap"])+1,action])
    queue_redraw()
    return true


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>180000:
        _error("missing or oversized racing proof")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _error("invalid racing proof JSON")
        return
    var proof: Dictionary=decoded
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_racing_proof.v1"
        or proof.get("settings_digest")!=authored.get("settings_digest")
        or proof.get("scene_digest")!=authored["scene"]["digest"]):
        _error("original race configuration/proof mismatch")
        return
    var actions: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if typeof(actions)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY or actions.size()>MAX_ACTIONS:
        _error("invalid or oversized racing action proof")
        return
    for action in actions:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _error("native action rejected: "+str(action))
            return
    if state.size()!=expected.size() or commands.size()!=actions.size():
        _error("missing or unexpected racing state field")
        return
    for field in state:
        if not expected.has(field):
            _error("missing expected racing field "+field)
            return
        var wanted: Variant=expected[field]
        if field=="corners":
            wanted=_integers(wanted)
        if state[field]!=wanted:
            _error("racing divergence "+field+" native="+str(state[field])
                   +" python="+str(wanted))
            return
    print("NATIVE_ADVANCED_RACING_OK "+str(authored["scene"]["digest"])+
          " actions="+str(commands.size())+
          " laps="+str(state["lap"])+
          " result="+("won" if bool(state["finished"]) else
                     "lost" if bool(state["failed"]) else "racing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String=""
    match event.keycode:
        KEY_W,KEY_UP:action="accelerate"
        KEY_S,KEY_DOWN:action="brake"
        KEY_SPACE:action="coast"
        KEY_A,KEY_LEFT:action="steer_left"
        KEY_D,KEY_RIGHT:action="steer_right"
        KEY_B:action="boost"
        KEY_P:action="pit"
        KEY_R:_reset()
    if action!="":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String=""
        match event.button_index:
            JOY_BUTTON_A:action="accelerate"
            JOY_BUTTON_B:action="brake"
            JOY_BUTTON_DPAD_LEFT:action="steer_left"
            JOY_BUTTON_DPAD_RIGHT:action="steer_right"
            JOY_BUTTON_X:action="boost"
            JOY_BUTTON_Y:action="pit"
            JOY_BUTTON_START:_reset()
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
    _text(Vector2(18,32),"Original Advanced Circuit Racing",23,Color.WHITE)
    _text(Vector2(18,57),"Lap %d/%d · Speed %d · Distance %d · Weather %s" %
        [int(state["lap"])+1,int(state["laps"]),int(state["speed"]),
         int(state["distance"]),str(state["weather"])],15,Color("#b1ebdb"))
    _text(Vector2(18,80),"Fuel %d  ·  Tires %d%%  ·  Engine %d%%  ·  Nitro %d  ·  Pits %d" %
        [int(state["fuel"]),int(state["tire_condition"]),
         int(state["engine_integrity"]),int(state["boost_charges"]),
         int(state["pit_crews"])],15,Color("#f1d4a5"))
    _text(Vector2(18,103),announcement,14,Color.WHITE)
    var width: float=maxf(250.0,size.x-50.0)
    var y_start: float=152.0
    for lane in range(-1,2):
        var lane_y: float=y_start+float(lane+1)*69.0
        draw_rect(Rect2(Vector2(20,lane_y),Vector2(width,59)),
                  Color("#233e51"),true)
        draw_line(Vector2(20,lane_y+59),Vector2(20+width,lane_y+59),
                  Color("#7d9ba6"),1.0)
        if lane==int(state["lane"]):
            var race_progress: float=float(int(state["position"]))/float(int(state["track_length"]))
            var player_x: float=24+race_progress*(width-48)
            draw_rect(Rect2(Vector2(player_x,lane_y+13),Vector2(35,28)),
                      Color("#82edbb"),true)
    for obstacle in [int(state["track_obstacle"])]:
        var obstacle_x: float=20+float(obstacle)/float(int(state["track_length"]))*width
        draw_rect(Rect2(Vector2(obstacle_x,y_start+69.0+16),Vector2(10,26)),
                  Color("#e77d82"),true)
    for corner in state["corners"]:
        var bend_x: float=20+float(corner)/float(int(state["track_length"]))*width
        draw_line(Vector2(bend_x,y_start+10),Vector2(bend_x,y_start+190),
                  Color("#c8ad72"),1.0)
    _text(Vector2(18,mini(size.y-20.0,403.0)),
          "W accelerate · S brake · A/D steer · Space coast · B boost · P pit · R reset",
          13,Color("#c2dbe0"))


func _text(point: Vector2,message: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,point,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_racing_godot_package(session: dict, settings: dict | None = None,
                                *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("original racing native export requires explicit authorization")
    if type(session) is not dict or session.get("editor")!="racing":
        raise AdvancedGodotExportError("only reviewed original circuit sessions have a native adapter")
    config=make_editor_document("racing",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("racing",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("racing",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    result=session["state"]
    game={"schema":SCHEMA,"editor":"racing","quality_floor":"advanced",
          "settings":config["settings"],"settings_digest":config["digest"],
          "scene":scene,"native_parity_verified":False,
          "external_assets_executed":False}
    proof={"schema":PROOF_SCHEMA,"scene_digest":scene["digest"],
           "settings_digest":config["digest"],
           "actions":list(session["actions"]),
           "expected":{key:result[key] for key in PROOF_FIELDS},
           "python_session_digest":session["digest"],
           "verified_by_python_replay":True}
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                    "Skeleton Original Advanced Circuit Racing").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_RACING.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Godot 4 Circuit Racing\n\n"
            "Independently executing offline native race with authored track,\n"
            "weather, finite pits/fuel, boost, tire/engine wear and real lap result.\n"
            "W/S accelerate/brake, A/D steer, Space coast, B boost, P pit, R reset.\n"
            "Godot headless replay: --headless --path godot -- --verify-racing\n"
            "Native GDScript recomputes all gameplay from approved source actions,\n"
            "then compares all final state fields to the Python-reviewed proof.\n"
            "Neither source creation nor ZIP download proves hardware certification\n"
            "or grants publication, trademark or copyrighted third-party asset use.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"racing",
        "native_adapter":"godot4_independent_circuit_racing",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{p:sha256(raw).hexdigest() for p,raw in sorted(files.items())},
        "godot_executed":False,
        "native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_RACING",
         "render_racing_godot_package"]
