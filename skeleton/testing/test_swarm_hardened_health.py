from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask


def test_hardened_health_marks_queued_without_workers_as_degraded() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("queued", {}))

    health = runtime.health()

    assert health["status"] == "degraded"
    assert health["availability"] == "awaiting_workers"
    assert health["snapshot"]["queued"] == 1
    assert health["snapshot"]["workers"] == 0


def test_hardened_health_marks_empty_runtime_as_idle() -> None:
    health = HardenedSwarmRuntime().health()

    assert health["status"] == "ok"
    assert health["availability"] == "idle"
