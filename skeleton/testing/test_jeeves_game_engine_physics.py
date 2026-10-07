from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_physics import (
    PHYSICS_POLICIES,
    BodyRecipe,
    BroadphaseKind,
    ConstraintRecipe,
    DistanceConstraint,
    HistoricalPhysicsWorld,
    PhysicsAdversary,
    PhysicsSceneSource,
    RigidBody,
    ShapeKind,
    Vec3,
    ZERO3,
    attach_physics_build,
    canonical_physics_patches,
    canonical_physics_source,
    compile_physics_build,
    physics_policy,
    world_from_source,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_era_has_physics_policy(
    era: EngineEra,
) -> None:
    assert era in PHYSICS_POLICIES
    assert physics_policy(era).era is era


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_canonical_physics_build_is_deterministic_and_passes_adversary(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )
    source = canonical_physics_source(
        era
    )

    first = compile_physics_build(
        era,
        source,
    )
    second = compile_physics_build(
        era,
        source,
    )

    assert first == second
    assert len(first.source_digest) == 64
    assert len(first.policy_digest) == 64
    assert len(first.manifest_digest) == 64

    attached = attach_physics_build(
        sandbox,
        source,
    )
    report = PhysicsAdversary().evaluate(
        attached,
        source,
    )

    assert report.passed
    assert report.score == 1.0
    assert {
        "manifest",
        "inventory",
        "integrity",
        "replay",
        "snapshot",
        "contact",
        "bounds",
        "constraints",
        "ccd",
        "queries",
    } == {
        probe.name
        for probe in report.probes
    }


def test_historical_policy_progression_changes_real_solver_capabilities() -> None:
    pong = physics_policy(
        EngineEra.PONG
    )
    sixteen = physics_policy(
        EngineEra.SIXTEEN_BIT
    )
    early3d = physics_policy(
        EngineEra.EARLY_3D
    )
    fixed = physics_policy(
        EngineEra.FIXED_3D
    )
    shader = physics_policy(
        EngineEra.SHADER
    )
    modern = physics_policy(
        EngineEra.MODERN
    )
    nxt = physics_policy(
        EngineEra.NEXT
    )

    assert pong.dimensions == 2
    assert pong.shapes == (
        ShapeKind.AABB,
    )
    assert not pong.friction
    assert (
        sixteen.broadphase
        is BroadphaseKind.SWEEP_X
    )
    assert sixteen.friction
    assert early3d.dimensions == 3
    assert not early3d.rotation
    assert ShapeKind.SPHERE in fixed.shapes
    assert fixed.rotation
    assert shader.constraints
    assert (
        modern.broadphase
        is BroadphaseKind.UNIFORM_GRID
    )
    assert modern.conservative_ccd
    assert modern.substeps == 4
    assert modern.max_toi_events == 16
    assert nxt.substeps == 8
    assert nxt.max_toi_events == 32
    assert physics_policy(
        EngineEra.HD
    ).max_toi_events == 8
    assert physics_policy(
        EngineEra.OPEN_WORLD
    ).max_toi_events == 8
    assert (
        nxt.solver_iterations
        > modern.solver_iterations
    )


def test_2d_eras_reject_3d_body_state() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.EIGHT_BIT,
        gravity=ZERO3,
    )

    with pytest.raises(
        GameEngineLabError,
        match="unsupported 3D state",
    ):
        world.spawn(
            RigidBody(
                "bad",
                ShapeKind.AABB,
                Vec3(
                    10.0,
                    10.0,
                    1.0,
                ),
            )
        )


def test_pong_rejects_sphere_shape() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.PONG,
        gravity=ZERO3,
    )

    with pytest.raises(
        GameEngineLabError,
        match="unavailable",
    ):
        world.spawn(
            RigidBody(
                "ball",
                ShapeKind.SPHERE,
                Vec3(
                    10.0,
                    10.0,
                    0.0,
                ),
            )
        )


def test_fixed_3d_sphere_collision_reduces_penetration() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.FIXED_3D,
        bounds=Vec3(
            100.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "a",
            ShapeKind.SPHERE,
            Vec3(
                45.0,
                50.0,
                50.0,
            ),
            Vec3(
                4.0,
                0.0,
                0.0,
            ),
            radius=6.0,
        )
    )
    world.spawn(
        RigidBody(
            "b",
            ShapeKind.SPHERE,
            Vec3(
                55.0,
                50.0,
                50.0,
            ),
            Vec3(
                -4.0,
                0.0,
                0.0,
            ),
            radius=6.0,
        )
    )

    before = world._contacts()
    assert before
    before_depth = max(
        contact.penetration
        for contact in before
    )

    world.step()

    after = world._contacts()
    after_depth = max(
        (
            contact.penetration
            for contact in after
        ),
        default=0.0,
    )

    assert after_depth < before_depth


