"""Broadphase, manifolds, conservation and segmented mass.

Momentum and energy are computed from the velocities the step returns. The
assertions compare those computations with the documented epsilons.
"""

from __future__ import annotations

import math

import pytest

from skeleton.frontier_contact import (
    AABB,
    ENERGY_INCREASE_EPSILON_J,
    IMPULSE_SUM_EPSILON_NS,
    LINEAR_MOMENTUM_EPSILON_NS,
    BoxBody,
    ContactRejected,
    ContactRuntime,
    MassSegment,
    SegmentedBody,
    SegmentedRuntime,
    SphereBody,
    center_of_mass,
    deform_box,
    discrete_slab_miss,
    move_box,
    overlapping_pairs,
    place_body,
    point_in_convex_hull,
    pose_body,
    retarget_animation,
    segment_endpoints,
    segment_mass_points,
    sphere_box_manifold,
    standing_body,
    step_contacts,
    step_segmented,
    swept_bounds,
    total_mass_kg,
)
from skeleton.jeeves.game_frontier_advanced_physics import (
    RigidBody,
    Vec3,
    sweep_spheres,
)


def _unit(x: float, y: float, z: float) -> tuple[float, float, float]:
    length = math.sqrt(x * x + y * y + z * z)
    return (x / length, y / length, z / length)


def _momentum(bodies: tuple[SphereBody, ...]) -> tuple[float, float, float]:
    total = [0.0, 0.0, 0.0]
    for body in bodies:
        for axis in range(3):
            total[axis] += body.mass_kg * body.velocity[axis]
    return (total[0], total[1], total[2])


def _kinetic(body: SphereBody) -> float:
    speed_sq = sum(component * component for component in body.velocity)
    spin_sq = sum(component * component for component in body.angular_velocity)
    inertia = 0.4 * body.mass_kg * body.radius_m * body.radius_m
    return 0.5 * body.mass_kg * speed_sq + 0.5 * inertia * spin_sq


def _distance(
    start: tuple[float, float, float], end: tuple[float, float, float]
) -> float:
    return math.sqrt(sum((end[axis] - start[axis]) ** 2 for axis in range(3)))


def _weighted_com(
    points: tuple[tuple[tuple[float, float, float], float], ...],
) -> tuple[float, float, float]:
    total = sum(mass for _, mass in points)
    return tuple(
        sum(point[axis] * mass for point, mass in points) / total for axis in range(3)
    )


def _barycentric_contains(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    query: tuple[float, float, float],
    tol: float = 1e-6,
) -> bool:
    def sub(left, right):
        return tuple(left[axis] - right[axis] for axis in range(3))

    def dot(left, right):
        return sum(left[axis] * right[axis] for axis in range(3))

    edge_b = sub(b, a)
    edge_c = sub(c, a)
    offset = sub(query, a)
    dot00 = dot(edge_b, edge_b)
    dot01 = dot(edge_b, edge_c)
    dot02 = dot(edge_b, offset)
    dot11 = dot(edge_c, edge_c)
    dot12 = dot(edge_c, offset)
    denom = dot00 * dot11 - dot01 * dot01
    assert abs(denom) > 1e-12
    inverse = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inverse
    v = (dot00 * dot12 - dot01 * dot02) * inverse
    w = 1.0 - u - v
    return u >= -tol and v >= -tol and w >= -tol


def _ground() -> BoxBody:
    return BoxBody(
        "ground", (0.0, 0.0, -0.5), (6.0, 6.0, 0.5), restitution=0.0, friction=0.45
    )


def test_broadphase_pairs_are_unique_and_repeatable() -> None:
    near_a = AABB((-0.2, -0.2, -0.2), (1.4, 0.4, 0.4))
    near_b = AABB((1.0, -0.2, -0.2), (2.2, 0.4, 0.4))
    far = AABB((9.0, 9.0, 9.0), (10.0, 10.0, 10.0))
    first = overlapping_pairs((near_a, near_b, far), cell_size_m=0.5)
    second = overlapping_pairs((near_a, near_b, far), cell_size_m=0.5)
    assert first == second == ((0, 1),)


