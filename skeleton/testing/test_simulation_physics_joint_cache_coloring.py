"""Joint warm-start cache, snapshot, rollback, and graph-coloring regressions."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.simulation.physics import (
    ConstraintColorSchedule,
    DistanceJoint,
    DistanceLimitJoint,
    JointImpulseCache,
    JointImpulseEntry,
    PhysicsRollbackSession,
    PhysicsSettings,
    PhysicsSnapshotError,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    PointJoint,
    RigidBody,
    SliderJoint,
    SphereShape,
    Vec3,
    color_constraints,
    detect_collision,
    verify_snapshot,
)


def _dynamic(body_id: str, position: Vec3) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        SphereShape(0.5),
        position=position,
        linear_damping=0.0,
        angular_damping=0.0,
    )


def _joint_world() -> PhysicsWorld:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
            constraint_velocity_iterations=8,
            constraint_position_iterations=4,
        )
    )
    world.add_body(RigidBody.static("anchor", SphereShape(0.25)))
    world.add_body(_dynamic("body", Vec3(2.0, 0.5, 0.0)))
    world.add_joint(PointJoint("point", "anchor", "body", bias_factor=0.15))
    return world


def test_joint_cache_accepts_signed_impulses_and_stable_row_identity() -> None:
    cache = JointImpulseCache(max_entries=8, max_age_ticks=4)
    joint = DistanceJoint("joint", "a", "b", rest_length=1.0)

    entry = cache.store(
        joint,
        "distance",
        impulse=-3.5,
        tick=2,
    )

    assert entry.key == "joint\x1fdistance"
    assert entry.impulse == pytest.approx(-3.5)
    assert cache.lookup(joint, "distance", tick=3) == entry


def test_joint_cache_evicts_oldest_then_lexical_key_deterministically() -> None:
    cache = JointImpulseCache(max_entries=2, max_age_ticks=8)
    a = DistanceJoint("a", "x", "y", rest_length=1.0)
    b = DistanceJoint("b", "x", "y", rest_length=1.0)
    c = DistanceJoint("c", "x", "y", rest_length=1.0)

    cache.store(b, "distance", impulse=1.0, tick=1)
    cache.store(a, "distance", impulse=2.0, tick=1)
    cache.store(c, "distance", impulse=3.0, tick=2)

    assert cache.lookup(a, "distance", tick=2) is None
    assert cache.lookup(b, "distance", tick=2) is not None
    assert cache.lookup(c, "distance", tick=2) is not None


def test_joint_cache_age_limit_prevents_stale_warm_start() -> None:
    cache = JointImpulseCache(max_entries=4, max_age_ticks=2)
    joint = DistanceJoint("joint", "a", "b", rest_length=1.0)
    cache.store(joint, "distance", impulse=2.0, tick=1)

    assert cache.lookup(joint, "distance", tick=3) is not None
    assert cache.lookup(joint, "distance", tick=4) is None
    assert cache.prune(tick=4) == 1
    assert len(cache) == 0


def test_joint_cache_rejects_regressed_tick() -> None:
    cache = JointImpulseCache()
    joint = DistanceJoint("joint", "a", "b", rest_length=1.0)
    cache.store(joint, "distance", impulse=1.0, tick=5)

    with pytest.raises(PhysicsValidationError, match="regressed"):
        cache.lookup(joint, "distance", tick=4)


def test_joint_cache_restore_rejects_duplicate_keys() -> None:
    entry = JointImpulseEntry(
        key="joint\x1fdistance",
        joint_id="joint",
        body_a="a",
        body_b="b",
        row_id="distance",
        impulse=1.0,
        last_tick=1,
    )
    cache = JointImpulseCache()

    with pytest.raises(PhysicsValidationError, match="duplicate"):
        cache.restore((entry, entry))


def test_joint_cache_is_authoritative_world_state() -> None:
    left = _joint_world()
    right = _joint_world()

    left.step()
    right.step()
    assert left.state_digest == right.state_digest
    assert left.joint_cache_size() > 0

    right._joint_cache.restore(())  # type: ignore[attr-defined]
    assert left.get_body("body").state_record() == right.get_body("body").state_record()
    assert left.state_digest != right.state_digest


def test_second_joint_frame_reports_warm_started_rows() -> None:
    world = _joint_world()

    first = world.step()[0]
    assert first.constraints.cached_rows > 0
    assert first.constraints.warm_started_rows == 0
    assert world.joint_cache_size() == first.constraints.cached_rows

    second = world.step()[0]
    assert second.constraints.warm_started_rows > 0
    assert second.constraints.cached_rows > 0


def test_joint_cache_snapshot_roundtrip_restores_exact_state() -> None:
    world = _joint_world()
    world.step(2)
    snapshot = world.capture_snapshot()
    digest = world.state_digest
    cached = snapshot.joint_cache
    assert cached

    world._joint_cache.restore(())  # type: ignore[attr-defined]
    assert world.state_digest != digest

    world.restore_snapshot(snapshot)
    assert world.state_digest == digest
    assert world.capture_snapshot().joint_cache == cached


def test_joint_cache_tampering_invalidates_snapshot_digest() -> None:
    world = _joint_world()
    world.step()
    snapshot = world.capture_snapshot()
    assert snapshot.joint_cache
    entry = snapshot.joint_cache[0]
    tampered_entry = replace(entry, impulse=entry.impulse + 1.0)
    tampered = replace(
        snapshot,
        joint_cache=(tampered_entry, *snapshot.joint_cache[1:]),
    )

    with pytest.raises(PhysicsSnapshotError, match="digest"):
        verify_snapshot(tampered)


def test_rollback_resimulation_with_joint_cache_is_exact() -> None:
    world = _joint_world()
    session = PhysicsRollbackSession(world, capacity=32)
    receipts = session.step(5)
    assert receipts[-1].constraints.cached_rows > 0
    final_digest = world.state_digest
    final_snapshot = world.capture_snapshot()

    session.rollback_to(2)
    session.resimulate_to(5)

    assert world.state_digest == final_digest
    assert world.capture_snapshot() == final_snapshot


def test_joint_removal_clears_all_cached_rows_for_joint() -> None:
    world = _joint_world()
    world.step()
    assert world.joint_cache_size() > 0

    world.remove_joint("point")

    assert world.joint_cache_size() == 0


def test_failed_tick_after_joint_cache_mutation_rolls_back_cache_exactly() -> None:
    world = _joint_world()
    world.step()
    before = world.capture_snapshot()
    before_digest = world.state_digest

    original_update_sleep = world._update_sleep  # type: ignore[attr-defined]

    def _fail_after_solve(graph, dt):
        del graph, dt
        raise RuntimeError("post-constraint synthetic failure")

    world._update_sleep = _fail_after_solve  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="post-constraint"):
            world.step()
    finally:
        world._update_sleep = original_update_sleep  # type: ignore[method-assign]

    assert world.state_digest == before_digest
    assert world.capture_snapshot() == before


def test_lower_and_upper_distance_limit_rows_have_distinct_cache_identity() -> None:
    cache = JointImpulseCache()
    joint = DistanceLimitJoint(
        "limit",
        "a",
        "b",
        minimum_length=1.0,
        maximum_length=2.0,
    )
    cache.store(joint, "limit:upper", impulse=-2.0, tick=1)

    assert cache.lookup(joint, "limit:lower", tick=2) is None
    assert cache.lookup(joint, "limit:upper", tick=2) is not None


def test_opposite_slider_stops_do_not_share_warm_start_impulse() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.01,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("anchor", SphereShape(0.25)))
    body = _dynamic("body", Vec3(3.0, 0.0, 0.0))
    world.add_body(body)
    world.add_joint(
        SliderJoint(
            "slider",
            "anchor",
            "body",
            lower_translation=-1.0,
            upper_translation=1.0,
        )
    )
    world.step()
    upper = world._joint_cache.lookup(  # type: ignore[attr-defined]
        world.get_joint("slider"),
        "limit:upper",
        tick=world.tick,
    )
    assert upper is not None

    body.position = Vec3(-3.0, 0.0, 0.0)
    body.linear_velocity = Vec3.zero()
    lower = world._joint_cache.lookup(  # type: ignore[attr-defined]
        world.get_joint("slider"),
        "limit:lower",
        tick=world.tick + 1,
    )
    assert lower is None


def _ground_contacts_for_two_bodies():
    ground = RigidBody.static("ground", PlaneShape())
    left = _dynamic("a", Vec3(-3.0, 0.5, 0.0))
    right = _dynamic("b", Vec3(3.0, 0.5, 0.0))
    left_contact = detect_collision(ground, left)
    right_contact = detect_collision(ground, right)
    assert left_contact is not None
    assert right_contact is not None
    bodies = {"ground": ground, "a": left, "b": right}
    return bodies, left_contact, right_contact


def test_coloring_allows_independent_contacts_sharing_static_anchor_same_batch() -> None:
    bodies, left_contact, right_contact = _ground_contacts_for_two_bodies()

    schedule = color_constraints(
        bodies,
        (right_contact, left_contact),
        (),
    )

    assert isinstance(schedule, ConstraintColorSchedule)
    assert schedule.stats.colors == 1
    assert schedule.stats.constraints == 2
    assert schedule.stats.contact_constraints == 2
    assert schedule.batches[0].dynamic_bodies == ("a", "b")
    assert schedule.batches[0].constraints == 2


def test_coloring_separates_constraints_that_share_dynamic_body() -> None:
    a = _dynamic("a", Vec3(-2.0, 0.0, 0.0))
    b = _dynamic("b", Vec3.zero())
    c = _dynamic("c", Vec3(2.0, 0.0, 0.0))
    joints = (
        DistanceJoint("ab", "a", "b", rest_length=2.0),
        DistanceJoint("bc", "b", "c", rest_length=2.0),
    )

    schedule = color_constraints(
        {"a": a, "b": b, "c": c},
        (),
        joints,
    )

    assert schedule.stats.colors == 2
    assert tuple(batch.constraints for batch in schedule.batches) == (1, 1)
    assert schedule.batches[0].dynamic_bodies == ("a", "b")
    assert schedule.batches[1].dynamic_bodies == ("b", "c")


def test_coloring_coalesces_disconnected_joint_edges() -> None:
    bodies = {
        "a": _dynamic("a", Vec3(-6.0, 0.0, 0.0)),
        "b": _dynamic("b", Vec3(-4.0, 0.0, 0.0)),
        "c": _dynamic("c", Vec3(4.0, 0.0, 0.0)),
        "d": _dynamic("d", Vec3(6.0, 0.0, 0.0)),
    }
    joints = (
        DistanceJoint("ab", "a", "b", rest_length=2.0),
        DistanceJoint("cd", "c", "d", rest_length=2.0),
    )

    schedule = color_constraints(bodies, (), tuple(reversed(joints)))

    assert schedule.stats.colors == 1
    assert schedule.batches[0].constraints == 2
    assert schedule.batches[0].dynamic_bodies == ("a", "b", "c", "d")


def test_coloring_contact_and_joint_sharing_dynamic_body_conflict() -> None:
    ground = RigidBody.static("ground", PlaneShape())
    a = _dynamic("a", Vec3(0.0, 0.5, 0.0))
    b = _dynamic("b", Vec3(2.0, 0.5, 0.0))
    contact = detect_collision(ground, a)
    assert contact is not None
    joint = DistanceJoint("ab", "a", "b", rest_length=2.0)

    schedule = color_constraints(
        {"ground": ground, "a": a, "b": b},
        (contact,),
        (joint,),
    )

    assert schedule.stats.colors == 2


def test_coloring_is_deterministic_under_input_order_permutation() -> None:
    bodies, left_contact, right_contact = _ground_contacts_for_two_bodies()
    anchor = RigidBody.static("anchor", SphereShape(0.25))
    c = _dynamic("c", Vec3(10.0, 0.0, 0.0))
    bodies["anchor"] = anchor
    bodies["c"] = c
    joint = DistanceJoint("anchor-c", "anchor", "c", rest_length=10.0)

    forward = color_constraints(
        bodies,
        (left_contact, right_contact),
        (joint,),
    )
    reverse = color_constraints(
        dict(reversed(tuple(bodies.items()))),
        (right_contact, left_contact),
        (joint,),
    )

    assert forward == reverse


def test_world_constraint_schedule_exposes_current_contact_and_joint_graph() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    world.add_body(_dynamic("a", Vec3(-2.0, 0.5, 0.0)))
    world.add_body(_dynamic("b", Vec3(2.0, 0.5, 0.0)))
    world.add_joint(DistanceJoint("link", "a", "b", rest_length=4.0))

    world.step()
    schedule = world.constraint_schedule()

    assert schedule.stats.contact_constraints == 2
    assert schedule.stats.joint_constraints == 1
    assert schedule.stats.constraints == 3
    for batch in schedule.batches:
        assert len(batch.dynamic_bodies) == len(set(batch.dynamic_bodies))


def test_joint_cache_settings_change_physics_configuration_identity() -> None:
    left = PhysicsWorld(PhysicsSettings(joint_cache_entries=32))
    right = PhysicsWorld(PhysicsSettings(joint_cache_entries=64))
    assert left.settings.fingerprint != right.settings.fingerprint
    assert left.configuration_digest != right.configuration_digest
