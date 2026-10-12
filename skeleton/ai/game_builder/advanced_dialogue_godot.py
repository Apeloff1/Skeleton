"""Godot 4 independent original Dialogue mechanics, source-bounded replay.

The native game interprets real player commands using its own GDScript state
transitions. The Python engine produces only a separately replay-verified
EXPECTATION, never per-turn snapshots or native mutable state.
"""
from __future__ import annotations

from hashlib import sha256

from .advanced_godot_export import (
    AdvancedGodotExportError, NativeAdvancedGamePackage, _json,
)
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import SceneError, make_advanced_scene, validate_advanced_scene
from .dual_runtime_export import _PROJECT, _SCENE, _EXPORT_PRESETS
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.godot_advanced_dialogue.v1"
PROOF_SCHEMA = "skeleton.game_builder.godot_advanced_dialogue_proof.v1"
PROOF_FIELDS = (
    "tick", "title", "position", "locations", "speakers",
    "active_speakers", "unmodeled_speakers",
    "text_delivery", "social_choices_enabled", "direct_statements",
    "corroborations", "history", "choices", "influence", "reputation",
    "support_count", "challenge_count", "attention_spent",
    "conversations", "checkpoint", "retired", "finished", "failed",
    "events", "statement_limit",
)

GODOT_DIALOGUE = r'''
extends Control
## Independent full-state source-bound original social gameplay.
const PROOF_FLAG: String = "--verify-dialogue"
const MAX_ACTIONS: int = 128
const LOCATIONS: Array = ["plaza", "market", "archive"]
var source: Dictionary = {}
var rules: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var history: Array = []
var playable: bool = false
var notice: String = "Talk to authentic local voices and compare evidence"


func _reject(message: String) -> void:
    push_error("NATIVE_ADVANCED_DIALOGUE_ERROR: " + message)
    if PROOF_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length() > 120000:
        _reject("absent or over-budget original dialogue source")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _reject("original dialogue source is not an object")
        return
    source = parsed
    if source.get("schema") != "skeleton.game_builder.godot_advanced_dialogue.v1":
        _reject("unknown original dialogue source version")
        return
    if typeof(source.get("scene")) != TYPE_DICTIONARY or typeof(source.get("settings")) != TYPE_DICTIONARY:
        _reject("authored scene and settings required")
        return
    rules = source["settings"]
    layout = source["scene"]["layout"]
    if typeof(layout.get("speakers")) != TYPE_ARRAY or layout["speakers"].size() < 1 or layout["speakers"].size() > 8:
        _reject("unsupported number of original living speakers")
        return
    if layout.get("locations") != LOCATIONS or layout.get("provenance") != "original_authored_statements":
        _reject("unrecognized original authored speaker locality")
        return
    _reset()
    playable = true
    get_window().title = "Skeleton Original Dialogue & Social Choice"
    if PROOF_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var voices: Array = []
    for datum in layout["speakers"]:
        var voice: Dictionary = datum.duplicate(true)
        voice["trust"] = int(rules["starting_trust"])
        voice["patience"] = int(datum["initial_patience"])
        voice["heard"] = 0
        voice["supported"] = 0
        voice["challenged"] = 0
        voice["memories"] = []
        voice["last_heard"] = null
        voices.append(voice)
    state = {
        "tick": 0, "title": str(layout["title"]),
        "position": int(layout["origin"]), "locations": LOCATIONS.duplicate(),
        "speakers": voices, "active_speakers": voices.size(),
        "unmodeled_speakers": int(rules["speakers"]) - voices.size(),
        "text_delivery": str(rules["text_delivery"]),
        "social_choices_enabled": bool(rules["choice_consequences"]),
        "direct_statements": [], "corroborations": [],
        "history": [], "choices": [],
        "influence": int(rules["starting_influence"]),
        "reputation": int(rules["starting_reputation"]),
        "support_count": 0, "challenge_count": 0,
        "attention_spent": 0, "conversations": 0,
        "checkpoint": false, "retired": false,
        "finished": false, "failed": false, "events": [],
        "statement_limit": int(rules["lines_per_scene"]),
    }
    history = []
    notice = "Speak, support or challenge local people; compare claims in archive"
    queue_redraw()


func _remember(voice: Dictionary, label: String) -> void:
    var limit: int = int(rules["memory_turns"])
    if limit == 0:
        voice["memories"] = []
        return
    voice["memories"].append({
        "turn": int(state["tick"]), "kind": label, "speaker": int(voice["id"]),
    })
    var count: int = mini(32, limit)
    while voice["memories"].size() > count:
        voice["memories"].pop_front()


func _decay() -> void:
    var lifetime: int = int(rules["memory_turns"])
    if lifetime == 0:
        return
    for voice in state["speakers"]:
        var surviving: Array = []
        for entry in voice["memories"]:
            if int(state["tick"]) - int(entry["turn"]) < lifetime:
                surviving.append(entry)
        voice["memories"] = surviving


func _action(command: String) -> bool:
    if bool(state["finished"]) or bool(state["failed"]) or history.size() >= MAX_ACTIONS:
        notice = "Dialogue already complete or replay capacity exhausted"
        return false
    if int(state["tick"]) >= int(rules["dialogue_turn_budget"]):
        notice = "Original finite turn budget exhausted"
        return false
    var events: Array = []
    if command.begins_with("travel:"):
        var part: String = command.get_slice(":", 1)
        if not part.is_valid_int() or str(int(part)) != part:
            notice = "Unregistered physical route"
            return false
        var next_stop: int = int(part)
        if next_stop < 0 or next_stop >= LOCATIONS.size() or absi(next_stop-int(state["position"])) != 1:
            notice = "Movement requires an adjacent original station"
            return false
        state["position"] = next_stop
        events.append("player_traveled_to_original_social_station")
    elif command.begins_with("speak:") or command.begins_with("support:") or command.begins_with("challenge:"):
        var verb: String = command.get_slice(":", 0)
        var code: String = command.get_slice(":", 1)
        if not code.is_valid_int() or str(int(code)) != code:
            notice = "Unregistered original speaker identity"
            return false
        var who: int = int(code)
        if who < 0 or who >= state["speakers"].size() or who > 7:
            notice = "Speaker outside detailed social world"
            return false
        var speaker: Dictionary = state["speakers"][who]
        if int(speaker["location"]) != int(state["position"]):
            notice = "Cannot speak to a remotely absent person"
            return false
        if int(speaker["patience"]) <= 0:
            notice = "Person's finite conversation patience depleted"
            return false
        if verb == "speak":
            if int(state["conversations"]) >= int(rules["lines_per_scene"]) or int(speaker["heard"]) > 0:
                notice = "Cannot mint another original first-hand source"
                return false
            speaker["heard"] = int(speaker["heard"]) + 1
            speaker["patience"] = int(speaker["patience"]) - 1
            speaker["last_heard"] = int(state["tick"])
            state["conversations"] = int(state["conversations"]) + 1
            state["direct_statements"].append({
                "speaker": int(speaker["id"]), "topic": int(speaker["topic"]),
                "position": int(speaker["position"]), "testimony": int(speaker["testimony"]),
                "source": "original_first_hand_speaker_statement",
                "heard_at": int(state["tick"]),
            })
            _remember(speaker,"first_hand_speech")
            events.append("original_direct_testimony_heard_at_real_position")
        else:
            if not bool(rules["choice_consequences"]) or int(speaker["heard"]) < 1:
                notice = "Choice lacks permission or genuine firsthand testimony"
                return false
            var cost: int = int(rules["support_cost"]) if verb == "support" else int(rules["challenge_cost"])
            if int(state["influence"]) < cost:
                notice = "Cannot spend unavailable finite influence"
                return false
            state["influence"] = int(state["influence"]) - cost
            speaker["patience"] = int(speaker["patience"]) - 1
            if verb == "support":
                speaker["supported"] = int(speaker["supported"]) + 1
                speaker["trust"] = mini(int(rules["trust_cap"]), int(speaker["trust"]) + int(rules["support_trust_gain"]))
                state["support_count"] = int(state["support_count"]) + 1
                state["reputation"] = int(state["reputation"]) + int(rules["support_reputation"])
                _remember(speaker, "paid_source_support")
                events.append("finite_cost_original_support_raised_real_trust")
            else:
                speaker["challenged"] = int(speaker["challenged"]) + 1
                speaker["trust"] = maxi(0, int(speaker["trust"]) - int(rules["challenge_trust_loss"]))
                state["challenge_count"] = int(state["challenge_count"]) + 1
                state["reputation"] = int(state["reputation"]) - int(rules["challenge_reputation"])
                _remember(speaker, "paid_source_challenge")
                events.append("finite_cost_original_challenge_with_social_consequence")
            state["choices"].append({
                "speaker": who, "branch": verb, "tick": int(state["tick"]), "cost": cost,
            })
    elif command.begins_with("compare:"):
        var topic_token: String = command.get_slice(":", 1)
        if not topic_token.is_valid_int() or str(int(topic_token)) != topic_token:
            notice = "Unrecognized social topic"
            return false
        var topic: int = int(topic_token)
        if topic < 0 or topic >= 4 or int(state["position"]) != 2 or topic in state["corroborations"]:
            notice = "Original archive must hold a new real source comparison"
            return false
        var distinct: Array = []
        for claim in state["direct_statements"]:
            if int(claim["topic"]) == topic and int(claim["speaker"]) not in distinct:
                distinct.append(int(claim["speaker"]))
        if distinct.size() < 2:
            notice = "Two independent direct speakers required"
            return false
        state["corroborations"].append(topic)
        state["corroborations"].sort()
        events.append("original_two_independent_direct_speaker_sources_compared")
    elif command == "claim":
        var trusted: bool = false
        for voice in state["speakers"]:
            if int(voice["supported"]) > 0 and int(voice["trust"]) >= int(rules["trust_threshold"]):
                trusted = true
                break
        if bool(state["checkpoint"]) or state["corroborations"].is_empty() or int(state["support_count"]) < int(rules["support_goal"]) or not trusted:
            notice = "Consensus requires distinct sources and actual social work"
            return false
        state["checkpoint"] = true
        events.append("earned_original_social_consensus_nonterminal")
    elif command == "retire":
        if not bool(state["checkpoint"]):
            notice = "Epilogue requires earned consensus"
            return false
        state["retired"] = true
        state["finished"] = true
        events.append("voluntary_original_dialogue_epilogue")
    elif command == "rest":
        if int(state["influence"]) >= int(rules["starting_influence"]):
            notice = "Cannot fabricate extra influence at full capacity"
            return false
        state["influence"] = mini(int(rules["starting_influence"]), int(state["influence"]) + int(rules["rest_influence"]))
        events.append("bounded_original_social_recovery")
    elif command == "inspect" or command == "wait":
        events.append("original_social_context_observed_without_fake_progress")
    else:
        notice = "Illegal original dialogue command"
        return false
    state["tick"] = int(state["tick"]) + 1
    if command.begins_with("speak:") or command.begins_with("support:") or command.begins_with("challenge:") or command.begins_with("compare:"):
        state["attention_spent"] = int(state["attention_spent"]) + 1
    if int(rules["memory_turns"]) > 0:
        state["history"].append({
            "turn": int(state["tick"]), "action": command,
            "events": events.duplicate(), "speaker_source_bound": true,
        })
        var cap: int = mini(64,int(rules["memory_turns"]))
        while state["history"].size() > cap:
            state["history"].pop_front()
    _decay()
    state["events"] = events
    history.append(command)
    notice = "Original dialogue turn " + str(state["tick"]) + ": " + command
    queue_redraw()
    return true


func _canonical_number(value: Variant) -> Variant:
    if typeof(value) == TYPE_FLOAT:
        if not is_finite(value) or floor(value) != value or absf(value) > 9007199254740991.0:
            return "invalid_float_in_integer_source"
        return int(value)
    if typeof(value) == TYPE_ARRAY:
        var translated: Array = []
        for element in value:
            translated.append(_canonical_number(element))
        return translated
    if typeof(value) == TYPE_DICTIONARY:
        var translated: Dictionary = {}
        for key in value.keys():
            translated[key] = _canonical_number(value[key])
        return translated
    return value


func _verify() -> void:
    var raw: String = FileAccess.get_file_as_string("res://proof.json")
    if raw.is_empty() or raw.length() > 180000:
        _reject("source proof missing or oversized")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _reject("original proof must be object")
        return
    var proof: Dictionary = parsed
    if proof.get("schema") != "skeleton.game_builder.godot_advanced_dialogue_proof.v1":
        _reject("unknown social proof version")
        return
    if proof.get("scene_digest") != source["scene"]["digest"] or proof.get("settings_digest") != source.get("settings_digest"):
        _reject("social source digest differs from reviewed proof")
        return
    if typeof(proof.get("verified_by_python_replay")) != TYPE_BOOL or not proof["verified_by_python_replay"]:
        _reject("independent reference verification is required")
        return
    var proposed: Variant = proof.get("actions")
    var expected_variant: Variant = proof.get("expected")
    if typeof(proposed) != TYPE_ARRAY or typeof(expected_variant) != TYPE_DICTIONARY:
        _reject("missing typed original actions or source state")
        return
    var actions: Array = proposed
    var expected: Dictionary = expected_variant
    if actions.size() > MAX_ACTIONS:
        _reject("social replay budget exceeded")
        return
    for action in actions:
        if typeof(action) != TYPE_STRING or not _action(str(action)):
            _reject("social evidence includes illegal player action")
            return
    if state.size() != expected.size():
        _reject("partial proof projection cannot authorize source parity")
        return
    for key in state.keys():
        if not expected.has(key) or _canonical_number(state[key]) != _canonical_number(expected[key]):
            _reject("independent source-state divergence: " + str(key) +
                " actual=" + JSON.stringify(state[key]) +
                " expected=" + JSON.stringify(expected.get(key)))
            return
    print("NATIVE_ADVANCED_DIALOGUE_OK")
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not playable or not event is InputEventKey or not event.pressed or event.echo:
        return
    var choice: String = ""
    match event.keycode:
        KEY_LEFT: choice = "travel:" + str(int(state["position"])-1)
        KEY_RIGHT: choice = "travel:" + str(int(state["position"])+1)
        KEY_1: choice = "speak:0"
        KEY_2: choice = "speak:1"
        KEY_3: choice = "speak:2"
        KEY_4: choice = "speak:3"
        KEY_5: choice = "speak:4"
        KEY_6: choice = "speak:5"
        KEY_7: choice = "speak:6"
        KEY_8: choice = "speak:7"
        KEY_S: choice = "support:0"
        KEY_C: choice = "challenge:0"
        KEY_A: choice = "compare:0"
        KEY_G: choice = "claim"
        KEY_E: choice = "retire"
        KEY_W: choice = "wait"
        KEY_I: choice = "inspect"
        KEY_R:
            _reset()
            return
    if not choice.is_empty():
        _action(choice)


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size),Color("#102432"))
    if not playable:
        return
    _write(Vector2(16,29),"ORIGINAL DIALOGUE  /  LOCAL FIRST-HAND SOURCES",20,Color("#e9e9d8"))
    _write(Vector2(16,56),str(state["title"])+" · Turn "+str(state["tick"]),14,Color("#cde7db"))
    for i in range(3):
        var x: float = 17.0+i*221.0
        var active: bool = int(state["position"]) == i
        draw_rect(Rect2(Vector2(x,75),Vector2(210,235)),
            Color("#35665e") if active else Color("#344a60"),true)
        _write(Vector2(x+9,99),str(LOCATIONS[i]).to_upper(),16,Color("#ffe3b2"))
        for voice in state["speakers"]:
            if int(voice["location"]) == i:
                var y: float = 122.0 + float(int(voice["id"])/3)*40.0
                _write(Vector2(x+8,y),str(voice["name"]),12,Color("#e8ecdf"))
                _write(Vector2(x+8,y+17),"Trust "+str(voice["trust"])+" / Patience "+str(voice["patience"]),
                    11,Color("#d1ead8"))
        if active:
            draw_rect(Rect2(Vector2(x+2,77),Vector2(206,231)),Color("#ffd58f"),false,2)
    _write(Vector2(17,350),"Influence "+str(state["influence"])+" · Reputation "+str(state["reputation"])+
        " · Firsthand sources "+str(state["direct_statements"].size()),14,Color.WHITE)
    _write(Vector2(17,379),"Independent topics verified "+str(state["corroborations"])+
        " · Social support "+str(state["support_count"]),13,Color("#e8e2aa"))
    _write(Vector2(17,410),notice,12,Color("#c5f1dd"))
    _write(Vector2(17,442),"Arrows: stations   1–8: speak   S/C: support/challenge Voice 1   A: compare topic 0",11,Color.WHITE)
    _write(Vector2(17,467),"G: consensus   E: epilogue   W: wait   I: inspect   R: restart",11,Color.WHITE)
    _write(Vector2(17,500),"Earned consensus · nonterminal" if bool(state["checkpoint"]) else
        "Gather two original sources and earn trust to reach social consensus",
        12,Color("#f3dfa6"))


func _write(at: Vector2, label: String, size_px: int, ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,label,
        HORIZONTAL_ALIGNMENT_LEFT,-1,size_px,ink)
'''


