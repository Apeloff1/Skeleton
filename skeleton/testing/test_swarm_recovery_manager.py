import pytest

from skeleton.agents.swarm_failover import ReplicaState
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_recovery_manager_captures_and_restores_latest() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("a", {"x": 1}))
    manager = SwarmRecoveryManager(max_checkpoints=2)
    sequence = manager.checkpoint(runtime)
    assert sequence == 1
    restored = manager.restore_latest()
    assert restored is not None
    assert restored.task("a").state is TaskState.QUEUED


def test_recovery_manager_restores_explicit_retained_sequence() -> None:
    runtime = SwarmRuntime()
    manager = SwarmRecoveryManager(max_checkpoints=3)
    runtime.submit(SwarmTask("a", {}))
    assert manager.checkpoint(runtime) == 1
    runtime.submit(SwarmTask("b", {}))
    assert manager.checkpoint(runtime) == 2

    first = manager.restore(1)
    second = manager.restore(2)

    assert first is not None and first.task("a") is not None
    assert first.task("b") is None
    assert second is not None and second.task("b") is not None


def test_recovery_manager_explicit_restore_validates_sequence() -> None:
    manager = SwarmRecoveryManager()
    assert manager.restore(1) is None
    with pytest.raises(ValueError, match="positive integer"):
        manager.restore(0)
    with pytest.raises(ValueError, match="positive integer"):
        manager.restore(True)


def test_recovery_manager_bounds_checkpoint_history() -> None:
    runtime = SwarmRuntime()
    manager = SwarmRecoveryManager(max_checkpoints=2)
    for i in range(3):
        runtime.submit(SwarmTask(str(i), {}))
        manager.checkpoint(runtime)
    status = manager.status()
    assert status.checkpoints == 2
    assert status.latest_sequence == 3
    assert manager.restore(1) is None
    assert manager.restore(2) is not None


def test_recovery_manager_elects_durable_replica() -> None:
    manager = SwarmRecoveryManager()
    leader = manager.elect({
        "a": ReplicaState("a", epoch=1, sequence=9),
        "b": ReplicaState("b", epoch=2, sequence=1),
        "c": ReplicaState("c", epoch=2, sequence=3),
    })
    assert leader == "c"
    assert manager.status().epoch == 2
