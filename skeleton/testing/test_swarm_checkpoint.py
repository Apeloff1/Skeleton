from skeleton.agents.swarm_checkpoint import CheckpointStore
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask


def test_checkpoint_capture_is_versioned_and_checksums_state() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("a", {"x": 1}))
    store = CheckpointStore(max_checkpoints=2, clock=lambda: 123.0)
    checkpoint = store.capture(runtime)
    assert checkpoint.sequence == 1
    assert checkpoint.created_at == 123.0
    assert len(checkpoint.checksum) == 64


def test_checkpoint_store_is_bounded() -> None:
    runtime = SwarmRuntime()
    store = CheckpointStore(max_checkpoints=2)
    store.capture(runtime)
    store.capture(runtime)
    third = store.capture(runtime)
    assert len(store) == 2
    assert store.latest() == third
    assert store.get(1) is None


def test_checkpoint_restore_recovers_tasks() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("a", {}))
    store = CheckpointStore()
    store.capture(runtime)
    restored = store.restore()
    assert restored.task("a") is not None