def test_sphere_box_contact_is_supported_from_fixed_3d() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.FIXED_3D,
        bounds=Vec3(
            100.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "sphere",
            ShapeKind.SPHERE,
            Vec3(
                50.0,
                50.0,
                50.0,
            ),
            radius=5.0,
        )
    )
    world.spawn(
        RigidBody(
            "box",
            ShapeKind.AABB,
            Vec3(
                57.0,
                50.0,
                50.0,
            ),
            half_extent=Vec3(
                4.0,
                4.0,
                4.0,
            ),
            static=True,
        )
    )

    contacts = world._contacts()

    assert len(contacts) == 1
    assert contacts[0].penetration > 0


def test_rotation_changes_orientation_only_when_era_supports_it() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.FIXED_3D,
        gravity=ZERO3,
    )
    body = RigidBody(
        "spinner",
        ShapeKind.SPHERE,
        Vec3(
            20.0,
            20.0,
            20.0,
        ),
        angular_velocity=Vec3(
            0.0,
            2.0,
            0.0,
        ),
    )
    world.spawn(body)
    before = body.orientation

    world.step(10)

    assert body.orientation != before
    magnitude = (
        body.orientation.w
        * body.orientation.w
        + body.orientation.x
        * body.orientation.x
        + body.orientation.y
        * body.orientation.y
        + body.orientation.z
        * body.orientation.z
    ) ** 0.5
    assert magnitude == pytest.approx(
        1.0,
        abs=1e-6,
    )


def test_constraints_fail_closed_before_shader_era() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.EARLY_3D,
        gravity=ZERO3,
    )
    for body_id, x in (
        ("a", 20.0),
        ("b", 30.0),
    ):
        world.spawn(
            RigidBody(
                body_id,
                ShapeKind.AABB,
                Vec3(
                    x,
                    20.0,
                    20.0,
                ),
            )
        )

    with pytest.raises(
        GameEngineLabError,
        match="constraints unavailable",
    ):
        world.add_constraint(
            DistanceConstraint(
                "link",
                "a",
                "b",
                10.0,
            )
        )


def test_shader_constraint_solver_reduces_distance_error() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.SHADER,
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "a",
            ShapeKind.SPHERE,
            Vec3(
                20.0,
                20.0,
                20.0,
            ),
        )
    )
    world.spawn(
        RigidBody(
            "b",
            ShapeKind.SPHERE,
            Vec3(
                40.0,
                20.0,
                20.0,
            ),
        )
    )
    world.add_constraint(
        DistanceConstraint(
            "link",
            "a",
            "b",
            10.0,
            1.0,
        )
    )
    before = abs(
        (
            world._bodies["b"].position
            - world._bodies["a"].position
        ).length()
        - 10.0
    )

    world.step()

    after = abs(
        (
            world._bodies["b"].position
            - world._bodies["a"].position
        ).length()
        - 10.0
    )

    assert after < before


def test_modern_force_application_is_deterministic() -> None:
    def run():
        world = HistoricalPhysicsWorld(
            EngineEra.MODERN,
            gravity=ZERO3,
        )
        world.spawn(
            RigidBody(
                "body",
                ShapeKind.SPHERE,
                Vec3(
                    20.0,
                    20.0,
                    20.0,
                ),
                mass=2.0,
            )
        )
        world.apply_force(
            "body",
            Vec3(
                12.0,
                3.0,
                -4.0,
            ),
            torque=Vec3(
                0.0,
                5.0,
                0.0,
            ),
        )
        world.step(30)
        return world.fingerprint()

    assert run() == run()


def test_snapshot_restore_reproduces_physics_identity() -> None:
    source = canonical_physics_source(
        EngineEra.MODERN
    )
    world = world_from_source(
        EngineEra.MODERN,
        source,
    )
    world.step(25)
    snapshot = world.snapshot()
    before = world.fingerprint()

    world.step(10)
    world.restore(snapshot)

    assert world.tick == 25
    assert world.fingerprint() == before


def test_physics_snapshot_tamper_is_rejected() -> None:
    source = canonical_physics_source(
        EngineEra.SHADER
    )
    world = world_from_source(
        EngineEra.SHADER,
        source,
    )
    world.step(5)
    snapshot = world.snapshot()
    forged = replace(
        snapshot,
        digest="0" * 64,
    )

    with pytest.raises(
        GameEngineLabError,
        match="digest mismatch",
    ):
        world.restore(forged)


