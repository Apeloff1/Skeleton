import pytest
from skeleton.frontier.gameforge_dependency import DependencyGate

def test_dependency_gate_requires_all():
 g=DependencyGate(("db","cache")); assert not g.ready; g.mark("db"); assert not g.ready; g.mark("cache"); assert g.ready

def test_dependency_gate_rejects_unknown():
 with pytest.raises(KeyError): DependencyGate(("db",)).mark("x")
