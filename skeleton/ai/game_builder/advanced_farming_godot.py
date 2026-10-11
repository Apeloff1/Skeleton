"""Ninth original native Godot 4 game: authored crop farming and market economy.

A real GDScript simulation separately executes farming progression and checks
the entire 23-field state after replay against an immutable Python receipt.
"""
from __future__ import annotations
from hashlib import sha256
from .advanced_godot_export import NativeAdvancedGamePackage,AdvancedGodotExportError,_json
from .advanced_gameplay_runtime import run_advanced_session,verify_advanced_session
from .advanced_level_scenes import make_advanced_scene,validate_advanced_scene
from .dual_runtime_export import _PROJECT,_SCENE,_EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_farming.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_farming_proof.v1"
PROOF_FIELDS=("day","season","weather","plots","coins","seeds","water",
              "fertilizer","harvest_stock","harvested","livestock","feed",
              "animal_health","animal_products","reputation","contracts_completed",
              "market_multiplier","seed","events","finished","failed")

GODOT_FARMING=r'''
extends Control
## Original playable crop and livestock economy, not scripted screenshot replay.
const VERIFY_FLAG: String="--verify-farming"
const MAX_ACTIONS: int=128
const WEATHER: Array=["sun","rain","sun","sun","sun","sun","drought"]
const VERBS: Array=["plant","water","harvest","till","compost"]
var source: Dictionary={}
var rules: Dictionary={}
var terrain: Dictionary={}
var state: Dictionary={}
var actions: Array=[]
var playable: bool=false
var notice: String="Grow crops, trade and establish a profitable original farm"


func _fail(message: String) -> void:
    push_error("NATIVE_ADVANCED_FARMING_ERROR: "+message)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var data: String=FileAccess.get_file_as_string("res://game.json")
    if data.is_empty() or data.length()>80000:
        _fail("missing or oversized original farm world")
        return
    var decoded: Variant=JSON.parse_string(data)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid original farm source")
        return
    source=decoded
    if source.get("schema")!="skeleton.game_builder.godot_advanced_farming.v1":
        _fail("unknown original farm native contract")
        return
    rules=source["settings"]
    terrain=source["scene"]["layout"]
    if terrain["plots"].size()<1 or terrain["plots"].size()>4:
        _fail("authored plots exceed the native sector budget")
        return
    playable=true
    _reset()
    get_window().title="Skeleton Original Advanced Farming"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var plots: Array=[]
    for plot in terrain["plots"]:
        plots.append({
            "id":int(plot["id"]),"soil":int(plot["soil"]),
            "moisture":int(plot["moisture"]),"crop":-1,
            "age":0,"pests":0,
        })
    var animals: int=2 if bool(rules["livestock"]) else 0
    state={
        "day":1,"season":0,"weather":str(terrain["starting_weather"]),
        "plots":plots,"coins":25,"seeds":8,"water":12,
        "fertilizer":2,"harvest_stock":0,"harvested":0,
        "livestock":animals,"feed":6 if animals>0 else 0,
        "animal_health":10 if animals>0 else 0,
        "animal_products":0,"reputation":0,"contracts_completed":0,
        "market_multiplier":int(terrain["market_multiplier"]),
        "seed":int(source["scene"]["seed"]),
        "events":[],"finished":false,"failed":false,
    }
    actions=[]
    notice="Plant · grow · harvest · sell · protect your fields"
    queue_redraw()


func _advance_day() -> Array:
    state["day"]=int(state["day"])+1
    var day: int=int(state["day"])
    var events: Array=["new_farm_day"]
    if bool(rules["seasons"]):
        state["season"]=int(int((day-1)/7)%4)
    var phase: int=(day+int(state["seed"]))%7
    state["weather"]=("rain" if phase in [1,4] else
                      "drought" if phase==6 else "sun")
    for p in state["plots"]:
        if state["weather"]=="rain":
            p["moisture"]=mini(5,int(p["moisture"])+2)
        else:
            p["moisture"]=maxi(0,int(p["moisture"])-
                (2 if state["weather"]=="drought" else 1))
        if int(p["crop"])>=0:
            if int(p["moisture"])>0 and int(p["soil"])>0:
                p["age"]=int(p["age"])+1
                events.append("crop_grew")
            if day%11==0:
                p["pests"]=mini(3,int(p["pests"])+1)
                events.append("seasonal_pests")
    if int(state["livestock"])>0:
        if int(state["feed"])>0:
            state["feed"]=int(state["feed"])-1
            if day%3==0 and int(state["animal_health"])>0:
                state["animal_products"]=int(state["animal_products"])+int(state["livestock"])
                events.append("livestock_produced")
        else:
            state["animal_health"]=maxi(0,int(state["animal_health"])-2)
            events.append("livestock_hungry")
    if day%7==0:
        state["coins"]=maxi(0,int(state["coins"])-2)
        events.append("market_upkeep")
    var crops: bool=false
    for plot in state["plots"]:
        if int(plot["crop"])>=0:
            crops=true
    if (day>=40 and int(state["coins"])<3 and int(state["seeds"])==0
        and int(state["harvest_stock"])==0 and not crops):
        state["failed"]=true
        events.append("farm_bankrupt")
    return events


func _step(command: String) -> bool:
    if (not playable or bool(state["finished"]) or bool(state["failed"])
        or actions.size()>=MAX_ACTIONS):
        return false
    var events: Array=[]
    if ":" in command and command.split(":")[0] in VERBS:
        var parts: PackedStringArray=command.split(":")
        if parts.size()!=2 or not parts[1].is_valid_int():
            return false
        var idx: int=int(parts[1])
        if idx<0 or idx>3 or idx>=state["plots"].size():
            return false
        var verb: String=parts[0]
        var p: Dictionary=state["plots"][idx]
        match verb:
            "plant":
                if int(p["crop"])>=0 or int(state["seeds"])<1:
                    return false
                p["crop"]=idx%mini(int(rules["crop_types"]),3)
                p["age"]=0
                p["pests"]=0
                state["seeds"]=int(state["seeds"])-1
                events.append("crop_planted")
            "water":
                if int(state["water"])<2 or int(p["moisture"])>=5:
                    return false
                state["water"]=int(state["water"])-2
                p["moisture"]=mini(5,int(p["moisture"])+2)
                events.append("plot_watered")
            "harvest":
                var target: int=(maxi(1,int(int(rules["growth_days"])/(int(p["crop"])+2)))
                                 if int(p["crop"])>=0 else 0)
                if int(p["crop"])<0 or int(p["age"])<target:
                    return false
                var amount: int=maxi(1,2+int(p["crop"])+
                    (1 if int(p["soil"])>=3 else 0)-int(p["pests"]))
                state["harvest_stock"]=int(state["harvest_stock"])+amount
                state["harvested"]=int(state["harvested"])+amount
                p["crop"]=-1
                p["age"]=0
                p["pests"]=0
                p["soil"]=maxi(0,int(p["soil"])-1)
                events.append("mature_crop_harvested")
            "till":
                if int(p["crop"])>=0 or int(state["coins"])<1 or int(p["soil"])>=5:
                    return false
                state["coins"]=int(state["coins"])-1
                p["soil"]=int(p["soil"])+1
                events.append("soil_cultivated")
            "compost":
                if int(state["fertilizer"])<1 or int(p["soil"])>=5:
                    return false
                state["fertilizer"]=int(state["fertilizer"])-1
                p["soil"]=mini(5,int(p["soil"])+2)
                p["pests"]=maxi(0,int(p["pests"])-1)
                events.append("soil_composted")
    elif command in ["advance","advance:4"]:
        for i in range(4 if command=="advance:4" else 1):
            if bool(state["finished"]) or bool(state["failed"]):
                break
            events.append_array(_advance_day())
    elif command=="irrigate":
        var active: Array=[]
        for p in state["plots"]:
            if int(p["crop"])>=0 and int(p["moisture"])<5:
                active.append(p)
        if active.is_empty() or int(state["water"])<active.size():
            return false
        for p in active:
            p["moisture"]=mini(5,int(p["moisture"])+1)
        state["water"]=int(state["water"])-active.size()
        events.append("field_irrigated")
    elif command=="buy_seeds":
        if int(state["coins"])<5:
            return false
        state["coins"]=int(state["coins"])-5
        state["seeds"]=int(state["seeds"])+4
        events.append("seeds_purchased")
    elif command=="sell":
        if int(state["harvest_stock"])<1:
            return false
        var batch: int=int(state["harvest_stock"])
        var price: int=3+int(state["market_multiplier"])+
            (1 if int(state["season"])==2 else 0)
        state["coins"]=int(state["coins"])+batch*price
        state["harvest_stock"]=0
        state["reputation"]=int(state["reputation"])+1
        if batch>=3:
            state["contracts_completed"]=int(state["contracts_completed"])+1
            events.append("market_contract_fulfilled")
        events.append("genuine_harvest_sold")
    elif command=="feed":
        if int(state["livestock"])<1 or int(state["harvest_stock"])<2:
            return false
        state["harvest_stock"]=int(state["harvest_stock"])-2
        state["feed"]=int(state["feed"])+4
        state["animal_health"]=mini(10,int(state["animal_health"])+1)
        events.append("livestock_fed")
    elif command=="collect":
        if int(state["animal_products"])<1:
            return false
        state["harvest_stock"]=int(state["harvest_stock"])+int(state["animal_products"])
        state["animal_products"]=0
        events.append("animal_products_collected")
    else:
        return false
    if (int(state["coins"])>=80 and int(state["harvested"])>=8
        and int(state["contracts_completed"])>=2):
        state["finished"]=true
        events.append("profitable_farm_established")
    state["events"]=events
    actions.append(command)
    notice=("Farm established" if bool(state["finished"])
        else "Farm bankrupt" if bool(state["failed"])
        else "Day %d · %s" % [int(state["day"]),command])
    queue_redraw()
    return true


func _proof_plots(raw: Array) -> Array:
    var out: Array=[]
    for item in raw:
        var p: Dictionary={}
        for key in ["id","soil","moisture","crop","age","pests"]:
            p[key]=int(item[key])
        out.append(p)
    return out


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>180000:
        _fail("missing or oversized farming proof")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid source-bound farming proof")
        return
    var proof: Dictionary=decoded
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_farming_proof.v1"
        or proof.get("scene_digest")!=source["scene"]["digest"]
        or proof.get("settings_digest")!=source.get("settings_digest")):
        _fail("original farm settings/proof mismatch")
        return
    var history: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if (typeof(history)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY
        or history.size()>MAX_ACTIONS):
        _fail("invalid bounded farm action transcript")
        return
    for action in history:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _fail("farming command rejected: "+str(action))
            return
    if actions.size()!=history.size() or state.size()!=expected.size():
        _fail("native farming state shape differs from verified source")
        return
    for field in state:
        if not expected.has(field):
            _fail("farming source proof missing "+field)
            return
        var wanted: Variant=(_proof_plots(expected[field]) if field=="plots"
                             else expected[field])
        if state[field]!=wanted:
            _fail("farming gameplay divergence "+field+" native="+str(state[field])
                  +" expected="+str(wanted))
            return
    print("NATIVE_ADVANCED_FARMING_OK "+str(source["scene"]["digest"])+
          " actions="+str(actions.size())+" day="+str(state["day"])
          +" result="+("won" if bool(state["finished"]) else
                      "lost" if bool(state["failed"]) else "farming"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not playable or not event is InputEventKey or not event.pressed or event.echo:
        return
    var command: String=""
    match event.keycode:
        KEY_1:command="plant:0"
        KEY_2:command="plant:1"
        KEY_3:command="plant:2"
        KEY_4:command="plant:3"
        KEY_Q:command="harvest:0"
        KEY_W:command="harvest:1"
        KEY_E:command="harvest:2"
        KEY_F:command="harvest:3"
        KEY_SPACE:command="advance"
        KEY_ENTER:command="advance:4"
        KEY_I:command="irrigate"
        KEY_B:command="buy_seeds"
        KEY_S:command="sell"
        KEY_L:command="feed"
        KEY_C:command="collect"
        KEY_R:_reset()
    if command!="":
        _step(command)
    get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code==NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#13251e"))
    if not playable:
        return
    _text(Vector2(16,31),"Original Advanced Farming · Godot 4",22,Color.WHITE)
    _text(Vector2(16,58),"Day %d · Season %d · Weather %s · Coins %d" %
        [int(state["day"]),int(state["season"]),str(state["weather"]),
         int(state["coins"])],16,Color("#b1ebc7"))
    _text(Vector2(16,82),"Seeds %d · Water %d · Fertilizer %d · Harvest %d" %
        [int(state["seeds"]),int(state["water"]),int(state["fertilizer"]),
         int(state["harvest_stock"])],14,Color("#eddbac"))
    _text(Vector2(16,107),"Livestock %d · Feed %d · Animal health %d · Products %d" %
        [int(state["livestock"]),int(state["feed"]),int(state["animal_health"]),
         int(state["animal_products"])],13,Color.WHITE)
    for i in range(state["plots"].size()):
        var plot: Dictionary=state["plots"][i]
        var x: float=18.0+float(i)*166.0
        var color: Color=Color("#56733a") if int(plot["crop"])<0 else Color("#a8bb4f")
        draw_rect(Rect2(Vector2(x,145),Vector2(151,125)),color,true)
        _text(Vector2(x+9,168),"Field "+str(i+1),16,Color("#10291e"))
        _text(Vector2(x+9,194),"Crop "+str(plot["crop"])+" · Age "+str(plot["age"]),
              12,Color("#10291e"))
        _text(Vector2(x+9,215),"Soil "+str(plot["soil"])+
              " · Water "+str(plot["moisture"]),12,Color("#10291e"))
        _text(Vector2(x+9,238),"Pests "+str(plot["pests"]),12,Color("#10291e"))
    _text(Vector2(16,305),notice,14,Color("#f2ddb7"))
    _text(Vector2(16,330),"Plant 1–4 · Harvest Q/W/E/F · Space day · Enter four days",
          13,Color.WHITE)
    _text(Vector2(16,353),"I irrigate · B seeds · S sell · L feed · C collect · R restart",
          13,Color.WHITE)
    _text(Vector2(16,378),"Harvest 8+, fulfill 2 contracts and earn 80 coins to win.",
          12,Color("#a8d8b6"))


func _text(at: Vector2,label: String,font_size: int,color: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,label,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,color)
'''


