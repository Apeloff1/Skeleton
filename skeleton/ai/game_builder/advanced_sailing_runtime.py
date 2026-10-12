"""Advanced original maritime reference engine: finite ports, navigation and rescue.

Integer-only fixed-step simulation. All authoritative state is reconstructed by
advanced_gameplay_runtime from reviewed editor and scene sources plus actions.
This is an original reference game, not certified marine physics or native build.
"""
from __future__ import annotations

from collections import deque

from .system_editors import SystemEditorError


class SailingActionError(SystemEditorError):
    """An illegal maritime command or spatial/world-state transition."""


ACTIONS = (
    "port", "starboard", "sail", "row", "anchor", "unanchor", "pump",
    "reef_sails", "full_sails", "lower_sails", "dock", "undock",
    "load", "deliver", "rescue", "fish", "resupply", "repair", "wait",
)
DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))
_LAYOUT_KEYS = frozenset({
    "width", "height", "home", "destination", "islands", "reefs",
    "castaway", "shoals", "pirate", "starting_heading", "warehouse",
})


def default_layout(cfg, seed):
    return {
        "width": 18, "height": 12, "home": [2, 2],
        "destination": [15, 9],
        "islands": [[5, 5], [6, 5], [9, 3], [10, 3], [12, 7]],
        "reefs": [[7, 6], [8, 6], [13, 8]],
        "castaway": [11, 5], "shoals": [[4, 7], [10, 8]],
        "pirate": [13, 3], "starting_heading": 0, "warehouse": 3,
    }


def normalize_layout(cfg, layout):
    if type(layout) is not dict or set(layout) != _LAYOUT_KEYS:
        raise SailingActionError("maritime scene requires exact authored source fields")
    w, h = layout["width"], layout["height"]
    if type(w) is not int or type(h) is not int or not 12 <= w <= 32 or not 8 <= h <= 24:
        raise SailingActionError("maritime map dimensions exceed bounded grid")
    def point(value):
        if type(value) is not list or len(value) != 2 or any(
            type(c) is not int for c in value
        ) or not (0 <= value[0] < w and 0 <= value[1] < h):
            raise SailingActionError("maritime coordinate must be on the chart")
        return tuple(value)
    def cells(name, limit):
        value = layout[name]
        if type(value) is not list or len(value) > limit:
            raise SailingActionError("maritime scene cell budget exceeded: " + name)
        result = [point(cell) for cell in value]
        if len(set(result)) != len(result):
            raise SailingActionError("duplicate maritime cell: " + name)
        return result
    islands = cells("islands", 96)
    reefs = cells("reefs", 64)
    shoals = cells("shoals", 24)
    home = point(layout["home"])
    dest = point(layout["destination"])
    castaway = point(layout["castaway"])
    pirate = point(layout["pirate"])
    if type(layout["starting_heading"]) is not int or layout["starting_heading"] not in range(4):
        raise SailingActionError("original vessel must have cardinal heading")
    if type(layout["warehouse"]) is not int or not 1 <= layout["warehouse"] <= 12:
        raise SailingActionError("finite warehouse requires bounded starting stock")
    important = [home, dest, castaway, pirate]
    if len(set(important)) != 4:
        raise SailingActionError("ports, survivor and opponent must be separate")
    if (set(islands) & (set(important) | set(reefs) | set(shoals))
            or set(reefs) & set(important)
            or set(shoals) & set(important)):
        raise SailingActionError("maritime source overlaps land, rescue or port")
    # This is a topology check, not a claim that weather/AI guarantees victory.
    visited = {home}
    queue = deque([home])
    blocked = set(islands)
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRECTIONS:
            nxt = (x + dx, y + dy)
            if (0 <= nxt[0] < w and 0 <= nxt[1] < h
                    and nxt not in blocked and nxt not in visited):
                visited.add(nxt)
                queue.append(nxt)
    if dest not in visited or not any(
        (castaway[0] + dx, castaway[1] + dy) in visited
        for dx, dy in DIRECTIONS
    ):
        raise SailingActionError("maritime route isolates port or rescue")
    return {
        "width": w, "height": h, "home": list(home), "destination": list(dest),
        "islands": [list(p) for p in islands],
        "reefs": [list(p) for p in reefs],
        "castaway": list(castaway), "shoals": [list(p) for p in shoals],
        "pirate": list(pirate), "starting_heading": layout["starting_heading"],
        "warehouse": layout["warehouse"],
    }


