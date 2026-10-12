"""Tenth genuinely executable offline native game: powered factory automation.

Godot's integer simulation is authored independently of the reference Python
rules. Replay proof checks every state field, including nested machines.
"""
from __future__ import annotations
from hashlib import sha256
from .advanced_godot_export import NativeAdvancedGamePackage,AdvancedGodotExportError,_json
from .advanced_gameplay_runtime import run_advanced_session,verify_advanced_session
from .advanced_level_scenes import make_advanced_scene,validate_advanced_scene
from .dual_runtime_export import _PROJECT,_SCENE,_EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_factory.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_factory_proof.v1"
PROOF_FIELDS=("tick","day","ore","coal","plates","components","boxes","shipped",
              "credits","power","power_cap","pollution","ore_deposit",
              "coal_deposit","market_price","contract_target","contracts",
              "mode","stations","machines","blocked_cycles","maintenance",
              "events","seed","finished","failed")

GODOT_FACTORY=r'''
extends Control
## All operations execute in this GDScript engine, no Python or external I/O.
const VERIFY_FLAG: String="--verify-factory"
const MAX_ACTIONS: int=128
const MACHINE_ACTIONS: Array=["build","upgrade","toggle","repair","sell"]
const ROLES: Array=["smelter","assembler","packer","generator"]
var source: Dictionary={}
var config: Dictionary={}
var layout: Dictionary={}
var state: Dictionary={}
var commands: Array=[]
var playable: bool=false
var notice: String="Build an original automation chain and ship real goods"


func _fail(reason: String) -> void:
    push_error("NATIVE_ADVANCED_FACTORY_ERROR: "+reason)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _normalize_stations(raw: Array) -> Array:
    var result: Array=[]
    for station in raw:
        result.append({"id":int(station["id"]),"role":str(station["role"])})
    return result


func _normalize_machines(raw: Array) -> Array:
    var result: Array=[]
    for machine in raw:
        result.append({"id":int(machine["id"]),"role":str(machine["role"]),
            "level":int(machine["level"]),"health":int(machine["health"]),
            "enabled":bool(machine["enabled"])})
    return result


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String=FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length()>80000:
        _fail("missing or oversized factory game source")
        return
    var parsed: Variant=JSON.parse_string(raw)
    if typeof(parsed)!=TYPE_DICTIONARY:
        _fail("invalid factory JSON")
        return
    source=parsed
    if source.get("schema")!="skeleton.game_builder.godot_advanced_factory.v1":
        _fail("unrecognized factory native source contract")
        return
    config=source["settings"]
    layout=source["scene"]["layout"]
    if (layout["stations"].is_empty() or layout["stations"].size()>4
        or int(layout["contract_target"])<2 or int(layout["contract_target"])>80):
        _fail("authored machine topology outside bounded game contract")
        return
    playable=true
    _reset()
    get_window().title="Skeleton Original Advanced Factory Automation"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    state={
        "tick":0,"day":1,"ore":10,"coal":6,"plates":0,"components":0,
        "boxes":0,"shipped":0,"credits":90,"power":int(config["power_supply"]),
        "power_cap":int(config["power_supply"]),"pollution":0,
        "ore_deposit":int(layout["ore_deposit"]),
        "coal_deposit":int(layout["coal_deposit"]),
        "market_price":int(layout["market_price"]),
        "contract_target":int(layout["contract_target"]),"contracts":0,
        "mode":"efficiency","stations":_normalize_stations(layout["stations"]),
        "machines":[],"blocked_cycles":0,"maintenance":0,
        "events":[],"seed":int(source["scene"]["seed"]),
        "finished":false,"failed":false,
    }
    commands=[]
    notice="Build smelter/assembler/packer · power production · ship contracts"
    queue_redraw()


func _machine(index: int) -> Dictionary:
    for m in state["machines"]:
        if int(m["id"])==index:
            return m
    return {}


func _tick() -> Array:
    state["tick"]=int(state["tick"])+1
    if int(state["tick"])%5==0:
        state["day"]=int(state["day"])+1
    var ev: Array=["factory_tick"]
    for station in state["stations"]:
        var m: Dictionary=_machine(int(station["id"]))
        if m.is_empty() or not bool(m["enabled"]) or int(m["health"])<=0:
            continue
        var role: String=str(m["role"])
        var cycle: int=mini(int(config["belt_speed"]),
            int(m["level"])+(1 if state["mode"]=="speed" else 0))
        if role=="generator":
            if int(state["coal"])>=1 and int(state["power"])<int(state["power_cap"]):
                state["coal"]=int(state["coal"])-1
                state["power"]=mini(int(state["power_cap"]),
                    int(state["power"])+cycle*6)
                ev.append("local_grid_generated")
            else:
                state["blocked_cycles"]=int(state["blocked_cycles"])+1
                ev.append("machine_stalled")
            continue
        var input_field: String=("ore" if role=="smelter" else
            "plates" if role=="assembler" else "components")
        var cost: int=2 if role in ["smelter","assembler"] else 1
        var unit_power: int=2 if role=="assembler" else 1
        var produced: int=mini(cycle,
            mini(int(int(state[input_field])/cost),
                int(int(state["power"])/unit_power)))
        if produced<=0:
            state["blocked_cycles"]=int(state["blocked_cycles"])+1
            ev.append("machine_stalled")
            continue
        state[input_field]=int(state[input_field])-produced*cost
        var output_field: String=("plates" if role=="smelter" else
            "components" if role=="assembler" else "boxes")
        state[output_field]=int(state[output_field])+produced
        state["power"]=int(state["power"])-produced*unit_power
        if bool(config["pollution"]):
            state["pollution"]=int(state["pollution"])+produced*(
                2 if state["mode"]=="speed" else 1)
        if int(state["tick"])%4==0:
            m["health"]=maxi(0,int(m["health"])-1)
            ev.append("wear_accumulated")
        ev.append("machine_produced")
    if bool(config["pollution"]) and int(state["pollution"])>=70:
        state["failed"]=true
        ev.append("pollution_shutdown")
    if (int(state["tick"])>=50 and int(state["credits"])<5
        and int(state["ore"])==0 and int(state["ore_deposit"])==0
        and int(state["boxes"])==0):
        state["failed"]=true
        ev.append("factory_bankrupt")
    return ev


func _step(action: String) -> bool:
    if (not playable or bool(state["finished"]) or bool(state["failed"])
        or commands.size()>=MAX_ACTIONS):
        return false
    var ev: Array=[]
    if ":" in action and action.split(":")[0] in MACHINE_ACTIONS:
        var parts: PackedStringArray=action.split(":")
        if parts.size()!=2 or not parts[1].is_valid_int():
            return false
        var index: int=int(parts[1])
        if index<0 or index>=state["stations"].size():
            return false
        var m: Dictionary=_machine(index)
        match parts[0]:
            "build":
                if not m.is_empty() or int(state["credits"])<15:
                    return false
                state["credits"]=int(state["credits"])-15
                state["machines"].append({
                    "id":index,"role":str(state["stations"][index]["role"]),
                    "level":1,"health":10,"enabled":true,
                })
                state["machines"].sort_custom(func(a,b):return int(a["id"])<int(b["id"]))
                ev.append("machine_constructed")
            "upgrade":
                if m.is_empty() or int(m["level"])>=3 or int(state["credits"])<12*int(m["level"]):
                    return false
                state["credits"]=int(state["credits"])-12*int(m["level"])
                m["level"]=int(m["level"])+1
                ev.append("machine_upgraded")
            "toggle":
                if m.is_empty():
                    return false
                m["enabled"]=not bool(m["enabled"])
                ev.append("machine_switched")
            "repair":
                if m.is_empty() or int(m["health"])>=10 or int(state["credits"])<5:
                    return false
                state["credits"]=int(state["credits"])-5
                m["health"]=mini(10,int(m["health"])+4)
                state["maintenance"]=int(state["maintenance"])+1
                ev.append("machine_repaired")
            "sell":
                if m.is_empty():
                    return false
                state["credits"]=int(state["credits"])+7*int(m["level"])
                state["machines"].erase(m)
                ev.append("machine_liquidated")
    elif action=="mine":
        if int(state["ore_deposit"])<1:
            return false
        var amount: int=mini(int(config["belt_speed"]),int(state["ore_deposit"]))
        state["ore_deposit"]=int(state["ore_deposit"])-amount
        state["ore"]=int(state["ore"])+amount
        ev.append("finite_ore_mined")
    elif action=="generate":
        if int(state["coal"])<1 or int(state["power"])>=int(state["power_cap"]):
            return false
        state["coal"]=int(state["coal"])-1
        state["power"]=mini(int(state["power_cap"]),int(state["power"])+8)
        ev.append("fuel_power_generated")
    elif action=="buy_coal":
        if int(state["credits"])<6 or int(state["coal_deposit"])<2:
            return false
        state["credits"]=int(state["credits"])-6
        state["coal_deposit"]=int(state["coal_deposit"])-2
        state["coal"]=int(state["coal"])+2
        ev.append("finite_coal_bought")
    elif action in ["tick","tick:4"]:
        for i in range(4 if action=="tick:4" else 1):
            if bool(state["finished"]) or bool(state["failed"]):
                break
            ev.append_array(_tick())
    elif action=="ship":
        if int(state["boxes"])<2:
            return false
        var count: int=mini(int(state["boxes"]),8)
        state["boxes"]=int(state["boxes"])-count
        state["shipped"]=int(state["shipped"])+count
        state["credits"]=int(state["credits"])+count*int(state["market_price"])
        state["contracts"]=int(state["contracts"])+1
        ev.append("manufacturing_contract_shipped")
    elif action=="scrub":
        if int(state["pollution"])<=0 or int(state["credits"])<5:
            return false
        state["credits"]=int(state["credits"])-5
        state["pollution"]=maxi(0,int(state["pollution"])-15)
        ev.append("pollution_scrubbed")
    elif action in ["priority:speed","priority:efficiency"]:
        state["mode"]=action.split(":")[1]
        ev.append("production_priority_changed")
    else:
        return false
    if (int(state["shipped"])>=int(state["contract_target"])
        and int(state["contracts"])>=2):
        state["finished"]=true
        ev.append("sustainable_factory_operating")
    state["events"]=ev
    commands.append(action)
    notice=("Factory commissioned!" if bool(state["finished"])
        else "Factory shut down" if bool(state["failed"])
        else "Tick %d · %s" % [int(state["tick"]),action])
    queue_redraw()
    return true


func _verify() -> void:
    var raw: String=FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length()>200000:
        _fail("missing or oversized independent factory transcript")
        return
    var decoded: Variant=JSON.parse_string(raw)
    if typeof(decoded)!=TYPE_DICTIONARY:
        _fail("invalid native factory source proof")
        return
    var proof: Dictionary=decoded
    if (proof.get("schema")!="skeleton.game_builder.godot_advanced_factory_proof.v1"
        or proof.get("scene_digest")!=source["scene"]["digest"]
        or proof.get("settings_digest")!=source.get("settings_digest")):
        _fail("factory world or settings mismatch")
        return
    var actions: Variant=proof.get("actions")
    var expected: Variant=proof.get("expected")
    if (typeof(actions)!=TYPE_ARRAY or typeof(expected)!=TYPE_DICTIONARY
        or actions.size()>MAX_ACTIONS):
        _fail("unbounded or invalid manufacturing proof")
        return
    for action in actions:
        if typeof(action)!=TYPE_STRING or not _step(action):
            _fail("invalid original factory order "+str(action))
            return
    if state.size()!=expected.size() or commands.size()!=actions.size():
        _fail("factory state schema diverged from reference")
        return
    for field in state:
        if not expected.has(field):
            _fail("factory proof missing "+field)
            return
        var wanted: Variant=expected[field]
        if field=="stations":
            wanted=_normalize_stations(wanted)
        elif field=="machines":
            wanted=_normalize_machines(wanted)
        if state[field]!=wanted:
            _fail("factory gameplay divergence "+field+" native="+str(state[field])
                  +" verified="+str(wanted))
            return
    print("NATIVE_ADVANCED_FACTORY_OK "+str(source["scene"]["digest"])+
          " actions="+str(commands.size())+" manufactured="+str(state["shipped"])+
          " result="+("won" if bool(state["finished"]) else
                     "lost" if bool(state["failed"]) else "producing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not playable or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String=""
    match event.keycode:
        KEY_1:action="build:0"
        KEY_2:action="build:1"
        KEY_3:action="build:2"
        KEY_4:action="build:3"
        KEY_Q:action="upgrade:0"
        KEY_W:action="upgrade:1"
        KEY_E:action="upgrade:2"
        KEY_F:action="upgrade:3"
        KEY_M:action="mine"
        KEY_G:action="generate"
        KEY_C:action="buy_coal"
        KEY_SPACE:action="tick"
        KEY_ENTER,KEY_KP_ENTER:action="tick:4"
        KEY_S:action="ship"
        KEY_P:action="scrub"
        KEY_V:action="priority:speed"
        KEY_B:action="priority:efficiency"
        KEY_R:_reset()
    if action!="":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String=""
        match event.button_index:
            JOY_BUTTON_A:action="tick"
            JOY_BUTTON_B:action="ship"
            JOY_BUTTON_X:action="mine"
            JOY_BUTTON_Y:action="generate"
            JOY_BUTTON_DPAD_LEFT:action="build:0"
            JOY_BUTTON_DPAD_UP:action="build:1"
            JOY_BUTTON_DPAD_RIGHT:action="build:2"
            JOY_BUTTON_DPAD_DOWN:action="build:3"
            JOY_BUTTON_LEFT_SHOULDER:action="priority:efficiency"
            JOY_BUTTON_RIGHT_SHOULDER:action="priority:speed"
            JOY_BUTTON_START:_reset()
        if action!="":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code==NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#101e2a"))
    if not playable:
        return
    _text(Vector2(17,31),"Original Advanced Factory Automation",22,Color.WHITE)
    _text(Vector2(17,56),"Tick %d  ·  Power %d/%d  ·  Credits %d  ·  Pollution %d" %
          [int(state["tick"]),int(state["power"]),int(state["power_cap"]),
           int(state["credits"]),int(state["pollution"])],14,Color("#a9dec6"))
    _text(Vector2(17,80),"Ore %d  Plates %d  Parts %d  Boxes %d  Coal %d" %
          [int(state["ore"]),int(state["plates"]),int(state["components"]),
           int(state["boxes"]),int(state["coal"])],14,Color("#e9d19f"))
    _text(Vector2(17,102),"Shipped %d/%d  ·  Contracts %d  ·  Mode %s" %
          [int(state["shipped"]),int(state["contract_target"]),
           int(state["contracts"]),str(state["mode"])],14,Color.WHITE)
    for station in state["stations"]:
        var i: int=int(station["id"])
        var x: float=20.0+float(i)*161.0
        var m: Dictionary=_machine(i)
        var ink: Color=(Color("#4e9ba1") if not m.is_empty() else Color("#64717e"))
        draw_rect(Rect2(Vector2(x,155),Vector2(148,118)),ink,true)
        _text(Vector2(x+7,180),str(station["role"]),14,Color.WHITE)
        _text(Vector2(x+7,206),"Slot "+str(i+1),13,Color("#deeee8"))
        _text(Vector2(x+7,234),("Lv "+str(m["level"])+" HP "+str(m["health"])
              if not m.is_empty() else "Build for 15"),12,Color.WHITE)
    _text(Vector2(17,312),notice,14,Color("#edd9ae"))
    _text(Vector2(17,336),"1–4 build  ·  Q/W/E/F upgrade  ·  M mine  ·  G generate",12,Color.WHITE)
    _text(Vector2(17,356),"Space tick · Enter four · S ship · P scrub · V/B speed/efficiency",12,
          Color("#c5d9e5"))
    _text(Vector2(17,379),"Finite deposits "+str(state["ore_deposit"])+" ore / "+
          str(state["coal_deposit"])+" coal; no resource creation from nothing",12,
          Color("#c4dfc7"))


func _text(at: Vector2,message: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_factory_godot_package(session: dict,settings: dict | None = None,
                                 *,authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("independent factory native export requires trusted operator")
    if type(session) is not dict or session.get("editor")!="factory":
        raise AdvancedGodotExportError("only reviewed original factory sessions use this native adapter")
    config=make_editor_document("factory",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None else
           make_advanced_scene("factory",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("factory",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    game={"schema":SCHEMA,"editor":"factory","quality_floor":"advanced",
          "settings":config["settings"],"settings_digest":config["digest"],
          "scene":scene,"native_parity_verified":False,
          "external_assets_executed":False}
    proof={"schema":PROOF_SCHEMA,"scene_digest":scene["digest"],
           "settings_digest":config["digest"],"actions":list(session["actions"]),
           "expected":{field:session["state"][field] for field in PROOF_FIELDS},
           "python_session_digest":session["digest"],
           "verified_by_python_replay":True}
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                    "Skeleton Original Advanced Factory").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_FACTORY.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Native Factory\n\n"
            "Offline Godot 4.4.1+ with actual production: mining, smelting,\n"
            "assembly, packaging, power, finite deposits, repairs, pollution,\n"
            "shipped market contracts, bankruptcy and genuine completion.\n"
            "1–4 build · Q/W/E/F upgrade · M mine · G power · C coal\n"
            "Space advance · Enter four cycles · S ship · P scrub · V/B mode\n"
            "Independent native gameplay replay: --headless --path godot -- --verify-factory\n"
            "All original gameplay and source-bound commands rerun in GDScript.\n"
            "Original project source is not hardware or publication certification.\n"
        ).encode("utf-8"),
    }
    manifest={"schema":"skeleton.game_builder.advanced_native_package.v1",
              "native_editor":"factory","native_adapter":"godot4_independent_factory",
              "advanced_floor":True,
              "source_session_digest":session["digest"],
              "authored_scene_digest":scene["digest"],
              "files":{name:sha256(raw).hexdigest() for name,raw in sorted(files.items())},
              "godot_executed":False,"native_hardware_certified":False,
              "publish_approved":False}
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_FACTORY",
         "render_factory_godot_package"]