def render_dialogue_godot_package(
    session: dict, settings: dict | None = None, *, authorized: bool
) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("Godot Dialogue export requires explicit local operator")
    if type(session) is not dict or session.get("editor") != "dialogue":
        raise AdvancedGodotExportError("authored replay-verified Dialogue game required")
    cfg = make_editor_document("dialogue", settings)
    try:
        verify_advanced_session(session, cfg["settings"])
    except SceneError as exc:
        raise AdvancedGodotExportError("reviewed Dialogue source scene does not match session settings") from exc
    scene = (
        validate_advanced_scene(session["scene"], cfg["settings"])
        if session.get("scene") is not None
        else make_advanced_scene("dialogue", cfg["settings"], seed=session["seed"])
    )
    if scene["editor"] != "dialogue" or scene["seed"] != session["seed"]:
        raise AdvancedGodotExportError("Dialogue scene and original receipt differ")
    if session.get("scene") is None:
        session = run_advanced_session(
            "dialogue", cfg["settings"], session["actions"],
            seed=session["seed"], scene=scene,
        )
        verify_advanced_session(session, cfg["settings"])
    if set(session["state"]) != set(PROOF_FIELDS):
        raise AdvancedGodotExportError("native source proof does not cover entire dialogue world")
    game = {
        "schema": SCHEMA, "editor": "dialogue", "quality_floor": "advanced",
        "settings": cfg["settings"], "settings_digest": cfg["digest"],
        "scene": scene, "native_parity_verified": False,
        "external_assets_executed": False,
    }
    proof = {
        "schema": PROOF_SCHEMA, "scene_digest": scene["digest"],
        "settings_digest": cfg["digest"], "actions": list(session["actions"]),
        "expected": {key: session["state"][key] for key in PROOF_FIELDS},
        "python_session_digest": session["digest"],
        "verified_by_python_replay": True,
    }
    files = {
        "godot/project.godot": _PROJECT.replace(
            "Skeleton Original Adventure", "Skeleton Original Dialogue World"
        ).encode("utf-8"),
        "godot/export_presets.cfg": _EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn": _SCENE.encode("utf-8"),
        "godot/scripts/main.gd": GODOT_DIALOGUE.lstrip().encode("utf-8"),
        "godot/game.json": _json(game),
        "godot/proof.json": _json(proof),
        "README.md": (
            "# Independent Original Dialogue Godot 4 Game\n\n"
            "Authored real social simulation with local persons, testimony, "
            "support, challenge, finite influence, source corroboration and "
            "optional earned consensus.\n"
            "Arrows: move. 1–8 speak to source speakers, S/C support/challenge "
            "source Voice 1, A compare topic zero at archive, G claim, E retire.\n"
            "Native proof: godot --headless --path godot -- --verify-dialogue\n"
            "The executable runs independent GDScript transitions and compares "
            "complete game state to a reference Python replay expectation.\n"
            "This package has not been certified for store, console or hardware.\n"
        ).encode("utf-8"),
    }
    manifest = {
        "schema": "skeleton.game_builder.advanced_native_package.v1",
        "native_editor": "dialogue",
        "native_adapter": "godot4_independent_firsthand_dialogue",
        "advanced_floor": True,
        "source_session_digest": session["digest"],
        "authored_scene_digest": scene["digest"],
        "files": {path: sha256(raw).hexdigest() for path, raw in sorted(files.items())},
        "godot_executed": False, "native_hardware_certified": False,
        "publish_approved": False,
    }
    files["release.json"] = _json(manifest)
    return NativeAdvancedGamePackage(files, manifest)


__all__ = [
    "SCHEMA", "PROOF_SCHEMA", "PROOF_FIELDS", "GODOT_DIALOGUE",
    "render_dialogue_godot_package",
]
