from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from skeleton.simulation.physics.body import RigidBody
from skeleton.simulation.physics.collision import (
    BroadPhasePair,
    SweepAndPruneBroadPhase,
)
from skeleton.simulation.physics.errors import PhysicsValidationError
from skeleton.simulation.physics.jvm_broadphase_accelerator import (
    BroadPhaseIndexPair,
    JvmBroadPhaseAccelerator,
    JvmBroadPhaseConfig,
)
from skeleton.simulation.physics.math3d import AABB, Vec3
from skeleton.simulation.physics.shapes import BoxShape, PlaneShape, SphereShape
from skeleton.simulation.physics.world import PhysicsSettings, PhysicsWorld


class _FakeBroadPhaseAccelerator:
    minimum_bodies = 1

    def __init__(self) -> None:
        self.calls = 0

    def compute_pairs(
        self,
        bodies: list[tuple[AABB, bool]],
        *,
        max_pairs: int,
        epsilon: float,
    ) -> list[BroadPhaseIndexPair]:
        del epsilon
        self.calls += 1
        pairs: list[BroadPhaseIndexPair] = []
        for left in range(len(bodies)):
            left_bounds, left_dynamic = bodies[left]
            for right in range(left + 1, len(bodies)):
                right_bounds, right_dynamic = bodies[right]
                if not left_dynamic and not right_dynamic:
                    continue
                if not left_bounds.overlaps(right_bounds):
                    continue
                if len(pairs) >= max_pairs:
                    raise RuntimeError("broad-phase pair bound exceeded")
                pairs.append(BroadPhaseIndexPair(left, right))
        return pairs


class _FailingBroadPhaseAccelerator:
    minimum_bodies = 1

    def compute_pairs(self, *args: object, **kwargs: object) -> list[BroadPhaseIndexPair]:
        raise RuntimeError("simulated JVM broad-phase failure")


class _MalformedBroadPhaseAccelerator:
    minimum_bodies = 1

    class _BadPair:
        left = 0
        right = 99_999

    def compute_pairs(self, *args: object, **kwargs: object) -> list[object]:
        return [self._BadPair()]


