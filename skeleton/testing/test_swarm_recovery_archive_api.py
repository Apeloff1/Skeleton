import copy

import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_ingress import SwarmIngressGovernor
from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmTask
from skeleton.api import swarm_recovery_archive_routes as routes
from skeleton.api.server import ServerState


def _state() -> ServerState:
    state = ServerState()
    state.bind_swarm_runtime(HardenedSwarmRuntime())
    state.bind_swarm_ingress(SwarmIngressGovernor(rate_capacity=100, rate_refill_per_second=100))
    state.swarm_recovery = SwarmRecoveryManager(max_checkpoints=4)
    return state


def test_archive_api_round_trip_preserves_paired_history(monkeypatch) -> None:
    source = _state()
    source.swarm_tenant_broker.submit_and_dispatch("acme", SwarmTask("task", {"x": 1}))
    source.swarm_recovery.checkpoint(source.swarm, source.swarm_tenant_broker)
    monkeypatch.setattr(routes, "_state", lambda: source)

    exported = routes.export_recovery_archive()
    assert exported["status"]["latest_sequence"] == 1
    assert exported["status"]["latest_tenant_sequence"] == 1
    assert exported["bytes"] > 0

    target = _state()
    old_runtime = target.swarm
    old_broker = target.swarm_broker
    monkeypatch.setattr(routes, "_state", lambda: target)

    imported = routes.import_recovery_archive(routes.RecoveryArchiveImport(archive=exported["archive"]))

    assert imported["imported"] is True
    assert imported["status"]["latest_sequence"] == 1
    assert imported["status"]["latest_tenant_sequence"] == 1
    assert target.swarm is old_runtime
    assert target.swarm_broker is old_broker


def test_archive_import_rejects_tamper_without_replacing_manager(monkeypatch) -> None:
    state = _state()
    state.swarm_recovery.checkpoint(state.swarm, state.swarm_tenant_broker)
    old_manager = state.swarm_recovery
    archive = copy.deepcopy(old_manager.export_archive())
    archive["runtime"][0]["state"]["counters"]["submitted"] = 999
    monkeypatch.setattr(routes, "_state", lambda: state)

    with pytest.raises(HTTPException) as exc:
        routes.import_recovery_archive(routes.RecoveryArchiveImport(archive=archive))

    assert exc.value.status_code == 422
    assert state.swarm_recovery is old_manager
    assert state.swarm_recovery.status().latest_sequence == 1


def test_archive_import_honors_body_size_limit(monkeypatch) -> None:
    state = _state()
    state.swarm.submit(SwarmTask("large", {"blob": "x" * 4096}))
    state.swarm_recovery.checkpoint(state.swarm)
    archive = state.swarm_recovery.export_archive()
    monkeypatch.setattr(routes, "_state", lambda: state)

    with pytest.raises(HTTPException) as exc:
        routes.import_recovery_archive(routes.RecoveryArchiveImport(archive=archive, max_bytes=1024))

    assert exc.value.status_code == 413


def test_archive_export_rejects_oversize_history(monkeypatch) -> None:
    state = _state()
    state.swarm.submit(SwarmTask("large", {"blob": "x" * 4096}))
    state.swarm_recovery.checkpoint(state.swarm)
    monkeypatch.setattr(routes, "_state", lambda: state)
    monkeypatch.setattr(routes, "MAX_ARCHIVE_BYTES", 256)

    with pytest.raises(HTTPException) as exc:
        routes.export_recovery_archive()

    assert exc.value.status_code == 413
