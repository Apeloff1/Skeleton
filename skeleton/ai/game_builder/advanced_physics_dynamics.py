"""Deterministic pair CCD and radial cable constraints for the original game solver.

Reference fixed-point mechanics use exact rational time of impact and bounded
integer state. CCD is for axis-aligned translation only: no rotating manifold,
licensed solver, or independent native-physics certification is implied.
"""
from __future__ import annotations

from fractions import Fraction
from math import isqrt


def _sign(value):
    return (value > 0) - (value < 0)


def _contact_time(first, second, before_a, before_b, axes):
    """Swept relative AABB against the sum of each source-bound body radius."""
    radius = first["radius"] + second["radius"]
    # Already-overlapping pairs are resolved by the ordinary discrete solver.
    if all(abs(before_a[axis] - before_b[axis]) < radius for axis in axes):
        return None
    enter = Fraction(0)
    leave = Fraction(1)
    normal_axis = None
    normal_sign = 0
    for axis in axes:
        relative = before_a[axis] - before_b[axis]
        travel = ((first["position"][axis] - before_a[axis]) -
                  (second["position"][axis] - before_b[axis]))
        if travel == 0:
            if abs(relative) > radius:
                return None
            continue
        near = Fraction(-radius - relative, travel)
        far = Fraction(radius - relative, travel)
        if near > far:
            near, far = far, near
        if near >= enter:
            enter = near
            normal_axis = axis
            normal_sign = -_sign(travel)
        leave = min(leave, far)
        if enter > leave:
            return None
    if normal_axis is None or enter < 0 or enter > 1 or leave < 0:
        return None
    return enter, normal_axis, normal_sign


def transfer_collision_spin(first, second, axis, normal, impulse, axes, config):
    """Bounded off-center spin estimate; collision hulls remain AABBs."""
    if config["spin_transfer"] == 0:
        return
    transverse = next((j for j in axes if j != axis), None)
    if transverse is None:
        return
    separation = second["position"][transverse] - first["position"][transverse]
    lever = max(-first["radius"], min(first["radius"], separation))
    torque = (impulse * lever * config["spin_transfer"] //
              max(1, 100 * first["mass"] * first["radius"]))
    torque = max(-config["max_angular_speed"], min(config["max_angular_speed"], torque))
    first["angular_velocity"] = max(
        -config["max_angular_speed"],
        min(config["max_angular_speed"], first["angular_velocity"] + normal * torque))
    second["angular_velocity"] = max(
        -config["max_angular_speed"],
        min(config["max_angular_speed"], second["angular_velocity"] - normal * torque))


def resolve_moving_pairs(state, config, previous, events):
    """Swept CCD for pairs missed by final-frame static-overlap tests.

    Stable authored order is the sole tie-breaker. Contact is stopped at time of
    impact for the pair, and the rest of that substep is conservatively lost:
    this avoids future-position trust or tunneling, but is not a continuous
    multi-contact manifold solver.
    """
    bodies = state["bodies"]
    axes = range(3 if state["depth"] > 1 else 2)
    contacts = 0
    for i, first in enumerate(bodies):
        if first["broken"]:
            continue
        for second in bodies[i+1:]:
            if second["broken"] or not (
                first["mask"] & second["layer"] and
                second["mask"] & first["layer"]
            ):
                continue
            time = _contact_time(
                first, second, previous[first["id"]], previous[second["id"]], axes
            )
            if time is None:
                continue
            toi, axis, normal = time
            relative_speed = first["velocity"][axis] - second["velocity"][axis]
            relative_travel = (
                first["position"][axis] - previous[first["id"]][axis] -
                second["position"][axis] + previous[second["id"]][axis])
            # The trajectories establish impact even if drag zeroed the end
            # velocities; otherwise fast damped bodies could still tunnel.
            approach = max(0, -relative_travel * normal,
                           -relative_speed * normal)
            if approach == 0:
                continue
            for body in (first, second):
                before = previous[body["id"]]
                for j in axes:
                    moved = body["position"][j] - before[j]
                    body["position"][j] = before[j] + int(Fraction(moved) * toi)
            first["position"][axis] += normal
            second["position"][axis] -= normal
            total = first["mass"] + second["mass"]
            restitution = min(
                config["wall_restitution"],
                min(config["material_restitution"],
                    {"wood":35,"metal":20,"rubber":80,"glass":15}[first["material"]],
                    {"wood":35,"metal":20,"rubber":80,"glass":15}[second["material"]]))
            impulse = approach * (100 + restitution) // 100
            change_a = impulse * second["mass"] // total
            change_b = impulse - change_a
            first["velocity"][axis] += normal * change_a
            second["velocity"][axis] -= normal * change_b
            transfer_collision_spin(first, second, axis, normal, impulse, axes, config)
            for body in (first, second):
                if impulse >= body["break_threshold"] and not body["broken"]:
                    body["broken"] = True
                    state["fractures"] += 1
            state["contacts"] += 1
            state["continuous_pair_contacts"] += 1
            events.append("continuous_pair_time_of_impact")
            contacts += 1
    return contacts


def advance_rotation(state, config):
    """Integer angular integration, with damping; does not rotate collision AABBs."""
    for body in state["bodies"]:
        if body["broken"]:
            continue
        body["orientation"] = (body["orientation"] + body["angular_velocity"]) % 360_000
        body["angular_velocity"] = int(
            Fraction(body["angular_velocity"] * (100-config["angular_damping"]),100))
        state["max_angular_speed_seen"] = max(
            state["max_angular_speed_seen"], abs(body["angular_velocity"]))


def apply_torque(body, config, clockwise):
    """Spend one impulse to change angular velocity against actual inertia."""
    inertia = max(1, body["mass"] * body["radius"] * body["radius"] // 100)
    change = max(1, config["torque_strength"] * 100 // inertia)
    new_velocity = body["angular_velocity"] + (change if clockwise else -change)
    body["angular_velocity"] = max(
        -config["max_angular_speed"], min(config["max_angular_speed"], new_velocity))


def solve_radial_rope(state, config, events, world_callback):
    """Constrain the Euclidean anchor radius, not independent per-axis boxes."""
    rope = state["rope"]
    if rope is None:
        return
    body = next((b for b in state["bodies"]
                 if b["id"] == rope["body"] and not b["broken"]), None)
    if body is None:
        state["rope"] = None
        return
    axes = range(3 if state["depth"] > 1 else 2)
    anchor = state["anchors"][rope["anchor"]]
    delta = [body["position"][j] - anchor[j] for j in axes]
    length = isqrt(sum(x*x for x in delta))
    if length <= config["rope_length"]:
        return
    extension = length - config["rope_length"]
    state["peak_cable_extension"] = max(state["peak_cable_extension"], extension)
    if extension > config["rope_strength"]:
        state["rope_breaks"] += 1
        state["rope"] = None
        events.append("physical_cable_snapped")
        return
    # Project onto exact cable length using integer floor, avoiding
    # extrapolation that manufactures velocity or crosses the anchor.
    for axis, difference in zip(axes, delta):
        body["position"][axis] = anchor[axis] + (
            difference * config["rope_length"] // max(1, length))
    outward = sum(body["velocity"][j] * delta[j] for j in axes)
    if outward > 0:
        magnitude = max(1, sum(x*x for x in delta))
        for axis, difference in zip(axes, delta):
            body["velocity"][axis] -= outward * difference // magnitude
    events.append("radial_cable_tension_constrained")
    world_callback(body, state, config, events)


__all__ = ["resolve_moving_pairs", "advance_rotation", "apply_torque",
           "solve_radial_rope", "transfer_collision_spin"]
