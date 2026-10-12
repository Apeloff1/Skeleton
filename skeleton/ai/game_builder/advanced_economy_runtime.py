"""Original, finite multi-market economy with conservation and replay semantics.

Markets have independent prices, stock, household cash and treasuries. Actors
transport real cargo, convert finite material, audit distinct settlements and
can earn a nonterminal trade milestone. This is a reference simulation, not an
empirical economic forecast or an executable commercial market integration.
"""
from __future__ import annotations

KINDS = ("food", "ore", "tools", "cloth", "timber", "medicine", "ceramics", "fuel")
ACTIONS = (
    "wait", "inspect", "harvest", "manufacture", "buy", "sell", "audit",
    "checkpoint", "retire", "rest", "relief",
) + tuple(f"travel:{n}" for n in range(16)) + tuple(
    f"focus:{n}" for n in range(16)
)


class EconomyActionError(ValueError):
    """Invalid source market, impossible transaction or forged milestone."""


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise EconomyActionError("invalid original economy " + label)
    return value


def _count(config):
    return min(config["goods"], config["active_goods_budget"], len(KINDS))


def _nodes(config):
    return min(config["market_nodes"], config["active_market_budget"])


def default_layout(config, seed):
    _integer(seed, 0, 2**31 - 1, "seed")
    goods, count = _count(config), _nodes(config)
    return {
        "title": "Original Trade Federation " + str(seed % 1000),
        "origin": 0,
        "markets": [
            {
                "id": i, "site": [i % 4, i // 4],
                "kind": ("port", "village", "city", "industrial")[i % 4],
                "inventory": [config["starting_stock"] + (i + j + seed) % 3
                              for j in range(goods)],
                "reserves": config["resource_reserve"],
                "household_cash": config["household_cash"],
                "treasury": config["market_treasury"],
            }
            for i in range(count)
        ],
        "trade_goal": 1, "nonterminal": True,
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "origin", "markets", "trade_goal", "nonterminal"
    }:
        raise EconomyActionError("exact original market scene structure required")
    title = layout["title"]
    if type(title) is not str or not 3 <= len(title) <= 64 or not all(
        c.isalnum() or c in " _-" for c in title
    ):
        raise EconomyActionError("unsafe original market title")
    if type(layout["origin"]) is not int or layout["origin"] != 0:
        raise EconomyActionError("market origin must be source anchored")
    if layout["nonterminal"] is not True:
        raise EconomyActionError("trade checkpoint must allow ongoing play")
    _integer(layout["trade_goal"], 1, 16, "delivery goal")
    if type(layout["markets"]) is not list or len(layout["markets"]) != _nodes(config):
        raise EconomyActionError("market locations must match active source budget")
    markets = []
    for i, node in enumerate(layout["markets"]):
        if type(node) is not dict or set(node) != {
            "id", "site", "kind", "inventory", "reserves", "household_cash", "treasury"
        }:
            raise EconomyActionError("market needs exact stock and treasury custody")
        if type(node["id"]) is not int or node["id"] != i:
            raise EconomyActionError("market identities cannot be forged or swapped")
        if type(node["site"]) is not list or node["site"] != [i % 4, i // 4]:
            raise EconomyActionError("market locations cannot teleport")
        kind = ("port", "village", "city", "industrial")[i % 4]
        if node["kind"] != kind:
            raise EconomyActionError("market role cannot be silently rewritten")
        stock = node["inventory"]
        if type(stock) is not list or len(stock) != _count(config):
            raise EconomyActionError("market stock must have exact source goods")
        entries = [_integer(v, 0, config["warehouse_capacity"], "stock")
                   for v in stock]
        markets.append({
            "id": i, "site": [i % 4, i // 4], "kind": kind,
            "inventory": entries,
            "reserves": _integer(node["reserves"], 0, config["resource_reserve"],
                                 "finite reserves"),
            "household_cash": _integer(node["household_cash"], 0,
                                       config["household_cash"], "household cash"),
            "treasury": _integer(node["treasury"], 0, config["market_treasury"],
                                 "treasury"),
        })
    return {
        "title": title, "origin": 0, "markets": markets,
        "trade_goal": layout["trade_goal"], "nonterminal": True,
    }


def _initial_market(node, config):
    return {
        **node, "prices": [
            min(config["price_ceiling"], config["base_price"] + j * 2 + node["id"])
            for j in range(_count(config))
        ],
        "sales": 0, "household_consumed": 0, "production": 0,
    }


def start(config, seed):
    scene = normalize_layout(config, default_layout(config, seed))
    count = _count(config)
    # Out-of-focus markets and goods are explicit aggregate cohorts, not fake
    # individually simulated settlements or unbounded actor allocations.
    other_markets = config["market_nodes"] - _nodes(config)
    other_goods = config["goods"] - count
    return {
        "tick": 0, "title": scene["title"], "position": 0, "focus": 0,
        "markets": [_initial_market(x, config) for x in scene["markets"]],
        "active_goods": list(KINDS[:count]), "active_market_count": _nodes(config),
        "unmodeled_good_families": other_goods,
        "unmodeled_market_nodes": other_markets,
        "cash": config["starting_cash"], "cargo": [0] * count,
        "cargo_origin": [-1] * count, "energy": config["player_energy"],
        "harvested": 0, "manufactured": 0, "transfers": 0,
        "imports_sold": 0, "market_sales": 0, "buy_count": 0,
        "household_consumed": 0, "household_spend": 0,
        "tax_receipts": 0, "transport_fees": 0, "audited": [],
        "checkpoint": False, "retired": False, "finished": False,
        "failed": False, "events": [], "trade_goal": scene["trade_goal"],
    }


def apply_scene(state, config, layout):
    scene = normalize_layout(config, layout)
    if state["tick"] != 0:
        raise EconomyActionError("active market cannot rewrite original source")
    state["title"] = scene["title"]
    state["position"] = scene["origin"]
    state["markets"] = [_initial_market(x, config) for x in scene["markets"]]
    state["trade_goal"] = scene["trade_goal"]


def _current(state):
    return state["markets"][state["position"]]


def _ask(node, good, config):
    return node["prices"][good] + config["spread"]


def _bid(node, good):
    return max(1, node["prices"][good] - 1)


def _cash(state, amount):
    if state["cash"] < amount:
        raise EconomyActionError("finite buyer cash cannot fund this transaction")
    state["cash"] -= amount


def _simulate_demand(state, config):
    # One deterministic, paid consumer purchase per market per period:
    # actual inventory and actual household balance are both reduced.
    if state["tick"] % config["demand_period"] != 0:
        return
    for node in state["markets"]:
        good = (state["tick"] // config["demand_period"] + node["id"]) % len(
            state["active_goods"]
        )
        price = _ask(node, good, config)
        if node["inventory"][good] > 0 and node["household_cash"] >= price:
            node["inventory"][good] -= 1
            node["household_cash"] -= price
            node["treasury"] += price
            node["household_consumed"] += 1
            state["household_consumed"] += 1
            state["household_spend"] += price
        old = node["prices"][good]
        midpoint = config["target_stock"]
        change = (config["price_elasticity"] if node["inventory"][good] < midpoint
                  else -config["price_elasticity"] if
                  node["inventory"][good] > midpoint else 0)
        node["prices"][good] = max(config["price_floor"],
                                   min(config["price_ceiling"], old + change))


def step(state, config, action):
    if action not in ACTIONS:
        raise EconomyActionError("unknown original market command")
    if state["finished"] or state["failed"]:
        raise EconomyActionError("retired trade campaign cannot advance")
    events = []
    node = _current(state)
    good = state["focus"]
    if action.startswith("focus:"):
        selected = int(action.split(":")[1])
        if selected >= len(state["active_goods"]):
            raise EconomyActionError("cannot trade unsimulated commodity cohort")
        state["focus"] = selected
        events.append("selected_source_good")
    elif action.startswith("travel:"):
        destination = int(action.split(":")[1])
        if destination >= len(state["markets"]) or abs(destination - state["position"]) != 1:
            raise EconomyActionError("cargo must follow adjoining authored market routes")
        _cash(state, config["transport_cost"])
        node["treasury"] += config["transport_cost"]
        state["transport_fees"] += config["transport_cost"]
        if any(state["cargo"]):
            state["transfers"] += sum(state["cargo"])
            events.append("physical_cargo_transported")
        state["position"] = destination
        events.append("adjacent_source_market_arrival")
    elif action == "buy":
        if node["inventory"][good] == 0:
            raise EconomyActionError("market cannot sell absent goods")
        if sum(state["cargo"]) >= config["cargo_capacity"]:
            raise EconomyActionError("physical cargo capacity exhausted")
        price = _ask(node, good, config)
        tax = price * config["trade_tax"] // 100
        _cash(state, price + tax)
        node["inventory"][good] -= 1
        node["treasury"] += price + tax
        state["tax_receipts"] += tax
        state["cargo"][good] += 1
        state["cargo_origin"][good] = node["id"]
        state["buy_count"] += 1
        events.append("paid_finite_market_purchase")
    elif action == "sell":
        if state["cargo"][good] == 0:
            raise EconomyActionError("market cannot accept invented cargo")
        if node["inventory"][good] >= config["warehouse_capacity"]:
            raise EconomyActionError("warehouse cannot receive further inventory")
        price = _bid(node, good)
        if node["treasury"] < price:
            raise EconomyActionError("market treasury has insufficient bid liquidity")
        node["inventory"][good] += 1
        node["treasury"] -= price
        state["cash"] += price
        state["cargo"][good] -= 1
        if state["cargo_origin"][good] != node["id"]:
            state["imports_sold"] += 1
            events.append("verified_cross_market_delivery")
        if state["cargo"][good] == 0:
            state["cargo_origin"][good] = -1
        state["market_sales"] += 1
        node["sales"] += 1
        events.append("market_paid_real_cargo_bid")
    elif action == "harvest":
        if state["energy"] < config["labor_cost"]:
            raise EconomyActionError("harvest requires finite player energy")
        if node["reserves"] == 0 or node["inventory"][0] >= config["warehouse_capacity"]:
            raise EconomyActionError("finite regional production reserve depleted")
        quantity = min(config["harvest_yield"], node["reserves"],
                       config["warehouse_capacity"] - node["inventory"][0])
        node["reserves"] -= quantity
        node["inventory"][0] += quantity
        state["energy"] -= config["labor_cost"]
        state["harvested"] += quantity
        node["production"] += quantity
        events.append("finite_regional_harvest")
    elif action == "manufacture":
        if len(state["active_goods"]) < 3:
            raise EconomyActionError("manufacturing requires ore and finished tools")
        if state["energy"] < config["labor_cost"]:
            raise EconomyActionError("manufacturing requires finite labor energy")
        if node["inventory"][1] < config["ore_per_tool"]:
            raise EconomyActionError("factory requires actual source material")
        if node["inventory"][2] >= config["warehouse_capacity"]:
            raise EconomyActionError("finished goods warehouse is at capacity")
        node["inventory"][1] -= config["ore_per_tool"]
        node["inventory"][2] += 1
        state["energy"] -= config["labor_cost"]
        state["manufactured"] += 1
        node["production"] += 1
        events.append("material_conserving_original_manufacture")
    elif action == "audit":
        if node["id"] in state["audited"]:
            raise EconomyActionError("same settlement audit cannot earn duplicate evidence")
        state["audited"].append(node["id"])
        state["audited"].sort()
        events.append("source_grounded_distinct_market_audit")
    elif action == "rest":
        if state["energy"] == config["player_energy"]:
            raise EconomyActionError("no labor fatigue to recover")
        _cash(state, config["rest_cost"])
        node["treasury"] += config["rest_cost"]
        state["energy"] = min(config["player_energy"],
                              state["energy"] + config["rest_gain"])
        events.append("paid_finite_market_rest")
    elif action == "relief":
        if node["household_cash"] >= config["household_cash"]:
            raise EconomyActionError("household relief cannot exceed source balance")
        amount = min(config["relief_grant"], node["treasury"],
                     config["household_cash"] - node["household_cash"])
        if amount == 0:
            raise EconomyActionError("treasury cannot fund actual household relief")
        node["treasury"] -= amount
        node["household_cash"] += amount
        events.append("finite_treasury_to_household_transfer")
    elif action == "checkpoint":
        if state["checkpoint"] or len(state["audited"]) < 2 or (
            state["manufactured"] < 1 or
            state["imports_sold"] < state["trade_goal"]
        ):
            raise EconomyActionError("market checkpoint requires production, distinct audits and imported deliveries")
        state["checkpoint"] = True
        events.append("earned_nonterminal_trade_cooperation")
    elif action == "retire":
        if not state["checkpoint"]:
            raise EconomyActionError("trade retirement requires a real earned checkpoint")
        state["retired"] = True
        state["finished"] = True
        events.append("voluntary_source_bound_trade_retirement")
    elif action in ("wait", "inspect"):
        events.append("market_observation" if action == "inspect" else "bounded_market_turn")
    state["tick"] += 1
    _simulate_demand(state, config)
    return events


__all__ = ["ACTIONS", "EconomyActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
