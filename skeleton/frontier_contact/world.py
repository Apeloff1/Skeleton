"""Fixed contact step: swept broadphase, manifold, then Coulomb impulse.

The scratch lists are returned only after every sub-step succeeds. Kinematic
terrain integrates with the spheres so both stay on the same clock. Exhausting
the iteration cap drops leftover time instead of stepping through a contact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from skeleton.frontier_contact.bodies import BoxBody, SphereBody
from skeleton.frontier_contact.broadphase import broadphase_volumes, swept_bounds
from skeleton.frontier_contact.errors import ContactRejected
from skeleton.frontier_contact.manifold import (
    ContactManifold,
    collision_contact,
    sphere_box_manifold,
    sphere_sphere_manifold,
)
from skeleton.jeeves.game_frontier_advanced_physics import (
    AdvancedPhysicsError,
    RigidBody,
    Vec3,
    resolve_contact,
)
from skeleton.jeeves.game_frontier_production import FrontierProductionError

_SOLVER_ERRORS = (
    AdvancedPhysicsError,
    FrontierProductionError,
    ZeroDivisionError,
    OverflowError,
)


@dataclass(frozen=True)
class ContactRecord:
    body_a: str
    body_b: str
    time_of_impact_s: float
    normal: tuple[float, float, float]
    point: tuple[float, float, float]
    points: tuple[tuple[float, float, float], ...]
    normal_impulse_ns: float
    friction_impulse_ns: float
    restitution: float
    friction_coefficient: float
    source: str
    feature: str


@dataclass(frozen=True)
class ContactStepResult:
    spheres: tuple[SphereBody, ...]
    boxes: tuple[BoxBody, ...]
    contacts: tuple[ContactRecord, ...]
    queried_bounds: tuple
    iterations_used: int


def _validate_population(
    spheres: tuple[SphereBody, ...],
    boxes: tuple[BoxBody, ...],
) -> None:
    seen: set[str] = set()
    for body in spheres:
        if not isinstance(body, SphereBody):
            raise ContactRejected("sphere required")
        if body.body_id in seen:
            raise ContactRejected("duplicate body id")
        seen.add(body.body_id)
    for body in boxes:
        if not isinstance(body, BoxBody):
            raise ContactRejected("box required")
        if body.body_id in seen:
            raise ContactRejected("duplicate body id")
        seen.add(body.body_id)


def _validate_dt(dt: object) -> float:
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise ContactRejected("dt must be a real number")
    step = float(dt)
    if math.isnan(step):
        raise ContactRejected("NaN")
    if not math.isfinite(step) or step < 0.0 or step > 10.0:
        raise ContactRejected("dt out of range")
    return step


def _validate_cap(iteration_cap: object) -> int:
    if (
        type(iteration_cap) is not int
        or isinstance(iteration_cap, bool)
        or iteration_cap < 1
    ):
        raise ContactRejected("iteration cap must be a positive integer")
    return iteration_cap


def _advance_sphere(body: SphereBody, dt: float) -> SphereBody:
    if dt == 0.0:
        return body
    return replace(
        body,
        position=tuple(
            body.position[axis] + body.velocity[axis] * dt for axis in range(3)
        ),
    )


def _advance_box(body: BoxBody, dt: float) -> BoxBody:
    if dt == 0.0:
        return body
    return replace(
        body,
        center=tuple(body.center[axis] + body.velocity[axis] * dt for axis in range(3)),
    )


def _as_rigid(body: SphereBody, velocity: Vec3 | None = None) -> RigidBody:
    return RigidBody(
        body.body_id,
        Vec3(*body.position),
        Vec3(*body.velocity) if velocity is None else velocity,
        body.mass_kg,
        body.radius_m,
        body.restitution,
        body.friction,
        Vec3(*body.angular_velocity),
    )


def _from_rigid(
    original: SphereBody, solved: RigidBody, velocity_offset: Vec3
) -> SphereBody:
    velocity = solved.velocity + velocity_offset
    return replace(
        original,
        position=(solved.position.x, solved.position.y, solved.position.z),
        velocity=(velocity.x, velocity.y, velocity.z),
        angular_velocity=(
            solved.angular_velocity.x,
            solved.angular_velocity.y,
            solved.angular_velocity.z,
        ),
    )


def _resting(manifold: ContactManifold, normal_speed: float) -> bool:
    penetration = manifold.points[0].penetration_m
    return (
        manifold.time_of_impact_s <= 1e-15
        and normal_speed >= -1e-8
        and penetration <= 1e-6
    )


def _record(
    manifold: ContactManifold,
    normal_impulse: float,
    friction_impulse: float,
    restitution: float,
    friction: float,
    *,
    absolute_time: float,
) -> ContactRecord:
    point = manifold.points[0]
    return ContactRecord(
        manifold.body_a,
        manifold.body_b,
        absolute_time,
        point.normal_a_to_b,
        point.point,
        tuple(item.point for item in manifold.points),
        normal_impulse,
        friction_impulse,
        restitution,
        friction,
        manifold.source,
        point.feature,
    )


@dataclass(frozen=True)
class _Event:
    toi: float
    rank: int
    left: int
    right: int
    manifold: ContactManifold


def _prefer(best: _Event | None, event: _Event) -> _Event:
    if best is None:
        return event
    key = (event.toi, event.rank, event.manifold.body_a, event.manifold.body_b)
    current = (best.toi, best.rank, best.manifold.body_a, best.manifold.body_b)
    return event if key < current else best


def _earliest(
    spheres: list[SphereBody],
    boxes: list[BoxBody],
    dt: float,
    cell_size_m: float,
) -> _Event | None:
    volumes, pairs = broadphase_volumes(
        tuple(spheres), tuple(boxes), dt, cell_size_m=cell_size_m
    )
    best: _Event | None = None
    for left, right in pairs:
        first = volumes[left]
        second = volumes[right]
        if first.kind == "sphere" and second.kind == "sphere":
            manifold = sphere_sphere_manifold(
                spheres[first.index], spheres[second.index], dt
            )
            rank = 0
        elif first.kind == "sphere" and second.kind == "box":
            manifold = sphere_box_manifold(
                spheres[first.index], boxes[second.index], dt
            )
            rank = 1
        elif first.kind == "box" and second.kind == "sphere":
            manifold = sphere_box_manifold(
                spheres[second.index], boxes[first.index], dt
            )
            rank = 1
        else:
            continue
        if manifold is None:
            continue
        if first.kind == "sphere" and second.kind == "sphere":
            normal = Vec3(*manifold.points[0].normal_a_to_b)
            relative = Vec3(*spheres[second.index].velocity) - Vec3(
                *spheres[first.index].velocity
            )
            if _resting(manifold, relative.dot(normal)):
                continue
        else:
            sphere_index = first.index if first.kind == "sphere" else second.index
            box_index = second.index if second.kind == "box" else first.index
            normal = Vec3(*manifold.points[0].normal_a_to_b)
            relative = Vec3(*boxes[box_index].velocity) - Vec3(
                *spheres[sphere_index].velocity
            )
            if _resting(manifold, relative.dot(normal)):
                continue
        best = _prefer(
            best, _Event(manifold.time_of_impact_s, rank, left, right, manifold)
        )
    return best


def _apply(
    spheres: list[SphereBody], boxes: list[BoxBody], event: _Event, consumed: float
) -> ContactRecord:
    if event.manifold.source.startswith("sphere_sphere"):
        left = next(
            index
            for index, body in enumerate(spheres)
            if body.body_id == event.manifold.body_a
        )
        right = next(
            index
            for index, body in enumerate(spheres)
            if body.body_id == event.manifold.body_b
        )
        solved = resolve_contact(
            _as_rigid(spheres[left]),
            _as_rigid(spheres[right]),
            collision_contact(
                event.manifold.points[0],
                math.sqrt(spheres[left].friction * spheres[right].friction),
                min(spheres[left].restitution, spheres[right].restitution),
            ),
        )
        if solved.body_b is None:
            raise ContactRejected("dynamic contact lost the second body")
        friction = math.sqrt(spheres[left].friction * spheres[right].friction)
        restitution = min(spheres[left].restitution, spheres[right].restitution)
        spheres[left] = _from_rigid(spheres[left], solved.body_a, Vec3(0.0, 0.0, 0.0))
        spheres[right] = _from_rigid(spheres[right], solved.body_b, Vec3(0.0, 0.0, 0.0))
        return _record(
            event.manifold,
            solved.normal_impulse_ns,
            solved.friction_impulse_ns,
            restitution,
            friction,
            absolute_time=consumed,
        )
    sphere_id = event.manifold.body_a
    box_id = event.manifold.body_b
    sphere_index = next(
        index for index, body in enumerate(spheres) if body.body_id == sphere_id
    )
    box_index = next(
        index for index, body in enumerate(boxes) if body.body_id == box_id
    )
    box = boxes[box_index]
    sphere = spheres[sphere_index]
    relative = _as_rigid(sphere, Vec3(*sphere.velocity) - Vec3(*box.velocity))
    solved = resolve_contact(
        relative,
        None,
        collision_contact(event.manifold.points[0], box.friction, box.restitution),
    )
    spheres[sphere_index] = _from_rigid(sphere, solved.body_a, Vec3(*box.velocity))
    friction = math.sqrt(sphere.friction * box.friction)
    restitution = min(sphere.restitution, box.restitution)
    return _record(
        event.manifold,
        solved.normal_impulse_ns,
        solved.friction_impulse_ns,
        restitution,
        friction,
        absolute_time=consumed,
    )


def step_contacts(
    spheres: tuple[SphereBody, ...],
    boxes: tuple[BoxBody, ...],
    dt: float,
    *,
    iteration_cap: int = 16,
    cell_size_m: float = 1.0,
) -> ContactStepResult:
    """Sweep candidate pairs, then resolve the earliest manifold.

    Terrain bounds are rebuilt from the current center, half extents and
    velocity before the first query and again after every accepted sub-step.
    """
    step = _validate_dt(dt)
    cap = _validate_cap(iteration_cap)
    _validate_population(spheres, boxes)
    try:
        return _step(spheres, boxes, step, cap, cell_size_m)
    except ContactRejected:
        raise
    except _SOLVER_ERRORS as exc:
        raise ContactRejected(str(exc)) from exc


def _step(
    spheres: tuple[SphereBody, ...],
    boxes: tuple[BoxBody, ...],
    dt: float,
    iteration_cap: int,
    cell_size_m: float,
) -> ContactStepResult:
    current_spheres = list(spheres)
    current_boxes = list(boxes)
    queried = swept_bounds(tuple(current_spheres), tuple(current_boxes), dt)
    receipts: list[ContactRecord] = []
    consumed = 0.0
    used = 0
    for iteration in range(iteration_cap):
        remaining = dt - consumed
        if remaining <= 1e-12:
            break
        event = _earliest(current_spheres, current_boxes, remaining, cell_size_m)
        if event is None:
            current_spheres = [
                _advance_sphere(body, remaining) for body in current_spheres
            ]
            current_boxes = [_advance_box(body, remaining) for body in current_boxes]
            consumed = dt
            break
        used = iteration + 1
        if event.toi > 0.0:
            current_spheres = [
                _advance_sphere(body, event.toi) for body in current_spheres
            ]
            current_boxes = [_advance_box(body, event.toi) for body in current_boxes]
            consumed += event.toi
        receipts.append(_apply(current_spheres, current_boxes, event, consumed))
    else:
        remaining = dt - consumed
        if (
            remaining > 1e-12
            and _earliest(current_spheres, current_boxes, remaining, cell_size_m)
            is None
        ):
            current_spheres = [
                _advance_sphere(body, remaining) for body in current_spheres
            ]
            current_boxes = [_advance_box(body, remaining) for body in current_boxes]
    return ContactStepResult(
        tuple(current_spheres), tuple(current_boxes), tuple(receipts), queried, used
    )


class ContactRuntime:
    """Holds committed spheres and terrain. A rejected step leaves both in place."""

    def __init__(
        self, spheres: tuple[SphereBody, ...], boxes: tuple[BoxBody, ...] = ()
    ) -> None:
        _validate_population(tuple(spheres), tuple(boxes))
        self._spheres = tuple(spheres)
        self._boxes = tuple(boxes)

    @property
    def spheres(self) -> tuple[SphereBody, ...]:
        return self._spheres

    @property
    def boxes(self) -> tuple[BoxBody, ...]:
        return self._boxes

    def step(
        self, dt: float, *, iteration_cap: int = 16, cell_size_m: float = 1.0
    ) -> ContactStepResult:
        prior_spheres = self._spheres
        prior_boxes = self._boxes
        try:
            result = step_contacts(
                prior_spheres,
                prior_boxes,
                dt,
                iteration_cap=iteration_cap,
                cell_size_m=cell_size_m,
            )
        except ContactRejected:
            self._spheres = prior_spheres
            self._boxes = prior_boxes
            raise
        self._spheres = result.spheres
        self._boxes = result.boxes
        return result
