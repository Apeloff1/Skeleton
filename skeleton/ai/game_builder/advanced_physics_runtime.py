"""Original fixed-point rigid-body physics playground with source-bound replay.

The reference uses a bounded 2D/3D grid, integer impulse integration,
bounded world/fixture collision, deterministic pairwise impulse response,
finite motors/anchors and genuine, reachable cargo targets. It is a game
mechanics reference, not an industrial continuous-collision or CFD solver.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction

from .system_editors import SystemEditorError


class PhysicsActionError(SystemEditorError):
    """Illegal physics control, configuration or authored geometry."""


SCALE = 100
MAX_BODIES = 8
DIRECTIONS = {
    "east": (1, 0, 0), "west": (-1, 0, 0),
    "up": (0, -1, 0), "down": (0, 1, 0),
    "front": (0, 0, 1), "back": (0, 0, -1),
}
ACTIONS = (
    "push:east", "push:west", "push:up", "push:down",
    "push:front", "push:back", "select:0", "select:1", "select:2",
    "select:3", "select:4", "select:5", "select:6", "select:7",
    "attach:0", "attach:1", "detach",
    "magnet:on", "magnet:off", "fan:on", "fan:off",
    "step", "step:4", "brake", "inspect",
)
MATERIALS = ("wood", "metal", "rubber", "glass")
MATERIAL_RESTITUTION = {"wood": 35, "metal": 20, "rubber": 80, "glass": 15}
LAYOUT_KEYS = {
    "width", "height", "depth", "floor_y", "water_y", "goal",
    "bodies", "fixtures", "anchors", "wind_direction",
}
BODY_KEYS = {"id", "position", "velocity", "radius", "mass",
             "material", "layer", "mask", "break_threshold"}
FIXTURE_KEYS = {"position", "half_size", "layer"}


def _number(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PhysicsActionError("invalid bounded physics source field: " + name)
    return value


def _triple(raw, lower, upper, name):
    if type(raw) is not list or len(raw) != 3:
        raise PhysicsActionError("exact three-axis physics vector required: " + name)
    return [_number(value, lower, upper, name) for value in raw]


def default_layout(config, seed):
    _number(seed, 0, 2**31 - 1, "seed")
    depth = 1 if config["dimension"] == "2d" else 3
    return {
        "width": 18, "height": 12, "depth": depth,
        "floor_y": 10, "water_y": 11,
        "goal": [8 * SCALE, 960, 0 if depth == 1 else SCALE],
        "bodies": [
            {"id": "payload", "position": [2 * SCALE, 960, 0 if depth == 1 else SCALE],
             "velocity": [0, 0, 0], "radius": 40, "mass": 4,
             "material": "wood", "layer": 1, "mask": 3, "break_threshold": 200},
            {"id": "counterweight", "position": [12 * SCALE, 760, 0 if depth == 1 else SCALE],
             "velocity": [0, 0, 0], "radius": 40, "mass": 8,
             "material": "metal", "layer": 2, "mask": 3, "break_threshold": 300},
        ][:min(2, config["max_bodies"])],
        "fixtures": [{"position": [14 * SCALE, 900, 0 if depth == 1 else SCALE],
                      "half_size": [45, 100, 40], "layer": 3}],
        "anchors": [[3 * SCALE, 500, 0 if depth == 1 else SCALE],
                    [11 * SCALE, 500, 0 if depth == 1 else SCALE]],
        "wind_direction": (-1, 1)[seed % 2],
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != LAYOUT_KEYS:
        raise PhysicsActionError("authored physics geometry must use exact source schema")
    width = _number(layout["width"], 12, 32, "width")
    height = _number(layout["height"], 8, 24, "height")
    depth = _number(layout["depth"], 1, 8, "depth")
    if config["dimension"] == "2d" and depth != 1:
        raise PhysicsActionError("2d source cannot silently declare depth")
    if config["dimension"] == "3d" and depth < 3:
        raise PhysicsActionError("3d world requires real traversable depth")
    floor = _number(layout["floor_y"], 3, height - 2, "floor_y")
    water = _number(layout["water_y"], floor, height - 1, "water_y")
    if type(layout["wind_direction"]) is not int or layout["wind_direction"] not in (-1, 1):
        raise PhysicsActionError("wind direction must be explicit signed vector")
    bound_x = (width - 1) * SCALE
    bound_y = (height - 1) * SCALE
    bound_z = (depth - 1) * SCALE
    goal = _triple(layout["goal"], 0, max(bound_x, bound_y, bound_z), "goal")
    if goal[0] > bound_x or goal[1] > floor * SCALE or goal[2] > bound_z:
        raise PhysicsActionError("cargo destination lies beyond physical map")
    if type(layout["bodies"]) is not list or not 1 <= len(layout["bodies"]) <= min(MAX_BODIES, config["max_bodies"]):
        raise PhysicsActionError("real authored bodies exceed configured budget")
    seen = set()
    bodies = []
    for index, original in enumerate(layout["bodies"]):
        if type(original) is not dict or set(original) != BODY_KEYS:
            raise PhysicsActionError("body must have exact original rigid-body schema")
        ident = original["id"]
        if type(ident) is not str or not (1 <= len(ident) <= 24) or not all(
            c.isascii() and (c.isalnum() or c == "_") for c in ident
        ) or ident in seen:
            raise PhysicsActionError("body identity must be unique bounded ASCII")
        seen.add(ident)
        pos = _triple(original["position"], 0, max(bound_x, bound_y, bound_z), "position")
        speed = _triple(original["velocity"], -config["speed_limit"], config["speed_limit"], "velocity")
        radius = _number(original["radius"], 15, 49, "radius")
        if (not radius <= pos[0] <= bound_x - radius
            or not radius <= pos[1] <= floor*SCALE - radius
            or (depth == 1 and pos[2] != 0)
            or (depth > 1 and not radius <= pos[2] <= bound_z - radius)):
            raise PhysicsActionError("body begins outside its authoritative collision boundary")
        material = original["material"]
        if type(material) is not str or material not in MATERIALS:
            raise PhysicsActionError("body uses unsupported material")
        bodies.append({
            "id": ident, "position": pos, "velocity": speed, "radius": radius,
            "mass": _number(original["mass"], 1, 64, "mass"),
            "material": material,
            "layer": _number(original["layer"], 1, 3, "layer"),
            "mask": _number(original["mask"], 1, 3, "mask"),
            "break_threshold": _number(original["break_threshold"], 30, 1000, "break_threshold"),
        })
    if bodies[0]["id"] != "payload":
        raise PhysicsActionError("source must give protected payload first identity")
    if all(abs(goal[axis]-bodies[0]["position"][axis]) <= config["goal_radius"]
           for axis in (range(3) if depth > 1 else range(2))):
        raise PhysicsActionError("goal cannot award victory on spawn without physical movement")
    for i, a in enumerate(bodies):
        for b in bodies[i+1:]:
            if all(abs(a["position"][axis] - b["position"][axis]) <
                   a["radius"] + b["radius"] for axis in range(3 if depth > 1 else 2)):
                raise PhysicsActionError("dynamic rigid bodies cannot begin interpenetrating")
    fixtures = layout["fixtures"]
    if type(fixtures) is not list or len(fixtures) > 24:
        raise PhysicsActionError("too many static fixtures")
    normalized_fixtures = []
    for original in fixtures:
        if type(original) is not dict or set(original) != FIXTURE_KEYS:
            raise PhysicsActionError("fixture must have exact solid geometry")
        pos = _triple(original["position"], 0, max(bound_x, bound_y, bound_z), "fixture")
        half = _triple(original["half_size"], 0, 150, "fixture half-size")
        if (min(half[0], half[1]) < 10 or
            pos[0] - half[0] < 0 or pos[0] + half[0] > bound_x or
            pos[1] - half[1] < 0 or pos[1] + half[1] > floor*SCALE or
            (depth == 1 and (pos[2] != 0 or half[2] > 49)) or
            (depth > 1 and (half[2] < 10 or pos[2] - half[2] < 0 or pos[2] + half[2] > bound_z))):
            raise PhysicsActionError("static fixture extends beyond the world")
        normalized_fixtures.append({
            "position": pos, "half_size": half,
            "layer": _number(original["layer"], 1, 3, "fixture layer"),
        })
    for body in bodies:
        for fixture in normalized_fixtures:
            if body["mask"] & fixture["layer"] and all(
                abs(body["position"][axis] - fixture["position"][axis])
                < body["radius"] + fixture["half_size"][axis]
                for axis in range(3 if depth > 1 else 2)
            ):
                raise PhysicsActionError("starting body overlaps a blocking solid")
    anchors = layout["anchors"]
    if type(anchors) is not list or len(anchors) != 2:
        raise PhysicsActionError("two original rope anchors required")
    anchor_points = []
    for entry in anchors:
        point = _triple(entry, 0, max(bound_x, bound_y, bound_z), "anchor")
        if (not point[0] <= bound_x or not point[1] <= floor * SCALE or
            not point[2] <= bound_z):
            raise PhysicsActionError("source rope anchor lies outside world")
        anchor_points.append(point)
    if anchor_points[0] == anchor_points[1]:
        raise PhysicsActionError("unique physical rope anchor positions required")
    if any(all(abs(goal[axis] - fixture["position"][axis])
               < config["goal_radius"] + fixture["half_size"][axis]
               for axis in range(3 if depth > 1 else 2))
           for fixture in normalized_fixtures):
        raise PhysicsActionError("authored cargo target is blocked by fixture")
    return {
        "width": width, "height": height, "depth": depth,
        "floor_y": floor, "water_y": water, "goal": goal,
        "bodies": bodies, "fixtures": normalized_fixtures,
        "anchors": anchor_points,
        "wind_direction": layout["wind_direction"],
    }


def start(config, seed):
    state = {
        "tick": 0, "frame": 0, "seed": seed,
        "width": 0, "height": 0, "depth": 0, "floor_y": 0,
        "water_y": 0, "goal": [], "bodies": [], "fixtures": [], "anchors": [],
        "wind_direction": 0, "selected": 0, "rope": None,
        "magnet": False, "fan": False,
        "battery": config["initial_battery"], "impulses_left": config["impulse_budget"],
        "motors_used": 0, "contacts": 0, "fractures": 0, "water_contacts": 0,
        "rope_breaks": 0, "max_velocity_seen": 0, "goal_frames": 0,
        "milestones": [], "events": [], "finished": False, "failed": False,
    }
    apply_scene(state, config, default_layout(config, seed))
    return state


def apply_scene(state, config, layout):
    scene = normalize_layout(config, layout)
    for key in LAYOUT_KEYS:
        state[key] = deepcopy(scene[key])
    state["bodies"] = [{
        **original, "sleep": 0, "broken": False
    } for original in scene["bodies"]]


def _sign(value):
    return (value > 0) - (value < 0)


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _collides(a, b, axes):
    return all(abs(a["position"][axis] - b["position"][axis])
               < a["radius"] + b["radius"] for axis in axes)


def _world(body, state, config, events, previous=None):
    radius = body["radius"]
    pos = body["position"]
    velocity = body["velocity"]
    boundaries = ((radius, (state["width"] - 1)*SCALE - radius),
                  (radius, state["floor_y"]*SCALE - radius),
                  (radius if state["depth"] > 1 else 0,
                   (state["depth"]-1)*SCALE-radius if state["depth"] > 1 else 0))
    for axis in (range(3) if state["depth"] > 1 else range(2)):
        lower, upper = boundaries[axis]
        if pos[axis] < lower or pos[axis] > upper:
            pos[axis] = _clamp(pos[axis], lower, upper)
            velocity[axis] = -velocity[axis] * config["wall_restitution"] // 100
            state["contacts"] += 1
            events.append("bounded_world_collision")
    for fixture in state["fixtures"]:
        if not (body["mask"] & fixture["layer"]):
            continue
        axes = range(3) if state["depth"] > 1 else range(2)
        # Swept point versus Minkowski-expanded AABB: rational t prevents
        # thin-fixture tunneling at the largest permitted impulse speed.
        if previous is not None:
            lo = [fixture["position"][a]-fixture["half_size"][a]-radius for a in axes]
            hi = [fixture["position"][a]+fixture["half_size"][a]+radius for a in axes]
            was_inside = all(lo[a] < previous[a] < hi[a] for a in axes)
            if not was_inside:
                entry, leave, hit_axis, normal = Fraction(0), Fraction(1), None, 0
                possible = True
                for axis in axes:
                    speed = pos[axis]-previous[axis]
                    if speed == 0:
                        if not lo[axis] <= previous[axis] <= hi[axis]:
                            possible = False
                            break
                        continue
                    near = Fraction(lo[axis]-previous[axis], speed)
                    far = Fraction(hi[axis]-previous[axis], speed)
                    if near > far:
                        near, far = far, near
                    if near >= entry:
                        entry, hit_axis, normal = near, axis, -_sign(speed)
                    leave = min(leave, far)
                    if entry > leave:
                        possible = False
                        break
                if possible and hit_axis is not None and 0 <= entry <= leave <= 1:
                    for axis in axes:
                        pos[axis] = previous[axis] + int(
                            Fraction(pos[axis]-previous[axis])*entry)
                    pos[hit_axis] += normal
                    velocity[hit_axis] = -velocity[hit_axis]*config["wall_restitution"]//100
                    state["contacts"] += 1
                    events.append("swept_fixture_contact")
        penetrations = [
            body["radius"] + fixture["half_size"][axis] -
            abs(pos[axis]-fixture["position"][axis]) for axis in axes
        ]
        if all(value > 0 for value in penetrations):
            axis = min(axes, key=lambda i: (penetrations[i], i))
            normal = _sign(pos[axis] - fixture["position"][axis])
            if normal == 0:
                normal = -1 if velocity[axis] >= 0 else 1
            pos[axis] += normal * penetrations[axis]
            velocity[axis] = -velocity[axis] * config["wall_restitution"] // 100
            state["contacts"] += 1
            events.append("fixture_contact")


def _pair_contacts(state, config, events):
    bodies = state["bodies"]
    axes = range(3) if state["depth"] > 1 else range(2)
    for i, first in enumerate(bodies):
        if first["broken"]:
            continue
        for second in bodies[i+1:]:
            if second["broken"] or not (first["mask"] & second["layer"]
                                       and second["mask"] & first["layer"]):
                continue
            if not _collides(first, second, axes):
                continue
            penetration = [
                first["radius"] + second["radius"] -
                abs(first["position"][axis] - second["position"][axis])
                for axis in axes
            ]
            axis = min(axes, key=lambda j: (penetration[j], j))
            direction = _sign(second["position"][axis] - first["position"][axis])
            if direction == 0:
                direction = 1 if i % 2 == 0 else -1
            # Resolve integer AABBs with mass-dependent penetration sharing.
            total = first["mass"] + second["mass"]
            push_a = max(1, penetration[axis] * second["mass"] // total)
            push_b = penetration[axis] - push_a
            first["position"][axis] -= direction * push_a
            second["position"][axis] += direction * push_b
            relative = first["velocity"][axis] - second["velocity"][axis]
            if relative * direction > 0:
                impulse = relative * (100 + min(MATERIAL_RESTITUTION[first["material"]],
                                               MATERIAL_RESTITUTION[second["material"]])) // 100
                delta_a = impulse * second["mass"] // total
                delta_b = impulse - delta_a
                first["velocity"][axis] -= direction * delta_a
                second["velocity"][axis] += direction * delta_b
                if impulse >= first["break_threshold"]:
                    first["broken"] = True
                    state["fractures"] += 1
                if impulse >= second["break_threshold"]:
                    second["broken"] = True
                    state["fractures"] += 1
            state["contacts"] += 1
            events.append("mass_conserving_contact")


def _advance(state, config, events):
    for _ in range(config["substeps"]):
        state["frame"] += 1
        for body in state["bodies"]:
            if body["broken"]:
                continue
            pos = body["position"]
            vel = body["velocity"]
            gravity = (config["gravity"]*SCALE + config["tick_hz"]//2)//config["tick_hz"]
            if pos[1] >= state["water_y"]*SCALE - body["radius"]:
                state["water_contacts"] += 1
                gravity -= config["buoyancy"] * SCALE // max(1, body["mass"]*config["tick_hz"])
                vel[0] = vel[0] * (100-config["water_drag"])//100
                if state["depth"] > 1:
                    vel[2] = vel[2] * (100-config["water_drag"])//100
            vel[1] = _clamp(vel[1]+gravity, -config["speed_limit"], config["speed_limit"])
            if state["fan"] and state["battery"] > 0:
                vel[0] = _clamp(vel[0] + state["wind_direction"]*config["fan_force"]//body["mass"],
                                -config["speed_limit"], config["speed_limit"])
            if (state["magnet"] and state["battery"] > 0
                    and body["material"] == "metal"):
                anchor = state["anchors"][0]
                if sum(abs(pos[i]-anchor[i]) for i in range(3)) <= config["magnet_range"]:
                    for axis in (range(3) if state["depth"] > 1 else range(2)):
                        vel[axis] = _clamp(vel[axis] + _sign(anchor[axis]-pos[axis])
                                          * config["magnet_force"]//body["mass"],
                                          -config["speed_limit"], config["speed_limit"])
            previous = pos[:]
            for axis in (range(3) if state["depth"] > 1 else range(2)):
                pos[axis] += vel[axis]
            # Physics controls do not create energy while resting on boundaries.
            for axis in (range(3) if state["depth"] > 1 else range(2)):
                vel[axis] = vel[axis] * (100-config["air_drag"])//100
            if pos[1] >= state["floor_y"] * SCALE - body["radius"]:
                vel[0] = vel[0] * (100-config["floor_friction"])//100
                if state["depth"] > 1:
                    vel[2] = vel[2] * (100-config["floor_friction"])//100
            state["max_velocity_seen"] = max(state["max_velocity_seen"], max(abs(v) for v in vel))
            _world(body, state, config, events, previous)
        for _solver in range(config["solver_iterations"]):
            before = state["contacts"]
            _pair_contacts(state, config, events)
            for body in state["bodies"]:
                if not body["broken"]:
                    _world(body, state, config, events)
            if state["contacts"] == before:
                break
        if state["rope"] is not None:
            rope = state["rope"]
            body = next((b for b in state["bodies"] if b["id"] == rope["body"] and not b["broken"]), None)
            if body is None:
                state["rope"] = None
            else:
                anchor = state["anchors"][rope["anchor"]]
                for axis in (range(3) if state["depth"] > 1 else range(2)):
                    difference = body["position"][axis] - anchor[axis]
                    if abs(difference) > config["rope_length"]:
                        tension = abs(difference) - config["rope_length"]
                        if tension > config["rope_strength"]:
                            state["rope_breaks"] += 1
                            state["rope"] = None
                            events.append("physical_cable_snapped")
                            break
                        body["position"][axis] = anchor[axis] + _sign(difference)*config["rope_length"]
                        body["velocity"][axis] = 0
                        events.append("cable_tension_constrained")
                if state["rope"] is not None:
                    _world(body, state, config, events)
        if (state["magnet"] or state["fan"]) and state["battery"] > 0:
            state["battery"] -= 1
            state["motors_used"] += 1
        payload = state["bodies"][0]
        if payload["broken"]:
            state["failed"] = True
            events.append("mission_payload_fractured")
            return
        if (all(abs(payload["position"][axis]-state["goal"][axis]) <=
                config["goal_radius"] for axis in (range(3) if state["depth"] > 1 else range(2)))
                and max(abs(v) for v in payload["velocity"]) <= config["goal_speed"]):
            state["goal_frames"] += 1
            if state["goal_frames"] >= config["goal_dwell_frames"]:
                if config["completion_mode"] == "challenge":
                    state["finished"] = True
                    events.append("original_physical_cargo_docked")
                    return
                if "cargo_docked" not in state["milestones"]:
                    state["milestones"].append("cargo_docked")
                    events.append("original_nonterminal_cargo_milestone")
        else:
            state["goal_frames"] = 0


def step(state, config, action):
    if action not in ACTIONS:
        raise PhysicsActionError("unknown authoritative physics command")
    if state["failed"] or state["finished"]:
        raise PhysicsActionError("terminal physics state cannot progress")
    body = state["bodies"][state["selected"]]
    events = []
    if action.startswith("select:"):
        selected = int(action[-1])
        if selected >= len(state["bodies"]) or state["bodies"][selected]["broken"]:
            raise PhysicsActionError("cannot select nonexistent/broken rigid body")
        state["selected"] = selected
    elif action.startswith("push:"):
        direction = DIRECTIONS[action.split(":")[1]]
        if config["dimension"] == "2d" and direction[2]:
            raise PhysicsActionError("2d solver does not invent z-axis movement")
        if state["impulses_left"] == 0 or body["broken"]:
            raise PhysicsActionError("actuator has exhausted its finite impulse budget")
        state["impulses_left"] -= 1
        for axis in range(3):
            body["velocity"][axis] = _clamp(
                body["velocity"][axis] + config["impulse_strength"]*direction[axis]//body["mass"],
                -config["speed_limit"], config["speed_limit"])
        events.append("finite_player_impulse_applied")
    elif action.startswith("attach:"):
        if state["rope"] is not None:
            raise PhysicsActionError("one active source-bound rope permitted")
        index = int(action[-1])
        anchor = state["anchors"][index]
        if sum(abs(body["position"][axis]-anchor[axis]) for axis in range(3)) > config["attach_range"]:
            raise PhysicsActionError("rope cannot attach to distant body")
        state["rope"] = {"body":body["id"],"anchor":index}
        events.append("physical_rope_attached")
    elif action == "detach":
        if state["rope"] is None:
            raise PhysicsActionError("no rope exists to detach")
        state["rope"] = None
        events.append("physical_rope_detached")
    elif action in ("magnet:on", "fan:on"):
        if state["battery"] <= 0:
            raise PhysicsActionError("motor battery has no remaining energy")
        state["magnet" if action.startswith("magnet") else "fan"] = True
        events.append("bounded_motor_energized")
    elif action in ("magnet:off", "fan:off"):
        state["magnet" if action.startswith("magnet") else "fan"] = False
        events.append("motor_deenergized")
    elif action == "brake":
        for axis in range(3):
            body["velocity"][axis] = body["velocity"][axis] * (100-config["brake_strength"])//100
        events.append("real_velocity_braked")
    else:
        events.append("physics_step_observed")
    state["tick"] += 1
    for _ in range(4 if action == "step:4" else 1):
        if state["finished"] or state["failed"]:
            break
        _advance(state, config, events)
    return events


__all__ = ["ACTIONS", "PhysicsActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