def test_physics_manifest_tamper_is_detected_and_repaired() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.OPEN_WORLD
    )
    source = canonical_physics_source(
        EngineEra.OPEN_WORLD
    )
    attached = attach_physics_build(
        sandbox,
        source,
    )
    path = (
        "physics/compiled/"
        "manifest.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                path,
                "{}",
                attached.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = PhysicsAdversary().evaluate(
        broken,
        source,
    )
    assert not before.passed
    assert "manifest" in before.failed

    repaired = broken.apply(
        canonical_physics_patches(
            broken,
            source,
        )
    )

    assert PhysicsAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_untracked_compiled_physics_file_is_detected_and_removed() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    source = canonical_physics_source(
        EngineEra.NEXT
    )
    attached = attach_physics_build(
        sandbox,
        source,
    )
    rogue_path = (
        "physics/compiled/"
        "rogue.json"
    )
    broken = attached.apply(
        (
            SandboxPatch(
                rogue_path,
                "{}",
            ),
        )
    )

    report = PhysicsAdversary().evaluate(
        broken,
        source,
    )

    assert not report.passed
    assert "inventory" in report.failed

    repaired = broken.apply(
        canonical_physics_patches(
            broken,
            source,
        )
    )

    assert (
        rogue_path
        not in repaired.tree.files
    )
    assert PhysicsAdversary().evaluate(
        repaired,
        source,
    ).passed


def test_physics_source_rejects_constraint_when_era_cannot_support_it() -> None:
    source = PhysicsSceneSource(
        bounds=Vec3(
            100.0,
            100.0,
            1.0,
        ),
        gravity=ZERO3,
        bodies=(
            BodyRecipe(
                "a",
                ShapeKind.AABB,
                Vec3(
                    20.0,
                    20.0,
                    0.0,
                ),
            ),
            BodyRecipe(
                "b",
                ShapeKind.AABB,
                Vec3(
                    30.0,
                    20.0,
                    0.0,
                ),
            ),
        ),
        constraints=(
            ConstraintRecipe(
                "link",
                "a",
                "b",
                10.0,
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="constraints unavailable",
    ):
        compile_physics_build(
            EngineEra.EIGHT_BIT,
            source,
        )


def test_runtime_quality_accepts_attested_physics_plane() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.HD
    )
    source = canonical_physics_source(
        EngineEra.HD
    )
    attached = attach_physics_build(
        sandbox,
        source,
    )

    assert lab.evaluate(
        attached
    ).passed



def test_jeeves_compiles_evaluates_and_simulates_historical_physics() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.SHADER,
        gameplay_dialect="immersive_sim",
    )
    source = canonical_physics_source(
        EngineEra.SHADER
    )

    compiled = jeeves.compile_game_physics(
        sandbox,
        source,
    )
    report = jeeves.evaluate_game_physics(
        compiled,
        source,
    )
    world = jeeves.simulate_game_physics(
        compiled,
        source,
        steps=30,
    )

    assert report.passed
    assert world.tick == 30
    assert world.bodies
    assert len(
        world.fingerprint()
    ) == 64
    assert (
        jeeves.evaluate_game_engine(
            compiled
        ).passed
    )



def test_snapshot_preserves_pending_force_and_torque_authority() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.MODERN,
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "body",
            ShapeKind.SPHERE,
            Vec3(
                20.0,
                20.0,
                20.0,
            ),
        )
    )
    world.apply_force(
        "body",
        Vec3(
            3.0,
            4.0,
            5.0,
        ),
        torque=Vec3(
            1.0,
            2.0,
            3.0,
        ),
    )
    snapshot = world.snapshot()

    world.step()
    world.restore(snapshot)

    body = world.bodies[0]
    assert body.force == Vec3(
        3.0,
        4.0,
        5.0,
    )
    assert body.torque == Vec3(
        1.0,
        2.0,
        3.0,
    )
    assert (
        world.fingerprint()
        == snapshot.digest
    )


def test_snapshot_rejects_different_constraint_authority() -> None:
    def make_world(
        rest_length: float,
    ) -> HistoricalPhysicsWorld:
        world = HistoricalPhysicsWorld(
            EngineEra.SHADER,
            gravity=ZERO3,
        )
        world.spawn(
            RigidBody(
                "a",
                ShapeKind.SPHERE,
                Vec3(
                    20.0,
                    20.0,
                    20.0,
                ),
            )
        )
        world.spawn(
            RigidBody(
                "b",
                ShapeKind.SPHERE,
                Vec3(
                    30.0,
                    20.0,
                    20.0,
                ),
            )
        )
        world.add_constraint(
            DistanceConstraint(
                "link",
                "a",
                "b",
                rest_length,
            )
        )
        return world

    source_world = make_world(
        10.0
    )
    snapshot = (
        source_world.snapshot()
    )
    different = make_world(
        8.0
    )

    with pytest.raises(
        GameEngineLabError,
        match="constraint set mismatch",
    ):
        different.restore(
            snapshot
        )


