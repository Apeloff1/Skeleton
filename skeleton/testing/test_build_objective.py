import pytest
from skeleton.automation.build_objective import BuildObjective
def test_objective():BuildObjective("x",("CI/CD",),("queue_drained",)).validate()
def test_duplicate_gate_rejected():
 with pytest.raises(ValueError):BuildObjective("x",("CI/CD","CI/CD"),("x",)).validate()
