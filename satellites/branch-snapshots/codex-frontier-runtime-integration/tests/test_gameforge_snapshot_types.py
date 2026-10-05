import pytest

from skeleton.frontier.gameforge_snapshot import RuntimeSnapshot


def test_snapshot_rejects_boolean_counters():
    with pytest.raises(TypeError):
        RuntimeSnapshot("running", True, True, 0, 1)


def test_snapshot_rejects_boolean_health():
    with pytest.raises(TypeError):
        RuntimeSnapshot("running", True, 0, 0, 1, health=True)