def test_physics_source_rejects_body_starting_outside_bounds() -> None:
    source = PhysicsSceneSource(
        bounds=Vec3(
            10.0,
            10.0,
            10.0,
        ),
        gravity=ZERO3,
        bodies=(
            BodyRecipe(
                "outside",
                ShapeKind.AABB,
                Vec3(
                    9.5,
                    5.0,
                    5.0,
                ),
                half_extent=Vec3(
                    1.0,
                    1.0,
                    1.0,
                ),
            ),
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="outside world bounds",
    ):
        compile_physics_build(
            EngineEra.EARLY_3D,
            source,
        )



@pytest.mark.parametrize(
    "era",
    [
        EngineEra.HD,
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_swept_ccd_prevents_fast_sphere_tunneling_through_thin_wall(
    era: EngineEra,
) -> None:
    world = HistoricalPhysicsWorld(
        era,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "projectile",
            ShapeKind.SPHERE,
            Vec3(
                10.0,
                50.0,
                50.0,
            ),
            Vec3(
                12_000.0,
                0.0,
                0.0,
            ),
            radius=0.5,
            mass=1.0,
            restitution=0.0,
            friction=0.0,
        )
    )
    world.spawn(
        RigidBody(
            "wall",
            ShapeKind.AABB,
            Vec3(
                50.0,
                50.0,
                50.0,
            ),
            half_extent=Vec3(
                0.25,
                20.0,
                20.0,
            ),
            restitution=0.0,
            friction=0.0,
            static=True,
        )
    )

    world.step()
    projectile = world._bodies[
        "projectile"
    ]

    assert projectile.position.x < 50.0
    assert projectile.velocity.x <= 0.0


def test_sweep_static_selects_earliest_wall_deterministically() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.NEXT,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "projectile",
            ShapeKind.SPHERE,
            Vec3(
                10.0,
                50.0,
                50.0,
            ),
            radius=0.5,
        )
    )
    for body_id, x in (
        ("near_wall", 40.0),
        ("far_wall", 70.0),
    ):
        world.spawn(
            RigidBody(
                body_id,
                ShapeKind.AABB,
                Vec3(
                    x,
                    50.0,
                    50.0,
                ),
                half_extent=Vec3(
                    0.25,
                    10.0,
                    10.0,
                ),
                static=True,
            )
        )

    first = world.sweep_static(
        "projectile",
        Vec3(
            100.0,
            0.0,
            0.0,
        ),
    )
    second = world.sweep_static(
        "projectile",
        Vec3(
            100.0,
            0.0,
            0.0,
        ),
    )

    assert first == second
    assert first is not None
    assert first.other == "near_wall"
    assert 0.0 < first.toi < 1.0
    assert first.normal == Vec3(
        1.0,
        0.0,
        0.0,
    )


def test_sweep_static_moving_away_returns_no_hit() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.MODERN,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "projectile",
            ShapeKind.SPHERE,
            Vec3(
                60.0,
                50.0,
                50.0,
            ),
            radius=0.5,
        )
    )
    world.spawn(
        RigidBody(
            "wall",
            ShapeKind.AABB,
            Vec3(
                50.0,
                50.0,
                50.0,
            ),
            half_extent=Vec3(
                0.25,
                10.0,
                10.0,
            ),
            static=True,
        )
    )

    assert (
        world.sweep_static(
            "projectile",
            Vec3(
                20.0,
                0.0,
                0.0,
            ),
        )
        is None
    )


def test_sweep_static_preserves_discrete_overlap_authority() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.HD,
        bounds=Vec3(
            100.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "projectile",
            ShapeKind.SPHERE,
            Vec3(
                49.8,
                50.0,
                50.0,
            ),
            radius=1.0,
        )
    )
    world.spawn(
        RigidBody(
            "wall",
            ShapeKind.AABB,
            Vec3(
                50.0,
                50.0,
                50.0,
            ),
            half_extent=Vec3(
                0.5,
                10.0,
                10.0,
            ),
            static=True,
        )
    )

    assert (
        world._contacts()
    )
    assert (
        world.sweep_static(
            "projectile",
            Vec3(
                10.0,
                0.0,
                0.0,
            ),
        )
        is None
    )


