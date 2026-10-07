import pytest

from skeleton.frontier.gameforge_snapshot import RuntimeSnapshot


def test_snapshot_rejects_invalid_health():
    with pytest.raises(ValueError):
        RuntimeSnapshot("ready", True, 0, 0, 2, health=2.0)


def test_snapshot_reports_recoverability():
    snapshot = RuntimeSnapshot("ready", True, 0, 0, 2)
    assert snapshot.recoverable
    assert not snapshot.saturated
