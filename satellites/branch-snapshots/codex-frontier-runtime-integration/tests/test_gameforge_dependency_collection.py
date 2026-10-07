import pytest

from skeleton.frontier.gameforge_dependency import DependencyGate


def test_dependency_gate_rejects_scalar_string():
    with pytest.raises(TypeError):
        DependencyGate("database")