def test_ccd_replay_is_bit_stable() -> None:
    def build_world():
        world = HistoricalPhysicsWorld(
            EngineEra.NEXT,
            bounds=Vec3(
                200.0,
                100.0,
                100.0,
            ),
            gravity=ZERO3,
        )
        world.spawn(
            RigidBody(
                "projectile",
                ShapeKind.SPHERE,
                Vec3(
                    10.0,
                    50.0,
                    50.0,
                ),
                Vec3(
                    8_000.0,
                    0.0,
                    0.0,
                ),
                radius=0.5,
                restitution=0.2,
            )
        )
        world.spawn(
            RigidBody(
                "wall",
                ShapeKind.AABB,
                Vec3(
                    50.0,
                    50.0,
                    50.0,
                ),
                half_extent=Vec3(
                    0.25,
                    20.0,
                    20.0,
                ),
                restitution=0.2,
                static=True,
            )
        )
        return world

    first = build_world()
    second = build_world()

    first.step(4)
    second.step(4)

    assert (
        first.fingerprint()
        == second.fingerprint()
    )
    assert first.snapshot() == second.snapshot()



def test_off_center_fixed_3d_contact_generates_deterministic_angular_impulse() -> None:
    def build_world():
        world = HistoricalPhysicsWorld(
            EngineEra.FIXED_3D,
            bounds=Vec3(
                100.0,
                100.0,
                100.0,
            ),
            gravity=ZERO3,
        )
        world.spawn(
            RigidBody(
                "a",
                ShapeKind.AABB,
                Vec3(
                    45.0,
                    50.0,
                    50.0,
                ),
                Vec3(
                    5.0,
                    0.0,
                    0.0,
                ),
                half_extent=Vec3(
                    6.0,
                    6.0,
                    6.0,
                ),
                restitution=0.2,
                friction=0.5,
            )
        )
        world.spawn(
            RigidBody(
                "b",
                ShapeKind.AABB,
                Vec3(
                    55.0,
                    54.0,
                    50.0,
                ),
                Vec3(
                    -5.0,
                    0.0,
                    0.0,
                ),
                half_extent=Vec3(
                    6.0,
                    6.0,
                    6.0,
                ),
                restitution=0.2,
                friction=0.5,
            )
        )
        return world

    first = build_world()
    second = build_world()

    first.step()
    second.step()

    assert (
        first.fingerprint()
        == second.fingerprint()
    )
    assert any(
        body.angular_velocity.length()
        > 1e-6
        for body
        in first.bodies
    )


def test_central_sphere_impact_does_not_invent_angular_velocity() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.FIXED_3D,
        bounds=Vec3(
            100.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "a",
            ShapeKind.SPHERE,
            Vec3(
                45.0,
                50.0,
                50.0,
            ),
            Vec3(
                5.0,
                0.0,
                0.0,
            ),
            radius=6.0,
            friction=0.5,
        )
    )
    world.spawn(
        RigidBody(
            "b",
            ShapeKind.SPHERE,
            Vec3(
                55.0,
                50.0,
                50.0,
            ),
            Vec3(
                -5.0,
                0.0,
                0.0,
            ),
            radius=6.0,
            friction=0.5,
        )
    )

    world.step()

    assert all(
        body.angular_velocity.length()
        <= 1e-9
        for body
        in world.bodies
    )


def test_pre_rotation_era_keeps_angular_state_disabled() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.EARLY_3D,
        bounds=Vec3(
            100.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "a",
            ShapeKind.AABB,
            Vec3(
                45.0,
                50.0,
                50.0,
            ),
            Vec3(
                5.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                6.0,
                6.0,
                6.0,
            ),
        )
    )
    world.spawn(
        RigidBody(
            "b",
            ShapeKind.AABB,
            Vec3(
                55.0,
                54.0,
                50.0,
            ),
            Vec3(
                -5.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                6.0,
                6.0,
                6.0,
            ),
        )
    )

    world.step()

    assert all(
        body.angular_velocity
        == ZERO3
        for body
        in world.bodies
    )



@pytest.mark.parametrize(
    "era",
    [
        EngineEra.HD,
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_global_ccd_prevents_fast_dynamic_spheres_from_crossing(
    era: EngineEra,
) -> None:
    world = HistoricalPhysicsWorld(
        era,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "left",
            ShapeKind.SPHERE,
            Vec3(
                90.0,
                50.0,
                50.0,
            ),
            Vec3(
                4_000.0,
                0.0,
                0.0,
            ),
            radius=1.0,
            restitution=0.0,
            friction=0.0,
        )
    )
    world.spawn(
        RigidBody(
            "right",
            ShapeKind.SPHERE,
            Vec3(
                110.0,
                50.0,
                50.0,
            ),
            Vec3(
                -4_000.0,
                0.0,
                0.0,
            ),
            radius=1.0,
            restitution=0.0,
            friction=0.0,
        )
    )

    world.step()

    left = world._bodies["left"]
    right = world._bodies["right"]
    assert left.position.x < right.position.x
    assert (
        right.position.x
        - left.position.x
        >= 2.0 - 1e-5
    )
    assert left.velocity.x <= right.velocity.x + 1e-6
    assert any(
        {
            contact.a,
            contact.b,
        }
        == {
            "left",
            "right",
        }
        for contact
        in world.last_contacts
    )


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_global_ccd_prevents_fast_dynamic_aabbs_from_crossing(
    era: EngineEra,
) -> None:
    world = HistoricalPhysicsWorld(
        era,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "a",
            ShapeKind.AABB,
            Vec3(
                90.0,
                50.0,
                50.0,
            ),
            Vec3(
                5_000.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                1.0,
                2.0,
                2.0,
            ),
            restitution=0.0,
            friction=0.0,
        )
    )
    world.spawn(
        RigidBody(
            "b",
            ShapeKind.AABB,
            Vec3(
                110.0,
                50.0,
                50.0,
            ),
            Vec3(
                -5_000.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                1.0,
                2.0,
                2.0,
            ),
            restitution=0.0,
            friction=0.0,
        )
    )

    world.step()

    a = world._bodies["a"]
    b = world._bodies["b"]
    assert a.position.x < b.position.x
    assert (
        b.position.x
        - a.position.x
        >= 2.0 - 1e-5
    )


