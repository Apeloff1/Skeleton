from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

from skeleton.memory.jvm_vector_accelerator import (
    JvmVectorAccelerator,
    JvmVectorConfig,
    JvmVectorUnavailable,
)
from skeleton.observability.jvm_accelerator import (
    JvmAcceleratorConfig,
    JvmAcceleratorUnavailable,
    JvmObservabilityAccelerator,
)
from skeleton.simulation.physics.jvm_broadphase_accelerator import (
    JvmBroadPhaseAccelerator,
    JvmBroadPhaseConfig,
    JvmBroadPhaseUnavailable,
)


def _missing_source_factories(tmp_path: Path):
    missing = tmp_path / "missing.java"
    return (
        (
            "observability",
            JvmObservabilityAccelerator(
                JvmAcceleratorConfig(
                    java_binary=sys.executable,
                    source=missing,
                    response_timeout_seconds=1.0,
                )
            ),
            JvmAcceleratorUnavailable,
        ),
        (
            "vector",
            JvmVectorAccelerator(
                JvmVectorConfig(
                    java_binary=sys.executable,
                    source=missing,
                    response_timeout_seconds=1.0,
                )
            ),
            JvmVectorUnavailable,
        ),
        (
            "physics",
            JvmBroadPhaseAccelerator(
                JvmBroadPhaseConfig(
                    java_binary=sys.executable,
                    source=missing,
                    response_timeout_seconds=1.0,
                )
            ),
            JvmBroadPhaseUnavailable,
        ),
    )


def test_status_is_nonstarting_and_records_source_start_failures(
    tmp_path: Path,
) -> None:
    for name, accelerator, unavailable in _missing_source_factories(tmp_path):
        before = accelerator.status()

        assert before.running is False, name
        assert before.closed is False, name
        assert before.pid is None, name
        assert before.starts == 0, name
        assert before.start_failures == 0, name
        assert before.requests == 0, name
        assert before.last_error is None, name

        with pytest.raises(unavailable):
            accelerator.ping()

        after = accelerator.status()
        assert after.running is False, name
        assert after.starts == 0, name
        assert after.start_failures == 1, name
        # Startup failed before a protocol frame could exist.
        assert after.requests == 0, name
        assert after.successful_requests == 0, name
        assert after.failed_requests == 0, name
        assert "source not found" in (after.last_error or ""), name


def test_repeated_start_failure_is_counted_per_attempt(tmp_path: Path) -> None:
    accelerator = JvmVectorAccelerator(
        JvmVectorConfig(
            java_binary=sys.executable,
            source=tmp_path / "still-missing.java",
            response_timeout_seconds=1.0,
        )
    )

    for _ in range(3):
        with pytest.raises(JvmVectorUnavailable):
            accelerator.ping()

    status = accelerator.status()
    assert status.start_failures == 3
    assert status.starts == 0
    assert status.requests == 0


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


def _java() -> str:
    java = shutil.which("java")
    if not java:
        pytest.skip("java is not installed")
    major = _java_major(java)
    if major is None or major < 21:
        pytest.skip("Java 21+ is required for accelerator lifecycle tests")
    return java


def _real_accelerators() -> tuple[tuple[str, Callable[[], object]], ...]:
    root = Path(__file__).resolve().parents[2]

    def observability() -> JvmObservabilityAccelerator:
        return JvmObservabilityAccelerator(
            JvmAcceleratorConfig(
                java_binary=_java(),
                source=(
                    root
                    / "java-accelerators"
                    / "observability"
                    / "AcceleratorMain.java"
                ),
                response_timeout_seconds=20,
                minimum_batch_values=1,
            )
        )

    def vector() -> JvmVectorAccelerator:
        return JvmVectorAccelerator(
            JvmVectorConfig(
                java_binary=_java(),
                source=(
                    root
                    / "java-accelerators"
                    / "vector"
                    / "VectorSearchMain.java"
                ),
                response_timeout_seconds=20,
                minimum_candidates=1,
            )
        )

    def physics() -> JvmBroadPhaseAccelerator:
        return JvmBroadPhaseAccelerator(
            JvmBroadPhaseConfig(
                java_binary=_java(),
                source=(
                    root
                    / "java-accelerators"
                    / "physics"
                    / "BroadPhaseMain.java"
                ),
                response_timeout_seconds=20,
                minimum_bodies=1,
                minimum_spatial_tests=1,
            )
        )

    return (
        ("observability", observability),
        ("vector", vector),
        ("physics", physics),
    )


@pytest.mark.parametrize(
    ("name", "factory"),
    _real_accelerators(),
)
def test_real_java_lifecycle_status_is_monotonic(
    name: str,
    factory: Callable[[], object],
) -> None:
    accelerator = factory()

    before = accelerator.status()
    assert before.running is False, name
    assert before.closed is False, name
    assert before.starts == 0, name
    assert before.restarts == 0, name
    assert before.requests == 0, name
    assert before.successful_requests == 0, name
    assert before.failed_requests == 0, name
    assert before.start_failures == 0, name

    processors = accelerator.ping()
    warmed = accelerator.status()
    assert processors >= 1, name
    assert warmed.running is True, name
    assert warmed.closed is False, name
    assert warmed.pid is not None, name
    assert warmed.server_processors == processors, name
    assert warmed.starts == 1, name
    assert warmed.start_failures == 0, name
    assert warmed.requests == 1, name
    assert warmed.successful_requests == 1, name
    assert warmed.failed_requests == 0, name

    accelerator.restart()
    restarted = accelerator.status()
    assert restarted.running is True, name
    assert restarted.starts == 2, name
    assert restarted.restarts == 1, name
    assert restarted.requests == 2, name
    assert restarted.successful_requests == 2, name
    assert restarted.start_failures == 0, name
    assert restarted.pid is not None, name

    accelerator.close()
    closed = accelerator.status()
    assert closed.running is False, name
    assert closed.closed is True, name
    assert closed.pid is None, name
    assert closed.starts == 2, name
    assert closed.restarts == 1, name
    assert closed.requests == 2, name
    assert closed.successful_requests == 2, name