def start(cfg, seed):
    state = {
        "tick": 0, "seed": seed, "heading": 0, "position": [2, 2],
        "anchored": False, "docked": True, "sails": "reefed",
        "wind_heading": seed % 4, "weather": "clear",
        "hull": cfg["hull_integrity"], "max_hull": cfg["hull_integrity"],
        "crew": cfg["crew_size"], "supplies": cfg["starting_supplies"],
        "coins": cfg["starting_coins"], "cargo": 0, "delivered": 0,
        "flooding": 0, "displacement": 0, "buoyancy_margin": 0,
        "pumps_used": 0,
        "rescued": 0, "passengers_ashore": 0, "rescued_identity": False,
        "warehouse": 3, "destination_stock": 0,
        "repair_stock": cfg["repairs_available"],
        "port_stock": [cfg["port_provisions"], cfg["port_provisions"]],
        "fishing_stock": [4, 4], "fishing_gear": cfg["fishing_gear"],
        "islands": [], "reefs": [], "shoals": [], "castaway": [],
        "pirate": [], "pirate_strikes": 0, "pirate_damage_taken": 0,
        "home": [], "destination": [], "width": 0, "height": 0,
        "distance_sailed": 0, "collisions": 0, "weather_damage": 0,
        "events": [], "finished": False, "failed": False,
    }
    apply_scene(state, cfg, default_layout(cfg, seed))
    return state


def apply_scene(state, cfg, layout):
    data = normalize_layout(cfg, layout)
    for key in ("width", "height", "home", "destination", "islands",
                "reefs", "shoals", "castaway", "pirate", "warehouse"):
        state[key] = data[key]
    state["position"] = data["home"][:]
    state["heading"] = data["starting_heading"]
    state["fishing_stock"] = [4] * len(data["shoals"])


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _damage(state, amount, event, events):
    if amount <= 0:
        return
    state["hull"] = max(0, state["hull"] - amount)
    events.append(event)
    if state["hull"] == 0:
        state["failed"] = True
        events.append("vessel_lost")


def _move(state, cfg, direction, events):
    x = state["position"][0] + direction[0]
    y = state["position"][1] + direction[1]
    if not 0 <= x < state["width"] or not 0 <= y < state["height"] or [x, y] in state["islands"]:
        state["collisions"] += 1
        _damage(state, cfg["collision_damage"], "hull_struck_shore", events)
        return False
    state["position"] = [x, y]
    state["distance_sailed"] += 1
    if [x, y] in state["reefs"]:
        _damage(state, cfg["reef_damage"], "reef_scraped_hull", events)
    return True


def _pirate_turn(state, cfg, events):
    if cfg["pirate_speed"] == 0 or state["failed"] or state["docked"]:
        return
    for _ in range(cfg["pirate_speed"]):
        pirate = state["pirate"]
        target = state["position"]
        choices = []
        for axis in (0, 1):
            delta = (target[axis] > pirate[axis]) - (target[axis] < pirate[axis])
            if delta:
                nxt = pirate[:]
                nxt[axis] += delta
                if nxt not in state["islands"] and nxt not in state["reefs"]:
                    choices.append(nxt)
        if choices:
            state["pirate"] = min(choices, key=lambda p: (_distance(p, target), p))
        if _distance(state["pirate"], target) <= 1:
            state["pirate_strikes"] += 1
            state["pirate_damage_taken"] += cfg["pirate_damage"]
            _damage(state, cfg["pirate_damage"], "pirate_broadside", events)
            break


