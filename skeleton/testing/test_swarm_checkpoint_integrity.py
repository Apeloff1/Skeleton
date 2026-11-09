from concurrent.futures import ThreadPoolExecutor

import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_checkpoint import CheckpointStore
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker


def _tenant_broker(runtime: HardenedSwarmRuntime) -> TenantSwarmBroker:
    return TenantSwarmBroker(
        SwarmBroker(runtime),
        SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100),
    )


def test_checkpoint_get_returns_isolated_state_copy() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("task", {"x": 1}))
    store = CheckpointStore()
    captured = store.capture(runtime)

    captured.state["tasks"].clear()
    restored = store.get(captured.sequence)

    assert restored is not None
    assert len(restored.state["tasks"]) == 1


def test_checkpoint_discard_does_not_rewind_sequence() -> None:
    runtime = HardenedSwarmRuntime()
    store = CheckpointStore()
    first = store.capture(runtime)
    assert store.discard(first.sequence) is True
    second = store.capture(runtime)
    assert second.sequence == first.sequence + 1
    assert store.sequences() == (second.sequence,)


def test_restore_detects_internal_checkpoint_tampering() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("task", {}))
    store = CheckpointStore()
    checkpoint = store.capture(runtime)

    # Deliberately corrupt the internal object to prove restore verifies integrity.
    store._items[-1].state["tasks"].clear()
    with pytest.raises(ValueError, match="checksum mismatch"):
        store.restore(checkpoint.sequence)


def test_paired_checkpoint_rolls_back_runtime_when_tenant_capture_fails(monkeypatch) -> None:
    runtime = HardenedSwarmRuntime()
    broker = _tenant_broker(runtime)
    recovery = SwarmRecoveryManager()

    def explode(sequence, tenant_broker):
        raise RuntimeError("sidecar failed")

    monkeypatch.setattr(recovery.tenant_store, "capture", explode)
    with pytest.raises(RuntimeError, match="sidecar failed"):
        recovery.checkpoint(runtime, broker)

    assert len(recovery.store) == 0
    assert len(recovery.tenant_store) == 0
    assert recovery.status().latest_sequence is None


def test_restore_tenants_rejects_orphan_sidecar() -> None:
    runtime = HardenedSwarmRuntime()
    broker = _tenant_broker(runtime)
    recovery = SwarmRecoveryManager()
    recovery.tenant_store.capture(7, broker)
    target = _tenant_broker(HardenedSwarmRuntime())

    with pytest.raises(ValueError, match="no runtime checkpoint"):
        recovery.restore_tenants(target, 7)


def test_checkpoint_store_allocates_unique_sequences_concurrently() -> None:
    runtime = HardenedSwarmRuntime()
    store = CheckpointStore(max_checkpoints=64)

    with ThreadPoolExecutor(max_workers=8) as pool:
        checkpoints = list(pool.map(lambda _: store.capture(runtime), range(32)))

    sequences = sorted(item.sequence for item in checkpoints)
    assert sequences == list(range(1, 33))
    assert store.sequences() == tuple(range(1, 33))
