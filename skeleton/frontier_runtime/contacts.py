"""Continuous collision and sequential multi-body contact for one fixed step.

Sphere sweeps and impulse resolution call the existing reference solvers in
``skeleton.jeeves.game_frontier_advanced_physics``. Actor controllers supply a
desired velocity. Position is integrated only along the swept timeline, so a
controller cannot write the unconstrained end pose through a thin wall.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from skeleton.jeeves.game_frontier_advanced_physics import (
    RigidBody,
    SweptContact,
    Vec3,
    resolve_contact,
    sweep_sphere_plane,
    sweep_spheres,
    vecnorm,
)
from skeleton.jeeves.game_frontier_production import Vec3 as ProductionVec3


class ContactStepError(ValueError):
    """Raised when a contact sub-step cannot be completed."""


@dataclass(frozen=True)
class ThinWall:
    wall_id: str
    point: Vec3
    normal: Vec3
    half_thickness_m: float
    friction: float
    restitution: float


def _production(vec: Vec3) -> ProductionVec3:
    return ProductionVec3(vec.x, vec.y, vec.z)


def discrete_sphere_tunnels(
    start: tuple[float, float, float],
    velocity: tuple[float, float, float],
    radius_m: float,
    dt: float,
    wall_point: tuple[float, float, float],
    wall_normal: tuple[float, float, float],
    half_thickness_m: float,
) -> bool:
    """True when end-of-step samples miss a slab the segment still crosses.

    A discrete overlap test at the start pose and the unconstrained end pose
    reports no contact. The midpoint of the slab is on opposite sides of those
    samples, which is the tunneling case continuous sweep is required to catch.
    """
    end = tuple(start[i] + velocity[i] * dt for i in range(3))
    ds = sum((start[i] - wall_point[i]) * wall_normal[i] for i in range(3))
    de = sum((end[i] - wall_point[i]) * wall_normal[i] for i in range(3))
    limit = half_thickness_m + radius_m
    if abs(ds) <= limit or abs(de) <= limit:
        return False
    return ds * de < 0


def _steer(body: RigidBody, desired: tuple[float, float, float], integrator: str, dt: float) -> RigidBody:
    target = Vec3(*desired)
    # Integrator name is the registered physics_model string.
    if "kinematics" in integrator or "tile collision" in integrator or integrator.startswith("2D"):
        velocity = target
    elif "multi-rate" in integrator:
        half = body.velocity + (target - body.velocity).scaled(0.5)
        velocity = half + (target - half).scaled(min(1.0, dt * 4.0))
    else:
        delta = target - body.velocity
        limit = 40.0 * dt
        magnitude = vecnorm(delta)
        if magnitude > limit > 0:
            delta = delta.scaled(limit / magnitude)
        velocity = body.velocity + delta
    speed = vecnorm(velocity)
    if speed > 9999:
        velocity = velocity.scaled(9999 / speed)
    return _replace_velocity(body, velocity)


def _replace_velocity(body: RigidBody, velocity: Vec3) -> RigidBody:
    from dataclasses import replace
    return replace(body, velocity=velocity)


def _advance(body: RigidBody, dt: float) -> RigidBody:
    from dataclasses import replace
    if dt == 0:
        return body
    return replace(body, position=body.position + body.velocity.scaled(dt))


def sweep_thin_wall(body: RigidBody, wall: ThinWall, dt: float) -> SweptContact | None:
    """Sweep both faces and ignore the face whose free half-space is behind the body."""
    best: SweptContact | None = None
    for sign in (1.0, -1.0):
        outward = wall.normal.scaled(sign)
        point = wall.point + wall.normal.scaled(sign * wall.half_thickness_m)
        signed_center = (body.position - point).dot(outward)
        if signed_center < -body.radius_m - 1e-8:
            continue
        hit = sweep_sphere_plane(
            body,
            plane_point=_production(point),
            plane_outward_normal=_production(outward),
            delta_s=dt,
            surface_friction=wall.friction,
            surface_restitution=wall.restitution,
        )
        if hit is None:
            continue
        if hit.time_of_impact_s <= 1e-15:
            # Resting or separating contact is not another sweep event.
            if body.velocity.dot(hit.contact.normal_a_to_b) <= 1e-8 and hit.contact.penetration_m <= 1e-6:
                continue
        if best is None or hit.time_of_impact_s < best.time_of_impact_s:
            best = hit
    return best


@dataclass(frozen=True)
class _Event:
    toi: float
    kind: int
    i: int
    j: int
    wall_id: str
    hit: SweptContact


def _earliest(bodies: list[RigidBody], walls: tuple[ThinWall, ...], dt: float) -> _Event | None:
    best: _Event | None = None
    for index, body in enumerate(bodies):
        for wall in walls:
            hit = sweep_thin_wall(body, wall, dt)
            if hit is None:
                continue
            event = _Event(hit.time_of_impact_s, 0, index, -1, wall.wall_id, hit)
            best = _prefer(best, event)
        for other in range(index + 1, len(bodies)):
            hit = sweep_spheres(body, bodies[other], delta_s=dt)
            if hit is None:
                continue
            if hit.time_of_impact_s <= 1e-15:
                relative = bodies[other].velocity - body.velocity
                if relative.dot(hit.contact.normal_a_to_b) >= -1e-8 and hit.contact.penetration_m <= 1e-6:
                    continue
            event = _Event(hit.time_of_impact_s, 1, index, other, "", hit)
            best = _prefer(best, event)
    return best


def _prefer(best: _Event | None, event: _Event) -> _Event:
    if best is None:
        return event
    key = (event.toi, event.kind, event.i, event.j, event.wall_id)
    current = (best.toi, best.kind, best.i, best.j, best.wall_id)
    return event if key < current else best


def _coulomb_mu(body: RigidBody, other: RigidBody | None, hit: SweptContact) -> float:
    other_friction = other.friction if other is not None else hit.contact.surface_friction
    return math.sqrt(body.friction * other_friction)


def _receipt(resolution, source: str, mu: float, restitution: float, other_id: str | None, wall_id: str | None, normal: Vec3) -> dict:
    return {
        "body_a": resolution.body_a.body_id,
        "body_b": other_id,
        "wall_id": wall_id,
        "source": source,
        "normal": [normal.x, normal.y, normal.z],
        "normal_impulse_ns": resolution.normal_impulse_ns,
        "friction_impulse_ns": resolution.friction_impulse_ns,
        "restitution": restitution,
        "friction_coefficient": mu,
        "energy_before_j": resolution.energy_before_j,
        "energy_after_j": resolution.energy_after_j,
        "energy_dissipated_j": resolution.energy_dissipated_j,
        "momentum_residual_ns": resolution.momentum_residual_ns,
        "separation_m": resolution.separation_m,
        "damage_a": resolution.damage_a,
        "damage_b": resolution.damage_b,
    }


def solve_actor_contacts(
    bodies: tuple[RigidBody, ...],
    walls: tuple[ThinWall, ...],
    *,
    dt: float,
    iteration_cap: int,
    integrator: str,
    desired: dict[str, tuple[float, float, float]],
    steer: bool = True,
) -> tuple[tuple[RigidBody, ...], tuple[dict, ...], int]:
    """Sweep, then resolve earliest contacts up to the era iteration cap.

    Leftover time is integrated only when no sweep remains inside it. Exhausting
    the cap therefore drops leftover time instead of stepping through a wall.
    """
    if type(iteration_cap) is not int or iteration_cap < 1:
        raise ContactStepError("iteration cap must be a positive integer")
    current = []
    for body in bodies:
        if steer:
            if body.body_id not in desired:
                raise ContactStepError(f"actor {body.body_id} has no controller")
            current.append(_steer(body, desired[body.body_id], integrator, dt))
        else:
            current.append(body)
    receipts: list[dict] = []
    consumed = 0.0
    used = 0
    for iteration in range(iteration_cap):
        remaining = dt - consumed
        if remaining <= 1e-12:
            break
        event = _earliest(current, walls, remaining)
        if event is None:
            current = [_advance(body, remaining) for body in current]
            consumed = dt
            break
        used = iteration + 1
        if event.toi > 0:
            current = [_advance(body, event.toi) for body in current]
            consumed += event.toi
        if event.kind == 0:
            body = current[event.i]
            resolved = resolve_contact(body, None, event.hit.contact)
            current[event.i] = resolved.body_a
            mu = _coulomb_mu(body, None, event.hit)
            receipts.append(_receipt(
                resolved, event.hit.source, mu, event.hit.contact.surface_restitution,
                None, event.wall_id, event.hit.contact.normal_a_to_b,
            ))
        else:
            left = current[event.i]
            right = current[event.j]
            resolved = resolve_contact(left, right, event.hit.contact)
            if resolved.body_b is None:
                raise ContactStepError("dynamic contact lost the second body")
            current[event.i] = resolved.body_a
            current[event.j] = resolved.body_b
            mu = _coulomb_mu(left, right, event.hit)
            restitution = min(left.restitution, right.restitution)
            receipts.append(_receipt(
                resolved, event.hit.source, mu, restitution, right.body_id, None,
                event.hit.contact.normal_a_to_b,
            ))
    else:
        remaining = dt - consumed
        if remaining > 1e-12 and _earliest(current, walls, remaining) is None:
            current = [_advance(body, remaining) for body in current]
    return tuple(current), tuple(receipts), used
