import pytest

from skeleton.frontier.gameforge_dependency import DependencyGate


def test_empty_dependency_set_is_not_implicitly_ready():
    with pytest.raises(ValueError):
        DependencyGate([])


def test_whitespace_dependency_name_is_rejected():
    with pytest.raises(ValueError):
        DependencyGate(["   "])