def _pair_signature(pairs: tuple[BroadPhasePair, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((pair.body_a, pair.body_b) for pair in pairs)


def _fixture_bodies() -> tuple[RigidBody, ...]:
    return (
        RigidBody.static(
            "ground",
            PlaneShape(),
        ),
        RigidBody.static(
            "static-a",
            BoxShape(Vec3(1.0, 1.0, 1.0)),
            position=Vec3(0.0, 5.0, 0.0),
        ),
        RigidBody.static(
            "static-b",
            SphereShape(1.0),
            position=Vec3(0.25, 5.0, 0.0),
        ),
        RigidBody.dynamic(
            "dynamic-a",
            SphereShape(1.0),
            position=Vec3(0.5, 5.0, 0.0),
        ),
        RigidBody.dynamic(
            "dynamic-b",
            BoxShape(Vec3(0.75, 0.75, 0.75)),
            position=Vec3(10.0, 5.0, 0.0),
        ),
    )


def test_fake_jvm_broadphase_matches_python_including_planes() -> None:
    bodies = _fixture_bodies()
    baseline = SweepAndPruneBroadPhase()
    fake = _FakeBroadPhaseAccelerator()
    accelerated = SweepAndPruneBroadPhase(
        use_jvm_acceleration=True,
        accelerator=fake,
    )

    expected = baseline.compute_pairs(bodies)
    actual = accelerated.compute_pairs(tuple(reversed(bodies)))

    assert _pair_signature(actual) == _pair_signature(expected)
    assert ("static-a", "static-b") not in _pair_signature(actual)
    assert ("dynamic-a", "ground") in _pair_signature(actual)
    assert ("dynamic-b", "ground") in _pair_signature(actual)
    assert fake.calls == 1
    assert accelerated.acceleration_stats()["successes"] == 1


def test_jvm_broadphase_failure_recomputes_with_python() -> None:
    bodies = _fixture_bodies()
    baseline = SweepAndPruneBroadPhase()
    accelerated = SweepAndPruneBroadPhase(
        use_jvm_acceleration=True,
        accelerator=_FailingBroadPhaseAccelerator(),
    )

    assert _pair_signature(accelerated.compute_pairs(bodies)) == _pair_signature(
        baseline.compute_pairs(bodies)
    )
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def test_malformed_injected_accelerator_cannot_corrupt_pair_indices() -> None:
    bodies = _fixture_bodies()
    baseline = SweepAndPruneBroadPhase()
    accelerated = SweepAndPruneBroadPhase(
        use_jvm_acceleration=True,
        accelerator=_MalformedBroadPhaseAccelerator(),
    )

    assert _pair_signature(accelerated.compute_pairs(bodies)) == _pair_signature(
        baseline.compute_pairs(bodies)
    )
    assert accelerated.acceleration_stats()["fallbacks"] == 1


def test_small_finite_world_bypasses_jvm_threshold() -> None:
    fake = _FakeBroadPhaseAccelerator()
    fake.minimum_bodies = 100
    broadphase = SweepAndPruneBroadPhase(
        use_jvm_acceleration=True,
        accelerator=fake,
    )

    pairs = broadphase.compute_pairs(_fixture_bodies())

    assert pairs
    assert fake.calls == 0
    assert broadphase.acceleration_stats()["bypassed_small_batch"] == 1


def test_plane_pairs_still_enforce_global_python_pair_bound() -> None:
    fake = _FakeBroadPhaseAccelerator()
    broadphase = SweepAndPruneBroadPhase(
        max_pairs=1,
        use_jvm_acceleration=True,
        accelerator=fake,
    )
    bodies = (
        RigidBody.static("ground", PlaneShape()),
        RigidBody.dynamic("a", SphereShape(1.0), position=Vec3(0.0, 2.0, 0.0)),
        RigidBody.dynamic("b", SphereShape(1.0), position=Vec3(10.0, 2.0, 0.0)),
    )

    with pytest.raises(PhysicsValidationError, match="pair bound"):
        broadphase.compute_pairs(bodies)


def _world(*, accelerated: bool, accelerator: object | None = None) -> PhysicsWorld:
    world = PhysicsWorld(
        PhysicsSettings(
            fixed_dt=1.0 / 120.0,
            gravity=Vec3(0.0, -9.81, 0.0),
            sleep_after_seconds=10.0,
        ),
        use_jvm_broadphase=accelerated,
        broad_phase_accelerator=accelerator,
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    for index, x in enumerate((-1.0, 0.0, 1.0)):
        body = RigidBody.dynamic(
            f"ball-{index}",
            SphereShape(0.6),
            position=Vec3(x, 2.0 + index * 0.1, 0.0),
            linear_damping=0.0,
            angular_damping=0.0,
        )
        world.add_body(body)
    return world


def test_world_step_with_fake_jvm_matches_python_receipts_and_digest() -> None:
    baseline = _world(accelerated=False)
    accelerated = _world(
        accelerated=True,
        accelerator=_FakeBroadPhaseAccelerator(),
    )

    baseline_receipts = baseline.step(20)
    accelerated_receipts = accelerated.step(20)

    assert accelerated_receipts == baseline_receipts
    assert accelerated.state_digest == baseline.state_digest
    assert accelerated.contacts() == baseline.contacts()
    stats = accelerated.broad_phase_acceleration_stats()
    assert stats["enabled"] is True
    assert stats["successes"] >= 1


def _java_major(java: str) -> int | None:
    completed = subprocess.run(
        [java, "-version"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    lines = (completed.stderr or completed.stdout).splitlines()
    if not lines:
        return None
    marker = 'version "'
    if marker not in lines[0]:
        return None
    version = lines[0].split(marker, 1)[1].split('"', 1)[0]
    head = version.split(".", 1)[0]
    if head == "1" and "." in version:
        head = version.split(".", 2)[1]
    try:
        return int(head)
    except ValueError:
        return None


def _real_config() -> JvmBroadPhaseConfig:
    java = shutil.which("java")
    if not java:
        pytest.skip("java is not installed")
    major = _java_major(java)
    if major is None or major < 21:
        pytest.skip("Java 21+ is required for the accelerator CI contract")
    source = (
        Path(__file__).resolve().parents[2]
        / "java-accelerators"
        / "physics"
        / "BroadPhaseMain.java"
    )
    return JvmBroadPhaseConfig(
        java_binary=java,
        source=source,
        response_timeout_seconds=20,
        minimum_bodies=1,
    )


def _aabb(
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
) -> AABB:
    return AABB(Vec3(*minimum), Vec3(*maximum))


def test_real_java_broadphase_roundtrip_matches_pair_contract() -> None:
    bodies = [
        (_aabb((0, 0, 0), (2, 2, 2)), True),
        (_aabb((1, 1, 1), (3, 3, 3)), False),
        (_aabb((1.5, 1.5, 1.5), (4, 4, 4)), False),
        (_aabb((10, 10, 10), (11, 11, 11)), True),
        (_aabb((2, 2, 2), (2, 2, 2)), True),
    ]

    with JvmBroadPhaseAccelerator(_real_config()) as accelerator:
        assert accelerator.ping() >= 1
        pairs = accelerator.compute_pairs(
            bodies,
            max_pairs=100,
            epsilon=1.0e-9,
        )

    assert [(pair.left, pair.right) for pair in pairs] == [
        (0, 1),
        (0, 2),
        (0, 4),
        (1, 4),
        (2, 4),
    ]


def test_real_java_physics_world_matches_python_world() -> None:
    baseline = _world(accelerated=False)
    accelerator = JvmBroadPhaseAccelerator(_real_config())
    accelerated = _world(accelerated=True, accelerator=accelerator)

    try:
        expected = baseline.step(12)
        actual = accelerated.step(12)
    finally:
        accelerator.close()

    assert actual == expected
    assert accelerated.state_digest == baseline.state_digest


def test_real_java_bridge_rejects_invalid_epsilon_before_ipc() -> None:
    accelerator = JvmBroadPhaseAccelerator(_real_config())
    try:
        with pytest.raises(ValueError, match="epsilon"):
            accelerator.compute_pairs(
                [(_aabb((0, 0, 0), (1, 1, 1)), True)],
                max_pairs=10,
                epsilon=math.inf,
            )
    finally:
        accelerator.close()
