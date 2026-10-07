"""Deterministic constraint graph coloring for parallel-ready solver batches.

A color batch never contains two constraints that mutate the same dynamic body.
Static and kinematic anchors are excluded from conflicts because the iterative
solver does not update their velocity/state through constraint impulses.

The schedule is deterministic: inputs are canonicalized, edges are sorted by
stable identity, and a greedy lowest-color assignment is used.
"""
from __future__ import annotations

from dataclasses import dataclass

from .body import BodyType, RigidBody
from .collision import ContactManifold
from .constraints import JointConstraint
from .errors import BodyNotFoundError, PhysicsValidationError


@dataclass(frozen=True, slots=True)
class ConstraintColorBatch:
    color: int
    manifolds: tuple[ContactManifold, ...]
    joints: tuple[JointConstraint, ...]
    dynamic_bodies: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.color, bool) or not isinstance(self.color, int) or self.color < 0:
            raise PhysicsValidationError("constraint color must be non-negative integer")
        if tuple(sorted(self.dynamic_bodies)) != self.dynamic_bodies:
            raise PhysicsValidationError("constraint color dynamic bodies must be sorted")
        if len(set(self.dynamic_bodies)) != len(self.dynamic_bodies):
            raise PhysicsValidationError("constraint color dynamic bodies must be unique")

    @property
    def constraints(self) -> int:
        return len(self.manifolds) + len(self.joints)


@dataclass(frozen=True, slots=True)
class ConstraintColorStats:
    colors: int
    constraints: int
    contact_constraints: int
    joint_constraints: int
    largest_batch: int
    largest_dynamic_body_set: int


@dataclass(frozen=True, slots=True)
class ConstraintColorSchedule:
    batches: tuple[ConstraintColorBatch, ...]
    stats: ConstraintColorStats

    def __post_init__(self) -> None:
        if tuple(batch.color for batch in self.batches) != tuple(range(len(self.batches))):
            raise PhysicsValidationError("constraint colors must be contiguous from zero")


@dataclass(frozen=True, slots=True)
class _Edge:
    sort_key: tuple[object, ...]
    dynamic_bodies: tuple[str, ...]
    manifold: ContactManifold | None = None
    joint: JointConstraint | None = None

    def __post_init__(self) -> None:
        if (self.manifold is None) == (self.joint is None):
            raise PhysicsValidationError("constraint color edge must bind exactly one constraint")
        if not self.dynamic_bodies:
            raise PhysicsValidationError("constraint color edge requires dynamic body")
        if tuple(sorted(self.dynamic_bodies)) != self.dynamic_bodies:
            raise PhysicsValidationError("constraint edge dynamic bodies must be sorted")


def _body(bodies: dict[str, RigidBody], body_id: str) -> RigidBody:
    try:
        return bodies[body_id]
    except KeyError as exc:
        raise BodyNotFoundError(body_id) from exc


def _dynamic_participants(
    bodies: dict[str, RigidBody],
    body_a: str,
    body_b: str,
) -> tuple[str, ...]:
    first = _body(bodies, body_a)
    second = _body(bodies, body_b)
    return tuple(
        sorted(
            body.body_id
            for body in (first, second)
            if body.body_type is BodyType.DYNAMIC
        )
    )


def _contact_key(manifold: ContactManifold) -> tuple[object, ...]:
    return (
        0,
        manifold.body_a,
        manifold.body_b,
        tuple(point.feature_id for point in manifold.points),
    )


def _joint_key(joint: JointConstraint) -> tuple[object, ...]:
    return (1, joint.joint_id, joint.body_a, joint.body_b, joint.kind.value)


def color_constraints(
    bodies: dict[str, RigidBody],
    manifolds: tuple[ContactManifold, ...],
    joints: tuple[JointConstraint, ...],
) -> ConstraintColorSchedule:
    edges: list[_Edge] = []

    for manifold in manifolds:
        participants = _dynamic_participants(
            bodies,
            manifold.body_a,
            manifold.body_b,
        )
        if not participants:
            continue
        edges.append(
            _Edge(
                sort_key=_contact_key(manifold),
                dynamic_bodies=participants,
                manifold=manifold,
            )
        )

    for joint in joints:
        participants = _dynamic_participants(
            bodies,
            joint.body_a,
            joint.body_b,
        )
        if not participants:
            continue
        edges.append(
            _Edge(
                sort_key=_joint_key(joint),
                dynamic_bodies=participants,
                joint=joint,
            )
        )

    edges.sort(key=lambda edge: edge.sort_key)
    used_by_color: list[set[str]] = []
    edges_by_color: list[list[_Edge]] = []

    for edge in edges:
        participants = set(edge.dynamic_bodies)
        selected = None
        for color, used in enumerate(used_by_color):
            if used.isdisjoint(participants):
                selected = color
                break
        if selected is None:
            selected = len(used_by_color)
            used_by_color.append(set())
            edges_by_color.append([])
        used_by_color[selected].update(participants)
        edges_by_color[selected].append(edge)

    batches: list[ConstraintColorBatch] = []
    for color, color_edges in enumerate(edges_by_color):
        manifolds_in_color = tuple(
            edge.manifold
            for edge in color_edges
            if edge.manifold is not None
        )
        joints_in_color = tuple(
            edge.joint
            for edge in color_edges
            if edge.joint is not None
        )
        dynamic_bodies = tuple(
            sorted(
                body_id
                for edge in color_edges
                for body_id in edge.dynamic_bodies
            )
        )
        if len(set(dynamic_bodies)) != len(dynamic_bodies):
            raise PhysicsValidationError(
                "constraint coloring produced a dynamic-body conflict"
            )
        batches.append(
            ConstraintColorBatch(
                color=color,
                manifolds=manifolds_in_color,
                joints=joints_in_color,
                dynamic_bodies=dynamic_bodies,
            )
        )

    result = tuple(batches)
    stats = ConstraintColorStats(
        colors=len(result),
        constraints=len(edges),
        contact_constraints=sum(1 for edge in edges if edge.manifold is not None),
        joint_constraints=sum(1 for edge in edges if edge.joint is not None),
        largest_batch=max((batch.constraints for batch in result), default=0),
        largest_dynamic_body_set=max(
            (len(batch.dynamic_bodies) for batch in result),
            default=0,
        ),
    )
    return ConstraintColorSchedule(result, stats)