def step(state, cfg, action):
    if action not in ACTIONS:
        raise SailingActionError("unknown maritime command")
    if state["finished"] or state["failed"]:
        raise SailingActionError("terminal voyages cannot be advanced")
    events = []
    port = (0 if state["position"] == state["home"] else
            1 if state["position"] == state["destination"] else None)
    docked = state["docked"]
    dock_actions = {"load", "deliver", "resupply", "repair"}
    if action in dock_actions and not docked:
        raise SailingActionError("harbor economy requires physical docking")
    if action in {"sail", "row"} and (docked or state["anchored"]):
        raise SailingActionError("vessel cannot navigate while docked or anchored")
    if action == "load":
        if port != 0 or state["warehouse"] == 0:
            raise SailingActionError("physical origin warehouse has no loadable goods")
        if state["cargo"] >= cfg["cargo_capacity"]:
            raise SailingActionError("cargo hold is full")
        state["cargo"] += 1
        state["warehouse"] -= 1
        events.append("finite_cargo_loaded")
    elif action == "deliver":
        if port != 1 or state["cargo"] == 0:
            raise SailingActionError("delivery requires real destination and cargo")
        delivered = state["cargo"]
        state["cargo"] = 0
        state["delivered"] += delivered
        state["destination_stock"] += delivered
        state["coins"] += delivered * cfg["cargo_sale_price"]
        if state["rescued"]:
            state["passengers_ashore"] += state["rescued"]
            state["rescued"] = 0
        events.append("physical_cargo_delivered")
    elif action == "resupply":
        if port is None or state["port_stock"][port] == 0 or state["coins"] < cfg["supply_price"]:
            raise SailingActionError("finite harbor provision purchase unavailable")
        state["port_stock"][port] -= 1
        state["coins"] -= cfg["supply_price"]
        state["supplies"] += cfg["provisions_per_purchase"]
        events.append("finite_harbor_provisions_purchased")
    elif action == "repair":
        if port is None or state["repair_stock"] == 0 or state["coins"] < cfg["repair_cost"]:
            raise SailingActionError("repair requires paid finite dock inventory")
        if state["hull"] >= state["max_hull"]:
            raise SailingActionError("undamaged hull requires no paid repair")
        state["repair_stock"] -= 1
        state["coins"] -= cfg["repair_cost"]
        state["hull"] = min(state["max_hull"], state["hull"] + cfg["repair_amount"])
        events.append("hull_repaired_with_paid_stock")
    elif action == "undock":
        if not docked:
            raise SailingActionError("vessel must be docked to depart")
        state["docked"] = False
        events.append("harbor_departure")
    elif action == "dock":
        if docked or port is None or state["anchored"] or state["coins"] < cfg["dock_fee"]:
            raise SailingActionError("docking requires a real port and berth fee")
        state["coins"] -= cfg["dock_fee"]
        state["docked"] = True
        events.append("paid_physical_harbor_arrival")
    elif action in ("port", "starboard"):
        if docked:
            raise SailingActionError("helm cannot turn moored vessel")
        state["heading"] = (state["heading"] + (-1 if action == "port" else 1)) % 4
        events.append("helm_heading_changed")
    elif action == "pump":
        if docked or state["flooding"] == 0 or state["supplies"] < 1:
            raise SailingActionError("active bilge pump requires flooding, provisions and crew")
        state["supplies"] -= 1
        state["flooding"] = max(0, state["flooding"] - cfg["pump_capacity"])
        state["pumps_used"] += 1
        events.append("crew_pumped_real_floodwater")
    elif action == "anchor":
        if docked or state["anchored"]:
            raise SailingActionError("anchor requires unanchored vessel at sea")
        state["anchored"] = True
        events.append("anchor_dropped")
    elif action == "unanchor":
        if not state["anchored"]:
            raise SailingActionError("anchor is not deployed")
        state["anchored"] = False
        events.append("anchor_raised")
    elif action in ("reef_sails", "full_sails", "lower_sails"):
        state["sails"] = {"reef_sails":"reefed", "full_sails":"full", "lower_sails":"lowered"}[action]
        events.append("rig_adjusted")
    elif action in ("sail", "row"):
        wind = cfg["wind_speed"]
        angle = (state["heading"] - state["wind_heading"]) % 4
        if action == "row":
            if cfg["oar_power"] == 0:
                raise SailingActionError("vessel has no auxiliary propulsion")
            speed = 1
        else:
            if state["sails"] == "lowered":
                raise SailingActionError("lowered sail cannot generate propulsion")
            speed = (0 if wind == 0 else
                     (2 if angle == 0 else 1 if angle in (1, 3) else 0))
            if state["sails"] == "reefed":
                speed = min(speed, 1)
            elif cfg["sail_efficiency"] <= 3:
                speed = min(speed, 1)
            elif wind >= 20 and cfg["sail_efficiency"] >= 7 and angle != 2:
                speed = min(3, speed + 1)
            # Hull displacement plus loaded goods impacts achievable speed.
            if cfg["ship_mass"] + state["cargo"] * 8 > 70:
                speed = max(0, speed - 1)
            if cfg["sea_state"] >= 9 and state["weather"] == "rough":
                speed = max(0, speed - 1)
            if speed == 0:
                events.append("becalmed_or_headwind")
        for _ in range(speed):
            if not _move(state, cfg, DIRECTIONS[state["heading"]], events) or state["failed"]:
                break
        if speed and state["weather"] == "storm" and state["sails"] == "full":
            state["weather_damage"] += cfg["storm_damage"]
            _damage(state, cfg["storm_damage"], "unreefed_sail_storm_load", events)
        if (speed and cfg["dynamic_currents"] and cfg["current_force"] > 0
                and state["tick"] % 3 == 2 and not state["failed"]):
            direction = DIRECTIONS[(state["wind_heading"] + 1) % 4]
            for _ in range(cfg["current_force"]):
                if not _move(state, cfg, direction, events) or state["failed"]:
                    break
            events.append("measured_current_drift")
    elif action == "rescue":
        if (docked or state["rescued_identity"] or
                _distance(state["position"], state["castaway"]) > cfg["rescue_distance"]
                or cfg["passenger_capacity"] == 0):
            raise SailingActionError("rescue requires physical survivor, range and berth")
        state["rescued_identity"] = True
        state["rescued"] += 1
        events.append("survivor_boarded_at_physical_position")
    elif action == "fish":
        if docked or state["fishing_gear"] == 0:
            raise SailingActionError("fishing requires real vessel and finite gear")
        shoal = next((i for i, p in enumerate(state["shoals"])
                      if _distance(p, state["position"]) <= 1 and state["fishing_stock"][i]), None)
        if shoal is None:
            raise SailingActionError("no fish remain in reachable original shoal")
        count = min(cfg["fishing_yield"], state["fishing_stock"][shoal])
        state["fishing_stock"][shoal] -= count
        state["fishing_gear"] -= 1
        state["supplies"] += count
        events.append("finite_shoal_fished")
    else:
        events.append("watch_kept")
    state["tick"] += 1
    state["wind_heading"] = (state["seed"] + state["tick"] // cfg["weather_period"]) % 4
    state["weather"] = ("clear", "breeze", "rough", "storm")[
        (state["seed"] + state["tick"] // cfg["weather_period"]) % 4
    ] if cfg["sea_state"] >= 8 else ("clear", "breeze", "rough", "clear")[
        (state["seed"] + state["tick"] // cfg["weather_period"]) % 4
    ]
    if not state["docked"] and state["tick"] % cfg["ration_period"] == 0:
        consumption = 1 + state["crew"] // 20 + (1 if state["rescued"] else 0)
        if state["supplies"] >= consumption:
            state["supplies"] -= consumption
            events.append("crew_rations_consumed")
        else:
            state["supplies"] = 0
            _damage(state, cfg["starvation_damage"], "crew_starvation", events)
    _pirate_turn(state, cfg, events)
    # Discrete marine displacement: flooding has mass, damage causes ingress.
    # Source configuration bounds all terms and every tick recomputes this
    # from authoritative stocks, rather than accepting client buoyancy flags.
    if not state["docked"] and state["hull"] < state["max_hull"]:
        ingress = (state["max_hull"] - state["hull"]) // cfg["leak_threshold"]
        state["flooding"] = min(300, state["flooding"] + ingress)
        if ingress:
            events.append("damaged_hull_ingress")
    state["displacement"] = (cfg["ship_mass"] + state["crew"] // 2
                             + state["cargo"] * 8 + state["rescued"] * 6
                             + state["flooding"])
    state["buoyancy_margin"] = cfg["buoyancy_capacity"] - state["displacement"]
    if state["buoyancy_margin"] < 0 and not state["failed"]:
        _damage(state, cfg["overload_damage"], "insufficient_buoyancy", events)
    mission = cfg["mission_type"]
    # The original warehouse starts finite; deliveries must not create stock.
    cargo_done = state["warehouse"] == 0 and state["cargo"] == 0 and state["delivered"] > 0
    rescue_done = state["passengers_ashore"] > 0
    won = ((mission == "trade" and cargo_done)
           or (mission == "rescue" and rescue_done)
           or (mission == "mixed" and cargo_done and rescue_done))
    if won and state["docked"] and state["position"] == state["destination"]:
        if cfg["completion_mode"] == "expedition":
            state["finished"] = True
            events.append("earned_original_maritime_expedition")
        elif "open_sea_milestone" not in state.get("milestones", []):
            state.setdefault("milestones", []).append("open_sea_milestone")
            events.append("open_sea_milestone")
    return events


__all__ = ["ACTIONS", "SailingActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
