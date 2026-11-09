"""Original, offline, integer-only flight gameplay across three flight models.

These are genuine distinct control envelopes, not differently named presets.
Aircraft and terrain are invented locally. This bounded reference simulation
does not certify aerodynamics, airworthiness, or commercial platform releases.
"""
from __future__ import annotations

ACTIONS = (
    "throttle_up", "throttle_down", "climb", "descend", "level",
    "bank_left", "bank_right", "center", "flaps_on", "flaps_off",
    "gear_down", "gear_up", "boost", "repair", "brake", "coast",
    "land", "inspect", "autopilot_on", "autopilot_off",
)
MODELS = ("arcade", "simcade", "simulation")
WEATHER = ("clear", "breezy", "storm")
MAX_TICKS = 128


class FlightActionError(ValueError):
    """A typed game command or reviewed original flight level is invalid."""


def _integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise FlightActionError("invalid original flight " + name)
    return value


def _point(value, config, name):
    if type(value) is not dict or set(value) != {"x", "altitude"}:
        raise FlightActionError("exact flight terrain coordinates required: " + name)
    return {
        "x": _integer(value["x"], 1, config["route_length"] - 1, name + ".x"),
        "altitude": _integer(value["altitude"], 0, config["max_altitude"], name + ".altitude"),
    }


