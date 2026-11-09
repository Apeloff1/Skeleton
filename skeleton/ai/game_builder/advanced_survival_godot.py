"""Independent original open-ended Godot 4 Survival & Crafting game.

The offline native executable owns region travel, finite stocks, hunger,
crafting, trade, weather, settlement milestones and permadeath rules.
Python receipts are exclusively proof expectations, never frame playback.
"""
from __future__ import annotations
from hashlib import sha256
from .advanced_godot_export import NativeAdvancedGamePackage, AdvancedGodotExportError, _json
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_survival.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_survival_proof.v1"
PROOF_FIELDS=("tick","day","region","regions","health","max_health","food",
              "water","wood","stone","raw_meat","tools","fire_ticks",
              "shelter_level","energy","trade_tokens","milestones","weather",
              "events","finished","failed")

GODOT_SURVIVAL=r'''
extends Control
## Native original open-world survival. Outpost milestones never end gameplay.
const VERIFY_FLAG: String = "--verify-survival"
const MAX_ACTIONS: int = 128
const ACTIONS: Array = [
    "forage","gather_wood","mine_stone","drink","hunt","cook",
    "craft_tool","light_fire","build_shelter","trade","travel","rest"
]
const BIOMES: Array = ["forest","plains","wetland","highland"]
const WEATHER: Array = ["clear","rain","cold","heat"]
const FINITE_STOCKS: Array = [
    "food_stock","wood_stock","water_stock","stone_stock","game_stock",
    "merchant_food_stock","merchant_water_stock"
]
var source: Dictionary = {}
var settings: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var commands: Array = []
var ready_to_play: bool = false
var notice: String = "Original endless survival · Gather, craft, settle"


func _fail(message: String) -> void:
    push_error("NATIVE_ADVANCED_SURVIVAL_ERROR: "+message)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _normalize_region(raw: Dictionary) -> Dictionary:
    var result: Dictionary = {
        "id":int(raw["id"]),"biome":str(raw["biome"]),
    }
    for key in FINITE_STOCKS:
        result[key]=int(raw[key])
    return result


func _normalize_regions(raw: Array) -> Array:
    var result: Array=[]
    for region in raw:
        result.append(_normalize_region(region))
    return result


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length()>250000:
        _fail("missing or oversized original survival world source")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid original world JSON")
        return
    source=decoded
    if source.get("schema")!="skeleton.game_builder.godot_advanced_survival.v1":
        _fail("native survival contract mismatch")
        return
    settings=source["settings"]
    layout=source["scene"]["layout"]
    if (layout["regions"].size()<2 or layout["regions"].size()>8
        or int(layout["starting_region"])<0
        or int(layout["starting_region"])>=layout["regions"].size()
        or str(layout["weather"]) not in WEATHER):
        _fail("authored survival region constraints violated")
        return
    ready_to_play=true
    _reset()
    get_window().title="Skeleton Original Advanced Survival & Crafting"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var max_hp: int=int(settings["max_health"])
    state={
        "tick":0,"day":1,"region":int(layout["starting_region"]),
        "regions":_normalize_regions(layout["regions"]),
        "health":max_hp,"max_health":max_hp,
        "food":int(settings["starting_food"]),
        "water":int(settings["starting_water"]),
        "wood":int(settings["initial_wood"]),
        "stone":0,"raw_meat":0,"tools":0,
        "fire_ticks":0,"shelter_level":0,"energy":10,
        "trade_tokens":2,"milestones":[],
        "weather":str(layout["weather"]),
        "events":[],"finished":false,"failed":false,
    }
    commands=[]
    notice="Explore, gather, craft and survive; an outpost is not the end"
    queue_redraw()


func _step(action: String) -> bool:
    if (not ready_to_play or bool(state["finished"]) or bool(state["failed"])
        or commands.size()>=MAX_ACTIONS or action not in ACTIONS):
        return false
    var local: Dictionary=state["regions"][int(state["region"])]
    var gathering: Dictionary={
        "forage":"food_stock",
        "gather_wood":"wood_stock",
        "mine_stone":"stone_stock",
        "hunt":"game_stock",
        "drink":"water_stock",
    }
    # Check every finite-resource prerequisite BEFORE time, hunger, exposure,
    # and all other world state advance.
    match action:
        "travel":
            if int(state["energy"])<3:
                return false
        "forage","gather_wood","mine_stone","hunt","drink":
            if int(local[gathering[action]])<=0 or int(state["energy"])<=0:
                return false
        "craft_tool":
            if int(state["wood"])<2 or int(state["stone"])<2:
                return false
        "light_fire":
            if int(state["wood"])<2:
                return false
        "cook":
            if int(state["fire_ticks"])<=0 or int(state["raw_meat"])<=0:
                return false
        "build_shelter":
            if (int(state["wood"])<3+int(state["shelter_level"])
                or int(state["stone"])<2 or int(state["shelter_level"])>=3):
                return false
        "trade":
            if (int(state["trade_tokens"])<=0
                or int(local["merchant_food_stock"])<2
                or int(local["merchant_water_stock"])<2):
                return false

    var events: Array=[]
    state["tick"]=int(state["tick"])+1
    match action:
        "travel":
            state["energy"]=int(state["energy"])-3
            state["region"]=(int(state["region"])+1)%state["regions"].size()
            events.append("region_discovered")
        "forage","gather_wood","mine_stone","hunt","drink":
            var stock: String=str(gathering[action])
            var amount: int=mini(int(local[stock]),2+
                              (1 if int(state["tools"])>0 else 0))
            local[stock]=int(local[stock])-amount
            match action:
                "forage":
                    state["food"]=int(state["food"])+amount
                "gather_wood":
                    state["wood"]=int(state["wood"])+amount
                "mine_stone":
                    state["stone"]=int(state["stone"])+amount
                "hunt":
                    state["raw_meat"]=int(state["raw_meat"])+amount
                "drink":
                    state["water"]=int(state["water"])+amount
            state["energy"]=int(state["energy"])-1
            events.append("finite_resource_harvested")
        "craft_tool":
            state["wood"]=int(state["wood"])-2
            state["stone"]=int(state["stone"])-2
            state["tools"]=int(state["tools"])+1
            events.append("tool_crafted")
        "light_fire":
            state["wood"]=int(state["wood"])-2
            state["fire_ticks"]=4
            events.append("fire_lit")
        "cook":
            state["raw_meat"]=int(state["raw_meat"])-1
            state["food"]=int(state["food"])+3
            events.append("meal_cooked")
        "build_shelter":
            var needed: int=3+int(state["shelter_level"])
            state["wood"]=int(state["wood"])-needed
            state["stone"]=int(state["stone"])-2
            state["shelter_level"]=int(state["shelter_level"])+1
            events.append("shelter_built")
            if "permanent_camp" not in state["milestones"]:
                state["milestones"].append("permanent_camp")
        "trade":
            state["trade_tokens"]=int(state["trade_tokens"])-1
            local["merchant_food_stock"]=int(local["merchant_food_stock"])-2
            local["merchant_water_stock"]=int(local["merchant_water_stock"])-2
            state["food"]=int(state["food"])+2
            state["water"]=int(state["water"])+2
            events.append("finite_market_trade")
        "rest":
            state["energy"]=mini(10,int(state["energy"])+5+
                                int(state["shelter_level"]))
            state["health"]=mini(int(settings["max_health"]),
                int(state["health"])+(2 if int(state["shelter_level"])>0 else 1))
            events.append("rested")

    if int(state["fire_ticks"])>0:
        state["fire_ticks"]=int(state["fire_ticks"])-1
    if int(state["tick"])%2==0:
        if int(state["food"])>0:
            state["food"]=int(state["food"])-1
        if int(state["water"])>0:
            state["water"]=int(state["water"])-1
        if int(state["food"])==0 or int(state["water"])==0:
            state["health"]=maxi(0,int(state["health"])-int(settings["hunger_rate"]))
            events.append("dehydration_or_hunger")
    if int(state["tick"])%6==0:
        state["day"]=int(state["day"])+1
        var weather_id: int=(int(state["day"])+int(state["region"]))%4
        state["weather"]=WEATHER[weather_id]
        if (str(state["weather"]) in ["cold","heat"]
            and int(state["shelter_level"])==0):
            state["health"]=maxi(0,int(state["health"])-1)
            events.append("weather_exposure")
    if int(state["shelter_level"])>=2 and int(state["tools"])>=1:
        if "self_sufficient_outpost" not in state["milestones"]:
            state["milestones"].append("self_sufficient_outpost")
            events.append("original_world_milestone")
    if int(state["health"])==0:
        state["failed"]=true
        events.append("survivor_lost")
    # Deliberately DO NOT set finished=true. The game world is open ended.
    state["events"]=events
    commands.append(action)
    notice=("Survivor lost" if bool(state["failed"])
            else "Day %d · %s" % [int(state["day"]),action])
    queue_redraw()
    return true


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>200000:
        _fail("missing or oversized survival proof")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid survival proof JSON")
        return
    var proof: Dictionary=decoded
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_survival_proof.v1"
        or proof.get("scene_digest")!=source["scene"]["digest"]
        or proof.get("settings_digest")!=source.get("settings_digest")):
        _fail("original world or settings proof mismatch")
        return
    var actions: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if (typeof(actions)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY
        or actions.size()>MAX_ACTIONS):
        _fail("invalid or oversized action transcript")
        return
    for action in actions:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _fail("rejected survival action "+str(action))
            return
    if state.size()!=expected.size() or commands.size()!=actions.size():
        _fail("survival state or history contract mismatch")
        return
    for field in state:
        if not expected.has(field):
            _fail("expected survival state missing "+field)
            return
        var wanted: Variant=expected[field]
        if field=="regions":
            wanted=_normalize_regions(wanted)
        if state[field]!=wanted:
            _fail("survival divergence "+field+" native="+str(state[field])
                   +" python="+str(wanted))
            return
    print("NATIVE_ADVANCED_SURVIVAL_OK "+str(source["scene"]["digest"])+
          " actions="+str(commands.size())+
          " day="+str(state["day"])+
          " result="+("lost" if bool(state["failed"]) else "open_world"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String=""
    match event.keycode:
        KEY_F:action="forage"
        KEY_W:action="gather_wood"
        KEY_M:action="mine_stone"
        KEY_D:action="drink"
        KEY_H:action="hunt"
        KEY_C:action="cook"
        KEY_T:action="craft_tool"
        KEY_L:action="light_fire"
        KEY_B:action="build_shelter"
        KEY_E:action="trade"
        KEY_TAB:action="travel"
        KEY_R:action="rest"
        KEY_BACKSPACE:_reset()
    if action!="":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String=""
        match event.button_index:
            JOY_BUTTON_A:action="forage"
            JOY_BUTTON_B:action="drink"
            JOY_BUTTON_X:action="gather_wood"
            JOY_BUTTON_Y:action="mine_stone"
            JOY_BUTTON_DPAD_UP:action="hunt"
            JOY_BUTTON_DPAD_DOWN:action="rest"
            JOY_BUTTON_DPAD_LEFT:action="travel"
            JOY_BUTTON_DPAD_RIGHT:action="trade"
            JOY_BUTTON_LEFT_SHOULDER:action="craft_tool"
            JOY_BUTTON_RIGHT_SHOULDER:action="build_shelter"
            JOY_BUTTON_START:_reset()
        if action!="":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code==NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#102025"))
    if not ready_to_play:
        return
    var region: Dictionary=state["regions"][int(state["region"])]
    _text(Vector2(18,32),"Original Open-World Survival & Crafting",21,Color.WHITE)
    _text(Vector2(18,58),"Day %d  ·  Region %d/%d  ·  Biome %s  ·  Weather %s" %
        [int(state["day"]),int(state["region"])+1,state["regions"].size(),
         str(region["biome"]),str(state["weather"])],15,Color("#a8e9c8"))
    _text(Vector2(18,82),"Health %d/%d   Energy %d   Fire %d   Shelter %d" %
        [int(state["health"]),int(state["max_health"]),int(state["energy"]),
         int(state["fire_ticks"]),int(state["shelter_level"])],
         15,Color("#f1dcb7"))
    _text(Vector2(18,106),"Food %d   Water %d   Wood %d   Stone %d   Meat %d   Tools %d" %
        [int(state["food"]),int(state["water"]),int(state["wood"]),
         int(state["stone"]),int(state["raw_meat"]),int(state["tools"])],
         14,Color("#c4dfca"))
    _text(Vector2(18,132),"Original region: remaining finite resources",15,Color.WHITE)
    var lines: Array=[
        "Food","Wood","Water","Stone","Game","Merchant food","Merchant water"
    ]
    for i in range(FINITE_STOCKS.size()):
        var y: float=165.0+float(i)*23.0
        var amount: int=int(region[FINITE_STOCKS[i]])
        _text(Vector2(22,y),str(lines[i])+": "+str(amount),13,
              Color("#b4e1b6") if amount>0 else Color("#d78a85"))
        draw_rect(Rect2(Vector2(180,y-13),Vector2(minf(300.0,float(amount)*6),10)),
                  Color("#6cbb93"),true)
    var milestone_text: String=", ".join(state["milestones"])
    _text(Vector2(18,347),"Milestones: "+(milestone_text if not milestone_text.is_empty() else "none"),
          13,Color("#e9ca91"))
    _text(Vector2(18,374),notice,13,Color("#d7e4cf"))
    _text(Vector2(18,405),"F forage · W wood · M stone · D water · H hunt · C cook",12,Color.WHITE)
    _text(Vector2(18,423),"T tool · L fire · B shelter · E trade · Tab travel · R rest",12,Color.WHITE)
    _text(Vector2(18,442),"Infinite play is NOT promised: all regional resources are finite.",12,
          Color("#e2b89b"))


func _text(position: Vector2,message: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,position,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_survival_godot_package(session: dict, settings: dict | None = None,
                                  *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("offline survival native export needs operator authorization")
    if type(session) is not dict or session.get("editor")!="survival":
        raise AdvancedGodotExportError("only reviewed original survival sessions use this native adapter")
    config=make_editor_document("survival",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("survival",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("survival",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    state=session["state"]
    game={
        "schema":SCHEMA,"editor":"survival","quality_floor":"advanced",
        "settings":config["settings"],"settings_digest":config["digest"],
        "scene":scene,"native_parity_verified":False,
        "external_assets_executed":False,
    }
    proof={
        "schema":PROOF_SCHEMA,"scene_digest":scene["digest"],
        "settings_digest":config["digest"],
        "actions":list(session["actions"]),
        "expected":{field:state[field] for field in PROOF_FIELDS},
        "python_session_digest":session["digest"],
        "verified_by_python_replay":True,
    }
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                       "Skeleton Original Advanced Survival").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_SURVIVAL.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Godot 4 Open-World Survival\n\n"
            "Independent offline Godot 4.4.1+ native game with authored biomes,\n"
            "finite resources, travel, hunger, weather, crafting, hunting, cooking,\n"
            "merchant trading, camp construction and open-ended milestones.\n"
            "F forage, W wood, M stone, D water, H hunt, C cook, T tool,\n"
            "L fire, B shelter, E trade, Tab travel, R rest, Backspace reset.\n"
            "A settlement milestone never automatically ends the original world.\n"
            "Verify: godot --headless --path godot -- --verify-survival\n"
            "GDScript independently reruns approved commands and checks every\n"
            "gameplay field against the Python-reviewed source proof.\n"
            "No console hardware, publishing, asset/IP rights certification.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"survival",
        "native_adapter":"godot4_independent_open_world_survival",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{p:sha256(body).hexdigest() for p,body in sorted(files.items())},
        "godot_executed":False,"native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_SURVIVAL",
         "render_survival_godot_package"]