def render_farming_godot_package(session: dict,settings: dict | None = None,
                                 *,authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("original farming native export needs trusted local authorization")
    if type(session) is not dict or session.get("editor")!="farming":
        raise AdvancedGodotExportError("reviewed original farm session required for native export")
    config=make_editor_document("farming",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("farming",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("farming",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    game={"schema":SCHEMA,"editor":"farming","quality_floor":"advanced",
          "settings":config["settings"],"settings_digest":config["digest"],
          "scene":scene,"native_parity_verified":False,
          "external_assets_executed":False}
    proof={"schema":PROOF_SCHEMA,"scene_digest":scene["digest"],
           "settings_digest":config["digest"],"actions":list(session["actions"]),
           "expected":{k:session["state"][k] for k in PROOF_FIELDS},
           "python_session_digest":session["digest"],
           "verified_by_python_replay":True}
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                     "Skeleton Original Advanced Farming").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_FARMING.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Godot 4 Farming Game\n\n"
            "Real offline crop/livestock farming with finite plot resources,\n"
            "rain/drought, pests, harvest, market contracts, animal feed.\n"
            "1–4 plant · Q/W/E/F harvest · Space day · Enter four days;\n"
            "I irrigate · B buy seeds · S sell · L feed · C collect.\n"
            "Native playback: godot --headless --path godot -- --verify-farming\n"
            "The independent GDScript world is checked against exact source.\n"
            "No console/retail/IP certification or automatic publication.\n"
        ).encode("utf-8"),
    }
    manifest={"schema":"skeleton.game_builder.advanced_native_package.v1",
              "native_editor":"farming","native_adapter":"godot4_independent_farming",
              "advanced_floor":True,
              "source_session_digest":session["digest"],
              "authored_scene_digest":scene["digest"],
              "files":{p:sha256(body).hexdigest() for p,body in sorted(files.items())},
              "godot_executed":False,"native_hardware_certified":False,
              "publish_approved":False}
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_FARMING",
         "render_farming_godot_package"]
