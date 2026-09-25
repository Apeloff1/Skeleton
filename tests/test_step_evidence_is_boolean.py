"""A step cannot claim evidence with the string false, and a letter is not a dependency."""

import pytest

from skeleton.jeeves.planning.admission import AdmissionPolicy
from skeleton.jeeves.planning.models import Goal, RiskTier, Step


def test_evidence_and_dependencies_are_not_invented() -> None:
    with pytest.raises(ValueError):
        Step("look", "inspect", evidence_required="false")
    with pytest.raises(ValueError):
        Step("look", "inspect", depends_on="look")
    with pytest.raises(ValueError):
        Step("look", "inspect", risk="critical")
    with pytest.raises(ValueError):
        Goal("goal", "a real goal", priority=True)
    step = Step("look", "inspect", evidence_required=False, risk=RiskTier.LOW)
    assert step.evidence_required is False
    with pytest.raises(ValueError):
        AdmissionPolicy(max_steps=True)
    with pytest.raises(ValueError):
        AdmissionPolicy(require_evidence="false")
