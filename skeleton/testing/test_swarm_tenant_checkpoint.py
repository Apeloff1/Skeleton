import pytest

from skeleton.agents.swarm_broker import SwarmBroker
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.agents.swarm_tenant_broker import TenantSwarmBroker
from skeleton.agents.swarm_tenant_checkpoint import TenantCheckpointStore


def _broker(runtime: HardenedSwarmRuntime, *, max_terminal_records: int = 100_000) -> TenantSwarmBroker:
    return TenantSwarmBroker(
        SwarmBroker(runtime),
        SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100),
        max_terminal_records=max_terminal_records,
    )


def test_tenant_checkpoint_round_trip_rebuilds_active_accounting() -> None:
    runtime = HardenedSwarmRuntime()
    source = _broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))

    store = TenantCheckpointStore(max_checkpoints=4)
    captured = store.capture(7, source)
    restored_runtime = HardenedSwarmRuntime.from_state(runtime.export_state(), requeue_leased=True)
    target = _broker(restored_runtime)
    repair = store.restore(target, 7)

    assert captured.sequence == 7
    assert target.tenant_for("task") == "acme"
    assert target.ingress.phase("acme", "task") == "queued"
    assert repair.restored_accounting == 1


def test_tenant_checkpoint_preserves_terminal_identity() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    source = _broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("task", {}))
    source.record_success("w", "task", completion_token="done")

    store = TenantCheckpointStore()
    store.capture(1, source)
    target = _broker(HardenedSwarmRuntime.from_state(runtime.export_state()))
    store.restore(target, 1)
    assert target.tenant_for("task") == "acme"
    assert target.status()["terminal_records"] == 1


def test_tenant_checkpoint_rejects_sequence_collision() -> None:
    first_runtime = HardenedSwarmRuntime()
    first = _broker(first_runtime)
    first.submit_and_dispatch("alpha", SwarmTask("a", {}))
    second_runtime = HardenedSwarmRuntime()
    second = _broker(second_runtime)
    second.submit_and_dispatch("beta", SwarmTask("b", {}))

    store = TenantCheckpointStore()
    store.capture(1, first)
    with pytest.raises(ValueError):
        store.capture(1, second)


def test_tenant_checkpoint_is_bounded() -> None:
    runtime = HardenedSwarmRuntime()
    broker = _broker(runtime)
    store = TenantCheckpointStore(max_checkpoints=2)
    store.capture(1, broker)
    store.capture(2, broker)
    store.capture(3, broker)
    assert store.sequences() == (2, 3)


def test_tenant_restore_requires_empty_target() -> None:
    runtime = HardenedSwarmRuntime()
    source = _broker(runtime)
    store = TenantCheckpointStore()
    store.capture(1, source)

    target_runtime = HardenedSwarmRuntime()
    target = _broker(target_runtime)
    target.submit_and_dispatch("busy", SwarmTask("existing", {}))
    with pytest.raises(ValueError):
        store.restore(target, 1)


def test_tenant_restore_rejects_active_task_missing_from_runtime() -> None:
    runtime = HardenedSwarmRuntime()
    source = _broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("task", {}))
    store = TenantCheckpointStore()
    store.capture(1, source)

    with pytest.raises(ValueError, match="missing from restored runtime"):
        store.restore(_broker(HardenedSwarmRuntime()), 1)


def test_tenant_restore_rejects_active_checkpoint_for_terminal_runtime_task() -> None:
    runtime = HardenedSwarmRuntime()
    source = _broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("task", {}))
    store = TenantCheckpointStore()
    store.capture(1, source)

    terminal_runtime = HardenedSwarmRuntime()
    terminal_runtime.register_worker("w")
    terminal_runtime.submit(SwarmTask("task", {}))
    terminal_runtime.lease("w")
    terminal_runtime.succeed("w", "task")

    with pytest.raises(ValueError, match="active tenant task is terminal"):
        store.restore(_broker(terminal_runtime), 1)


def test_tenant_restore_rejects_terminal_checkpoint_for_active_runtime_task() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w")
    source = _broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("task", {}))
    source.record_success("w", "task", completion_token="done")
    store = TenantCheckpointStore()
    store.capture(1, source)

    active_runtime = HardenedSwarmRuntime()
    active_runtime.submit(SwarmTask("task", {}))
    with pytest.raises(ValueError, match="terminal tenant task is active"):
        store.restore(_broker(active_runtime), 1)


def test_tenant_restore_enforces_target_terminal_capacity() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=2)
    source = _broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("a", {}))
    source.record_success("w", "a", completion_token="a-done")
    source.submit_and_dispatch("acme", SwarmTask("b", {}))
    source.record_success("w", "b", completion_token="b-done")
    store = TenantCheckpointStore()
    store.capture(1, source)

    restored_runtime = HardenedSwarmRuntime.from_state(runtime.export_state())
    with pytest.raises(ValueError, match="terminal record capacity"):
        store.restore(_broker(restored_runtime, max_terminal_records=1), 1)
