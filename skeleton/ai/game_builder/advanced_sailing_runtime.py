"""Original navigable sailing engine: finite voyage, ship trim and earned docking.

Three independently tuned vessel hulls, waves, tide/current drift, grounding,
navigation marks and physical cargo delivery. Local integer-only game reference;
this is not a certified maritime training simulator or console release.
"""
from __future__ import annotations

VESSELS = ("skiff", "sloop", "schooner")
SEAS = ("lagoon", "coastal", "open_sea", "storm")
ACTIONS = (
    "hoist", "lower", "trim_in", "trim_out", "reef", "unreef",
    "helm_port", "helm_starboard", "center_helm", "tack", "jibe",
    "start_engine", "stop_engine", "throttle_up", "throttle_down",
    "heave_to", "raise_anchor", "drop_anchor", "repair", "rest",
    "coast", "dock", "inspect",
)


class SailingActionError(ValueError):
    """Illegal vessel action, forged geometry or impossible original voyage."""


def _int(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise SailingActionError("invalid original maritime " + name)
    return value


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    length = config["route_length"]
    return {
        "title": "Original Tide Route " + str(seed % 1000),
        "sea": SEAS[seed % len(SEAS)],
        "start": [0, 0],
        "harbor_start": length - config["harbor_length"],
        "harbor_end": length,
        "buoys": [length // 3, 2 * length // 3],
        "shoals": [
            {"x": length // 2, "lane": seed % 3 - 1, "depth": 1},
            {"x": length // 2 + 4, "lane": -1, "depth": 2},
        ],
        "current_direction": (-1, 1)[seed % 2],
        "cargo_manifest": config["cargo_contract"],
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "sea", "start", "harbor_start", "harbor_end",
        "buoys", "shoals", "current_direction", "cargo_manifest",
    }:
        raise SailingActionError("exact reviewed maritime route schema required")
    name = layout["title"]
    if type(name) is not str or not 3 <= len(name) <= 64 or not all(
        c.isalnum() or c in " -_" for c in name
    ):
        raise SailingActionError("original maritime route title is unsafe")
    if type(layout["sea"]) is not str or layout["sea"] not in SEAS:
        raise SailingActionError("unsupported original seascape")
    if (type(layout["start"]) is not list or len(layout["start"]) != 2
        or any(type(coord) is not int for coord in layout["start"])
        or layout["start"] != [0, 0]):
        raise SailingActionError("vessel must depart exact integer chart origin")
    length = config["route_length"]
    limit = length - config["harbor_length"]
    if (_int(layout["harbor_start"], 1, length - 1, "harbor start") != limit
        or _int(layout["harbor_end"], length, length, "harbor end") != length):
        raise SailingActionError("port cannot override authored voyage distance")
    buoys = layout["buoys"]
    if type(buoys) is not list or len(buoys) != 2:
        raise SailingActionError("voyage must retain two navigable route marks")
    first = _int(buoys[0], 1, limit - 2, "first buoy")
    second = _int(buoys[1], first + 1, limit - 1, "second buoy")
    shoals = layout["shoals"]
    if type(shoals) is not list or len(shoals) > 8:
        raise SailingActionError("shoal density violates bounded navigation chart")
    safe = []
    visited = set()
    for record in shoals:
        if type(record) is not dict or set(record) != {"x", "lane", "depth"}:
            raise SailingActionError("a shallow-water entry must have strict geometry")
        x = _int(record["x"], 1, limit - 1, "shoal x")
        lane = _int(record["lane"], -3, 3, "shoal lane")
        depth = _int(record["depth"], 0, 12, "shoal depth")
        if (x, lane) in visited:
            raise SailingActionError("duplicated shoal position in original chart")
        visited.add((x, lane))
        safe.append({"x": x, "lane": lane, "depth": depth})
    safe.sort(key=lambda item: (item["x"], item["lane"]))
    current = _int(layout["current_direction"], -1, 1, "current direction")
    if not current:
        raise SailingActionError("current direction must be signed")
    if _int(layout["cargo_manifest"], 1, config["cargo_capacity"], "cargo") != config["cargo_contract"]:
        raise SailingActionError("manifest cannot forge contracted original cargo")
    return {
        "title": name, "sea": layout["sea"], "start": [0, 0],
        "harbor_start": limit, "harbor_end": length,
        "buoys": [first, second], "shoals": safe,
        "current_direction": current, "cargo_manifest": config["cargo_contract"],
    }


def start(config, seed):
    source = default_layout(config, seed)
    return {
        "tick": 0, "x": 0, "lane": 0, "speed": config["launch_speed"],
        "heading": 0, "sails": True, "reefed": False,
        "trim": config["sail_trim"], "anchor": False, "engine": False,
        "throttle": 0, "fuel": config["engine_fuel"],
        "hull": config["hull_integrity"], "mast": config["mast_integrity"],
        "cargo": config["cargo_contract"], "cargo_delivered": 0,
        "crew_fatigue": 0, "crew_morale": config["crew_morale"],
        "provisions": config["provisions"], "parts": config["repair_supplies"],
        "buoys_seen": [], "buoys_missed": [], "groundings": 0, "wave_hits": 0,
        "current_events": 0, "score": 0,
        "sea": source["sea"], "title": source["title"],
        "harbor_start": source["harbor_start"], "harbor_end": source["harbor_end"],
        "buoys": source["buoys"], "shoals": source["shoals"],
        "current_direction": source["current_direction"],
        "manifest": source["cargo_manifest"],
        "events": [], "finished": False, "failed": False,
    }


def apply_scene(state, config, layout):
    source = normalize_layout(config, layout)
    if state["tick"] != 0:
        raise SailingActionError("cannot overwrite a voyaging ship chart")
    state["x"], state["lane"] = source["start"]
    for key in ("sea", "title", "harbor_start", "harbor_end",
                "buoys", "shoals", "current_direction"):
        state[key] = ([dict(v) for v in source[key]] if key == "shoals" else
                      list(source[key]) if key == "buoys" else source[key])
    state["manifest"] = source["cargo_manifest"]


def step(state, config, action):
    if action not in ACTIONS:
        raise SailingActionError("unknown original maritime command")
    if state["finished"] or state["failed"]:
        raise SailingActionError("voyage already terminated")
    events = []
    if action == "hoist":
        if state["mast"] <= 0:
            raise SailingActionError("broken mast cannot raise an effective sail")
        state["sails"] = True
    elif action == "lower":
        state["sails"] = False
    elif action == "trim_in":
        state["trim"] = min(100, state["trim"] + 20)
    elif action == "trim_out":
        state["trim"] = max(0, state["trim"] - 20)
    elif action == "reef":
        state["reefed"] = True
    elif action == "unreef":
        state["reefed"] = False
    elif action == "helm_port":
        state["heading"] = max(-2, state["heading"] - 1)
    elif action == "helm_starboard":
        state["heading"] = min(2, state["heading"] + 1)
    elif action == "center_helm":
        state["heading"] = 0
    elif action in ("tack", "jibe"):
        if not state["sails"] or state["speed"] <= 0:
            raise SailingActionError("tack and jibe require genuine water movement")
        state["heading"] = -state["heading"]
        state["speed"] = max(0, state["speed"] - (3 if action == "tack" else 1))
        events.append("tack_completed" if action == "tack" else "jibe_completed")
    elif action == "start_engine":
        if state["fuel"] <= 0:
            raise SailingActionError("auxiliary engine needs remaining fuel")
        state["engine"] = True
    elif action == "stop_engine":
        state["engine"] = False
    elif action == "throttle_up":
        if state["fuel"] <= 0:
            raise SailingActionError("diesel throttle cannot mint fuel")
        state["engine"] = True
        state["throttle"] = min(100, state["throttle"] + 25)
    elif action == "throttle_down":
        state["throttle"] = max(0, state["throttle"] - 25)
    elif action == "heave_to":
        state["sails"] = False
        state["engine"] = False
        state["throttle"] = 0
        state["speed"] = max(0, state["speed"] - 7)
        events.append("controlled_drift")
    elif action == "raise_anchor":
        state["anchor"] = False
    elif action == "drop_anchor":
        state["anchor"] = True
        state["sails"] = False
        state["speed"] = max(0, state["speed"] - config["anchor_brake"])
    elif action == "repair":
        if not state["parts"] or (
            state["hull"] == config["hull_integrity"] and state["mast"] == config["mast_integrity"]
        ):
            raise SailingActionError("real vessel damage and finite spares required")
        state["parts"] -= 1
        state["hull"] = min(config["hull_integrity"], state["hull"] + 18)
        state["mast"] = min(config["mast_integrity"], state["mast"] + 8)
        events.append("vessel_repaired")
    elif action == "rest":
        state["crew_fatigue"] = max(0, state["crew_fatigue"] - 12)
        state["crew_morale"] = min(100, state["crew_morale"] + 2)
    elif action == "dock":
        if (state["harbor_start"] <= state["x"] <= state["harbor_end"]
            and state["speed"] <= config["safe_dock_speed"]
            and not state["sails"] and not state["engine"]
            and state["anchor"] and len(state["buoys_seen"]) == 2
            and state["cargo"] == state["manifest"] and state["hull"] > 0):
            state["tick"] += 1
            state["finished"] = True
            state["cargo_delivered"] = state["manifest"]
            state["cargo"] = 0
            state["score"] += 100 + state["cargo_delivered"] + state["hull"]
            state["events"] = ["original_cargo_delivered", "harbor_docked"]
            return state["events"]
        events.append("harbor_docking_refused")

    state["tick"] += 1
    previous_x = state["x"]
    vessel = config["vessel_class"]
    if vessel not in VESSELS:
        raise SailingActionError("unknown real sail and hull dynamics")
    # A vessel's sail loading, inertia and shallow-water draft materially vary.
    efficiency = {"skiff": 12, "sloop": 10, "schooner": 8}[vessel]
    drag = {"skiff": 3, "sloop": 2, "schooner": 1}[vessel]
    wind = max(0, config["wind_speed"] - config["wind_variability"] * (
        1 if state["sea"] == "storm" and state["tick"] % 3 == 0 else 0))
    sail = (wind * config["sail_area"] * state["trim"] * efficiency // 100000
            if state["sails"] and not state["anchor"] and state["mast"] > 0 else 0)
    if state["reefed"]:
        sail = max(0, sail // 2)
    sail = max(0, sail - abs(state["heading"]))
    motor = (config["engine_power"] * state["throttle"] // 100
             if state["engine"] and not state["anchor"] and state["fuel"] > 0 else 0)
    if motor:
        state["fuel"] = max(0, state["fuel"] - 1 - state["throttle"] // 50)
    if state["fuel"] == 0:
        state["engine"] = False
    deceleration = max(1, state["speed"] * drag // 8)
    if state["anchor"]:
        deceleration += config["anchor_brake"]
    change = max(-5, min(5, (sail + motor)//3 - deceleration))
    state["speed"] = max(0, min(config["max_speed"], state["speed"] + change))
    if state["anchor"]:
        state["speed"] = min(state["speed"], 1)
    state["lane"] += state["heading"] if state["speed"] > 0 else 0
    if config["dynamic_currents"] and state["tick"] % config["current_period"] == 0:
        state["lane"] += state["current_direction"] * max(1, config["tide_strength"] // 6)
        state["current_events"] += 1
        events.append("tidal_current_drift")
    if abs(state["lane"]) > 3:
        state["hull"] -= 5
        state["lane"] = max(-3, min(3, state["lane"]))
        events.append("channel_boundary_strike")
    state["x"] = min(config["route_length"] + 2,
                     state["x"] + (max(1, state["speed"] // 3) if state["speed"] else 0))
    for buoy in state["buoys"]:
        if previous_x < buoy <= state["x"]:
            if abs(state["lane"]) <= config["buoy_lane_tolerance"]:
                state["buoys_seen"].append(buoy)
                state["score"] += 25
                events.append("navigation_mark_earned")
            else:
                state["buoys_missed"].append(buoy)
                events.append("navigation_mark_missed")
    for hazard in state["shoals"]:
        if (previous_x < hazard["x"] <= state["x"]
            and hazard["lane"] == state["lane"]
            and hazard["depth"] < config["draft"]):
            state["groundings"] += 1
            state["hull"] -= config["shoal_damage"]
            state["cargo"] = max(0, state["cargo"] - config["cargo_spill"])
            events.append("shallow_reef_grounding")
    if state["sea"] in ("storm", "open_sea") and state["tick"] % 4 == 0:
        waves = max(0, config["sea_state"] * (2 if state["sea"] == "storm" else 1)
                    - config["storm_resistance"] // 4)
        if waves:
            state["hull"] -= waves
            state["mast"] = max(0, state["mast"] - (waves if state["sails"] else 0))
            state["wave_hits"] += 1
            events.append("sea_state_waves")
    if action != "rest":
        state["crew_fatigue"] += max(1, config["crew_size"] // 10)
    state["provisions"] = max(0, state["provisions"] - 1)
    if state["crew_fatigue"] > config["fatigue_limit"]:
        state["crew_morale"] = max(0, state["crew_morale"] - 2)
        events.append("crew_exhaustion")
    if (state["hull"] <= 0 or state["mast"] <= 0 and not state["engine"]
        or state["provisions"] == 0 or state["x"] > state["harbor_end"]
        or state["tick"] >= config["voyage_turn_limit"]):
        state["hull"] = max(0, state["hull"])
        state["failed"] = True
        events.append("voyage_failed")
    state["events"] = events
    return events
