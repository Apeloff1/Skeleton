"""Original advanced colony simulation: bounded cohorts, labor, survival and crises.

This is a game, not an editor metadata preview. Each command spends real
resources and changes the independently replayed colony state. A settled world
can remain playable after milestones without an artificial victory screen.
"""
from __future__ import annotations

ROLES = ("farmers", "gatherers", "miners", "guards", "medics", "engineers")
BUILDINGS = ("farm", "well", "house", "clinic", "watch", "workshop")
BIOMES = ("river", "forest", "ridge", "grassland", "wetland", "highland")
ACTIONS = (
    tuple("assign:" + role for role in ROLES)
    + tuple("release:" + role for role in ROLES)
    + tuple("build:" + b for b in BUILDINGS)
    + ("gather_wood", "quarry", "forage", "draw_water", "scavenge",
       "expedition", "trade", "recruit", "rest", "ration", "feast",
       "fortify", "treat", "tick", "tick:4")
)

class ColonyActionError(ValueError):
    """Untrusted scene data or a logically impossible player command."""


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ColonyActionError("invalid bounded colony " + name)
    return value


def default_layout(config, seed):
    return {"districts": [
        {"id": 0, "biome": "river", "wood": 30 + seed % 6,
         "stone": 12, "food": 16, "water": 36},
        {"id": 1, "biome": "forest", "wood": 55, "stone": 9,
         "food": 22, "water": 12},
        {"id": 2, "biome": "ridge", "wood": 8, "stone": 55,
         "food": 6, "water": 8},
    ], "starting_district": 0, "threat_level": 2, "caravan_stock": 18}


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "districts", "starting_district", "threat_level", "caravan_stock"
    }:
        raise ColonyActionError("colony scene requires exact geographic and threat fields")
    districts = layout["districts"]
    if type(districts) is not list or not 2 <= len(districts) <= 6:
        raise ColonyActionError("colony needs two to six finite authored districts")
    out = []
    for i, district in enumerate(districts):
        if type(district) is not dict or set(district) != {
            "id", "biome", "wood", "stone", "food", "water"
        }:
            raise ColonyActionError("district needs exact original biome and stock fields")
        if type(district["id"]) is not int or district["id"] != i:
            raise ColonyActionError("district IDs must be ordered without gaps")
        if type(district["biome"]) is not str or district["biome"] not in BIOMES:
            raise ColonyActionError("unknown original district biome")
        out.append({"id": i, "biome": district["biome"], **{
            k: _integer(district[k], 0, 100_000, k)
            for k in ("wood", "stone", "food", "water")
        }})
    start = _integer(layout["starting_district"], 0, len(out) - 1,
                     "starting_district")
    _integer(layout["threat_level"], 0, 8, "threat_level")
    _integer(layout["caravan_stock"], 0, 100_000, "caravan_stock")
    if all(d["food"] == 0 and d["water"] == 0 for d in out):
        raise ColonyActionError("colony source has no possibility of obtaining food or water")
    return {"districts": out, "starting_district": start,
            "threat_level": layout["threat_level"],
            "caravan_stock": layout["caravan_stock"]}


def start(config, seed):
    _integer(seed, 0, 2**31 - 1, "seed")
    population = config["settlers"]
    return apply_scene({
        "seed": seed, "tick": 0, "day": 1, "population": population,
        "healthy": population, "morale": 65, "health": 100,
        "food": max(20, population * 2), "water": max(20, population * 2),
        "wood": 14, "stone": 9, "medicine": 4, "credits": 20,
        "district": 0, "districts": [], "threat_level": 0,
        "caravan_stock": 0, "buildings": {name: 0 for name in BUILDINGS},
        "workers": {name: 0 for name in ROLES},
        "fortification": 0, "injured": 0, "expeditions": 0,
        "threats_survived": 0, "starvation_days": 0,
        "milestones": [], "events": [], "finished": False, "failed": False,
    }, config, default_layout(config, seed))


def apply_scene(state, config, layout):
    approved = normalize_layout(config, layout)
    state["district"] = approved["starting_district"]
    state["districts"] = [dict(d) for d in approved["districts"]]
    state["threat_level"] = approved["threat_level"]
    state["caravan_stock"] = approved["caravan_stock"]
    return state


