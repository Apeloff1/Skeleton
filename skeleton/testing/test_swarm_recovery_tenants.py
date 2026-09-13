from dataclasses import asdict

from skeleton.agents.swarm_broker import SwarmBroker
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


def test_checkpoint_captures_runtime_and_tenant_sidecar_at_same_sequence() -> None:
    runtime = HardenedSwarmRuntime()
    broker = _tenant_broker(runtime)
    broker.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    recovery = SwarmRecoveryManager(max_checkpoints=4)

    sequence = recovery.checkpoint(runtime, broker)
    status = recovery.status()

    assert sequence == 1
    assert status.latest_sequence == 1
    assert status.latest_tenant_sequence == 1
    assert status.tenant_aligned is True
    assert status.tenant_checkpoints == 1


def test_cold_restore_reconstructs_tenant_ownership_and_accounting() -> None:
    runtime = HardenedSwarmRuntime()
    source = _tenant_broker(runtime)
    source.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(runtime, source)

    restored_runtime = recovery.restore_latest()
    assert restored_runtime is not None
    target = _tenant_broker(restored_runtime)
    repair = recovery.restore_tenants(target)

    assert repair is not None
    assert target.tenant_for("task") == "acme"
    assert target.ingress.phase("acme", "task") == "queued"
    assert repair.restored_accounting == 1


def test_runtime_only_checkpoint_remains_backward_compatible() -> None:
    runtime = HardenedSwarmRuntime()
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(runtime)
    status = recovery.status()

    assert status.checkpoints == 1
    assert status.tenant_checkpoints == 0
    assert status.latest_tenant_sequence is None
    assert status.tenant_aligned is True

    restored = recovery.restore_latest()
    assert restored is not None
    target = _tenant_broker(restored)
    assert recovery.restore_tenants(target) is None


def test_status_detects_tenant_sidecar_lag() -> None:
    runtime = HardenedSwarmRuntime()
    broker = _tenant_broker(runtime)
    recovery = SwarmRecoveryManager()
    recovery.checkpoint(runtime, broker)
    runtime.submit(SwarmTask("later", {}))
    recovery.checkpoint(runtime)

    status = asdict(recovery.status())
    assert status["latest_sequence"] == 2
    assert status["latest_tenant_sequence"] == 1
    assert status["tenant_aligned"] is False


def test_tenant_sidecar_is_bounded_with_runtime_store() -> None:
    runtime = HardenedSwarmRuntime()
    broker = _tenant_broker(runtime)
    recovery = SwarmRecoveryManager(max_checkpoints=2)

    recovery.checkpoint(runtime, broker)
    recovery.checkpoint(runtime, broker)
    recovery.checkpoint(runtime, broker)

    assert len(recovery.store) == 2
    assert len(recovery.tenant_store) == 2
    assert recovery.status().latest_sequence == 3
    assert recovery.status().latest_tenant_sequence == 3