def default_layout(config, seed):
    _integer(seed, 0, 2**31 - 1, "seed")
    length = config["route_length"]
    runway = config["runway_length"]
    return {
        "title": "Original Sky Route " + str(seed % 1000),
        "weather": WEATHER[seed % len(WEATHER)],
        "start": {"x": 0, "altitude": config["launch_altitude"]},
        "runway_start": length - runway,
        "runway_end": length,
        "beacons": [
            {"x": length // 3, "floor": config["waypoint_floor"],
             "ceiling": config["waypoint_ceiling"]},
            {"x": 2 * length // 3, "floor": config["waypoint_floor"],
             "ceiling": config["waypoint_ceiling"]},
        ],
        "ridges": [
            {"x": length // 2, "altitude": config["terrain_height"]},
            {"x": min(length - runway - 1, length // 2 + 3),
             "altitude": max(0, config["terrain_height"] // 2)},
        ],
        "airspace": {"min_lane": -config["airspace_width"],
                     "max_lane": config["airspace_width"]},
        "wind_direction": (-1, 1)[seed % 2],
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "weather", "start", "runway_start", "runway_end",
        "beacons", "ridges", "airspace", "wind_direction",
    }:
        raise FlightActionError("flight level requires exact typed original source")
    if type(layout["title"]) is not str or not 3 <= len(layout["title"]) <= 64 or not all(
        ch.isalnum() or ch in " -_" for ch in layout["title"]
    ):
        raise FlightActionError("invalid bounded original flight level title")
    if layout["weather"] not in WEATHER or type(layout["weather"]) is not str:
        raise FlightActionError("unsupported original weather program")
    origin = layout["start"]
    if type(origin) is not dict or set(origin) != {"x", "altitude"} or (
        type(origin["x"]) is not int or origin["x"] != 0
    ):
        raise FlightActionError("original aircraft must launch at route origin")
    altitude = _integer(origin["altitude"], 1, config["max_altitude"] - 1,
                        "launch altitude")
    if altitude != config["launch_altitude"]:
        raise FlightActionError("source takeoff must use reviewed altitude and origin")
    length = config["route_length"]
    runway = config["runway_length"]
    if (_integer(layout["runway_start"], 1, length - 1, "runway start") != length - runway
        or _integer(layout["runway_end"], length, length, "runway end") != length):
        raise FlightActionError("runway cannot bypass the configured route/landing budget")
    beacons = layout["beacons"]
    if type(beacons) is not list or len(beacons) != 2:
        raise FlightActionError("route requires two independent authored navigation fixes")
    fixed = []
    prev = 0
    for beacon in beacons:
        if type(beacon) is not dict or set(beacon) != {"x", "floor", "ceiling"}:
            raise FlightActionError("exact navigation beacon schema required")
        x = _integer(beacon["x"], prev + 1, length - runway - 1, "beacon x")
        floor = _integer(beacon["floor"], 1, config["max_altitude"] - 1, "beacon floor")
        ceiling = _integer(beacon["ceiling"], floor + 1, config["max_altitude"],
                           "beacon ceiling")
        fixed.append({"x": x, "floor": floor, "ceiling": ceiling})
        prev = x
    ridges = layout["ridges"]
    if type(ridges) is not list or len(ridges) > 8:
        raise FlightActionError("too many original terrain ridges")
    terrain = [_point(r, config, "ridge") for r in ridges]
    if len({p["x"] for p in terrain}) != len(terrain) or any(
        p["x"] >= length - runway for p in terrain
    ):
        raise FlightActionError("ridge coordinates must be unique and outside the runway")
    terrain.sort(key=lambda p: p["x"])
    air = layout["airspace"]
    if type(air) is not dict or set(air) != {"min_lane", "max_lane"}:
        raise FlightActionError("exact authored airspace corridor required")
    if (_integer(air["min_lane"], -8, -1, "west corridor") != -config["airspace_width"]
        or _integer(air["max_lane"], 1, 8, "east corridor") != config["airspace_width"]):
        raise FlightActionError("authored airspace cannot enlarge original editor budget")
    wind = _integer(layout["wind_direction"], -1, 1, "wind direction")
    if wind == 0:
        raise FlightActionError("wind direction must be signed")
    return {
        "title": layout["title"], "weather": layout["weather"],
        "start": {"x": 0, "altitude": altitude},
        "runway_start": length - runway, "runway_end": length,
        "beacons": fixed, "ridges": terrain,
        "airspace": {"min_lane": -config["airspace_width"],
                     "max_lane": config["airspace_width"]},
        "wind_direction": wind,
    }


def start(config, seed):
    scene = default_layout(config, seed)
    state = {
        "tick": 0, "x": 0, "altitude": config["launch_altitude"], "vertical_speed": 0,
        "speed": min(config["engine_thrust"] * 2, config["stall_speed"] + 20),
        "throttle": 45, "pitch": 0, "bank": 0, "lane": 0,
        "fuel": config["fuel_capacity"], "hull": config["damage_tolerance"],
        "temperature": 0, "icing": 0,
        "gear": False, "flaps": False, "autopilot": config["autopilot"],
        "boosts": config["boost_charges"], "repairs": config["repair_kits"],
        "beacons_seen": [], "beacons_missed": [], "stalls": 0, "terrain_hits": 0,
        "crosswind_events": 0, "score": 0, "landed": False,
        "weather": scene["weather"], "wind_direction": scene["wind_direction"],
        "runway_start": scene["runway_start"], "runway_end": scene["runway_end"],
        "beacons": scene["beacons"], "ridges": scene["ridges"],
        "airspace": scene["airspace"], "title": scene["title"],
        "events": [], "finished": False, "failed": False,
    }
    return state


def apply_scene(state, config, layout):
    scene = normalize_layout(config, layout)
    if state["tick"] != 0:
        raise FlightActionError("authoring cannot mutate an active aircraft")
    state["x"] = scene["start"]["x"]
    state["altitude"] = scene["start"]["altitude"]
    for key in ("weather", "wind_direction", "runway_start", "runway_end",
                "beacons", "ridges", "airspace", "title"):
        state[key] = scene[key] if key not in ("beacons", "ridges", "airspace") else (
            [dict(p) for p in scene[key]] if key != "airspace" else dict(scene[key]))


def step(state, config, action):
    if action not in ACTIONS:
        raise FlightActionError("unknown original aircraft control")
    if state["finished"] or state["failed"]:
        raise FlightActionError("cannot control a terminated flight")
    mode = config["flight_model"]
    if mode not in MODELS:
        raise FlightActionError("unknown physical flight fidelity mode")
    events = []
    if action == "autopilot_on":
        state["autopilot"] = True
    elif action == "autopilot_off":
        state["autopilot"] = False
    if action == "throttle_up":
        state["throttle"] = min(100, state["throttle"] + 15)
    elif action == "throttle_down":
        state["throttle"] = max(0, state["throttle"] - 15)
    elif action == "climb":
        state["pitch"] = min(3, state["pitch"] + 1)
    elif action == "descend":
        state["pitch"] = max(-3, state["pitch"] - 1)
    elif action == "level":
        state["pitch"] = 0
    elif action == "bank_left":
        state["bank"] = max(-2, state["bank"] - 1)
    elif action == "bank_right":
        state["bank"] = min(2, state["bank"] + 1)
    elif action == "center":
        state["bank"] = 0
    elif action == "flaps_on":
        state["flaps"] = True
    elif action == "flaps_off":
        state["flaps"] = False
    elif action == "gear_down":
        state["gear"] = True
    elif action == "gear_up":
        state["gear"] = False
    elif action == "boost":
        if not state["boosts"] or state["fuel"] < 8:
            raise FlightActionError("boost needs stored energy and original fuel")
        state["boosts"] -= 1
        state["fuel"] -= 8
        state["temperature"] += 20
        state["speed"] += 12
        events.append("afterburner_used")
    elif action == "repair":
        if state["repairs"] == 0 or state["hull"] == config["damage_tolerance"]:
            raise FlightActionError("repair requires a finite kit and genuine damage")
        state["repairs"] -= 1
        state["hull"] = min(config["damage_tolerance"], state["hull"] + 20)
        events.append("physical_airframe_repaired")
    elif action == "brake":
        state["throttle"] = max(0, state["throttle"] - 25)
        state["speed"] = max(0, state["speed"] - (12 if state["flaps"] else 7))
    elif action == "land":
        if (state["runway_start"] <= state["x"] <= state["runway_end"]
            and 0 < state["altitude"] <= config["landing_altitude"]
            and config["stall_speed"] <= state["speed"] <= config["landing_speed"]
            and state["gear"] and len(state["beacons_seen"]) == 2
            and state["fuel"] >= config["landing_fuel_reserve"]):
            state["tick"] += 1
            state["landed"] = state["finished"] = True
            state["score"] += 100 + state["hull"] + state["fuel"]
            state["events"] = ["runway_landing_confirmed", "route_completed"]
            return state["events"]
        events.append("landing_refused_unmet_conditions")
    if state["autopilot"] and action not in ("climb", "descend", "level",
                                            "bank_left", "bank_right", "center"):
        state["bank"] += (-1 if state["bank"] > 0 else 1 if state["bank"] < 0 else 0)
        if state["altitude"] > config["waypoint_ceiling"] - 10:
            state["pitch"] = -1
        elif state["altitude"] < config["waypoint_floor"] + 15:
            state["pitch"] = 1
        else:
            state["pitch"] = 0
    state["tick"] += 1
    previous_x = state["x"]
    # Integer fixed-step dynamics with mode-dependent drag, wind and stall.
    drag = config["drag"] * {"arcade": 1, "simcade": 2, "simulation": 3}[mode]
    effective_drag = drag + (8 if state["gear"] else 0) + (6 if state["flaps"] else 0)
    throttle_force = state["throttle"] * config["engine_thrust"] // 100
    delta = (throttle_force - state["speed"] * effective_drag // 100) // 9
    if state["fuel"] == 0:
        delta = -max(2, state["speed"] // 10)
    state["speed"] = max(0, min(config["engine_thrust"] * 2,
                                state["speed"] + delta))
    burn = config["fuel_burn"] + state["throttle"] // 40 + (
        1 if mode == "simulation" else 0)
    state["fuel"] = max(0, state["fuel"] - burn)
    weather_scale = {"clear": 0, "breezy": 1, "storm": 2}[state["weather"]]
    wind = (config["wind_strength"] + config["headwind"]) * weather_scale
    if wind > 0 and state["tick"] % config["wind_period"] == 0:
        shift = state["wind_direction"] * max(1, wind // (
            20 if mode == "arcade" else 12 if mode == "simcade" else 7))
        state["lane"] += shift
        state["crosswind_events"] += 1
        events.append("crosswind_drift")
    state["lane"] += state["bank"] * config["control_response"]
    if state["lane"] < state["airspace"]["min_lane"] or state["lane"] > state["airspace"]["max_lane"]:
        state["hull"] -= 6 if mode == "arcade" else 12
        state["lane"] = max(state["airspace"]["min_lane"],
                            min(state["airspace"]["max_lane"], state["lane"]))
        events.append("airspace_excursion")
    stall_speed = max(1, config["stall_speed"] - (8 if state["flaps"] else 0))
    stalled = state["speed"] < stall_speed
    if stalled:
        state["stalls"] += 1
        events.append("aerodynamic_stall")
    climb = state["pitch"] * config["lift_response"]
    if mode == "simulation":
        climb -= config["mass"] // 25
        climb -= abs(state["bank"])
    elif mode == "simcade":
        climb -= config["mass"] // 50
    if stalled:
        climb -= (config["stall_sink"] * {"arcade": 1, "simcade": 2,
                                         "simulation": 3}[mode]) // 2
    if state["weather"] == "storm" and state["tick"] % 4 == 0:
        climb -= config["turbulence"]
        state["icing"] += (1 if mode == "simulation" else 0)
        events.append("storm_downdraft")
    if state["icing"] and state["tick"] % 3 == 0:
        climb -= state["icing"] // 3
    state["vertical_speed"] = climb
    state["altitude"] = min(config["max_altitude"],
                            state["altitude"] + state["vertical_speed"])
    travel = max(1, (state["speed"] + 10) // 25)
    state["x"] = min(config["route_length"] + 2, state["x"] + travel)
    for beacon in state["beacons"]:
        if previous_x < beacon["x"] <= state["x"]:
            ok = (beacon["floor"] <= state["altitude"] <= beacon["ceiling"]
                  and abs(state["lane"]) <= 1)
            (state["beacons_seen"] if ok else state["beacons_missed"]).append(beacon["x"])
            state["score"] += 30 if ok else 0
            events.append("navigation_fix_earned" if ok else "navigation_fix_missed")
    for ridge in state["ridges"]:
        if previous_x < ridge["x"] <= state["x"] and state["altitude"] <= ridge["altitude"]:
            state["hull"] -= 25
            state["terrain_hits"] += 1
            events.append("terrain_strike")
    state["temperature"] = max(0, state["temperature"] - config["cooling_rate"] + (
        3 if state["throttle"] > 85 else 0))
    if state["temperature"] > config["engine_heat_limit"]:
        state["hull"] -= 5
        events.append("engine_overheat")
    if state["altitude"] <= 0:
        state["hull"] = 0
        events.append("ground_impact")
    if state["hull"] <= 0 or state["x"] > state["runway_end"] or (
        state["fuel"] == 0 and state["speed"] < stall_speed
    ) or state["tick"] >= config["flight_steps_limit"]:
        state["hull"] = max(0, state["hull"])
        state["failed"] = True
        events.append("flight_failed")
    state["events"] = events
    return events
