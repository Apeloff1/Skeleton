import pytest

from skeleton.frontier.gameforge_snapshot import RuntimeSnapshot


def test_snapshot_reports_saturation():
    snapshot = RuntimeSnapshot("ready", True, 2, 2, 2)
    assert snapshot.saturated


def test_snapshot_recoverability_requires_live_ready_dependencies():
    assert RuntimeSnapshot("ready", True, 0, 0, 2).recoverable
    assert not RuntimeSnapshot("ready", False, 0, 0, 2).recoverable
    assert not RuntimeSnapshot("stopped", True, 0, 0, 2).recoverable


def test_snapshot_rejects_boolean_counters():
    with pytest.raises(TypeError):
        RuntimeSnapshot("ready", True, True, 0, 2)


def test_snapshot_rejects_budget_overflow():
    with pytest.raises(ValueError):
        RuntimeSnapshot("ready", True, 0, 3, 2)


def test_snapshot_rejects_invalid_health():
    with pytest.raises(ValueError):
        RuntimeSnapshot("ready", True, 0, 0, 2, health=1.1)