def test_dynamic_pair_toi_selection_is_deterministic_under_equal_time_hits() -> None:
    def build_world():
        world = HistoricalPhysicsWorld(
            EngineEra.NEXT,
            bounds=Vec3(
                200.0,
                200.0,
                100.0,
            ),
            gravity=ZERO3,
        )
        world.spawn(
            RigidBody(
                "center",
                ShapeKind.SPHERE,
                Vec3(
                    100.0,
                    100.0,
                    50.0,
                ),
                radius=1.0,
                static=True,
            )
        )
        world.spawn(
            RigidBody(
                "a_left",
                ShapeKind.SPHERE,
                Vec3(
                    80.0,
                    100.0,
                    50.0,
                ),
                Vec3(
                    4_000.0,
                    0.0,
                    0.0,
                ),
                radius=1.0,
                restitution=0.0,
            )
        )
        world.spawn(
            RigidBody(
                "b_right",
                ShapeKind.SPHERE,
                Vec3(
                    120.0,
                    100.0,
                    50.0,
                ),
                Vec3(
                    -4_000.0,
                    0.0,
                    0.0,
                ),
                radius=1.0,
                restitution=0.0,
            )
        )
        return world

    first = build_world()
    second = build_world()

    first_hit = first._earliest_pair_sweep(
        1.0 / 60.0
    )
    second_hit = second._earliest_pair_sweep(
        1.0 / 60.0
    )

    assert first_hit == second_hit
    assert first_hit is not None
    assert (
        first_hit.moving,
        first_hit.other,
    ) == (
        "a_left",
        "center",
    )


def test_non_ccd_era_keeps_historical_discrete_step_path() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.SHADER,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "left",
            ShapeKind.SPHERE,
            Vec3(
                90.0,
                50.0,
                50.0,
            ),
            Vec3(
                4_000.0,
                0.0,
                0.0,
            ),
            radius=1.0,
            restitution=0.0,
        )
    )
    world.spawn(
        RigidBody(
            "right",
            ShapeKind.SPHERE,
            Vec3(
                110.0,
                50.0,
                50.0,
            ),
            Vec3(
                -4_000.0,
                0.0,
                0.0,
            ),
            radius=1.0,
            restitution=0.0,
        )
    )

    assert not world.policy.conservative_ccd
    world.step()

    # Historical shader-era simulation intentionally retains discrete
    # collision semantics; the modern CCD path must not leak backward.
    assert (
        world._bodies["left"].position.x
        != 90.0
    )



def test_raycast_returns_stable_distance_order_and_nearest_hit() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.MODERN,
        bounds=Vec3(
            200.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "near_box",
            ShapeKind.AABB,
            Vec3(
                40.0,
                50.0,
                50.0,
            ),
            half_extent=Vec3(
                2.0,
                5.0,
                5.0,
            ),
            static=True,
        )
    )
    world.spawn(
        RigidBody(
            "far_sphere",
            ShapeKind.SPHERE,
            Vec3(
                70.0,
                50.0,
                50.0,
            ),
            radius=3.0,
            static=True,
        )
    )

    first = world.raycast(
        Vec3(
            10.0,
            50.0,
            50.0,
        ),
        Vec3(
            2.0,
            0.0,
            0.0,
        ),
        100.0,
    )
    second = world.raycast(
        Vec3(
            10.0,
            50.0,
            50.0,
        ),
        Vec3(
            2.0,
            0.0,
            0.0,
        ),
        100.0,
    )

    assert first == second
    assert tuple(
        hit.body_id
        for hit in first
    ) == (
        "near_box",
        "far_sphere",
    )
    assert first[0].distance < first[1].distance
    assert (
        world.raycast_first(
            Vec3(
                10.0,
                50.0,
                50.0,
            ),
            Vec3(
                1.0,
                0.0,
                0.0,
            ),
            100.0,
        )
        == first[0]
    )


