from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask


def test_restore_preserves_fifo_then_advances_sequence() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=4)
    runtime.submit(SwarmTask("a", {}, priority=10))
    runtime.submit(SwarmTask("b", {}, priority=10))
    restored = HardenedSwarmRuntime.from_state(runtime.export_state())
    restored.submit(SwarmTask("c", {}, priority=10))
    leased = restored.lease("w", limit=3)
    assert [task.id for task in leased] == ["a", "b", "c"]


def test_restore_resets_worker_monotonic_liveness() -> None:
    now = [5.0]
    runtime = HardenedSwarmRuntime(clock=lambda: now[0])
    runtime.register_worker("w")
    state = runtime.export_state()
    now[0] = 500.0
    restored = HardenedSwarmRuntime.from_state(state, clock=lambda: now[0])
    assert restored.worker("w").last_seen == 500.0
    assert restored.stale_workers(stale_after=1.0) == ()
