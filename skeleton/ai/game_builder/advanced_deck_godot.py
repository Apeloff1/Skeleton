"""Native Godot 4 deck battler, true rule execution and Python proof parity.

The Godot game independently shuffles, draws and discards cards; applies all
eight original card types, finite energy, armor, poison, potions and rotating
enemy intentions. Source-only packaging is never native certification.
"""
from __future__ import annotations
from hashlib import sha256

from .advanced_godot_export import (
    NativeAdvancedGamePackage, AdvancedGodotExportError, _json,
)
from .advanced_gameplay_runtime import (
    run_advanced_session, verify_advanced_session,
)
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA="skeleton.game_builder.godot_advanced_deck_battler.v1"
PROOF_SCHEMA="skeleton.game_builder.godot_advanced_deck_battler_proof.v1"
PROOF_FIELDS=(
    "round","seed","hand_limit","max_hp","hp","enemy_hp","enemy_max_hp",
    "energy","energy_limit","block","enemy_block","strength","weak","poison",
    "enemy_strength","enemy_poison","potions","hand","draw_pile","discard",
    "exhaust","deck_origin","enemy_pattern","enemy_intent","damage_dealt",
    "score","events","finished","failed",
)

GODOT_DECK_BATTLER=r'''
extends Control
## Independent native original card-battle simulation and replay witness.
const VERIFY_FLAG: String = "--verify-deck"
const MAX_ACTIONS: int = 128
const COSTS: Dictionary = {
    "strike":1, "guard":1, "pierce":2, "drain":2,
    "rally":1, "scry":0, "ward":1, "spark":1
}
const ACTIONS: Array = [
    "play:0","play:1","play:2","play:3","play:4",
    "end_turn","potion"
]
var world: Dictionary = {}
var rules: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var ready_to_play: bool = false
var commands: Array = []
var notice: String = "Original cards · 1–5 play, Enter ends turn, H heals"


func _native_error(reason: String) -> void:
    push_error("NATIVE_ADVANCED_DECK_ERROR: " + reason)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _shuffle(cards: Array, value: int) -> Array:
    # Exactly reproduce the bounded 31-bit integer LCG of the Python
    # original. Intermediate products fit in signed 64-bit Godot integers.
    var shuffled: Array = cards.duplicate(true)
    var rng: int = (value ^ 0xA5B35705) & 0x7fffffff
    for i in range(shuffled.size()-1,0,-1):
        rng = (1103515245 * rng + 12345) & 0x7fffffff
        var other: int = rng % (i+1)
        var previous: Variant = shuffled[i]
        shuffled[i] = shuffled[other]
        shuffled[other] = previous
    return shuffled


func _draw_cards(count: int) -> void:
    for i in range(count):
        if state["hand"].size() >= int(state["hand_limit"]):
            break
        if state["draw_pile"].is_empty():
            if state["discard"].is_empty():
                break
            state["draw_pile"] = _shuffle(state["discard"],
                                      int(state["seed"])+int(state["round"]))
            state["discard"] = []
        state["hand"].append(state["draw_pile"].pop_back())


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length() > 80000:
        _native_error("missing or oversized authored deck")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _native_error("invalid native source JSON")
        return
    world = parsed
    if world.get("schema") != "skeleton.game_builder.godot_advanced_deck_battler.v1":
        _native_error("incompatible original card game source")
        return
    rules = world["settings"]
    layout = world["scene"]["layout"]
    if (layout["cards"].size() < 10 or layout["cards"].size() > 40
        or int(layout["hand_size"]) < 3 or int(layout["hand_size"]) > 5):
        _native_error("authored deck or hand exceeds gameplay rules")
        return
    ready_to_play = true
    _reset()
    get_window().title = "Skeleton Original Advanced Deck Battler"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var seed: int = int(world["scene"]["seed"])
    state = {
        "round":1,"seed":seed,"hand_limit":int(layout["hand_size"]),
        "max_hp":int(rules["starting_health"]),
        "hp":int(rules["starting_health"]),
        "enemy_hp":int(rules["enemy_health"]),
        "enemy_max_hp":int(rules["enemy_health"]),
        "energy":int(rules["energy_per_turn"]),
        "energy_limit":int(rules["energy_per_turn"]),
        "block":0,"enemy_block":int(layout["enemy_armor"]),
        "strength":0,"weak":0,"poison":0,
        "enemy_strength":0,"enemy_poison":0,
        "potions":int(layout["potions"]),
        "hand":[],"draw_pile":_shuffle(layout["cards"],seed),
        "discard":[],"exhaust":[],
        "deck_origin":layout["cards"].duplicate(true),
        "enemy_pattern":layout["enemy_pattern"].duplicate(true),
        "enemy_intent":str(layout["enemy_pattern"][0]),
        "damage_dealt":0,"score":0,"events":[],
        "finished":false,"failed":false,
    }
    commands=[]
    _draw_cards(int(state["hand_limit"]))
    notice="Original battle: plan every card and enemy intention"
    queue_redraw()


func _enemy_damage(amount: int, piercing: bool = false) -> int:
    var damage: int = maxi(0,amount)
    var armor: int = 0
    if not piercing:
        armor = mini(int(state["enemy_block"]),damage)
    state["enemy_block"] = int(state["enemy_block"])-armor
    var actual: int = mini(int(state["enemy_hp"]),damage-armor)
    state["enemy_hp"] = int(state["enemy_hp"])-actual
    state["damage_dealt"] = int(state["damage_dealt"])+actual
    return actual


func _player_damage(amount: int) -> void:
    var blocked: int = mini(int(state["block"]),amount)
    state["block"] = int(state["block"])-blocked
    state["hp"] = maxi(0,int(state["hp"])-(amount-blocked))


func _step(action: String) -> bool:
    if (not ready_to_play or bool(state["finished"]) or bool(state["failed"])
        or commands.size() >= MAX_ACTIONS or action not in ACTIONS):
        return false
    var events: Array = []
    if action.begins_with("play:"):
        var index: int = int(action.substr(5))
        if index >= state["hand"].size():
            return false
        var card: String = str(state["hand"][index])
        if not COSTS.has(card):
            return false
        var cost: int = int(COSTS[card])
        if int(state["energy"]) < cost:
            return false
        state["energy"] = int(state["energy"])-cost
        state["hand"].remove_at(index)
        state["discard"].append(card)
        match card:
            "strike":
                _enemy_damage(int(rules["attack_damage"])+int(state["strength"]))
            "guard":
                state["block"] = int(state["block"])+int(rules["block_value"])
            "pierce":
                _enemy_damage(int(rules["attack_damage"])+3+
                              int(state["strength"]),true)
            "drain":
                var dealt: int = _enemy_damage(maxi(1,
                    int(rules["attack_damage"])/2+int(state["strength"])))
                state["hp"] = mini(int(state["max_hp"]),int(state["hp"])+dealt)
            "rally":
                state["strength"] = int(state["strength"])+2
            "scry":
                _draw_cards(2)
            "ward":
                state["block"] = int(state["block"])+maxi(2,int(rules["block_value"])/2)
                state["poison"] = maxi(0,int(state["poison"])-2)
            "spark":
                state["enemy_poison"] = int(state["enemy_poison"])+3
        events.append("card_"+card+"_played")
    elif action == "potion":
        if int(state["potions"]) <= 0 or int(state["hp"]) == int(state["max_hp"]):
            return false
        state["potions"] = int(state["potions"])-1
        state["hp"] = mini(int(state["max_hp"]),int(state["hp"])+8)
        events.append("potion_consumed")
    elif action == "end_turn":
        var intent: String = str(state["enemy_intent"])
        if int(state["enemy_poison"]) > 0:
            state["enemy_hp"] = maxi(0,int(state["enemy_hp"])-int(state["enemy_poison"]))
            state["enemy_poison"] = int(state["enemy_poison"])-1
            events.append("enemy_poison_tick")
        if int(state["enemy_hp"]) > 0:
            match intent:
                "attack":
                    _player_damage(4+int(state["enemy_strength"]))
                    events.append("enemy_attacked")
                "defend":
                    state["enemy_block"] = int(state["enemy_block"])+5
                    events.append("enemy_guarded")
                "poison":
                    state["poison"] = int(state["poison"])+2
                    events.append("player_poisoned")
                "charge":
                    state["enemy_strength"] = int(state["enemy_strength"])+2
                    events.append("enemy_enraged")
        if int(state["poison"]) > 0:
            state["hp"] = maxi(0,int(state["hp"])-int(state["poison"]))
            state["poison"] = int(state["poison"])-1
            events.append("player_poison_tick")
        state["discard"].append_array(state["hand"])
        state["hand"] = []
        state["round"] = int(state["round"])+1
        state["block"] = 0
        state["energy"] = int(state["energy_limit"])
        var intent_index: int = (int(state["round"])-1) % state["enemy_pattern"].size()
        state["enemy_intent"] = state["enemy_pattern"][intent_index]
        _draw_cards(int(state["hand_limit"]))
        events.append("new_turn")
    if int(state["enemy_hp"]) <= 0:
        state["enemy_hp"] = 0
        state["finished"] = true
        state["score"] = maxi(1,1000+int(state["hp"])*3-int(state["round"])*10)
        events.append("enemy_boss_defeated")
    if int(state["hp"]) <= 0:
        state["hp"] = 0
        state["failed"] = true
        state["finished"] = false
        events.append("player_battle_lost")
    state["events"] = events
    commands.append(action)
    notice = ("Boss defeated!" if bool(state["finished"])
        else "Battle lost" if bool(state["failed"]) else action)
    queue_redraw()
    return true


func _verify() -> void:
    var raw: String = FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length() > 180000:
        _native_error("missing or oversized authoritative source proof")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _native_error("invalid original card proof")
        return
    var proof: Dictionary = parsed
    if (proof.get("schema") != "skeleton.game_builder.godot_advanced_deck_battler_proof.v1"
        or proof.get("scene_digest") != world["scene"]["digest"]
        or proof.get("settings_digest") != world.get("settings_digest")):
        _native_error("authored deck/setting mismatch")
        return
    var sequence: Variant = proof.get("actions")
    var expected: Variant = proof.get("expected")
    if typeof(sequence) != TYPE_ARRAY or typeof(expected) != TYPE_DICTIONARY:
        _native_error("invalid game evidence")
        return
    if sequence.size() > MAX_ACTIONS:
        _native_error("replay exceeds bounded command capacity")
        return
    for action in sequence:
        if typeof(action) != TYPE_STRING or not _step(action):
            _native_error("native action rejected: "+str(action))
            return
    if state.size() != expected.size():
        _native_error("proof fields are missing or unexpected")
        return
    for field in state:
        if not expected.has(field) or state[field] != expected[field]:
            _native_error("independent "+str(field)+" mismatch native="+
                          str(state[field])+" python="+str(expected.get(field,"<missing>")))
            return
    if commands.size() != sequence.size():
        _native_error("transcript count mismatch")
        return
    print("NATIVE_ADVANCED_DECK_OK " + str(world["scene"]["digest"]) +
          " actions=" + str(commands.size()) +
          " outcome=" + ("won" if bool(state["finished"])
                         else "lost" if bool(state["failed"]) else "playing"))
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not ready_to_play or not event is InputEventKey or not event.pressed or event.echo:
        return
    var choice: String = ""
    match event.keycode:
        KEY_1, KEY_KP_1: choice="play:0"
        KEY_2, KEY_KP_2: choice="play:1"
        KEY_3, KEY_KP_3: choice="play:2"
        KEY_4, KEY_KP_4: choice="play:3"
        KEY_5, KEY_KP_5: choice="play:4"
        KEY_ENTER, KEY_KP_ENTER: choice="end_turn"
        KEY_H: choice="potion"
        KEY_R: _reset()
    if choice != "":
        _step(choice)
    get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventJoypadButton and event.pressed:
        var choice: String = ""
        match event.button_index:
            JOY_BUTTON_DPAD_LEFT: choice="play:0"
            JOY_BUTTON_DPAD_RIGHT: choice="play:1"
            JOY_BUTTON_DPAD_UP: choice="play:2"
            JOY_BUTTON_DPAD_DOWN: choice="play:3"
            JOY_BUTTON_A: choice="play:4"
            JOY_BUTTON_X: choice="end_turn"
            JOY_BUTTON_Y: choice="potion"
            JOY_BUTTON_START: _reset()
        if choice != "":
            _step(choice)
        get_viewport().set_input_as_handled()


func _notification(code: int) -> void:
    if code == NOTIFICATION_RESIZED:
        queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#111b29"))
    if not ready_to_play:
        return
    _text(Vector2(16,32),"Original Advanced Deck Battler",23,Color.WHITE)
    _text(Vector2(16,57),"Turn %d · Energy %d · Deck %d · Discard %d" %
        [int(state["round"]),int(state["energy"]),
         state["draw_pile"].size(),state["discard"].size()],15,Color("#a5ead9"))
    _text(Vector2(16,84),"BOSS  %d/%d HP   Shield %d   Poison %d   Intent %s" %
        [int(state["enemy_hp"]),int(state["enemy_max_hp"]),
         int(state["enemy_block"]),int(state["enemy_poison"]),
         str(state["enemy_intent"])],15,Color("#eebf9d"))
    _text(Vector2(16,109),"YOU   %d/%d HP   Shield %d   Poison %d   STR %d   Potions %d" %
        [int(state["hp"]),int(state["max_hp"]),int(state["block"]),
         int(state["poison"]),int(state["strength"]),int(state["potions"])],
         15,Color("#a5ebbb"))
    _text(Vector2(16,138),notice,14,Color("#f2d7a8"))
    for index in range(state["hand"].size()):
        var card: String = str(state["hand"][index])
        var px: float = 16.0 + float(index) * 105.0
        var py: float = 163.0
        var rect: Rect2 = Rect2(Vector2(px,py),Vector2(98,130))
        draw_rect(rect,Color("#294860"),true)
        draw_rect(rect,Color("#77b8ae"),false,2.0)
        _text(Vector2(px+7,py+30),card,15,Color.WHITE)
        _text(Vector2(px+7,py+55),"Cost "+str(COSTS.get(card,0)),12,Color("#f5ca8f"))
        _text(Vector2(px+7,py+112),"Key "+str(index+1),12,Color("#d2eee5"))
    _text(Vector2(16,minf(size.y-25.0,350.0)),
          "1–5 play cards · Enter end turn · H potion · R restart",
          13,Color("#aeced8"))


func _text(at: Vector2, label: String, font_size: int, ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,label,
        HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_deck_godot_package(session: dict, settings: dict | None = None,
                              *, authorized: bool) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("native card-game export needs operator authorization")
    if type(session) is not dict or session.get("editor")!="deck_battler":
        raise AdvancedGodotExportError("only reviewed original deck sessions can use this native adapter")
    config=make_editor_document("deck_battler",settings)
    verify_advanced_session(session,config["settings"])
    scene=(validate_advanced_scene(session["scene"],config["settings"])
           if session.get("scene") is not None
           else make_advanced_scene("deck_battler",config["settings"],seed=session["seed"]))
    if session.get("scene") is None:
        session=run_advanced_session("deck_battler",config["settings"],
                                     session["actions"],seed=session["seed"],scene=scene)
    state=session["state"]
    game={"schema":SCHEMA,"editor":"deck_battler","quality_floor":"advanced",
          "settings":config["settings"],"settings_digest":config["digest"],
          "scene":scene,"native_parity_verified":False,
          "external_asset_execution":False}
    proof={"schema":PROOF_SCHEMA,
           "scene_digest":scene["digest"],"settings_digest":config["digest"],
           "actions":session["actions"],
           "expected":{key:state[key] for key in PROOF_FIELDS},
           "python_session_digest":session["digest"],
           "verified_by_python_replay":True}
    files={
        "godot/project.godot":_PROJECT.replace("Skeleton Original Adventure",
                              "Skeleton Original Advanced Deck Battler").encode("utf-8"),
        "godot/export_presets.cfg":_EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn":_SCENE.encode("utf-8"),
        "godot/scripts/main.gd":GODOT_DECK_BATTLER.lstrip().encode("utf-8"),
        "godot/game.json":_json(game),
        "godot/proof.json":_json(proof),
        "README.md":(
            "# Original Advanced Native Deck Battler\n\n"
            "Offline Godot 4.4.1+ game with eight original card types, seed-deterministic\n"
            "shuffle, finite card economy, poison, defense, status effects and enemy AI.\n"
            "1–5: select current hand card; Enter: end turn; H: potion; R: restart.\n"
            "Run: godot --headless --path godot -- --verify-deck\n"
            "The native engine executes rules independently of the verified Python\n"
            "transcript and rejects any state divergence. This source export is not\n"
            "a native hardware certificate, licensing clearance or store publication.\n"
        ).encode("utf-8"),
    }
    manifest={
        "schema":"skeleton.game_builder.advanced_native_package.v1",
        "native_editor":"deck_battler",
        "native_adapter":"godot4_independent_deck_battler",
        "advanced_floor":True,
        "source_session_digest":session["digest"],
        "authored_scene_digest":scene["digest"],
        "files":{path:sha256(raw).hexdigest() for path,raw in sorted(files.items())},
        "godot_executed":False,"native_hardware_certified":False,
        "publish_approved":False,
    }
    files["release.json"]=_json(manifest)
    return NativeAdvancedGamePackage(files,manifest)


__all__=["SCHEMA","PROOF_SCHEMA","PROOF_FIELDS","GODOT_DECK_BATTLER",
         "render_deck_godot_package"]
