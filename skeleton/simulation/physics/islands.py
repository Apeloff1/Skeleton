"""Deterministic contact/joint islands and parallel-ready solve partitions."""
from __future__ import annotations

from dataclasses import dataclass

from .body import BodyType, RigidBody
from .collision import ContactManifold
from .constraints import ConstraintSolver, ConstraintStats, JointConstraint
from .contacts import ContactCache
from .errors import BodyNotFoundError, PhysicsValidationError
from .joint_cache import JointImpulseCache
from .solver import SequentialImpulseSolver, SolverStats


@dataclass(frozen=True, slots=True)
class PhysicsIsland:
    """One independent dynamic solve component.

    dynamic_bodies contains only BodyType.DYNAMIC nodes. Static and kinematic
    bodies referenced by contacts/joints are anchors and do not connect otherwise
    independent dynamic components through their infinite/prescribed mass state.
    """

    island_id: str
    dynamic_bodies: tuple[str, ...]
    anchors: tuple[str, ...]
    manifolds: tuple[ContactManifold, ...]
    joints: tuple[JointConstraint, ...]
    awake: bool

    def __post_init__(self) -> None:
        if not self.island_id:
            raise PhysicsValidationError("island_id must be non-empty")
        if not self.dynamic_bodies:
            raise PhysicsValidationError("physics island requires dynamic body")
        if tuple(sorted(self.dynamic_bodies)) != self.dynamic_bodies:
            raise PhysicsValidationError("island dynamic bodies must be sorted")
        if len(set(self.dynamic_bodies)) != len(self.dynamic_bodies):
            raise PhysicsValidationError("island dynamic bodies must be unique")
        if self.island_id != self.dynamic_bodies[0]:
            raise PhysicsValidationError(
                "island_id must equal lexically first dynamic body"
            )
        if tuple(sorted(self.anchors)) != self.anchors:
            raise PhysicsValidationError("island anchors must be sorted")
        if len(set(self.anchors)) != len(self.anchors):
            raise PhysicsValidationError("island anchors must be unique")
        if set(self.dynamic_bodies) & set(self.anchors):
            raise PhysicsValidationError("island anchors cannot be dynamic nodes")
        if not isinstance(self.awake, bool):
            raise PhysicsValidationError("island awake must be boolean")

    def state_record(self) -> dict[str, object]:
        return {
            "island_id": self.island_id,
            "dynamic_bodies": self.dynamic_bodies,
            "anchors": self.anchors,
            "contacts": tuple(
                (
                    manifold.body_a,
                    manifold.body_b,
                    tuple(point.feature_id for point in manifold.points),
                )
                for manifold in self.manifolds
            ),
            "joints": tuple(joint.joint_id for joint in self.joints),
            "awake": self.awake,
        }


@dataclass(frozen=True, slots=True)
class IslandGraphStats:
    islands: int
    dynamic_bodies: int
    contact_manifolds: int
    joints: int
    awake_islands: int
    sleeping_islands: int
    largest_dynamic_body_count: int


@dataclass(frozen=True, slots=True)
class IslandGraph:
    islands: tuple[PhysicsIsland, ...]
    stats: IslandGraphStats

    def __post_init__(self) -> None:
        if tuple(sorted(row.island_id for row in self.islands)) != tuple(
            row.island_id for row in self.islands
        ):
            raise PhysicsValidationError("islands must be sorted by island_id")

    def propagate_awake(self, bodies: dict[str, RigidBody]) -> int:
        """Wake all dynamic nodes in any island containing one awake node."""

        awakened = 0
        for island in self.islands:
            if not island.awake:
                continue
            for body_id in island.dynamic_bodies:
                body = bodies[body_id]
                if not body.awake:
                    body.wake()
                    awakened += 1
        return awakened


class _UnionFind:
    def __init__(self, body_ids: tuple[str, ...]) -> None:
        self.parent = {body_id: body_id for body_id in body_ids}

    def find(self, body_id: str) -> str:
        parent = self.parent[body_id]
        while parent != self.parent[parent]:
            parent = self.parent[parent]
        root = parent
        current = body_id
        while self.parent[current] != current:
            following = self.parent[current]
            self.parent[current] = root
            current = following
        return root

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        # Stable lexical root selection makes graph identity independent of
        # traversal order.
        if root_left < root_right:
            self.parent[root_right] = root_left
        else:
            self.parent[root_left] = root_right


def _body(
    bodies: dict[str, RigidBody],
    body_id: str,
) -> RigidBody:
    try:
        return bodies[body_id]
    except KeyError as exc:
        raise BodyNotFoundError(body_id) from exc


