from __future__ import annotations

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_health_is_critical_when_work_exists_without_workers() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("job", {}))

    health = runtime.health()

    assert health["status"] == "critical"
    assert health["queue_pressure"] == 1.0


def test_health_reports_stale_workers() -> None:
    clock = Clock()
    runtime = SwarmRuntime(clock=clock)
    runtime.register_worker("stale")
    clock.advance(91)

    health = runtime.health(stale_after=90)

    assert health["status"] == "degraded"
    assert health["stale_workers"] == ["stale"]


def test_heartbeat_recovers_worker_from_stale_classification() -> None:
    clock = Clock()
    runtime = SwarmRuntime(clock=clock)
    runtime.register_worker("worker")
    clock.advance(100)
    assert runtime.stale_workers(stale_after=90)

    runtime.heartbeat("worker")

    assert runtime.stale_workers(stale_after=90) == ()
    assert runtime.health(stale_after=90)["status"] == "healthy"


def test_health_reports_saturation_and_queue_pressure() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("leased", {}))
    runtime.submit(SwarmTask("queued", {}))
    runtime.lease("w", limit=1)

    health = runtime.health()

    assert health["worker_saturation"] == 0.5
    assert health["queue_pressure"] == 1.0
    assert health["snapshot"]["leased"] == 1
    assert health["snapshot"]["queued"] == 1
