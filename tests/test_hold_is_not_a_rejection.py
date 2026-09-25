"""A hold is not a rejection, and a proposal that changes nothing is not a replan."""

import pytest

from skeleton.jeeves.planning.admission import AdmissionDecision, AdmissionResult
from skeleton.jeeves.planning.ledger import EventKind, PlanLedger
from skeleton.jeeves.planning.models import Goal, Plan, Step
from skeleton.jeeves.planning.replanning import Observation, ReplanProposal, ReplanReason, apply_proposal


def test_a_hold_is_not_written_as_rejected() -> None:
    ledger = PlanLedger()
    plan_id = "ab" * 32
    with pytest.raises(ValueError):
        ledger.record_admission(AdmissionResult(AdmissionDecision.HOLD, plan_id, (), ()))
    with pytest.raises(ValueError):
        ledger.append(plan_id, "admitted", "created")
    event = ledger.append(plan_id, EventKind.CREATED, "draft")
    assert event.kind is EventKind.CREATED
    assert ledger.verify() is True
    with pytest.raises(ValueError):
        Observation("sensor", "evidence_gap", "missing", severity=True)
    plan = Plan(Goal("goal", "a real goal"), (Step("look", "inspect"),))
    proposal = ReplanProposal(plan.id, (), (), ("no change",), 1.0)
    with pytest.raises(ValueError):
        apply_proposal(plan, proposal)
    with pytest.raises(ValueError):
        ReplanProposal(plan.id, (), (), ("sure",), True)
    observed = Observation("look", ReplanReason.DEPENDENCY_FAILURE, "blocked", severity=80)
    assert observed.reason is ReplanReason.DEPENDENCY_FAILURE
