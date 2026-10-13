"""Source-bound original Godot 4 market game with independent economic rules.

The generated GDScript executes its own market transitions and compares the
entire resulting economic state with a replay-proved Python session. It does
not replay precomputed state snapshots or silently certify native hardware.
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

SCHEMA = "skeleton.game_builder.godot_advanced_economy.v1"
PROOF_SCHEMA = "skeleton.game_builder.godot_advanced_economy_proof.v1"
# All authoritative fields, not merely a victory bit or selected balances.
PROOF_FIELDS = (
    "tick", "title", "position", "focus", "markets", "active_goods",
    "active_market_count", "unmodeled_good_families", "unmodeled_market_nodes",
    "cash", "cargo", "cargo_lots", "energy", "harvested", "manufactured",
    "transfers", "imports_sold", "market_sales", "buy_count",
    "household_consumed", "household_spend", "tax_receipts", "transport_fees",
    "audited", "checkpoint", "retired", "finished", "failed", "events",
    "trade_goal",
)

GODOT_ECONOMY = r'''
extends Control
## Independent original market simulation: no Python process or state injection.
const VERIFY_FLAG: String = "--verify-economy"
const GOODS: Array = ["food", "ore", "tools", "cloth", "timber", "medicine", "ceramics", "fuel"]
const MAX_ACTIONS: int = 128
var source: Dictionary = {}
var rules: Dictionary = {}
var layout: Dictionary = {}
var state: Dictionary = {}
var command_history: Array = []
var playable: bool = false
var notice: String = "Explore original markets, produce and move real cargo"


func _fail(message: String) -> void:
    push_error("NATIVE_ADVANCED_ECONOMY_ERROR: " + message)
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        get_tree().quit(1)


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    var raw: String = FileAccess.get_file_as_string("res://game.json")
    if raw.is_empty() or raw.length() > 100000:
        _fail("missing or oversized authored market source")
        return
    var parsed: Variant = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        _fail("invalid market-source JSON")
        return
    source = parsed
    if source.get("schema") != "skeleton.game_builder.godot_advanced_economy.v1":
        _fail("unrecognized native economy schema")
        return
    rules = source["settings"]
    layout = source["scene"]["layout"]
    if layout["markets"].size() < 2 or layout["markets"].size() > 16:
        _fail("unbounded or absent physical markets")
        return
    if mini(8, mini(int(rules["goods"]), int(rules["active_goods_budget"]))) < 3:
        _fail("no physically manufacturable source goods")
        return
    _reset()
    playable = true
    get_window().title = "Skeleton Original Trading Economy"
    if VERIFY_FLAG in OS.get_cmdline_user_args():
        _verify()


func _reset() -> void:
    var count: int = mini(8, mini(int(rules["goods"]), int(rules["active_goods_budget"])))
    var nodes: int = mini(int(rules["market_nodes"]), int(rules["active_market_budget"]))
    var goods: Array = []
    var cargo: Array = []
    var lots: Array = []
    for j in range(count):
        goods.append(GOODS[j])
        cargo.append(0)
        lots.append([])
    var markets: Array = []
    for node in layout["markets"]:
        var market: Dictionary = node.duplicate(true)
        var prices: Array = []
        for j in range(count):
            prices.append(mini(int(rules["price_ceiling"]),
                int(rules["base_price"]) + j * 2 + int(node["id"])))
        market["prices"] = prices
        market["sales"] = 0
        market["household_consumed"] = 0
        market["production"] = 0
        markets.append(market)
    state = {
        "tick": 0, "title": str(layout["title"]), "position": 0, "focus": 0,
        "markets": markets, "active_goods": goods,
        "active_market_count": nodes,
        "unmodeled_good_families": int(rules["goods"]) - count,
        "unmodeled_market_nodes": int(rules["market_nodes"]) - nodes,
        "cash": int(rules["starting_cash"]), "cargo": cargo, "cargo_lots": lots,
        "energy": int(rules["player_energy"]), "harvested": 0, "manufactured": 0,
        "transfers": 0, "imports_sold": 0, "market_sales": 0, "buy_count": 0,
        "household_consumed": 0, "household_spend": 0, "tax_receipts": 0,
        "transport_fees": 0, "audited": [], "checkpoint": false,
        "retired": false, "finished": false, "failed": false, "events": [],
        "trade_goal": int(layout["trade_goal"]),
    }
    command_history = []
    notice = "A audit · M make tools · H harvest · B buy · S sell · arrows travel"
    queue_redraw()


func _cost(amount: int) -> bool:
    if int(state["cash"]) < amount:
        notice = "Insufficient finite player cash"
        return false
    state["cash"] = int(state["cash"]) - amount
    return true


func _market() -> Dictionary:
    return state["markets"][int(state["position"])]


func _ask(node: Dictionary, good: int) -> int:
    return int(node["prices"][good]) + int(rules["spread"])


func _bid(node: Dictionary, good: int) -> int:
    return maxi(1, int(node["prices"][good]) - 1)


func _demand() -> void:
    if int(state["tick"]) % int(rules["demand_period"]) != 0:
        return
    for node in state["markets"]:
        var good: int = (int(int(state["tick"]) / int(rules["demand_period"])) +
            int(node["id"])) % state["active_goods"].size()
        var price: int = _ask(node, good)
        if int(node["inventory"][good]) > 0 and int(node["household_cash"]) >= price:
            node["inventory"][good] = int(node["inventory"][good]) - 1
            node["household_cash"] = int(node["household_cash"]) - price
            node["treasury"] = int(node["treasury"]) + price
            node["household_consumed"] = int(node["household_consumed"]) + 1
            state["household_consumed"] = int(state["household_consumed"]) + 1
            state["household_spend"] = int(state["household_spend"]) + price
        var change: int = 0
        if int(node["inventory"][good]) < int(rules["target_stock"]):
            change = int(rules["price_elasticity"])
        elif int(node["inventory"][good]) > int(rules["target_stock"]):
            change = -int(rules["price_elasticity"])
        node["prices"][good] = clampi(int(node["prices"][good]) + change,
            int(rules["price_floor"]), int(rules["price_ceiling"]))


func _step(action: String) -> bool:
    if bool(state["finished"]) or bool(state["failed"]) or command_history.size() >= MAX_ACTIONS:
        notice = "Campaign terminal or bounded replay limit exceeded"
        return false
    var events: Array = []
    var node: Dictionary = _market()
    var good: int = int(state["focus"])
    if action.begins_with("focus:"):
        var token: String = action.get_slice(":", 1)
        if not token.is_valid_int() or str(int(token)) != token or int(token) > 15:
            notice = "Only exact registered source-good tokens may be selected"
            return false
        var who: int = int(token)
        if who < 0 or who >= state["active_goods"].size():
            notice = "Commodity is outside detailed original trade budget"
            return false
        state["focus"] = who
        events.append("selected_source_good")
    elif action.begins_with("travel:"):
        var route: String = action.get_slice(":", 1)
        if not route.is_valid_int() or str(int(route)) != route or int(route) > 15:
            notice = "Only exact registered physical route identifiers permitted"
            return false
        var to: int = int(route)
        if to < 0 or to >= state["markets"].size() or absi(to-int(state["position"])) != 1:
            notice = "Only adjacent physical market routes are permitted"
            return false
        if not _cost(int(rules["transport_cost"])):
            return false
        node["treasury"] = int(node["treasury"]) + int(rules["transport_cost"])
        state["transport_fees"] = int(state["transport_fees"]) + int(rules["transport_cost"])
        var transported: int = 0
        for units in state["cargo"]:
            transported += int(units)
        if transported > 0:
            state["transfers"] = int(state["transfers"]) + transported
            events.append("physical_cargo_transported")
        state["position"] = to
        events.append("adjacent_source_market_arrival")
    elif action == "buy":
        if int(node["inventory"][good]) <= 0:
            notice = "Source market has no such goods"
            return false
        var carried: int = 0
        for units in state["cargo"]:
            carried += int(units)
        if carried >= int(rules["cargo_capacity"]):
            notice = "Freight capacity exhausted"
            return false
        var price: int = _ask(node, good)
        var tax: int = int(price * int(rules["trade_tax"]) / 100)
        if not _cost(price + tax):
            return false
        node["inventory"][good] = int(node["inventory"][good]) - 1
        node["treasury"] = int(node["treasury"]) + price + tax
        state["tax_receipts"] = int(state["tax_receipts"]) + tax
        state["cargo"][good] = int(state["cargo"][good]) + 1
        state["cargo_lots"][good].append(int(node["id"]))
        state["buy_count"] = int(state["buy_count"]) + 1
        events.append("paid_finite_market_purchase")
    elif action == "sell":
        if int(state["cargo"][good]) <= 0:
            notice = "No real cargo exists for sale"
            return false
        if int(node["inventory"][good]) >= int(rules["warehouse_capacity"]):
            notice = "Market warehouse full"
            return false
        var bid: int = _bid(node, good)
        if int(node["treasury"]) < bid:
            notice = "Local source market lacks bid liquidity"
            return false
        node["inventory"][good] = int(node["inventory"][good]) + 1
        node["treasury"] = int(node["treasury"]) - bid
        state["cash"] = int(state["cash"]) + bid
        state["cargo"][good] = int(state["cargo"][good]) - 1
        var origin: int = int(state["cargo_lots"][good].pop_front())
        if origin != int(node["id"]):
            state["imports_sold"] = int(state["imports_sold"]) + 1
            events.append("verified_cross_market_delivery")
        state["market_sales"] = int(state["market_sales"]) + 1
        node["sales"] = int(node["sales"]) + 1
        events.append("market_paid_real_cargo_bid")
    elif action == "harvest":
        if int(state["energy"]) < int(rules["labor_cost"]):
            notice = "Insufficient finite work energy"
            return false
        if int(node["reserves"]) <= 0 or int(node["inventory"][0]) >= int(rules["warehouse_capacity"]):
            notice = "Finite regional harvest depleted"
            return false
        var quantity: int = mini(int(rules["harvest_yield"]),
            mini(int(node["reserves"]), int(rules["warehouse_capacity"])-int(node["inventory"][0])))
        node["reserves"] = int(node["reserves"]) - quantity
        node["inventory"][0] = int(node["inventory"][0]) + quantity
        state["energy"] = int(state["energy"]) - int(rules["labor_cost"])
        state["harvested"] = int(state["harvested"]) + quantity
        node["production"] = int(node["production"]) + quantity
        events.append("finite_regional_harvest")
    elif action == "manufacture":
        if state["active_goods"].size() < 3 or int(state["energy"]) < int(rules["labor_cost"]):
            notice = "No manufacturing capacity or player energy"
            return false
        if int(node["inventory"][1]) < int(rules["ore_per_tool"]):
            notice = "No actual ore input stock"
            return false
        if int(node["inventory"][2]) >= int(rules["warehouse_capacity"]):
            notice = "Finished goods warehouse is full"
            return false
        node["inventory"][1] = int(node["inventory"][1]) - int(rules["ore_per_tool"])
        node["inventory"][2] = int(node["inventory"][2]) + 1
        state["energy"] = int(state["energy"]) - int(rules["labor_cost"])
        state["manufactured"] = int(state["manufactured"]) + 1
        node["production"] = int(node["production"]) + 1
        events.append("material_conserving_original_manufacture")
    elif action == "audit":
        if int(node["id"]) in state["audited"]:
            notice = "Cannot duplicate physical settlement audit"
            return false
        state["audited"].append(int(node["id"]))
        state["audited"].sort()
        events.append("source_grounded_distinct_market_audit")
    elif action == "rest":
        if int(state["energy"]) == int(rules["player_energy"]):
            notice = "No actual fatigue to recover"
            return false
        if not _cost(int(rules["rest_cost"])):
            return false
        node["treasury"] = int(node["treasury"]) + int(rules["rest_cost"])
        state["energy"] = mini(int(rules["player_energy"]),
            int(state["energy"]) + int(rules["rest_gain"]))
        events.append("paid_finite_market_rest")
    elif action == "relief":
        if int(node["household_cash"]) >= int(rules["household_cash"]):
            notice = "Household already has full source allowance"
            return false
        var amount: int = mini(int(rules["relief_grant"]),
            mini(int(node["treasury"]),int(rules["household_cash"])-int(node["household_cash"])))
        if amount <= 0:
            notice = "Treasury cannot fund relief"
            return false
        node["treasury"] = int(node["treasury"]) - amount
        node["household_cash"] = int(node["household_cash"]) + amount
        events.append("finite_treasury_to_household_transfer")
    elif action == "checkpoint":
        if bool(state["checkpoint"]) or state["audited"].size() < 2 or (
            int(state["manufactured"]) < 1 or int(state["imports_sold"]) < int(state["trade_goal"])
        ):
            notice = "Requires actual manufacturing, imports and two audits"
            return false
        state["checkpoint"] = true
        events.append("earned_nonterminal_trade_cooperation")
    elif action == "retire":
        if not bool(state["checkpoint"]):
            notice = "Retirement requires earned milestone"
            return false
        state["retired"] = true
        state["finished"] = true
        events.append("voluntary_source_bound_trade_retirement")
    elif action == "wait" or action == "inspect":
        events.append("market_observation" if action == "inspect" else "bounded_market_turn")
    else:
        notice = "Unsupported authored economic command"
        return false
    state["tick"] = int(state["tick"]) + 1
    _demand()
    state["events"] = events
    command_history.append(action)
    notice = "Executed " + action + " · source-bounded market turn"
    queue_redraw()
    return true


func _parity_value(value: Variant) -> Variant:
    # Godot JSON numbers are floats even where Python source has an integer.
    # Normalize ONLY finite integral JSON numbers to integers recursively.
    # This does not round fractional forgery, convert strings, or equate bools.
    if typeof(value) == TYPE_FLOAT:
        if not is_finite(value) or floor(value) != value or absf(value) > 9007199254740991.0:
            return "invalid_nonintegral_or_unsafe_number"
        return int(value)
    if typeof(value) == TYPE_ARRAY:
        var normalized: Array = []
        for entry in value:
            normalized.append(_parity_value(entry))
        return normalized
    if typeof(value) == TYPE_DICTIONARY:
        var normalized: Dictionary = {}
        for name in value:
            normalized[name] = _parity_value(value[name])
        return normalized
    return value


func _verify() -> void:
    var text: String = FileAccess.get_file_as_string("res://proof.json")
    if text.is_empty() or text.length() > 200000:
        _fail("missing or oversized source replay proof")
        return
    var decoded: Variant = JSON.parse_string(text)
    if typeof(decoded) != TYPE_DICTIONARY:
        _fail("invalid verified Python proof")
        return
    var proof: Dictionary = decoded
    if proof.get("schema") != "skeleton.game_builder.godot_advanced_economy_proof.v1":
        _fail("unknown source proof schema")
        return
    if proof.get("scene_digest") != source["scene"]["digest"] or (
        proof.get("settings_digest") != source.get("settings_digest")
    ) or typeof(proof.get("verified_by_python_replay")) != TYPE_BOOL or not proof["verified_by_python_replay"]:

        _fail("source and proof configuration identity mismatch")
        return
    var history: Variant = proof.get("actions")
    var expected_data: Variant = proof.get("expected")
    if typeof(history) != TYPE_ARRAY or typeof(expected_data) != TYPE_DICTIONARY:
        _fail("native proof must include typed actions and state")
        return
    var actions: Array = history
    if actions.size() > MAX_ACTIONS:
        _fail("source action replay budget exceeded")
        return
    for action in actions:
        if typeof(action) != TYPE_STRING or not _step(str(action)):
            _fail("source replay contains illegal economic action")
            return
    var expected: Dictionary = proof.get("expected", {})
    for key in expected.keys():
        if not state.has(key):
            _fail("proof requests an unknown source market variable")
            return
        if _parity_value(state[key]) != _parity_value(expected[key]):
            _fail("independent economic divergence: " + str(key) +
                " actual=" + JSON.stringify(state[key]) +
                " expected=" + JSON.stringify(expected[key]))
            return
    if expected.size() != state.size():
        _fail("incomplete source economic parity projection")
        return
    print("NATIVE_ADVANCED_ECONOMY_OK")
    get_tree().quit(0)


func _unhandled_key_input(event: InputEvent) -> void:
    if not playable or not event is InputEventKey or not event.pressed or event.echo:
        return
    var action: String = ""
    match event.keycode:
        KEY_0: action = "focus:0"
        KEY_1: action = "focus:1"
        KEY_2: action = "focus:2"
        KEY_3: action = "focus:3"
        KEY_4: action = "focus:4"
        KEY_5: action = "focus:5"
        KEY_6: action = "focus:6"
        KEY_7: action = "focus:7"
        KEY_LEFT: action = "travel:" + str(int(state["position"]) - 1)
        KEY_RIGHT: action = "travel:" + str(int(state["position"]) + 1)
        KEY_M: action = "manufacture"
        KEY_H: action = "harvest"
        KEY_B: action = "buy"
        KEY_S: action = "sell"
        KEY_A: action = "audit"
        KEY_C: action = "checkpoint"
        KEY_T: action = "retire"
        KEY_L: action = "relief"
        KEY_E: action = "rest"
        KEY_W: action = "wait"
        KEY_I: action = "inspect"
        KEY_R:
            _reset()
            return
    if not action.is_empty():
        _step(action)


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO,size), Color("#112130"))
    if not playable:
        return
    _write(Vector2(16,32),"ORIGINAL ECONOMY  /  INDEPENDENT GODOT MARKET",
        20,Color("#ddf2ee"))
    _write(Vector2(16,57),str(state["title"])+"  |  Tick "+str(state["tick"]),
        13,Color("#c9e1bc"))
    var market_count: int = state["markets"].size()
    for i in range(market_count):
        var node: Dictionary = state["markets"][i]
        var x: float = 18.0 + float(i%4)*165.0
        var y: float = 82.0 + float(int(i/4))*84.0
        var selected: bool = i == int(state["position"])
        draw_rect(Rect2(Vector2(x,y),Vector2(157,72)),
            Color("#3b715c") if selected else Color("#344e61"),true)
        if selected:
            draw_rect(Rect2(Vector2(x+2,y+2),Vector2(153,68)),
                Color("#f3dfa0"),false,2.0)
        _write(Vector2(x+9,y+20),str(i)+" · "+str(node["kind"]),14,Color.WHITE)
        _write(Vector2(x+9,y+40),"Stock "+str(node["inventory"][int(state["focus"])])+
            " | Ask "+str(_ask(node,int(state["focus"]))),12,Color("#d5ecdf"))
        _write(Vector2(x+9,y+57),"Treasury "+str(node["treasury"]),11,Color("#ead3aa"))
    _write(Vector2(17,292),"Focused good: "+str(state["active_goods"][int(state["focus"])]),
        15,Color("#eddd9e"))
    _write(Vector2(17,319),"Player cash "+str(state["cash"])+" | Cargo "+
        str(state["cargo"])+" | Work energy "+str(state["energy"]),
        13,Color.WHITE)
    _write(Vector2(17,346),"Crafted "+str(state["manufactured"])+" | Imports "+
        str(state["imports_sold"])+" | Audits "+str(state["audited"]) +
        " | Household sales "+str(state["household_consumed"]),12,Color.WHITE)
    _write(Vector2(17,378),notice,12,Color("#bcead5"))
    _write(Vector2(17,409),"A audit  M manufacture  H harvest  B buy  S sell  Left/Right market",
        12,Color("#d1dcea"))
    _write(Vector2(17,435),"0–7 focus good  L relief  E rest  C milestone  T retire  R restart",
        12,Color("#d1dcea"))
    _write(Vector2(17,466),
        "Earned nonterminal trade milestone" if bool(state["checkpoint"]) else
        "Produce tools, sell imports and audit distinct markets",
        13,Color("#d9dfa1"))


func _write(at: Vector2, label: String, font_size: int, ink: Color) -> void:
    draw_string(ThemeDB.fallback_font,at,label,
        HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
'''


def render_economy_godot_package(
    session: dict, settings: dict | None = None, *, authorized: bool
) -> NativeAdvancedGamePackage:
    if not authorized:
        raise PermissionError("original native economy export requires trusted local operator")
    if type(session) is not dict or session.get("editor") != "economy":
        raise AdvancedGodotExportError("original verified Economy source session required")
    config = make_editor_document("economy", settings)
    verify_advanced_session(session, config["settings"])
    scene = (
        validate_advanced_scene(session["scene"], config["settings"])
        if session.get("scene") is not None
        else make_advanced_scene("economy", config["settings"], seed=session["seed"])
    )
    # A stateless session without an explicit authored scene must first be
    # rebound to the exact default scene and independently replayed again.
    if session.get("scene") is None:
        session = run_advanced_session(
            "economy", config["settings"], session["actions"],
            seed=session["seed"], scene=scene,
        )
    game = {
        "schema": SCHEMA, "editor": "economy", "quality_floor": "advanced",
        "settings": config["settings"], "settings_digest": config["digest"],
        "scene": scene, "native_parity_verified": False,
        "external_assets_executed": False,
    }
    proof = {
        "schema": PROOF_SCHEMA, "scene_digest": scene["digest"],
        "settings_digest": config["digest"], "actions": list(session["actions"]),
        "expected": {key: session["state"][key] for key in PROOF_FIELDS},
        "python_session_digest": session["digest"],
        "verified_by_python_replay": True,
    }
    files = {
        "godot/project.godot": _PROJECT.replace(
            "Skeleton Original Adventure", "Skeleton Original Advanced Economy"
        ).encode("utf-8"),
        "godot/export_presets.cfg": _EXPORT_PRESETS.encode("utf-8"),
        "godot/scenes/main.tscn": _SCENE.encode("utf-8"),
        "godot/scripts/main.gd": GODOT_ECONOMY.lstrip().encode("utf-8"),
        "godot/game.json": _json(game),
        "godot/proof.json": _json(proof),
        "README.md": (
            "# Original Advanced Godot Trading Economy\n\n"
            "Independently executing Godot 4 source-bound market game. "
            "Manufacture, finite supply, money, household demand, paid bids, "
            "goods, real transport and original market checkpoints.\n"
            "Keyboard: A audit, M manufacture, H harvest, B buy, S sell, "
            "arrows move between markets, 0–7 select good, C claim trade "
            "milestone, T retire, R restart.\n"
            "Native verification: godot --headless --path godot -- --verify-economy\n"
            "A success line is printed only when full independent native market "
            "state matches the replay-verified Python source projection.\n"
            "The package is not hardware certified or authorized for publication.\n"
        ).encode("utf-8"),
    }
    manifest = {
        "schema": "skeleton.game_builder.advanced_native_package.v1",
        "native_editor": "economy",
        "native_adapter": "godot4_independent_market_economy",
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
    "SCHEMA", "PROOF_SCHEMA", "PROOF_FIELDS", "GODOT_ECONOMY",
    "render_economy_godot_package",
]