def test_raycast_sphere_reports_outward_surface_normal() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.HD,
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "target",
            ShapeKind.SPHERE,
            Vec3(
                50.0,
                50.0,
                50.0,
            ),
            radius=5.0,
            static=True,
        )
    )

    hit = world.raycast_first(
        Vec3(
            10.0,
            50.0,
            50.0,
        ),
        Vec3(
            1.0,
            0.0,
            0.0,
        ),
        100.0,
    )

    assert hit is not None
    assert hit.body_id == "target"
    assert hit.distance == pytest.approx(
        35.0
    )
    assert hit.point.x == pytest.approx(
        45.0
    )
    assert hit.normal == Vec3(
        -1.0,
        0.0,
        0.0,
    )


def test_raycast_filters_dynamic_static_and_excluded_bodies() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.NEXT,
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "dynamic",
            ShapeKind.SPHERE,
            Vec3(
                30.0,
                50.0,
                50.0,
            ),
            radius=2.0,
        )
    )
    world.spawn(
        RigidBody(
            "static",
            ShapeKind.AABB,
            Vec3(
                50.0,
                50.0,
                50.0,
            ),
            half_extent=Vec3(
                2.0,
                5.0,
                5.0,
            ),
            static=True,
        )
    )
    origin = Vec3(
        10.0,
        50.0,
        50.0,
    )
    direction = Vec3(
        1.0,
        0.0,
        0.0,
    )

    assert tuple(
        hit.body_id
        for hit
        in world.raycast(
            origin,
            direction,
            100.0,
            include_static=False,
        )
    ) == (
        "dynamic",
    )
    assert tuple(
        hit.body_id
        for hit
        in world.raycast(
            origin,
            direction,
            100.0,
            include_dynamic=False,
        )
    ) == (
        "static",
    )
    assert tuple(
        hit.body_id
        for hit
        in world.raycast(
            origin,
            direction,
            100.0,
            exclude=(
                "dynamic",
            ),
        )
    ) == (
        "static",
    )


def test_overlap_queries_are_exact_for_box_and_sphere_shapes() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.MODERN,
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "box",
            ShapeKind.AABB,
            Vec3(
                30.0,
                30.0,
                30.0,
            ),
            half_extent=Vec3(
                2.0,
                2.0,
                2.0,
            ),
            static=True,
        )
    )
    world.spawn(
        RigidBody(
            "sphere",
            ShapeKind.SPHERE,
            Vec3(
                40.0,
                30.0,
                30.0,
            ),
            radius=2.0,
        )
    )

    assert world.overlap_aabb(
        Vec3(
            30.0,
            30.0,
            30.0,
        ),
        Vec3(
            3.0,
            3.0,
            3.0,
        ),
    ) == (
        "box",
    )
    assert world.overlap_sphere(
        Vec3(
            39.0,
            30.0,
            30.0,
        ),
        2.0,
    ) == (
        "sphere",
    )
    assert world.overlap_aabb(
        Vec3(
            35.0,
            35.0,
            30.0,
        ),
        Vec3(
            1.0,
            1.0,
            1.0,
        ),
    ) == ()


def test_2d_raycast_is_planar_and_rejects_pure_z_direction() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.EIGHT_BIT,
        bounds=Vec3(
            100.0,
            100.0,
            1.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "wall",
            ShapeKind.AABB,
            Vec3(
                50.0,
                50.0,
                0.0,
            ),
            half_extent=Vec3(
                2.0,
                5.0,
                1.0,
            ),
            static=True,
        )
    )

    hit = world.raycast_first(
        Vec3(
            10.0,
            50.0,
            99.0,
        ),
        Vec3(
            1.0,
            0.0,
            20.0,
        ),
        100.0,
    )

    assert hit is not None
    assert hit.body_id == "wall"
    assert hit.point.z == 0.0

    with pytest.raises(
        GameEngineLabError,
        match="direction must be non-zero",
    ):
        world.raycast(
            Vec3(
                10.0,
                50.0,
                0.0,
            ),
            Vec3(
                0.0,
                0.0,
                1.0,
            ),
            100.0,
        )


@pytest.mark.parametrize(
    "distance",
    [
        0.0,
        -1.0,
        float("inf"),
        float("nan"),
    ],
)
def test_raycast_rejects_invalid_distance(
    distance: float,
) -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.MODERN,
        gravity=ZERO3,
    )

    with pytest.raises(
        GameEngineLabError,
        match="distance",
    ):
        world.raycast(
            ZERO3,
            Vec3(
                1.0,
                0.0,
                0.0,
            ),
            distance,
        )