def test_swept_aabb_includes_a_fast_body_the_rest_pose_misses() -> None:
    sphere = SphereBody("fast", (0.0, 0.0, 0.0), (40.0, 0.0, 0.0), 1.0, 0.3, 0.0, 0.0)
    box = BoxBody("far", (8.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    assert overlapping_pairs(swept_bounds((sphere,), (box,), 0.0)) == ()
    assert overlapping_pairs(swept_bounds((sphere,), (box,), 0.3)) == ((0, 1),)


def test_sphere_sphere_manifold_uses_the_existing_sweep() -> None:
    left = SphereBody("left", (-0.6, 0.0, 0.0), (0.8, 0.0, 0.0), 1.0, 0.4, 0.2, 0.1)
    right = SphereBody("right", (0.7, 0.15, 0.0), (-0.4, 0.0, 0.0), 1.5, 0.4, 0.2, 0.1)
    reference = sweep_spheres(
        RigidBody(
            "left", Vec3(-0.6, 0.0, 0.0), Vec3(0.8, 0.0, 0.0), 1.0, 0.4, 0.2, 0.1
        ),
        RigidBody(
            "right", Vec3(0.7, 0.15, 0.0), Vec3(-0.4, 0.0, 0.0), 1.5, 0.4, 0.2, 0.1
        ),
        delta_s=1.0,
    )
    assert reference is not None
    result = step_contacts((left, right), (), 1.0)
    assert result.contacts
    assert result.contacts[0].source == reference.source == "sphere_sphere_linear_ccd"
    assert result.contacts[0].time_of_impact_s == pytest.approx(
        reference.time_of_impact_s, abs=1e-12
    )
    assert result.contacts[0].points


def test_continuous_sweep_catches_a_sphere_that_would_tunnel() -> None:
    start = (0.0, 0.0, 0.0)
    velocity = (50.0, 0.0, 0.0)
    radius = 0.2
    dt = 0.2
    sphere = SphereBody("fast", start, velocity, 1.0, radius, 0.0, 0.0)
    box = BoxBody(
        "thin", (5.0, 0.0, 0.0), (0.05, 3.0, 3.0), restitution=0.0, friction=0.0
    )
    end = tuple(start[axis] + velocity[axis] * dt for axis in range(3))
    box_min = tuple(box.center[axis] - box.half_extents[axis] for axis in range(3))
    box_max = tuple(box.center[axis] + box.half_extents[axis] for axis in range(3))

    def overlaps(center: tuple[float, float, float]) -> bool:
        closest = tuple(
            min(max(center[axis], box_min[axis]), box_max[axis]) for axis in range(3)
        )
        return (
            sum((center[axis] - closest[axis]) ** 2 for axis in range(3))
            <= radius * radius
        )

    assert not overlaps(start)
    assert not overlaps(end)
    assert discrete_slab_miss(
        start, velocity, radius, dt, box.center, (1.0, 0.0, 0.0), box.half_extents[0]
    )
    result = step_contacts((sphere,), (box,), dt)
    assert result.contacts
    assert result.contacts[0].source == "sphere_box_linear_ccd"
    assert result.contacts[0].feature == "face"
    landed = result.spheres[0].position[0]
    assert landed < box_max[0]
    assert landed + radius <= box_min[0] + 1e-4


def test_isolated_elastic_pair_conserves_linear_momentum() -> None:
    left = SphereBody("left", (-1.2, 0.0, 0.0), (2.5, 0.0, 0.0), 2.0, 0.5, 1.0, 0.0)
    right = SphereBody("right", (1.4, 0.0, 0.0), (-1.1, 0.0, 0.0), 5.0, 0.5, 1.0, 0.0)
    before = (left, right)
    result = step_contacts(before, (), 0.8)
    assert result.contacts
    assert result.contacts[0].normal_impulse_ns > 0.0
    assert result.contacts[0].friction_impulse_ns == pytest.approx(0.0, abs=1e-12)
    before_momentum = _momentum(before)
    after_momentum = _momentum(result.spheres)
    residual = math.sqrt(
        sum((after_momentum[axis] - before_momentum[axis]) ** 2 for axis in range(3))
    )
    assert residual <= LINEAR_MOMENTUM_EPSILON_NS
    normal = result.contacts[0].normal
    closing = -sum(
        (right.velocity[axis] - left.velocity[axis]) * normal[axis] for axis in range(3)
    )
    separating = sum(
        (result.spheres[1].velocity[axis] - result.spheres[0].velocity[axis])
        * normal[axis]
        for axis in range(3)
    )
    assert closing > 0.0
    assert separating / closing == pytest.approx(1.0, abs=1e-5)
    energy_before = _kinetic(left) + _kinetic(right)
    energy_after = _kinetic(result.spheres[0]) + _kinetic(result.spheres[1])
    assert energy_after <= energy_before + ENERGY_INCREASE_EPSILON_J
    assert energy_before - energy_after <= ENERGY_INCREASE_EPSILON_J


def test_friction_does_not_increase_mechanical_energy() -> None:
    left = SphereBody("left", (-1.0, 0.0, 0.0), (2.0, 0.0, 0.0), 1.2, 0.5, 0.3, 0.9)
    right = SphereBody("right", (1.0, 0.35, 0.0), (0.0, 0.0, 0.0), 1.4, 0.5, 0.3, 0.8)
    result = step_contacts((left, right), (), 1.0)
    assert result.contacts
    assert result.contacts[0].friction_impulse_ns > 0.0
    assert result.contacts[0].friction_coefficient == pytest.approx(
        math.sqrt(left.friction * right.friction)
    )
    energy_before = _kinetic(left) + _kinetic(right)
    energy_after = sum(_kinetic(body) for body in result.spheres)
    assert energy_after <= energy_before + ENERGY_INCREASE_EPSILON_J


def test_moving_and_deformable_terrain_updates_bounds_before_the_query() -> None:
    sphere = SphereBody("rider", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.4, 0.0, 0.2)
    original = BoxBody(
        "slab",
        (4.0, 0.0, 0.0),
        (0.3, 0.3, 0.3),
        (0.0, 0.0, 0.0),
        restitution=0.0,
        friction=0.2,
    )
    missed = step_contacts((sphere,), (original,), 0.05)
    assert missed.contacts == ()
    moved = move_box(original, (0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    deformed = deform_box(moved, (1.0, 0.5, 0.5))
    result = step_contacts((sphere,), (deformed,), 0.2)
    bounds = result.queried_bounds[1]
    assert bounds.minimum[0] == pytest.approx(-1.0)
    assert bounds.maximum[0] == pytest.approx(3.0)
    assert result.contacts


def test_rejects_duplicate_ids_nan_and_negative_mass() -> None:
    with pytest.raises(ContactRejected, match="duplicate body id"):
        step_contacts(
            (
                SphereBody("same", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.2),
                SphereBody("same", (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.2),
            ),
            (),
            0.1,
        )
    with pytest.raises(ContactRejected, match="NaN"):
        SphereBody("nan", (float("nan"), 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.2)
    with pytest.raises(ContactRejected, match="negative mass"):
        SphereBody("heavy", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), -2.0, 0.2)
    with pytest.raises(ContactRejected, match="negative mass"):
        BoxBody("terrain", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), mass_kg=-0.4)
    with pytest.raises(ContactRejected, match="negative mass"):
        MassSegment("leg", 0, 0.4, -3.0, 0.05)
    runtime = ContactRuntime(
        (SphereBody("kept", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 1.0, 0.2),)
    )
    snapshot = runtime.spheres
    with pytest.raises(ContactRejected, match="NaN"):
        runtime.step(float("nan"))
    assert runtime.spheres is snapshot


def test_corner_and_edge_features() -> None:
    corner = sphere_box_manifold(
        SphereBody("corner", (2.0, 2.0, 2.0), (-1.0, -1.0, -1.0), 1.0, 0.5, 0.0, 0.0),
        BoxBody("block", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
        1.0,
    )
    assert corner is not None
    assert corner.points[0].feature == "vertex"
    assert all(component < 0.0 for component in corner.points[0].normal_a_to_b)
    edge = sphere_box_manifold(
        SphereBody("edge", (2.0, 0.0, 2.0), (-1.0, 0.0, -1.0), 1.0, 0.5, 0.0, 0.0),
        BoxBody("block", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
        1.0,
    )
    assert edge is not None
    assert edge.points[0].feature == "edge"


def test_pose_aware_center_of_mass_stays_inside_the_segment_hull() -> None:
    body = standing_body()
    points = segment_mass_points(body)
    computed = _weighted_com(points)
    assert computed == pytest.approx(center_of_mass(body))
    total = sum(mass for _, mass in points)
    weights = [mass / total for _, mass in points]
    assert all(weight > 0.0 for weight in weights)
    assert sum(weights) == pytest.approx(1.0)
    reconstructed = tuple(
        sum(points[index][0][axis] * weights[index] for index in range(len(points)))
        for axis in range(3)
    )
    assert reconstructed == pytest.approx(computed)
    assert _barycentric_contains(points[0][0], points[1][0], points[2][0], computed)
    swung = pose_body(
        body,
        (body.local_axes[0], _unit(0.9, -0.2, -0.4), body.local_axes[2]),
    )
    swung_points = segment_mass_points(swung)
    swung_com = _weighted_com(swung_points)
    assert swung_com == pytest.approx(center_of_mass(swung))
    assert math.dist(computed, swung_com) > 1e-3
    assert _barycentric_contains(
        swung_points[0][0], swung_points[1][0], swung_points[2][0], swung_com
    )
    cloud = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    assert point_in_convex_hull(cloud, (0.2, 0.2, 0.2))
    assert not point_in_convex_hull(cloud, (1.0, 1.0, 1.0))


def test_retarget_preserves_target_bone_lengths_and_segment_count() -> None:
    target = standing_body()
    source = SegmentedBody(
        "source",
        (0.0, 0.0, 0.2),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        (
            MassSegment("chest", -1, 0.30, 20.0, 0.12, False),
            MassSegment("left", 0, 0.18, 4.0, 0.05, False),
            MassSegment("right", 0, 0.22, 4.0, 0.05, False),
        ),
        (
            (0.0, 0.0, 1.0),
            _unit(0.1, 0.8, -0.5),
            _unit(-0.7, -0.2, -0.6),
        ),
        0.0,
        0.4,
    )
    mapped = retarget_animation(source, target)
    assert len(mapped.segments) == len(target.segments) == len(source.segments)
    assert mapped.local_axes == source.local_axes
    for (head, tail), destination, origin in zip(
        segment_endpoints(mapped), mapped.segments, source.segments
    ):
        length = _distance(head, tail)
        assert length == pytest.approx(destination.length_m, abs=1e-9)
        assert abs(length - origin.length_m) > 1e-3
    with pytest.raises(ContactRejected, match="segment count"):
        retarget_animation(
            SegmentedBody(
                "extra",
                (0.0, 0.0, 0.4),
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0),
                target.segments + (MassSegment("arm", 0, 0.3, 3.0, 0.05, True),),
                target.local_axes + (_unit(1.0, 0.2, 0.1),),
            ),
            target,
        )
    with pytest.raises(ContactRejected, match="unit"):
        pose_body(target, (target.local_axes[0], (2.0, 0.0, 0.0), target.local_axes[2]))


def _plant(body: SegmentedBody, velocity: tuple[float, float, float]) -> SegmentedBody:
    points = segment_mass_points(body)
    shifts = []
    for index in (1, 2):
        target_z = body.segments[index].radius_m - 0.02
        shifts.append(target_z - points[index][0][2])
    root = body.root_position
    return place_body(body, (root[0], root[1], root[2] + min(shifts)), velocity)


def test_multipoint_contact_impulses_sum_to_the_net_impulse() -> None:
    planted = _plant(standing_body(), (0.35, -0.15, -1.1))
    before = planted.velocity
    result = step_segmented(planted, 0.05, _ground(), iteration_cap=8)
    names = {
        impulse.segment
        for impulse in result.impulses
        if impulse.normal_impulse_ns > 0.0
    }
    assert len(names) >= 2
    net = [0.0, 0.0, 0.0]
    for impulse in result.impulses:
        for axis in range(3):
            net[axis] += impulse.impulse_ns[axis]
    mass = total_mass_kg(planted)
    change = tuple(
        mass * (result.body.velocity[axis] - before[axis]) for axis in range(3)
    )
    residual = math.sqrt(sum((net[axis] - change[axis]) ** 2 for axis in range(3)))
    assert residual <= IMPULSE_SUM_EPSILON_NS
    assert net[2] > 0.0
    assert result.body.velocity[2] > before[2]


def test_failed_segment_step_does_not_partially_update_the_body() -> None:
    body = standing_body()
    runtime = SegmentedRuntime(body)
    swung = pose_body(
        body, (body.local_axes[0], _unit(0.2, 0.7, -0.6), body.local_axes[2])
    )
    ground = _ground()
    with pytest.raises(ContactRejected, match="NaN"):
        runtime.step(float("nan"), ground, pose_source=swung)
    assert runtime.body is body
    assert runtime.body.local_axes == body.local_axes
    with pytest.raises(ContactRejected, match="duplicate body id"):
        runtime.step(
            0.02,
            BoxBody(body.body_id, ground.center, ground.half_extents),
            pose_source=swung,
        )
    assert runtime.body is body
    assert runtime.body.root_position == body.root_position


def test_fast_limb_does_not_tunnel_through_terrain() -> None:
    body = place_body(standing_body(), (0.0, 0.0, 4.0), (0.0, 0.0, -80.0))
    points = segment_mass_points(body)
    lowest = min(point[2] for point, _ in points)
    dt = 0.1
    unconstrained = lowest - 80.0 * dt
    result = step_segmented(body, dt, _ground(), iteration_cap=16)
    landed = min(point[2] for point, _ in segment_mass_points(result.body))
    assert result.impulses
    assert landed > unconstrained + 1.0
    assert landed > -0.5


def test_repeat_steps_match() -> None:
    left = SphereBody("left", (-0.8, 0.1, 0.0), (1.2, 0.0, 0.0), 1.0, 0.3, 0.4, 0.2)
    right = SphereBody("right", (0.9, -0.1, 0.2), (-0.4, 0.1, 0.0), 1.3, 0.3, 0.4, 0.2)
    box = BoxBody(
        "pad", (0.0, 0.0, -1.0), (3.0, 3.0, 0.4), restitution=0.1, friction=0.3
    )
    assert step_contacts((left, right), (box,), 0.2) == step_contacts(
        (left, right), (box,), 0.2
    )