def _take(stock, name, amount):
    if stock[name] < amount:
        raise ColonyActionError("insufficient finite " + name + " for action")
    stock[name] -= amount


def _harvest(state, stock, item, amount, events):
    if stock[item] == 0:
        raise ColonyActionError("authored district " + item + " supply exhausted")
    got = min(stock[item], amount)
    stock[item] -= got
    state[item] += got
    events.append("finite_" + item + "_collected")


def _advance(state, config):
    state["tick"] += 1
    state["day"] += 1
    events = ["colony_day_advanced"]
    people = state["population"]
    jobs = state["workers"]
    structures = state["buildings"]
    district = state["districts"][state["district"]]
    farm = min(district["food"], jobs["farmers"] * (1 + structures["farm"]))
    district["food"] -= farm
    state["food"] += farm
    gathered = min(district["wood"], jobs["gatherers"] * 2)
    district["wood"] -= gathered
    state["wood"] += gathered
    mined = min(district["stone"], jobs["miners"])
    district["stone"] -= mined
    state["stone"] += mined
    drawn = min(district["water"], max(0, structures["well"] * 3))
    district["water"] -= drawn
    state["water"] += drawn
    if farm or gathered or mined or drawn:
        events.append("assigned_labor_produced_finite_goods")
    appetite = max(1, (people + 3) // 4) + config["need_decay"] // 4
    for good in ("food", "water"):
        state[good] = max(0, state[good] - appetite)
    if state["food"] == 0 or state["water"] == 0:
        state["starvation_days"] += 1
        state["morale"] = max(0, state["morale"] - 5)
        state["health"] = max(0, state["health"] - 7)
        events.append("basic_needs_unmet")
    else:
        state["starvation_days"] = 0
        state["morale"] = min(100, state["morale"] + 1)
    if state["injured"]:
        care = min(state["injured"],
                   jobs["medics"] * (1 + structures["clinic"]), state["medicine"])
        state["injured"] -= care
        state["medicine"] -= care
        if care:
            events.append("injured_settlers_healed")
    if config["threats"] != "off" and state["day"] % 5 == 0:
        strength = state["threat_level"] + 2 + (state["day"] // 10
                   if config["threats"] == "adaptive" else 0)
        defense = jobs["guards"] * 2 + structures["watch"] * 3 + state["fortification"]
        if defense < strength:
            wounds = min(people - state["injured"], max(1, strength - defense))
            state["injured"] += wounds
            state["morale"] = max(0, state["morale"] - wounds * 3)
            state["health"] = max(0, state["health"] - wounds)
            events.append("colony_raid_breached_defenses")
        else:
            state["threats_survived"] += 1
            state["morale"] = min(100, state["morale"] + 2)
            events.append("colony_raid_repulsed")
    if state["health"] == 0 or state["starvation_days"] >= 4:
        losses = max(1, people // 8)
        state["population"] = max(0, people - losses)
        state["injured"] = min(state["injured"], state["population"])
        if sum(jobs.values()) > state["population"]:
            for key in reversed(ROLES):
                remove = min(jobs[key], sum(jobs.values()) - state["population"])
                jobs[key] -= remove
        state["health"] = max(20, state["health"])
        events.append("colony_population_lost")
    houses = 1 + structures["house"] * 6
    if state["population"] > max(config["settlers"], houses):
        state["morale"] = max(0, state["morale"] - 2)
    if state["day"] >= 8 and state["food"] >= 5 and state["water"] >= 5             and structures["farm"] and structures["well"]:
        if "self_sufficient_settlement" not in state["milestones"]:
            state["milestones"].append("self_sufficient_settlement")
            events.append("self_sufficient_colony_milestone")
    if state["day"] >= 12 and state["morale"] >= 55 and             state["threats_survived"] >= 2 and structures["clinic"] and             structures["watch"]:
        if "thriving_outpost" not in state["milestones"]:
            state["milestones"].append("thriving_outpost")
            events.append("thriving_outpost_milestone")
    if state["population"] == 0:
        state["failed"] = True
        events.append("colony_abandoned")
    return events


def step(state, config, action):
    if action not in ACTIONS:
        raise ColonyActionError("unregistered colony player action")
    if state["failed"] or state["finished"]:
        raise ColonyActionError("terminal colony cannot accept actions")
    events = []
    district = state["districts"][state["district"]]
    if action.startswith("assign:"):
        role = action.split(":", 1)[1]
        if sum(state["workers"].values()) >= min(config["jobs"], state["population"]):
            raise ColonyActionError("all bounded available settlers already assigned")
        state["workers"][role] += 1
        events.append("settler_assigned_to_real_job")
    elif action.startswith("release:"):
        role = action.split(":", 1)[1]
        if state["workers"][role] == 0:
            raise ColonyActionError("no settler assigned to that job")
        state["workers"][role] -= 1
        events.append("settler_reassigned")
    elif action.startswith("build:"):
        name = action.split(":", 1)[1]
        if state["buildings"][name] >= 4:
            raise ColonyActionError("authored building count cap reached")
        costs = {"farm": (4, 2), "well": (2, 4), "house": (5, 3),
                 "clinic": (4, 5), "watch": (5, 5), "workshop": (6, 7)}
        wood, stone = costs[name]
        _take(state, "wood", wood)
        _take(state, "stone", stone)
        state["buildings"][name] += 1
        events.append("civic_structure_constructed")
    elif action in ("gather_wood", "quarry", "forage", "draw_water"):
        item = {"gather_wood": "wood", "quarry": "stone",
                "forage": "food", "draw_water": "water"}[action]
        _harvest(state, district, item, 4, events)
    elif action == "scavenge":
        _take(state, "credits", 2)
        state["medicine"] += 2 + state["buildings"]["workshop"]
        events.append("medical_supplies_scavenged")
    elif action == "expedition":
        if state["population"] - sum(state["workers"].values()) < 1:
            raise ColonyActionError("an unassigned scout is required")
        _take(state, "food", 1)
        target = (state["district"] + 1) % len(state["districts"])
        state["district"] = target
        state["expeditions"] += 1
        events.append("new_original_district_explored")
    elif action == "trade":
        if state["caravan_stock"] < 3:
            raise ColonyActionError("finite caravan has no supplies")
        _take(state, "credits", 4)
        state["caravan_stock"] -= 3
        state["food"] += 2
        state["water"] += 1
        events.append("finite_caravan_trade")
    elif action == "recruit":
        if state["population"] >= config["settlers"] + state["buildings"]["house"] * 6:
            raise ColonyActionError("housing capacity prevents expansion")
        _take(state, "credits", 8)
        state["population"] += 1
        state["healthy"] += 1
        events.append("new_original_colonist_recruited")
    elif action == "rest":
        state["morale"] = min(100, state["morale"] + 2)
        state["health"] = min(100, state["health"] + 4)
        events.append("settlers_recovered")
    elif action == "ration":
        _take(state, "food", 1)
        state["morale"] = max(0, state["morale"] - 2)
        state["water"] += 1
        events.append("resource_ration_reallocated")
    elif action == "feast":
        _take(state, "food", max(2, state["population"] // 3))
        state["morale"] = min(100, state["morale"] + 10)
        events.append("community_feast_held")
    elif action == "fortify":
        _take(state, "wood", 3)
        _take(state, "stone", 2)
        state["fortification"] = min(20, state["fortification"] + 2)
        events.append("colony_perimeter_fortified")
    elif action == "treat":
        if state["injured"] == 0:
            raise ColonyActionError("no wounded colonists to treat")
        _take(state, "medicine", 1)
        state["injured"] -= 1
        events.append("wounded_colonist_treated")
    elif action in ("tick", "tick:4"):
        for _ in range(4 if action == "tick:4" else 1):
            if state["failed"]:
                break
            events.extend(_advance(state, config))
    state["events"] = events
    return events


__all__ = ["ACTIONS", "ROLES", "BUILDINGS", "ColonyActionError",
           "default_layout", "normalize_layout", "start", "apply_scene", "step"]