def build_islands(
    bodies: dict[str, RigidBody],
    manifolds: tuple[ContactManifold, ...],
    joints: tuple[JointConstraint, ...],
) -> IslandGraph:
    dynamic_ids = tuple(
        sorted(
            body_id
            for body_id, body in bodies.items()
            if body.body_type is BodyType.DYNAMIC
        )
    )
    union = _UnionFind(dynamic_ids)
    dynamic_set = set(dynamic_ids)

    ordered_manifolds = tuple(
        sorted(
            manifolds,
            key=lambda row: (
                row.body_a,
                row.body_b,
                tuple(point.feature_id for point in row.points),
            ),
        )
    )
    ordered_joints = tuple(sorted(joints, key=lambda row: row.joint_id))

    for manifold in ordered_manifolds:
        _body(bodies, manifold.body_a)
        _body(bodies, manifold.body_b)
        if manifold.body_a in dynamic_set and manifold.body_b in dynamic_set:
            union.union(manifold.body_a, manifold.body_b)

    for joint in ordered_joints:
        _body(bodies, joint.body_a)
        _body(bodies, joint.body_b)
        if joint.body_a in dynamic_set and joint.body_b in dynamic_set:
            union.union(joint.body_a, joint.body_b)

    members: dict[str, list[str]] = {}
    for body_id in dynamic_ids:
        root = union.find(body_id)
        members.setdefault(root, []).append(body_id)

    islands: list[PhysicsIsland] = []
    for root in sorted(members):
        component = tuple(sorted(members[root]))
        component_set = set(component)

        component_manifolds = tuple(
            manifold
            for manifold in ordered_manifolds
            if manifold.body_a in component_set
            or manifold.body_b in component_set
        )
        component_joints = tuple(
            joint
            for joint in ordered_joints
            if joint.body_a in component_set
            or joint.body_b in component_set
        )

        anchors: set[str] = set()
        for manifold in component_manifolds:
            for body_id in (manifold.body_a, manifold.body_b):
                if body_id not in component_set:
                    anchors.add(body_id)
        for joint in component_joints:
            for body_id in (joint.body_a, joint.body_b):
                if body_id not in component_set:
                    anchors.add(body_id)

        awake = any(bodies[body_id].awake for body_id in component)
        islands.append(
            PhysicsIsland(
                island_id=component[0],
                dynamic_bodies=component,
                anchors=tuple(sorted(anchors)),
                manifolds=component_manifolds,
                joints=component_joints,
                awake=awake,
            )
        )

    result = tuple(sorted(islands, key=lambda row: row.island_id))
    stats = IslandGraphStats(
        islands=len(result),
        dynamic_bodies=len(dynamic_ids),
        contact_manifolds=len(ordered_manifolds),
        joints=len(ordered_joints),
        awake_islands=sum(1 for row in result if row.awake),
        sleeping_islands=sum(1 for row in result if not row.awake),
        largest_dynamic_body_count=max(
            (len(row.dynamic_bodies) for row in result),
            default=0,
        ),
    )
    return IslandGraph(result, stats)


@dataclass(frozen=True, slots=True)
class IslandSolveReceipt:
    graph: IslandGraphStats
    solver: SolverStats
    constraints: ConstraintStats


def solve_islands(
    bodies: dict[str, RigidBody],
    graph: IslandGraph,
    *,
    contact_solver: SequentialImpulseSolver,
    constraint_solver: ConstraintSolver,
    cache: ContactCache,
    joint_cache: JointImpulseCache,
    tick: int,
    dt: float,
) -> IslandSolveReceipt:
    normal_impulses = 0
    friction_impulses = 0
    position_corrections = 0
    warm_started_contacts = 0
    maximum_penetration = 0.0

    joint_count = 0
    joint_velocity_impulses = 0
    joint_position_corrections = 0
    maximum_joint_error = 0.0
    distance_joints = 0
    point_joints = 0
    spring_joints = 0
    limit_joints = 0
    hinge_joints = 0
    fixed_joints = 0
    slider_joints = 0
    warm_started_rows = 0

    for island in graph.islands:
        if island.manifolds:
            contact_stats = contact_solver.solve(
                bodies,
                island.manifolds,
                cache=cache,
                tick=tick,
            )
            normal_impulses += contact_stats.normal_impulses
            friction_impulses += contact_stats.friction_impulses
            position_corrections += contact_stats.position_corrections
            warm_started_contacts += contact_stats.warm_started_contacts
            maximum_penetration = max(
                maximum_penetration,
                contact_stats.maximum_penetration,
            )

        if island.joints:
            joint_stats = constraint_solver.solve(
                bodies,
                island.joints,
                dt=dt,
                cache=joint_cache,
                tick=tick,
            )
            joint_count += joint_stats.joints
            joint_velocity_impulses += joint_stats.velocity_impulses
            joint_position_corrections += joint_stats.position_corrections
            maximum_joint_error = max(
                maximum_joint_error,
                joint_stats.maximum_error,
            )
            distance_joints += joint_stats.distance_joints
            point_joints += joint_stats.point_joints
            spring_joints += joint_stats.spring_joints
            limit_joints += joint_stats.limit_joints
            hinge_joints += joint_stats.hinge_joints
            fixed_joints += joint_stats.fixed_joints
            slider_joints += joint_stats.slider_joints
            warm_started_rows += joint_stats.warm_started_rows

    cache.prune(tick=tick)
    return IslandSolveReceipt(
        graph=graph.stats,
        solver=SolverStats(
            velocity_iterations=contact_solver.velocity_iterations,
            position_iterations=contact_solver.position_iterations,
            normal_impulses=normal_impulses,
            friction_impulses=friction_impulses,
            position_corrections=position_corrections,
            maximum_penetration=maximum_penetration,
            warm_started_contacts=warm_started_contacts,
            cached_contacts=len(cache),
        ),
        constraints=ConstraintStats(
            joints=joint_count,
            velocity_impulses=joint_velocity_impulses,
            position_corrections=joint_position_corrections,
            maximum_error=maximum_joint_error,
            distance_joints=distance_joints,
            point_joints=point_joints,
            spring_joints=spring_joints,
            limit_joints=limit_joints,
            hinge_joints=hinge_joints,
            fixed_joints=fixed_joints,
            slider_joints=slider_joints,
            warm_started_rows=warm_started_rows,
            cached_rows=len(joint_cache),
        ),
    )
