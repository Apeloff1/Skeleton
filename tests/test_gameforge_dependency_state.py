import pytest

from skeleton.frontier.gameforge_dependency import DependencyGate


def test_dependency_gate_reports_pending_and_count():
    gate = DependencyGate(["db", "cache"])
    assert gate.pending == frozenset({"db", "cache"})
    assert gate.ready_count == 0
    assert not gate.mark("db")
    assert gate.pending == frozenset({"cache"})
    assert gate.mark("cache")
    assert gate.ready


def test_dependency_gate_rejects_non_boolean_state():
    gate = DependencyGate(["db"])
    with pytest.raises(TypeError):
        gate.mark("db", 1)
