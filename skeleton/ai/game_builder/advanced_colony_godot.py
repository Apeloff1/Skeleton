"""Independently simulated original Godot 4 colony game and source-bound replay.

The native scene owns its economy, workers, finite geography, raids and crises.
Python states are proof expectations; native rules execute without Python.
"""
from __future__ import annotations
from hashlib import sha256
from .advanced_godot_export import (
    NativeAdvancedGamePackage, AdvancedGodotExportError, _json,
)
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.godot_advanced_colony.v1"
PROOF_SCHEMA = "skeleton.game_builder.godot_advanced_colony_proof.v1"
PROOF_FIELDS = (
    "seed", "tick", "day", "population", "healthy", "morale", "health",
    "food", "water", "wood", "stone", "medicine", "credits", "district",
    "districts", "threat_level", "caravan_stock", "buildings", "workers",
    "fortification", "injured", "ration_days", "expeditions",
    "threats_survived", "starvation_days", "milestones", "events",
    "finished", "failed",
)
GODOT_COLONY = r'''
extends Control
## An original independently executing colony game, not trace playback.
const VERIFY_FLAG: String = "--verify-colony"
const MAX_ACTIONS: int = 128
const ROLES: Array = ["farmers","gatherers","miners","guards","medics","engineers"]
const BUILDINGS: Array = ["farm","well","house","clinic","watch","workshop"]
var source: Dictionary = {}
var config: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var commands: Array = []
var playable: bool = false
var notice: String = "Manage original frontier colony and defend finite supplies"


func _fail(reason: String) -> void:
    push_error("NATIVE_ADVANCED_COLONY_ERROR: " + reason)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _districts(raw: Array) -> Array:
    var out: Array = []
    for district in raw:
        out.append({
            "id":int(district["id"]), "biome":str(district["biome"]),
            "wood":int(district["wood"]), "stone":int(district["stone"]),
            "food":int(district["food"]), "water":int(district["water"]),
        })
    return out


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length() > 100000:
        _fail("missing or oversized authored colony")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _fail("invalid source JSON")
        return
    source = parsed
    if source.get("schema") != "skeleton.game_builder.godot_advanced_colony.v1":
        _fail("incompatible authored colony schema")
        return
    config = source["settings"]
    layout = source["scene"]["layout"]
    if (layout["districts"].size() < 2 or layout["districts"].size() > 6
        or int(layout["starting_district"]) >= layout["districts"].size()):
        _fail("invalid bounded original colony geography")
        return
    playable = true
    _reset()
    get_window().title = "Skeleton Original Advanced Colony"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var people: int = int(config["settlers"])
    var structures: Dictionary = {}
    var roles: Dictionary = {}
    for name in BUILDINGS:
        structures[name] = 0
    for name in ROLES:
        roles[name] = 0
    state = {
        "seed":int(source["scene"]["seed"]), "tick":0, "day":1,
        "population":people,"healthy":people,"morale":65,"health":100,
        "food":maxi(int(config["initial_stores"]),people*2),
        "water":maxi(int(config["initial_stores"]),people*2),
        "wood":14,"stone":9,"medicine":4,
        "credits":int(config["starting_credits"]),
        "district":int(layout["starting_district"]),
        "districts":_districts(layout["districts"]),
        "threat_level":int(layout["threat_level"]),
        "caravan_stock":int(layout["caravan_stock"]),
        "buildings":structures,"workers":roles,
        "fortification":0,"injured":0,"ration_days":0,"expeditions":0,
        "threats_survived":0,"starvation_days":0,
        "milestones":[],"events":[],"finished":false,"failed":false,
    }
    commands=[]
    notice="Assign workers, construct local infrastructure and survive"
    queue_redraw()


func _people_assigned() -> int:
    var result: int = 0
    for role in ROLES:
        result += int(state["workers"][role])
    return result


func _take(item: String, amount: int) -> void:
    state[item] = int(state[item]) - amount


func _advance() -> Array:
    state["tick"] = int(state["tick"])+1
    state["day"] = int(state["day"])+1
    var events: Array = ["colony_day_advanced"]
    var people: int = int(state["population"])
    var jobs: Dictionary = state["workers"]
    var structures: Dictionary = state["buildings"]
    var district: Dictionary = state["districts"][int(state["district"])]
    var farm: int = mini(int(district["food"]),
        int(jobs["farmers"])*(1+int(structures["farm"]))*int(config["worker_productivity"]))
    district["food"] = int(district["food"]) - farm
    state["food"] = int(state["food"]) + farm
    var gathered: int = mini(int(district["wood"]),
        int(jobs["gatherers"])*2*int(config["worker_productivity"]))
    district["wood"] = int(district["wood"]) - gathered
    state["wood"] = int(state["wood"]) + gathered
    var mined: int = mini(int(district["stone"]),
        int(jobs["miners"])*int(config["worker_productivity"]))
    district["stone"] = int(district["stone"]) - mined
    state["stone"] = int(state["stone"]) + mined
    var drawn: int = mini(int(district["water"]),
        int(structures["well"])*int(config["water_yield"]))
    district["water"] = int(district["water"]) - drawn
    state["water"] = int(state["water"]) + drawn
    if farm or gathered or mined or drawn:
        events.append("assigned_labor_produced_finite_goods")
    var appetite: int = maxi(1,int((people+3)/4))+int(int(config["need_decay"])/4)
    if str(config["food_policy"]) == "frugal":
        appetite = maxi(1,appetite-1)
        state["morale"] = maxi(0,int(state["morale"])-1)
        events.append("frugal_consumption_policy")
    elif str(config["food_policy"]) == "abundant":
        appetite += 1
        state["morale"] = mini(100,int(state["morale"])+2)
        events.append("abundant_consumption_policy")
    if int(state["ration_days"]) > 0:
        appetite = maxi(1,appetite-1)
        state["ration_days"] = int(state["ration_days"])-1
    for good in ["food","water"]:
        state[good] = maxi(0,int(state[good])-appetite)
    if int(state["food"]) == 0 or int(state["water"]) == 0:
        state["starvation_days"] = int(state["starvation_days"])+1
        state["morale"] = maxi(0,int(state["morale"])-5)
        state["health"] = maxi(0,int(state["health"])-7)
        events.append("basic_needs_unmet")
    else:
        state["starvation_days"] = 0
        state["morale"] = mini(100,int(state["morale"])+
            (2 if bool(config["relationships"]) else 1))
    if int(state["injured"]) > 0:
        var care: int = mini(int(state["injured"]),
            mini(int(jobs["medics"])*(1+int(structures["clinic"])),
                 int(state["medicine"])))
        state["injured"] = int(state["injured"])-care
        state["medicine"] = int(state["medicine"])-care
        if care:
            events.append("injured_settlers_healed")
    var disaster_cycle: int = 7 if str(config["disasters"]) == "rare" else 4
    if str(config["disasters"]) != "off" and int(state["day"])%disaster_cycle == 0:
        var loss: int = mini(int(state["food"]),2+int(state["threat_level"]))
        state["food"] = int(state["food"])-loss
        state["health"] = maxi(0,int(state["health"])-
            (1 if int(structures["clinic"]) else 3))
        events.append("severe_weather_damaged_colony_supplies")
    if int(config["disease_pressure"]) > 0 and int(state["day"])%7 == 0:
        var sick: int = mini(maxi(0,people-int(state["injured"])),
            maxi(0,int(config["disease_pressure"])-int(structures["clinic"])))
        state["injured"] = int(state["injured"])+sick
        if sick:
            events.append("preventable_colony_disease_outbreak")
    if (str(config["threats"]) != "off"
        and int(state["day"])%int(config["raid_interval"]) == 0):
        var strength: int = int(state["threat_level"])+2+(
            int(int(state["day"])/10) if str(config["threats"]) == "adaptive" else 0)
        var defense: int = int(jobs["guards"])*2+int(structures["watch"])*3+int(state["fortification"])
        if defense < strength:
            var wounds: int = mini(people-int(state["injured"]),maxi(1,strength-defense))
            state["injured"] = int(state["injured"])+wounds
            state["morale"] = maxi(0,int(state["morale"])-wounds*3)
            state["health"] = maxi(0,int(state["health"])-wounds)
            events.append("colony_raid_breached_defenses")
        else:
            state["threats_survived"] = int(state["threats_survived"])+1
            state["morale"] = mini(100,int(state["morale"])+2)
            events.append("colony_raid_repulsed")
    if int(state["health"]) == 0 or int(state["starvation_days"]) >= 4:
        var losses: int = maxi(1,int(people/8))
        state["population"] = maxi(0,people-losses)
        state["injured"] = mini(int(state["injured"]),int(state["population"]))
        if _people_assigned() > int(state["population"]):
            var reversed_roles: Array = ROLES.duplicate()
            reversed_roles.reverse()
            for role in reversed_roles:
                var remove: int = mini(int(jobs[role]),
                    _people_assigned()-int(state["population"]))
                jobs[role] = int(jobs[role])-remove
        state["health"] = maxi(20,int(state["health"]))
        events.append("colony_population_lost")
    var houses: int = 1+int(structures["house"])*6
    if int(state["population"]) > maxi(int(config["settlers"]),houses):
        state["morale"] = maxi(0,int(state["morale"])-2)
    if (int(state["day"]) >= 8 and int(state["food"]) >= 5
        and int(state["water"]) >= 5 and int(structures["farm"]) > 0
        and int(structures["well"]) > 0):
        if not "self_sufficient_settlement" in state["milestones"]:
            state["milestones"].append("self_sufficient_settlement")
            events.append("self_sufficient_colony_milestone")
    if (int(state["day"]) >= 12 and int(state["morale"]) >= 55
        and int(state["threats_survived"]) >= 2
        and int(structures["clinic"]) > 0 and int(structures["watch"]) > 0):
        if not "thriving_outpost" in state["milestones"]:
            state["milestones"].append("thriving_outpost")
            events.append("thriving_outpost_milestone")
    state["healthy"] = maxi(0,int(state["population"])-int(state["injured"]))
    if (str(config["ending_policy"]) == "thriving_victory"
        and "thriving_outpost" in state["milestones"]):
        state["finished"] = true
        events.append("authored_campaign_victory")
    if int(state["population"]) == 0:
        state["failed"] = true
        events.append("colony_abandoned")
    return events


func _step(action: String) -> bool:
    if not playable or bool(state["failed"]) or bool(state["finished"]) \
        or commands.size() >= MAX_ACTIONS:
        return false
    var events: Array = []
    var district: Dictionary = state["districts"][int(state["district"])]
    if action.begins_with("assign:"):
        var role: String = action.substr(7)
        if not role in ROLES or _people_assigned() >= mini(int(config["jobs"]),int(state["population"])):
            return false
        state["workers"][role] = int(state["workers"][role])+1
        events.append("settler_assigned_to_real_job")
    elif action.begins_with("release:"):
        var role: String = action.substr(8)
        if not role in ROLES or int(state["workers"][role]) == 0:
            return false
        state["workers"][role] = int(state["workers"][role])-1
        events.append("settler_reassigned")
    elif action.begins_with("build:"):
        var name: String = action.substr(6)
        if not name in BUILDINGS or int(state["buildings"][name]) >= 4:
            return false
        var costs: Dictionary = {
            "farm":[4,2],"well":[2,4],"house":[5,3],
            "clinic":[4,5],"watch":[5,5],"workshop":[6,7],
        }
        var pair: Array = costs[name]
        if int(state["wood"]) < int(pair[0]) or int(state["stone"]) < int(pair[1]):
            return false
        _take("wood",int(pair[0]))
        _take("stone",int(pair[1]))
        state["buildings"][name] = int(state["buildings"][name])+1
        events.append("civic_structure_constructed")
    elif action in ["gather_wood","quarry","forage","draw_water"]:
        var resource: String = {
            "gather_wood":"wood","quarry":"stone",
            "forage":"food","draw_water":"water",
        }[action]
        if int(district[resource]) == 0:
            return false
        var got: int = mini(int(district[resource]),4)
        district[resource] = int(district[resource])-got
        state[resource] = int(state[resource])+got
        events.append("finite_"+resource+"_collected")
    elif action == "scavenge":
        if int(state["credits"]) < 2:
            return false
        _take("credits",2)
        state["medicine"] = int(state["medicine"])+2+int(state["buildings"]["workshop"])
        events.append("medical_supplies_scavenged")
    elif action == "expedition":
        if int(state["population"])-_people_assigned() < 1 or int(state["food"]) < 1:
            return false
        _take("food",1)
        state["district"] = (int(state["district"])+1)%state["districts"].size()
        state["expeditions"] = int(state["expeditions"])+1
        events.append("new_original_district_explored")
    elif action == "trade":
        if int(state["caravan_stock"]) < 3 or int(state["credits"]) < 4:
            return false
        _take("credits",4)
        state["caravan_stock"] = int(state["caravan_stock"])-3
        state["food"] = int(state["food"])+2
        state["water"] = int(state["water"])+1
        events.append("finite_caravan_trade")
    elif action == "recruit":
        if not bool(config["allow_migration"]):
            return false
        if (int(state["population"]) >= int(config["settlers"])+
            int(state["buildings"]["house"])*6 or int(state["credits"]) < 8):
            return false
        _take("credits",8)
        state["population"] = int(state["population"])+1
        state["healthy"] = int(state["healthy"])+1
        events.append("new_original_colonist_recruited")
    elif action == "rest":
        state["morale"] = mini(100,int(state["morale"])+2)
        state["health"] = mini(100,int(state["health"])+4)
        events.append("settlers_recovered")
    elif action == "ration":
        if int(state["ration_days"]) >= 4:
            return false
        state["ration_days"] = int(state["ration_days"])+1
        state["morale"] = maxi(0,int(state["morale"])-2)
        events.append("temporary_consumption_rationing")
    elif action == "feast":
        var cost: int = maxi(2,int(int(state["population"])/3))
        if int(state["food"]) < cost:
            return false
        _take("food",cost)
        state["morale"] = mini(100,int(state["morale"])+10)
        events.append("community_feast_held")
    elif action == "fortify":
        if int(state["fortification"]) >= 20 \
            or int(state["wood"]) < 3 or int(state["stone"]) < 2:
            return false
        _take("wood",3)
        _take("stone",2)
        state["fortification"] = mini(20,int(state["fortification"])+2)
        events.append("colony_perimeter_fortified")
    elif action == "treat":
        if int(state["injured"]) == 0 or int(state["medicine"]) < 1:
            return false
        _take("medicine",1)
        state["injured"] = int(state["injured"])-1
        events.append("wounded_colonist_treated")
    elif action in ["tick","tick:4"]:
        for i in range(4 if action == "tick:4" else 1):
            if bool(state["failed"]):
                break
            events.append_array(_advance())
    else:
        return false
    state["events"] = events
    commands.append(action)
    notice = ("Outpost thriving" if bool(state["finished"]) else
        "Colony abandoned" if bool(state["failed"]) else
        "Day %d  %s" % [int(state["day"]),action])
    queue_redraw()
    return true


func _verify() -> void:
    var raw: String = FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length() > 220000:
        _fail("missing or oversized colony replay")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _fail("invalid replay proof")
        return
    var proof: Dictionary = parsed
    if (proof.get("schema") != "skeleton.game_builder.godot_advanced_colony_proof.v1"
        or proof.get("scene_digest") != source["scene"]["digest"]
        or proof.get("settings_digest") != source["settings_digest"]):
        _fail("source geometry or settings changed")
        return
    if (typeof(proof.get("actions")) != TYPE_ARRAY
        or typeof(proof.get("expected")) != TYPE_DICTIONARY
        or proof["actions"].size() > MAX_ACTIONS):
        _fail("unbounded colony proof")
        return
    for action in proof["actions"]:
        if typeof(action) != TYPE_STRING or not _step(action):
            _fail("invalid original colony player order " + str(action))
            return
    var expected: Dictionary = proof["expected"]
    if expected.size() != state.size() or commands.size() != proof["actions"].size():
        _fail("colony replay state field count diverged")
        return
    for field in state:
        if not expected.has(field):
            _fail("colony proof missing " + field)
            return
        var wanted: Variant = expected[field]
        if field == "districts":
            wanted = _districts(wanted)
        elif field == "workers" or field == "buildings":
            if typeof(wanted) != TYPE_DICTIONARY:
                _fail("colony civic source requires structured worker/building counts")
                return
            var normalized: Dictionary = {}
            for key in wanted:
                normalized[str(key)] = int(wanted[key])
            wanted = normalized
        if state[field] != wanted:
            _fail("colony independent rules mismatch at " + field +
                " native=" + str(state[field]) + " reference=" + str(wanted))
            return
    print("NATIVE_ADVANCED_COLONY_OK " + str(source["scene"]["digest"]) +
        " actions=" + str(commands.size()) + " days=" + str(state["day"]) +
        " surviving=" + str(state["population"]))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not playable or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String = ""
    match event.keycode:
        KEY_1: action="build:farm"
        KEY_2: action="build:well"
        KEY_3: action="build:house"
        KEY_4: action="build:clinic"
        KEY_5: action="build:watch"
        KEY_6: action="build:workshop"
        KEY_F: action="assign:farmers"
        KEY_G: action="assign:gatherers"
        KEY_M: action="assign:miners"
        KEY_D: action="assign:guards"
        KEY_H: action="assign:medics"
        KEY_E: action="assign:engineers"
        KEY_SPACE: action="tick"
        KEY_ENTER,KEY_KP_ENTER: action="tick:4"
        KEY_X: action="expedition"
        KEY_W: action="draw_water"
        KEY_T: action="trade"
        KEY_Q: action="quarry"
        KEY_P: action="forage"
        KEY_V: action="fortify"
        KEY_R: _reset()
    if action != "":
        _step(action)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var action: String = ""
        match event.button_index:
            JOY_BUTTON_A: action="tick"
            JOY_BUTTON_B: action="expedition"
            JOY_BUTTON_X: action="forage"
            JOY_BUTTON_Y: action="fortify"
            JOY_BUTTON_DPAD_UP: action="build:farm"
            JOY_BUTTON_DPAD_DOWN: action="build:well"
            JOY_BUTTON_DPAD_LEFT: action="assign:guards"
            JOY_BUTTON_DPAD_RIGHT: action="assign:farmers"
            JOY_BUTTON_START: _reset()
        if action != "":
            _step(action)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code == NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#112031"))
    if not playable:
        return
    _text(Vector2(16,30),"Original Advanced Colony · Frontier",21,Color.WHITE)
    _text(Vector2(16,56),"Day %d · Settlers %d (%d injured) · Morale %d · Health %d" %
        [int(state["day"]),int(state["population"]),int(state["injured"]),
         int(state["morale"]),int(state["health"])],14,Color("#c9e3ef"))
    _text(Vector2(16,80),"Food %d  Water %d  Timber %d  Stone %d  Medicine %d  Credits %d" %
        [int(state["food"]),int(state["water"]),int(state["wood"]),
         int(state["stone"]),int(state["medicine"]),int(state["credits"])],14,Color("#fff4c4"))
    _text(Vector2(16,105),"District %d · Threat %d · Walls %d · Survived %d" %
        [int(state["district"])+1,int(state["threat_level"]),
         int(state["fortification"]),int(state["threats_survived"])],14,Color("#b7dcae"))
    var names: Array = state["districts"]
    for i in range(names.size()):
        var d: Dictionary = names[i]
        var pos: Vector2 = Vector2(20+float(i%3)*225,145+float(int(i/3))*115)
        var active: bool = i == int(state["district"])
        draw_rect(Rect2(pos,Vector2(210,100)),
                  Color("#1f6174") if active else Color("#334959"),true)
        _text(pos+Vector2(8,23),str(d["biome"]).capitalize(),15,Color.WHITE)
        _text(pos+Vector2(8,48),"Wood %d · Stone %d" %
              [int(d["wood"]),int(d["stone"])],12,Color.WHITE)
        _text(pos+Vector2(8,69),"Food %d · Water %d" %
              [int(d["food"]),int(d["water"])],12,Color.WHITE)
    _text(Vector2(16,400),"Buildings: "+str(state["buildings"]),12,Color.WHITE)
    _text(Vector2(16,424),"Workers: "+str(state["workers"]),12,Color("#d5e4f2"))
    _text(Vector2(16,453),"Milestones: "+str(state["milestones"]),12,Color("#e3e9b6"))
    _text(Vector2(16,485),notice,13,Color("#dff1c6"))
    _text(Vector2(16,511),"1–6 build · F/G/M/D/H/E jobs · Space 1 day · Enter 4 days",12,Color.WHITE)
    _text(Vector2(16,530),"X explore · W water · T trade · Q quarry · P forage · V fortify · R reset",
          12,Color("#dce5ef"))


func _text(at: Vector2,message: String,font_size: int,ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,message,
                HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_colony_godot_package(session: dict, settings: dict | None = None,
                                *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("original native colony export needs trusted local operator")
    if type(session) is not dict or session.get("editor") != "colony":
        raise AdvancedGodotExportError("only original reviewed colony session accepted")
    cfg = make_editor_document("colony", settings)
    verify_advanced_session(session, cfg["settings"])
    scene = (validate_advanced_scene(session["scene"], cfg["settings"])
             if session.get("scene") is not None else
             make_advanced_scene("colony", cfg["settings"], seed=session["seed"]))
    if session.get("scene") is None:
        session = run_advanced_session("colony", cfg["settings"],
                                      session["actions"], seed=session["seed"],
                                      scene=scene)
    game = {
        "schema": SCHEMA, "editor": "colony", "quality_floor": "advanced",
        "settings": cfg["settings"], "settings_digest": cfg["digest"],
        "scene": scene, "native_parity_verified": False,
        "third_party_game_assets": False,
    }
    proof = {
        "schema": PROOF_SCHEMA, "scene_digest": scene["digest"],
        "settings_digest": cfg["digest"], "actions": list(session["actions"]),
        "expected": {field: session["state"][field] for field in PROOF_FIELDS},
        "python_session_digest": session["digest"],
        "verified_by_python_replay": True,
    }
    files = {
        "godot/project.godot": _PROJECT.replace(
            "Skeleton Original Adventure", "Skeleton Original Advanced Colony").encode(),
        "godot/export_presets.cfg": _EXPORT_PRESETS.encode(),
        "godot/scenes/main.tscn": _SCENE.encode(),
        "godot/scripts/main.gd": GODOT_COLONY.lstrip().encode(),
        "godot/game.json": _json(game),
        "godot/proof.json": _json(proof),
        "README.md": (
            "# Original Advanced Colony\n\n"
            "Independent offline Godot 4 game: authored finite districts, "
            "worker jobs, crop supply, water, materials, civic buildings, "
            "migrations, disease, weather and colony raids.\n"
            "Keyboard: 1–6 build; F/G/M/D/H/E assign jobs; Space advance; "
            "Enter 4 days; X expedition; W water; T trade; Q quarry; "
            "P forage; V fortify; R restart. Gamepad supported.\n"
            "Source-bound full native replay: "
            "godot --headless --path godot -- --verify-colony\n"
            "ZIP source is not a desktop/console hardware or release certificate.\n"
        ).encode(),
    }
    manifest = {
        "schema": "skeleton.game_builder.advanced_native_package.v1",
        "native_editor": "colony", "native_adapter": "godot4_independent_colony",
        "advanced_floor": True,
        "source_session_digest": session["digest"],
        "authored_scene_digest": scene["digest"],
        "files": {name: sha256(raw).hexdigest() for name, raw in sorted(files.items())},
        "godot_executed": False, "native_hardware_certified": False,
        "publish_approved": False,
    }
    files["release.json"] = _json(manifest)
    return NativeAdvancedGamePackage(files, manifest)


__all__ = ["SCHEMA", "PROOF_SCHEMA", "PROOF_FIELDS",
           "GODOT_COLONY", "render_colony_godot_package"]
