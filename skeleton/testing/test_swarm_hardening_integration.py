from skeleton.agents.swarm_gc import compact_runtime
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask


def test_gc_preserves_hardened_runtime_type_and_limits() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=10, max_workers=3, max_lease_seconds=77)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("done", {}))
    runtime.lease("w")
    runtime.succeed("w", "done")
    runtime.submit(SwarmTask("queued", {}))
    rebuilt, result = compact_runtime(runtime, keep_terminal=0)
    assert isinstance(rebuilt, HardenedSwarmRuntime)
    assert rebuilt.max_workers == 3
    assert rebuilt.max_lease_seconds == 77
    assert result.removed == 1
    assert rebuilt.task("queued") is not None


def test_recovery_restores_hardened_runtime() -> None:
    runtime = HardenedSwarmRuntime(max_workers=7, max_lease_seconds=90)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    manager = SwarmRecoveryManager(max_checkpoints=2)
    manager.checkpoint(runtime)
    restored = manager.restore_latest()
    assert isinstance(restored, HardenedSwarmRuntime)
    assert restored.max_workers == 7
    assert restored.max_lease_seconds == 90
    assert restored.task("t") is not None
