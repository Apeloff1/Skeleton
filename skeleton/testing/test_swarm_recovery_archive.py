import pytest

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


def test_recovery_archive_round_trip_restores_runtime_and_tenants() -> None:
    runtime = HardenedSwarmRuntime()
    tenant = _tenant_broker(runtime)
    tenant.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    manager = SwarmRecoveryManager(max_checkpoints=4)
    manager.checkpoint(runtime, tenant)

    restored_manager = SwarmRecoveryManager.from_archive_bytes(manager.export_archive_bytes())
    restored_runtime = restored_manager.restore_latest()
    assert restored_runtime is not None
    restored_tenant = _tenant_broker(restored_runtime)
    repair = restored_manager.restore_tenants(restored_tenant)

    assert restored_manager.status().latest_sequence == 1
    assert restored_manager.status().tenant_aligned is True
    assert restored_runtime.task("task") is not None
    assert restored_tenant.tenant_for("task") == "acme"
    assert restored_tenant.ingress.phase("acme", "task") == "queued"
    assert repair is not None and repair.restored_accounting == 1


def test_recovery_archive_preserves_sequence_monotonicity_after_import() -> None:
    runtime = HardenedSwarmRuntime()
    manager = SwarmRecoveryManager(max_checkpoints=4)
    assert manager.checkpoint(runtime) == 1
    assert manager.checkpoint(runtime) == 2

    restored = SwarmRecoveryManager.from_archive(manager.export_archive())
    assert restored.checkpoint(runtime) == 3
    assert restored.store.sequences() == (1, 2, 3)


def test_recovery_archive_rejects_outer_checksum_tampering() -> None:
    manager = SwarmRecoveryManager()
    manager.checkpoint(HardenedSwarmRuntime())
    archive = manager.export_archive()
    archive["max_checkpoints"] = 99

    with pytest.raises(ValueError, match="archive checksum mismatch"):
        SwarmRecoveryManager.from_archive(archive)


def test_recovery_archive_rejects_runtime_checkpoint_corruption_even_with_resealed_archive() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("task", {}))
    manager = SwarmRecoveryManager()
    manager.checkpoint(runtime)
    archive = manager.export_archive()
    archive["runtime"][0]["state"]["tasks"][0]["priority"] = 999
    payload = {key: value for key, value in archive.items() if key != "archive_checksum"}
    archive["archive_checksum"] = SwarmRecoveryManager._archive_checksum(payload)

    with pytest.raises(ValueError, match="checkpoint checksum mismatch"):
        SwarmRecoveryManager.from_archive(archive)


def test_recovery_archive_rejects_orphan_tenant_sidecar() -> None:
    runtime = HardenedSwarmRuntime()
    tenant = _tenant_broker(runtime)
    manager = SwarmRecoveryManager()
    manager.checkpoint(runtime, tenant)
    archive = manager.export_archive()
    archive["runtime"] = []
    payload = {key: value for key, value in archive.items() if key != "archive_checksum"}
    archive["archive_checksum"] = SwarmRecoveryManager._archive_checksum(payload)

    with pytest.raises(ValueError, match="no runtime checkpoint"):
        SwarmRecoveryManager.from_archive(archive)


def test_recovery_archive_rejects_invalid_bytes() -> None:
    with pytest.raises(ValueError, match="invalid recovery archive payload"):
        SwarmRecoveryManager.from_archive_bytes(b"not-json")

    with pytest.raises(TypeError, match="must be bytes"):
        SwarmRecoveryManager.from_archive_bytes("not-bytes")
