"""A constraint that nothing checks is not valid, and True is not a budget."""

import pytest

from skeleton.jeeves.planning.constraints import Constraint, ConstraintKind, validate_constraints
from skeleton.jeeves.planning.models import Goal, Plan, Step


def test_an_unenforced_kind_does_not_pass() -> None:
    with pytest.raises(ValueError):
        Constraint("cap", ConstraintKind.BUDGET, limit=True)
    with pytest.raises(ValueError):
        Constraint("need", ConstraintKind.REQUIRED)
    with pytest.raises(ValueError):
        Constraint("need", "required", value="look")
    plan = Plan(Goal("goal", "a real goal"), (Step("look", "inspect"),))
    report = validate_constraints(plan, (Constraint("safe", ConstraintKind.SAFETY),))
    assert report.valid is False
    assert report.violations[0].reason == "constraint kind is not enforced"
    held = validate_constraints(plan, (Constraint("cap", ConstraintKind.BUDGET, limit=1),))
    assert held.valid is True