def test_global_ccd_handles_fast_dynamic_sphere_against_dynamic_box() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.NEXT,
        bounds=Vec3(
            250.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    world.spawn(
        RigidBody(
            "sphere",
            ShapeKind.SPHERE,
            Vec3(
                80.0,
                50.0,
                50.0,
            ),
            Vec3(
                8_000.0,
                0.0,
                0.0,
            ),
            radius=1.0,
            mass=1.0,
            restitution=0.0,
            friction=0.0,
        )
    )
    world.spawn(
        RigidBody(
            "box",
            ShapeKind.AABB,
            Vec3(
                110.0,
                50.0,
                50.0,
            ),
            Vec3(
                -1_000.0,
                0.0,
                0.0,
            ),
            half_extent=Vec3(
                2.0,
                3.0,
                3.0,
            ),
            mass=2.0,
            restitution=0.0,
            friction=0.0,
        )
    )

    world.step()

    sphere = world._bodies[
        "sphere"
    ]
    box = world._bodies[
        "box"
    ]
    assert (
        sphere.position.x
        < box.position.x
    )
    assert (
        box.position.x
        - sphere.position.x
        >= 3.0 - 1e-4
    )
    assert any(
        {
            contact.a,
            contact.b,
        }
        == {
            "sphere",
            "box",
        }
        for contact
        in world.last_contacts
    )


def test_global_ccd_is_independent_of_body_spawn_order() -> None:
    def run(
        order: tuple[
            str,
            ...,
        ],
    ):
        recipes = {
            "left": dict(
                shape=ShapeKind.SPHERE,
                position=Vec3(
                    90.0,
                    50.0,
                    50.0,
                ),
                velocity=Vec3(
                    4_000.0,
                    0.0,
                    0.0,
                ),
            ),
            "right": dict(
                shape=ShapeKind.SPHERE,
                position=Vec3(
                    110.0,
                    50.0,
                    50.0,
                ),
                velocity=Vec3(
                    -4_000.0,
                    0.0,
                    0.0,
                ),
            ),
            "wall": dict(
                shape=ShapeKind.AABB,
                position=Vec3(
                    140.0,
                    50.0,
                    50.0,
                ),
                velocity=ZERO3,
            ),
        }
        world = HistoricalPhysicsWorld(
            EngineEra.NEXT,
            bounds=Vec3(
                250.0,
                100.0,
                100.0,
            ),
            gravity=ZERO3,
        )
        for body_id in order:
            recipe = recipes[
                body_id
            ]
            if body_id == "wall":
                world.spawn(
                    RigidBody(
                        body_id,
                        recipe[
                            "shape"
                        ],
                        recipe[
                            "position"
                        ],
                        recipe[
                            "velocity"
                        ],
                        half_extent=Vec3(
                            1.0,
                            10.0,
                            10.0,
                        ),
                        static=True,
                    )
                )
            else:
                world.spawn(
                    RigidBody(
                        body_id,
                        recipe[
                            "shape"
                        ],
                        recipe[
                            "position"
                        ],
                        recipe[
                            "velocity"
                        ],
                        radius=1.0,
                        restitution=0.1,
                        friction=0.0,
                    )
                )
        world.step(3)
        return (
            world.fingerprint(),
            tuple(
                (
                    body.body_id,
                    body.position,
                    body.velocity,
                )
                for body
                in world.bodies
            ),
        )

    forward = run(
        (
            "left",
            "right",
            "wall",
        )
    )
    reverse = run(
        (
            "wall",
            "right",
            "left",
        )
    )

    assert forward == reverse


def test_swept_broadphase_excludes_far_dynamic_pairs() -> None:
    world = HistoricalPhysicsWorld(
        EngineEra.MODERN,
        bounds=Vec3(
            1000.0,
            100.0,
            100.0,
        ),
        gravity=ZERO3,
    )
    for body_id, x, velocity in (
        (
            "a",
            50.0,
            100.0,
        ),
        (
            "b",
            54.0,
            -100.0,
        ),
        (
            "far",
            900.0,
            0.0,
        ),
    ):
        world.spawn(
            RigidBody(
                body_id,
                ShapeKind.SPHERE,
                Vec3(
                    x,
                    50.0,
                    50.0,
                ),
                Vec3(
                    velocity,
                    0.0,
                    0.0,
                ),
                radius=1.0,
            )
        )

    pairs = (
        world._swept_pair_candidates(
            1.0 / 60.0
        )
    )

    assert (
        "a",
        "b",
    ) in pairs
    assert all(
        "far" not in pair
        for pair in pairs
    )
