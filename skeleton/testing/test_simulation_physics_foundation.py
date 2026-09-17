"""Contract tests for the deterministic 3D physics foundation."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    AABB,
    BodyType,
    BoxShape,
    GamePhysicsProfile,
    GameplayScale,
    PhysicsMaterial,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    Ray,
    RigidBody,
    SphereShape,
    SweepAndPruneBroadPhase,
    Vec3,
    detect_collision,
)


def test_vec3_dot_cross_and_normalization() -> None:
    x = Vec3.axis(0)
    y = Vec3.axis(1)
    assert x.dot(y) == 0.0
    assert x.cross(y) == Vec3.axis(2)
    assert Vec3(3.0, 0.0, 4.0).normalized().length() == pytest.approx(1.0)


def test_vec3_rejects_non_finite_state() -> None:
    with pytest.raises(PhysicsValidationError):
        Vec3(float("nan"), 0.0, 0.0)
    with pytest.raises(PhysicsValidationError):
        Vec3(0.0, float("inf"), 0.0)


def test_quaternion_axis_angle_rotates_vector() -> None:
    rotation = Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5)
    result = rotation.rotate(Vec3.axis(0))
    assert result.x == pytest.approx(0.0, abs=1.0e-9)
    assert result.y == pytest.approx(1.0, abs=1.0e-9)
    assert result.z == pytest.approx(0.0, abs=1.0e-9)


def test_quaternion_angular_integration_preserves_unit_length() -> None:
    orientation = Quat.identity()
    for _ in range(100):
        orientation = orientation.integrate_world_angular_velocity(Vec3(0.0, 2.0, 0.0), 0.01)
    assert orientation.length_squared() == pytest.approx(1.0, abs=1.0e-9)


def test_aabb_overlap_and_query_geometry() -> None:
    left = AABB.from_center_half_extents(Vec3.zero(), Vec3.one())
    touching = AABB.from_center_half_extents(Vec3(2.0, 0.0, 0.0), Vec3.one())
    apart = AABB.from_center_half_extents(Vec3(3.0, 0.0, 0.0), Vec3.one())
    assert left.overlaps(touching)
    assert not left.overlaps(apart)


def test_sphere_mass_and_inertia_are_analytic() -> None:
    shape = SphereShape(2.0)
    props = shape.mass_properties(3.0)
    expected_mass = 3.0 * (4.0 / 3.0) * math.pi * 8.0
    expected_inertia = (2.0 / 5.0) * expected_mass * 4.0
    assert props.mass == pytest.approx(expected_mass)
    assert props.inertia.m00 == pytest.approx(expected_inertia)
    assert props.inertia.m11 == pytest.approx(expected_inertia)
    assert props.inertia.m22 == pytest.approx(expected_inertia)


def test_box_mass_and_principal_inertia_are_analytic() -> None:
    shape = BoxShape(Vec3(1.0, 2.0, 3.0))
    props = shape.mass_properties(2.0)
    assert props.mass == pytest.approx(96.0)
    assert props.inertia.m00 == pytest.approx((96.0 / 3.0) * (4.0 + 9.0))
    assert props.inertia.m11 == pytest.approx((96.0 / 3.0) * (1.0 + 9.0))
    assert props.inertia.m22 == pytest.approx((96.0 / 3.0) * (1.0 + 4.0))


def test_plane_offset_is_signed() -> None:
    assert PlaneShape(offset=-2.5).offset == -2.5


def test_dynamic_body_derives_mass_from_shape_density() -> None:
    body = RigidBody.dynamic("ball", SphereShape(1.0), density=2.0)
    assert body.body_type is BodyType.DYNAMIC
    assert body.mass == pytest.approx((8.0 / 3.0) * math.pi)
    assert body.inverse_mass == pytest.approx(1.0 / body.mass)


def test_linear_impulse_changes_momentum_by_impulse() -> None:
    body = RigidBody.dynamic("ball", SphereShape(1.0), density=1.0)
    impulse = Vec3(3.0, -2.0, 1.0)
    before = body.linear_velocity * body.mass
    body.apply_impulse(impulse)
    after = body.linear_velocity * body.mass
    assert after - before == impulse


def test_off_center_impulse_generates_angular_velocity() -> None:
    body = RigidBody.dynamic("box", BoxShape(Vec3.one()), density=1.0)
    body.apply_impulse(Vec3(1.0, 0.0, 0.0), point=Vec3(0.0, 1.0, 0.0))
    assert body.angular_velocity.z < 0.0


def test_static_body_ignores_force_and_impulse() -> None:
    body = RigidBody.static("wall", BoxShape(Vec3.one()))
    body.apply_force(Vec3(100.0, 0.0, 0.0))
    body.apply_impulse(Vec3(100.0, 0.0, 0.0))
    assert body.position == Vec3.zero()
    assert body.linear_velocity == Vec3.zero()
    assert body.force == Vec3.zero()


def test_broadphase_pairs_are_stable_and_skip_static_static() -> None:
    dynamic = RigidBody.dynamic("dynamic", SphereShape(1.0), position=Vec3.zero())
    static_a = RigidBody.static("a", SphereShape(1.0), position=Vec3(0.5, 0.0, 0.0))
    static_b = RigidBody.static("b", SphereShape(1.0), position=Vec3(0.75, 0.0, 0.0))
    broad = SweepAndPruneBroadPhase()
    pairs = broad.compute_pairs((static_b, dynamic, static_a))
    assert tuple((row.body_a, row.body_b) for row in pairs) == (
        ("a", "dynamic"),
        ("b", "dynamic"),
    )


def test_sphere_sphere_manifold_has_a_to_b_normal() -> None:
    a = RigidBody.dynamic("a", SphereShape(1.0), position=Vec3.zero())
    b = RigidBody.dynamic("b", SphereShape(1.0), position=Vec3(1.5, 0.0, 0.0))
    manifold = detect_collision(a, b)
    assert manifold is not None
    assert manifold.normal == Vec3.axis(0)
    assert manifold.penetration == pytest.approx(0.5)


def test_separated_spheres_do_not_collide() -> None:
    a = RigidBody.dynamic("a", SphereShape(1.0), position=Vec3.zero())
    b = RigidBody.dynamic("b", SphereShape(1.0), position=Vec3(2.1, 0.0, 0.0))
    assert detect_collision(a, b) is None


def test_plane_sphere_contact_points_out_of_solid_halfspace() -> None:
    ground = RigidBody.static("ground", PlaneShape())
    sphere = RigidBody.dynamic("sphere", SphereShape(1.0), position=Vec3(0.0, 0.75, 0.0))
    manifold = detect_collision(ground, sphere)
    assert manifold is not None
    assert manifold.normal == Vec3.axis(1)
    assert manifold.penetration == pytest.approx(0.25)


def test_sphere_box_collision_uses_oriented_box_frame() -> None:
    box = RigidBody.static(
        "box",
        BoxShape(Vec3(2.0, 0.5, 0.5)),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
    )
    sphere = RigidBody.dynamic(
        "sphere",
        SphereShape(0.4),
        position=Vec3(0.0, 2.2, 0.0),
    )
    manifold = detect_collision(box, sphere)
    assert manifold is not None
    assert manifold.penetration > 0.0


def test_obb_sat_rejects_rotated_separated_boxes() -> None:
    a = RigidBody.dynamic(
        "a",
        BoxShape(Vec3.one()),
        orientation=Quat.from_axis_angle(Vec3.axis(1), math.pi * 0.25),
    )
    b = RigidBody.dynamic(
        "b",
        BoxShape(Vec3.one()),
        position=Vec3(4.0, 0.0, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(1), -math.pi * 0.25),
    )
    assert detect_collision(a, b) is None


def test_obb_sat_detects_rotated_overlap() -> None:
    a = RigidBody.dynamic(
        "a",
        BoxShape(Vec3.one()),
        orientation=Quat.from_axis_angle(Vec3.axis(1), math.pi * 0.25),
    )
    b = RigidBody.dynamic(
        "b",
        BoxShape(Vec3.one()),
        position=Vec3(1.5, 0.0, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(1), -math.pi * 0.25),
    )
    manifold = detect_collision(a, b)
    assert manifold is not None
    assert manifold.penetration >= 0.0
    assert manifold.normal.dot(b.position - a.position) >= 0.0


def _zero_gravity_world() -> PhysicsWorld:
    return PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )


def test_world_integrates_constant_velocity_without_damping() -> None:
    world = _zero_gravity_world()
    body = RigidBody.dynamic(
        "body",
        SphereShape(0.5),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    body.linear_velocity = Vec3(3.0, 0.0, 0.0)
    world.add_body(body)
    world.step(120)
    assert body.position.x == pytest.approx(3.0, abs=1.0e-9)


def test_world_integrates_gravity_semi_implicitly() -> None:
    settings = PhysicsSettings(
        gravity=Vec3(0.0, -10.0, 0.0),
        fixed_dt=0.1,
        sleep_after_seconds=10.0,
    )
    world = PhysicsWorld(settings)
    body = RigidBody.dynamic(
        "body",
        SphereShape(0.5),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    world.add_body(body)
    world.step()
    assert body.linear_velocity.y == pytest.approx(-1.0)
    assert body.position.y == pytest.approx(-0.1)


def test_elastic_equal_mass_head_on_spheres_exchange_velocity_direction() -> None:
    world = _zero_gravity_world()
    material = PhysicsMaterial(friction=0.0, restitution=1.0)
    left = RigidBody.dynamic(
        "left",
        SphereShape(0.5),
        position=Vec3(-0.49, 0.0, 0.0),
        material=material,
        linear_damping=0.0,
        angular_damping=0.0,
    )
    right = RigidBody.dynamic(
        "right",
        SphereShape(0.5),
        position=Vec3(0.49, 0.0, 0.0),
        material=material,
        linear_damping=0.0,
        angular_damping=0.0,
    )
    left.linear_velocity = Vec3(1.0, 0.0, 0.0)
    right.linear_velocity = Vec3(-1.0, 0.0, 0.0)
    world.add_body(left)
    world.add_body(right)
    world.step()
    assert left.linear_velocity.x < 0.0
    assert right.linear_velocity.x > 0.0
    assert left.linear_velocity.x == pytest.approx(-1.0, abs=1.0e-8)
    assert right.linear_velocity.x == pytest.approx(1.0, abs=1.0e-8)


def test_ground_contact_prevents_persistent_downward_velocity() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
            velocity_iterations=12,
            position_iterations=5,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    ball = RigidBody.dynamic(
        "ball",
        SphereShape(0.5),
        position=Vec3(0.0, 0.55, 0.0),
        material=PhysicsMaterial(friction=0.8, restitution=0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    world.add_body(ball)
    world.step(30)
    assert ball.position.y > 0.45
    assert ball.linear_velocity.y > -0.2


def test_world_query_aabb_is_stably_ordered() -> None:
    world = _zero_gravity_world()
    world.add_body(RigidBody.dynamic("z", SphereShape(0.5), position=Vec3.zero()))
    world.add_body(RigidBody.dynamic("a", SphereShape(0.5), position=Vec3.zero()))
    query = AABB.from_center_half_extents(Vec3.zero(), Vec3.one())
    assert world.query_aabb(query) == ("a", "z")


def _deterministic_world() -> PhysicsWorld:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3(0.0, -9.81, 0.0),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    body = RigidBody.dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(0.0, 3.0, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    body.apply_impulse(Vec3(1.0, 0.0, 0.3), point=Vec3(0.0, 3.5, 0.0))
    world.add_body(body)
    return world


def test_equal_worlds_produce_equal_receipts_and_digests() -> None:
    left = _deterministic_world()
    right = _deterministic_world()
    assert left.state_digest == right.state_digest
    assert left.step(25) == right.step(25)
    assert left.state_digest == right.state_digest


def test_state_digest_binds_shape_geometry() -> None:
    left = _zero_gravity_world()
    right = _zero_gravity_world()
    left.add_body(RigidBody.dynamic("body", SphereShape(1.0)))
    right.add_body(RigidBody.dynamic("body", SphereShape(2.0)))
    assert left.state_digest != right.state_digest


def test_gameplay_jump_height_maps_to_physical_launch_speed() -> None:
    profile = GamePhysicsProfile.earth()
    jump = profile.jump_for_height(2.0)
    assert jump.launch_speed == pytest.approx(math.sqrt(2.0 * 9.81 * 2.0))
    assert jump.time_to_apex == pytest.approx(jump.launch_speed / 9.81)


def test_gameplay_scale_keeps_jump_semantics_in_game_units() -> None:
    profile = GamePhysicsProfile.earth(meters_per_unit=0.5)
    jump = profile.jump_for_height(4.0)
    assert jump.jump_height == 4.0
    assert jump.launch_speed == pytest.approx(math.sqrt(2.0 * 9.81 * 2.0) / 0.5)


def test_gameplay_fall_time_and_impact_speed_agree() -> None:
    profile = GamePhysicsProfile.earth()
    time = profile.time_to_fall(20.0)
    impact = profile.impact_speed(20.0)
    assert time == pytest.approx(math.sqrt(40.0 / 9.81))
    assert impact == pytest.approx(9.81 * time)


def test_projectile_solver_hits_target_for_each_real_arc() -> None:
    profile = GamePhysicsProfile.earth()
    origin = Vec3.zero()
    target = Vec3(20.0, 2.0, 0.0)
    solutions = profile.projectile_solutions(origin, target, 20.0)
    assert len(solutions) == 2
    assert {solution.arc for solution in solutions} == {"low", "high"}
    for solution in solutions:
        end = profile.projectile_position(
            origin,
            solution.launch_velocity,
            solution.flight_time,
        )
        assert end.almost_equal(target, tolerance=1.0e-7)


def test_projectile_solver_returns_empty_when_target_is_unreachable() -> None:
    profile = GamePhysicsProfile.earth()
    assert profile.projectile_solutions(Vec3.zero(), Vec3(100.0, 100.0, 0.0), 5.0) == ()


def test_stopping_and_turning_calculations_follow_classical_mechanics() -> None:
    assert GamePhysicsProfile.stopping_distance(20.0, 10.0) == pytest.approx(20.0)
    assert GamePhysicsProfile.stopping_time(20.0, 10.0) == pytest.approx(2.0)
    assert GamePhysicsProfile.turning_radius(20.0, 8.0) == pytest.approx(50.0)


def test_terminal_velocity_respects_scale() -> None:
    earth = GamePhysicsProfile.earth()
    scaled = GamePhysicsProfile.earth(meters_per_unit=0.5)
    kwargs = {"mass": 80.0, "drag_coefficient": 1.0, "reference_area": 0.7}
    assert scaled.terminal_velocity(**kwargs) == pytest.approx(
        earth.terminal_velocity(**kwargs) * 2.0
    )


def test_world_body_bound_fails_closed() -> None:
    world = PhysicsWorld(PhysicsSettings(max_bodies=1))
    world.add_body(RigidBody.dynamic("one", SphereShape(1.0)))
    with pytest.raises(PhysicsValidationError):
        world.add_body(RigidBody.dynamic("two", SphereShape(1.0)))


def test_invalid_gameplay_scale_rejected() -> None:
    with pytest.raises(PhysicsValidationError):
        GameplayScale(0.0)


def test_world_raycast_orders_hits_by_distance_then_id() -> None:
    world = _zero_gravity_world()
    world.add_body(RigidBody.static("far", SphereShape(1.0), position=Vec3(5.0, 0.0, 0.0)))
    world.add_body(RigidBody.static("near", SphereShape(1.0), position=Vec3(2.0, 0.0, 0.0)))
    hits = world.raycast(Ray(Vec3.zero(), Vec3.axis(0), 10.0))
    assert tuple(hit.body_id for hit in hits) == ("near", "far")
    assert hits[0].distance == pytest.approx(1.0)
    assert hits[1].distance == pytest.approx(4.0)


def test_raycast_hits_rotated_box_in_local_frame() -> None:
    world = _zero_gravity_world()
    world.add_body(
        RigidBody.static(
            "box",
            BoxShape(Vec3(2.0, 0.5, 0.5)),
            position=Vec3(0.0, 3.0, 0.0),
            orientation=Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
        )
    )
    hit = world.raycast_closest(Ray(Vec3.zero(), Vec3.axis(1), 10.0))
    assert hit is not None
    assert hit.body_id == "box"
    assert hit.distance == pytest.approx(1.0, abs=1.0e-9)


def test_sphere_cast_expands_target_geometry_for_toi_query() -> None:
    world = _zero_gravity_world()
    world.add_body(RigidBody.static("target", SphereShape(1.0), position=Vec3(5.0, 0.0, 0.0)))
    hits = world.sphere_cast(Ray(Vec3.zero(), Vec3.axis(0), 10.0), 0.5)
    assert len(hits) == 1
    assert hits[0].distance == pytest.approx(3.5)


def test_world_query_ignore_set_is_respected() -> None:
    world = _zero_gravity_world()
    world.add_body(RigidBody.static("a", SphereShape(1.0), position=Vec3(2.0, 0.0, 0.0)))
    world.add_body(RigidBody.static("b", SphereShape(1.0), position=Vec3(4.0, 0.0, 0.0)))
    hit = world.raycast_closest(Ray(Vec3.zero(), Vec3.axis(0), 10.0), ignore=("a",))
    assert hit is not None
    assert hit.body_id == "b"


def test_state_digest_changes_with_accumulated_force_and_sleep_timer() -> None:
    left = _zero_gravity_world()
    right = _zero_gravity_world()
    body_left = RigidBody.dynamic("body", SphereShape(1.0))
    body_right = RigidBody.dynamic("body", SphereShape(1.0))
    left.add_body(body_left)
    right.add_body(body_right)
    assert left.state_digest == right.state_digest

    body_left.apply_force(Vec3(1.0, 0.0, 0.0))
    assert left.state_digest != right.state_digest

    body_left.clear_accumulators()
    assert left.state_digest == right.state_digest

    body_left.sleep_time = 0.25
    assert left.state_digest != right.state_digest


def test_broadphase_pair_budget_fails_closed() -> None:
    broad = SweepAndPruneBroadPhase(max_pairs=1)
    bodies = tuple(
        RigidBody.dynamic(str(index), SphereShape(10.0), position=Vec3(float(index), 0.0, 0.0))
        for index in range(3)
    )
    with pytest.raises(PhysicsValidationError, match="pair bound"):
        broad.compute_pairs(bodies)


def test_vertical_downward_projectile_solution_hits_target() -> None:
    profile = GamePhysicsProfile.earth()
    origin = Vec3(0.0, 5.0, 0.0)
    target = Vec3.zero()
    solution = profile.projectile_solutions(origin, target, 10.0)
    assert len(solution) == 1
    end = profile.projectile_position(
        origin,
        solution[0].launch_velocity,
        solution[0].flight_time,
    )
    assert end.almost_equal(target, tolerance=1.0e-8)


def test_invalid_world_gravity_type_fails_closed() -> None:
    with pytest.raises(PhysicsValidationError, match="gravity"):
        PhysicsSettings(gravity="down")  # type: ignore[arg-type]


def test_live_external_force_prevents_sleep_before_accumulator_clear() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.1,
            sleep_linear_speed=100.0,
            sleep_angular_speed=100.0,
            sleep_after_seconds=0.1,
        )
    )
    body = RigidBody.dynamic(
        "body",
        SphereShape(1.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    body.apply_force(Vec3(1.0, 0.0, 0.0))
    world.add_body(body)
    world.step()
    assert body.awake
    assert body.force == Vec3.zero()


def test_failed_solver_rolls_back_entire_tick_atomically() -> None:
    world = _zero_gravity_world()
    body = RigidBody.dynamic(
        "body",
        SphereShape(1.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    body.linear_velocity = Vec3(3.0, 1.0, 0.0)
    body.apply_force(Vec3(2.0, 0.0, 0.0))
    world.add_body(body)

    before_digest = world.state_digest
    before_position = body.position
    before_velocity = body.linear_velocity
    before_force = body.force
    before_tick = world.tick
    before_contacts = world.contacts()

    class _FailingSolver:
        def solve(self, bodies, manifolds):
            bodies["body"].position = Vec3(999.0, 999.0, 999.0)
            bodies["body"].linear_velocity = Vec3(-999.0, 0.0, 0.0)
            raise RuntimeError("synthetic solver failure")

    world._solver = _FailingSolver()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="synthetic solver failure"):
        world.step()

    assert world.tick == before_tick
    assert world.state_digest == before_digest
    assert body.position == before_position
    assert body.linear_velocity == before_velocity
    assert body.force == before_force
    assert world.contacts() == before_contacts


def test_world_measure_reports_center_of_mass_and_linear_momentum() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    left = RigidBody.dynamic(
        "left",
        SphereShape(1.0),
        density=1.0,
        position=Vec3(-2.0, 0.0, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    right = RigidBody.dynamic(
        "right",
        SphereShape(1.0),
        density=3.0,
        position=Vec3(2.0, 0.0, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    left.linear_velocity = Vec3(2.0, 0.0, 0.0)
    right.linear_velocity = Vec3(-1.0, 0.0, 0.0)
    world.add_body(left)
    world.add_body(right)

    measure = world.measure()
    assert measure.dynamic_bodies == 2
    assert measure.center_of_mass.x == pytest.approx(1.0)
    expected_px = left.mass * 2.0 - right.mass
    assert measure.linear_momentum.x == pytest.approx(expected_px)


def test_world_measure_potential_energy_uses_gravity_direction() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3(0.0, -10.0, 0.0)))
    body = RigidBody.dynamic("body", SphereShape(1.0), position=Vec3(0.0, 5.0, 0.0))
    world.add_body(body)
    measure = world.measure()
    assert measure.potential_energy == pytest.approx(body.mass * 10.0 * 5.0)
    assert measure.mechanical_energy == pytest.approx(
        measure.kinetic_energy + measure.potential_energy
    )
