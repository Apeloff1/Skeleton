"""Finite deterministic original-market game engine.

Trades spend actual credits and move goods between player cargo and authored
markets. Regional production depletes ore-like reserves, consumption removes
stock, price movement reacts to scarcity, and debt cannot be invented away.
This is a replayable local reference simulator, not a real trading exchange.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = (
    "inspect", "wait", "survey", "buy:1", "buy:5", "sell:1", "sell:5",
    "produce", "invest", "borrow", "repay", "checkpoint", "retire",
) + tuple("travel:" + str(i) for i in range(100))
MAX_TURNS = 128


class EconomyActionError(ValueError):
    """Invalid market source, unaffordable trade, or unearned milestone."""


def _int(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise EconomyActionError("invalid original economy " + name)
    return value


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    nodes = []
    for i in range(config["market_nodes"]):
        stock = max(1, config["goods"] // 2 + (seed + i * 7) % max(1, config["goods"] // 2 + 1))
        nodes.append({
            "id": i,
            "stock": stock,
            "capacity": max(stock + 1, config["goods"] * 2),
            "reserves": config["goods"] * 4 + (seed + i) % 13,
            "output": 1 + (seed + i) % 4,
            "demand": 1 + (seed + i * 3) % 3,
            "price": 5 + (seed * 3 + i * 11) % 19,
            "treasury": 200,
        })
    return {"title": "Original Market Network " + str(seed % 1000),
            "nodes": nodes, "home": 0}


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {"title", "nodes", "home"}:
        raise EconomyActionError("exact market map fields required")
    if type(layout["title"]) is not str or not 1 <= len(layout["title"]) <= 100:
        raise EconomyActionError("invalid market title")
    if type(layout["nodes"]) is not list or len(layout["nodes"]) != config["market_nodes"]:
        raise EconomyActionError("all configured markets must have bounded original stock")
    _int(layout["home"], 0, len(layout["nodes"]) - 1, "home")
    keys = {"id", "stock", "capacity", "reserves", "output", "demand", "price", "treasury"}
    result = []
    for i, raw in enumerate(layout["nodes"]):
        if type(raw) is not dict or set(raw) != keys:
            raise EconomyActionError("exact non-executable market node required")
        node = dict(raw)
        _int(node["id"], i, i, "node_id")
        _int(node["capacity"], 1, max(2, config["goods"] * 10), "capacity")
        _int(node["stock"], 0, node["capacity"], "stock")
        _int(node["reserves"], 0, config["goods"] * 100, "reserves")
        _int(node["output"], 0, 100, "output")
        _int(node["demand"], 0, 100, "demand")
        _int(node["price"], 1, 1000, "price")
        _int(node["treasury"], 0, 1000000, "treasury")
        result.append(node)
    return {"title": layout["title"], "nodes": result, "home": layout["home"]}


def start(config, seed):
    level = normalize_layout(config, default_layout(config, seed))
    return {
        "title": level["title"], "nodes": deepcopy(level["nodes"]),
        "home": level["home"], "market": level["home"], "visited": [level["home"]],
        "credits": 200, "cargo": 0, "cargo_limit": max(5, config["goods"]),
        "debt": 0, "bank_cash": 10000, "bank_claims": 0,
        "tax_collected": 0, "trade_volume": 0, "trade_count": 0,
        "total_produced": 0, "total_consumed": 0, "total_spoiled": 0,
        "investments": 0, "journeys": 0, "fuel_spent": 0,
        "tick": 0, "net_worth": 200, "highest_net_worth": 200,
        "earned_checkpoint": False, "retired": False, "finished": False,
        "failed": False, "events": [], "journal": [],
    }


def apply_scene(state, config, layout):
    if state["tick"] != 0:
        raise EconomyActionError("market source cannot replace an active session")
    level = normalize_layout(config, layout)
    state["title"] = level["title"]
    state["nodes"] = deepcopy(level["nodes"])
    state["home"] = state["market"] = level["home"]
    state["visited"] = [level["home"]]


def _neighbors(source, target, length):
    # Roads connect adjacent towns with cyclic travel, never teleportation.
    return length > 1 and (target - source) % length in (1, length - 1)


def _market_update(state, config, events):
    for node in state["nodes"]:
        demand = node["demand"]
        consumed = min(node["stock"], demand)
        node["stock"] -= consumed
        state["total_consumed"] += consumed
        if consumed:
            events.append("real_household_consumption")
        output = min(node["output"], node["capacity"] - node["stock"])
        if config["finite_inventory"]:
            output = min(output, node["reserves"])
            node["reserves"] -= output
        node["stock"] += output
        state["total_produced"] += output
        if output:
            events.append("bounded_market_production")
        gap = demand - consumed
        surplus = max(0, node["stock"] - node["capacity"] // 2)
        change = (gap * config["price_elasticity"]) - (
            surplus * config["price_elasticity"] // max(1, config["goods"]))
        node["price"] = max(1, min(1000, node["price"] + change))


def _net_worth(state):
    price = state["nodes"][state["market"]]["price"]
    return state["credits"] + state["cargo"] * price - state["debt"]


def step(state, config, action):
    if action not in ACTIONS:
        raise EconomyActionError("unrecognized original market order")
    if state["finished"] or state["failed"]:
        raise EconomyActionError("terminal economy session cannot advance")
    events = []
    nodes = state["nodes"]
    node = nodes[state["market"]]
    if action.startswith("travel:"):
        dest = int(action.split(":")[1])
        if dest >= len(nodes) or not _neighbors(state["market"], dest, len(nodes)):
            raise EconomyActionError("trading routes require adjacent actual markets")
        cost = 2 + state["cargo"] // max(1, state["cargo_limit"] // 4)
        if state["credits"] < cost:
            raise EconomyActionError("insufficient freight credits")
        state["credits"] -= cost
        node["treasury"] += cost
        state["fuel_spent"] += cost
        state["market"] = dest
        state["journeys"] += 1
        if dest not in state["visited"]:
            state["visited"].append(dest)
            state["visited"].sort()
        events.append("paid_intermarket_carriage")
    elif action.startswith("buy:"):
        quantity = int(action.split(":")[1])
        cost = quantity * node["price"]
        levy = (cost * config["trade_tax"] + 99) // 100
        if node["stock"] < quantity or state["cargo"] + quantity > state["cargo_limit"]:
            raise EconomyActionError("finite physical market stock or cargo insufficient")
        if state["credits"] < cost + levy:
            raise EconomyActionError("market purchase cannot spend nonexistent credits")
        state["credits"] -= cost + levy
        state["cargo"] += quantity
        node["stock"] -= quantity
        node["treasury"] += cost + levy
        state["tax_collected"] += levy
        state["trade_volume"] += quantity
        state["trade_count"] += 1
        events.append("physical_goods_bought_with_actual_credits")
    elif action.startswith("sell:"):
        quantity = int(action.split(":")[1])
        gross = quantity * node["price"]
        levy = (gross * config["trade_tax"] + 99) // 100
        proceeds = gross - levy
        if state["cargo"] < quantity:
            raise EconomyActionError("cannot sell goods outside actual cargo")
        if node["stock"] + quantity > node["capacity"]:
            raise EconomyActionError("market capacity does not accept infinite goods")
        if node["treasury"] < proceeds:
            raise EconomyActionError("buyer market lacks real purchasing cash")
        state["cargo"] -= quantity
        state["credits"] += proceeds
        node["stock"] += quantity
        node["treasury"] -= proceeds
        state["tax_collected"] += levy
        state["trade_volume"] += quantity
        state["trade_count"] += 1
        events.append("physical_goods_sold_to_funded_market")
    elif action == "produce":
        # Cottage production transforms credits into one unit, using reserves.
        if state["credits"] < 3 or state["cargo"] >= state["cargo_limit"]:
            raise EconomyActionError("crafting requires physical capacity and credits")
        if node["reserves"] <= 0:
            raise EconomyActionError("actual production resource exhausted")
        state["credits"] -= 3
        node["treasury"] += 3
        node["reserves"] -= 1
        state["cargo"] += 1
        state["total_produced"] += 1
        events.append("paid_cottage_production")
    elif action == "invest":
        if state["credits"] < 30 or node["output"] >= 100 or (
            node["capacity"] + 5 > config["goods"] * 10):
            raise EconomyActionError("bounded investment budget exceeded")
        state["credits"] -= 30
        node["treasury"] += 30
        node["output"] += 1
        node["capacity"] += 5
        state["investments"] += 1
        events.append("paid_original_workshop_expansion")
    elif action == "borrow":
        if state["bank_cash"] < 25 or state["debt"] + 25 > 200:
            raise EconomyActionError("finite lending capacity exhausted")
        state["bank_cash"] -= 25
        state["bank_claims"] += 25
        state["credits"] += 25
        state["debt"] += 25
        events.append("funded_debt_issued")
    elif action == "repay":
        payment = min(25, state["debt"])
        if payment == 0 or state["credits"] < payment:
            raise EconomyActionError("repayment requires outstanding debt and cash")
        state["credits"] -= payment
        state["debt"] -= payment
        state["bank_cash"] += payment
        state["bank_claims"] -= payment
        events.append("actual_debt_repaid")
    elif action == "checkpoint":
        if not state["earned_checkpoint"]:
            raise EconomyActionError("cannot claim trading success without real proof")
        events.append("earned_trade_network_checkpoint")
    elif action == "retire":
        if not state["earned_checkpoint"] or state["market"] != state["home"] or state["debt"]:
            raise EconomyActionError("ending requires earned market, repaid debt and return home")
        state["finished"] = state["retired"] = True
        events.append("voluntary_original_trader_retirement")
    elif action == "survey":
        events.append("regional_prices_and_inventory_observed")
    elif action == "inspect":
        events.append("verified_original_market_inspection")
    else:
        events.append("market_time_advanced")

    state["tick"] += 1
    if not state["finished"]:
        _market_update(state, config, events)
    state["net_worth"] = _net_worth(state)
    state["highest_net_worth"] = max(state["highest_net_worth"], state["net_worth"])
    if (state["trade_volume"] >= max(4, min(20, len(nodes) * 2))
            and len(state["visited"]) >= min(3, len(nodes))
            and state["net_worth"] >= 200 and not state["earned_checkpoint"]):
        state["earned_checkpoint"] = True
        events.append("original_trading_milestone_earned")
    if state["tick"] >= MAX_TURNS and not state["finished"]:
        state["failed"] = True
        events.append("market_session_turn_budget_exhausted")
    state["journal"].append({
        "tick": state["tick"], "action": action, "market": state["market"],
        "credits": state["credits"], "cargo": state["cargo"],
        "debt": state["debt"], "net_worth": state["net_worth"],
    })
    state["events"] = events
    return events


__all__ = ["ACTIONS", "EconomyActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
