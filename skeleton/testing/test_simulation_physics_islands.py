"""Deterministic physics island graph and solve regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    DistanceJoint,
    PhysicsMaterial,
    PhysicsSettings,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    SphereShape,
    Vec3,
    detect_collision,
)
from skeleton.simulation.physics.islands import build_islands


def _dynamic(
    body_id: str,
    *,
    position: Vec3,
    awake: bool = True,
) -> RigidBody:
    body = RigidBody.dynamic(
        body_id,
        SphereShape(0.5),
        position=position,
        material=PhysicsMaterial(friction=0.4, restitution=0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    if not awake:
        body.sleep()
    return body


def test_isolated_dynamic_bodies_form_sorted_singleton_islands() -> None:
    bodies = {
        "z": _dynamic("z", position=Vec3(5.0, 0.0, 0.0)),
        "a": _dynamic("a", position=Vec3(-5.0, 0.0, 0.0)),
    }
    graph = build_islands(bodies, (), ())
    assert tuple(island.island_id for island in graph.islands) == ("a", "z")
    assert tuple(island.dynamic_bodies for island in graph.islands) == (
        ("a",),
        ("z",),
    )
    assert graph.stats.islands == 2
    assert graph.stats.largest_dynamic_body_count == 1


def test_dynamic_contact_unions_two_bodies_into_one_island() -> None:
    left = _dynamic("a", position=Vec3(-0.4, 0.0, 0.0))
    right = _dynamic("b", position=Vec3(0.4, 0.0, 0.0))
    manifold = detect_collision(left, right)
    assert manifold is not None

    graph = build_islands(
        {"a": left, "b": right},
        (manifold,),
        (),
    )
    assert len(graph.islands) == 1
    assert graph.islands[0].dynamic_bodies == ("a", "b")
    assert graph.islands[0].anchors == ()


def test_shared_static_floor_does_not_bridge_unrelated_dynamic_islands() -> None:
    ground = RigidBody.static("ground", PlaneShape())
    left = _dynamic("a", position=Vec3(-4.0, 0.5, 0.0))
    right = _dynamic("b", position=Vec3(4.0, 0.5, 0.0))
    left_contact = detect_collision(ground, left)
    right_contact = detect_collision(ground, right)
    assert left_contact is not None
    assert right_contact is not None

    graph = build_islands(
        {"a": left, "b": right, "ground": ground},
        (left_contact, right_contact),
        (),
    )
    assert tuple(island.dynamic_bodies for island in graph.islands) == (
        ("a",),
        ("b",),
    )
    assert all(island.anchors == ("ground",) for island in graph.islands)


def test_distance_joint_unions_dynamic_bodies_without_contact() -> None:
    left = _dynamic("a", position=Vec3(-2.0, 0.0, 0.0))
    right = _dynamic("b", position=Vec3(2.0, 0.0, 0.0))
    joint = DistanceJoint("link", "a", "b", rest_length=4.0)

    graph = build_islands(
        {"a": left, "b": right},
        (),
        (joint,),
    )
    assert len(graph.islands) == 1
    assert graph.islands[0].dynamic_bodies == ("a", "b")
    assert tuple(row.joint_id for row in graph.islands[0].joints) == ("link",)


def test_static_joint_anchor_does_not_bridge_two_dynamic_islands() -> None:
    anchor = RigidBody.static("anchor", SphereShape(0.5))
    left = _dynamic("a", position=Vec3(-2.0, 0.0, 0.0))
    right = _dynamic("b", position=Vec3(2.0, 0.0, 0.0))
    left_joint = DistanceJoint("left", "a", "anchor", rest_length=2.0)
    right_joint = DistanceJoint("right", "b", "anchor", rest_length=2.0)

    graph = build_islands(
        {"a": left, "anchor": anchor, "b": right},
        (),
        (right_joint, left_joint),
    )
    assert tuple(island.dynamic_bodies for island in graph.islands) == (
        ("a",),
        ("b",),
    )
    assert all(island.anchors == ("anchor",) for island in graph.islands)


def test_awake_propagation_wakes_sleeping_dynamic_neighbor() -> None:
    left = _dynamic("a", position=Vec3(-0.4, 0.0, 0.0), awake=True)
    right = _dynamic("b", position=Vec3(0.4, 0.0, 0.0), awake=False)
    manifold = detect_collision(left, right)
    assert manifold is not None
    graph = build_islands(
        {"a": left, "b": right},
        (manifold,),
        (),
    )

    assert right.awake is False
    awakened = graph.propagate_awake({"a": left, "b": right})
    assert awakened == 1
    assert right.awake is True


def test_sleeping_disconnected_island_is_not_woken_by_other_awake_island() -> None:
    left = _dynamic("a", position=Vec3(-5.0, 0.0, 0.0), awake=True)
    right = _dynamic("b", position=Vec3(5.0, 0.0, 0.0), awake=False)
    graph = build_islands({"a": left, "b": right}, (), ())

    awakened = graph.propagate_awake({"a": left, "b": right})
    assert awakened == 0
    assert left.awake is True
    assert right.awake is False


def test_world_receipt_reports_island_partition() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_dynamic("a", position=Vec3(-5.0, 0.0, 0.0)))
    world.add_body(_dynamic("b", position=Vec3(5.0, 0.0, 0.0)))

    receipt = world.step()[0]
    assert receipt.islands.islands == 2
    assert receipt.islands.dynamic_bodies == 2
    assert receipt.islands.largest_dynamic_body_count == 1


def test_shared_ground_world_remains_two_solver_islands() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    world.add_body(_dynamic("a", position=Vec3(-4.0, 0.5, 0.0)))
    world.add_body(_dynamic("b", position=Vec3(4.0, 0.5, 0.0)))

    receipt = world.step()[0]
    assert receipt.manifolds == 2
    assert receipt.islands.islands == 2
    assert receipt.islands.contact_manifolds == 2


def test_joint_connected_quiet_bodies_sleep_as_one_island() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.1,
            sleep_linear_speed=0.1,
            sleep_angular_speed=0.1,
            sleep_after_seconds=0.2,
        )
    )
    left = _dynamic("a", position=Vec3(-1.0, 0.0, 0.0))
    right = _dynamic("b", position=Vec3(1.0, 0.0, 0.0))
    world.add_body(left)
    world.add_body(right)
    world.add_joint(DistanceJoint("link", "a", "b", rest_length=2.0))

    world.step(3)

    assert left.awake is False
    assert right.awake is False


def test_force_on_one_joint_body_wakes_entire_island_before_integration() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.1,
            sleep_after_seconds=0.1,
        )
    )
    left = _dynamic("a", position=Vec3(-1.0, 0.0, 0.0))
    right = _dynamic("b", position=Vec3(1.0, 0.0, 0.0))
    world.add_body(left)
    world.add_body(right)
    world.add_joint(DistanceJoint("link", "a", "b", rest_length=2.0))
    world.step(2)
    assert not left.awake and not right.awake

    left.apply_force(Vec3(10.0, 0.0, 0.0))
    world.step()

    assert left.awake
    assert right.awake
    assert right.position.x != pytest.approx(1.0)


def test_island_graph_identity_is_independent_of_input_order() -> None:
    a = _dynamic("a", position=Vec3(-0.4, 0.0, 0.0))
    b = _dynamic("b", position=Vec3(0.4, 0.0, 0.0))
    c = _dynamic("c", position=Vec3(5.0, 0.0, 0.0))
    contact = detect_collision(a, b)
    assert contact is not None

    left = build_islands(
        {"c": c, "a": a, "b": b},
        (contact,),
        (),
    )
    right = build_islands(
        {"b": b, "a": a, "c": c},
        tuple(reversed((contact,))),
        tuple(reversed(())),
    )
    assert left == right
