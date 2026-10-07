from __future__ import annotations

from skeleton.agents.swarm_recovery import SwarmRecoveryManager
from skeleton.api import swarm_recovery_archive_routes as routes


class _CountingLock:
    def __init__(self) -> None:
        self.depth = 0
        self.acquisitions = 0

    def __enter__(self):
        self.depth += 1
        self.acquisitions += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.depth -= 1


class _State:
    def __init__(self) -> None:
        self._swarm_bind_lock = _CountingLock()
        self.swarm_recovery = None


def test_lazy_recovery_initialization_uses_server_state_lock(monkeypatch) -> None:
    state = _State()
    monkeypatch.setattr(routes, "_state", lambda: state)

    recovery = routes._recovery()

    assert isinstance(recovery, SwarmRecoveryManager)
    assert state.swarm_recovery is recovery
    assert state._swarm_bind_lock.acquisitions == 1
    assert state._swarm_bind_lock.depth == 0


def test_archive_import_publishes_verified_manager_under_server_lock(monkeypatch) -> None:
    state = _State()
    original = SwarmRecoveryManager(max_checkpoints=4)
    state.swarm_recovery = original
    monkeypatch.setattr(routes, "_state", lambda: state)

    source = SwarmRecoveryManager(max_checkpoints=4)
    body = routes.RecoveryArchiveImport(archive=source.export_archive())
    result = routes.import_recovery_archive(body)

    assert result["imported"] is True
    assert state.swarm_recovery is not original
    assert isinstance(state.swarm_recovery, SwarmRecoveryManager)
    assert state._swarm_bind_lock.acquisitions == 1
    assert state._swarm_bind_lock.depth == 0


def test_invalid_archive_never_enters_publication_lock(monkeypatch) -> None:
    state = _State()
    original = SwarmRecoveryManager(max_checkpoints=4)
    state.swarm_recovery = original
    monkeypatch.setattr(routes, "_state", lambda: state)

    archive = original.export_archive()
    archive["archive_checksum"] = "tampered"
    body = routes.RecoveryArchiveImport(archive=archive)

    try:
        routes.import_recovery_archive(body)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
    else:
        raise AssertionError("tampered archive should be rejected")

    assert state.swarm_recovery is original
    assert state._swarm_bind_lock.acquisitions == 0
