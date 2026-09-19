from skeleton.jeeves.planning import *
import pytest


def sample_plan():
    goal = Goal("deploy", "prepare a bounded deployment plan", priority=80)
    steps = (
        Step("inspect", "inspect inputs", risk=RiskTier.LOW),
        Step("validate", "validate inputs", depends_on=("inspect",), risk=RiskTier.MEDIUM),
        Step("report", "write report", depends_on=("validate",), risk=RiskTier.LOW),
    )
    return Plan(goal, steps)


def test_topological_order_is_deterministic():
    assert topological_order(sample_plan()) == ("inspect", "validate", "report")


def test_cycle_rejected():
    with pytest.raises(ValueError, match="cycle"):
        Plan(Goal("x", "x"), (Step("a", "a", depends_on=("b",)), Step("b", "b", depends_on=("a",))))


def test_admission_and_ledger():
    plan = sample_plan()
    result = admit(plan, constraints=(Constraint("required-report", ConstraintKind.REQUIRED, value="report"),))
    assert result.admitted
    ledger = PlanLedger()
    ledger.record_plan(plan)
    ledger.record_admission(result)
    assert ledger.verify()


def test_forbidden_constraint_rejects():
    plan = Plan(Goal("x", "x"), (Step("a", "run forbidden thing"),))
    result = admit(plan, constraints=(Constraint("no-run", ConstraintKind.FORBIDDEN, value="forbidden"),))
    assert not result.admitted


def test_replan_requires_current_base():
    plan = sample_plan()
    proposal = propose(plan, (Observation("validate", ReplanReason.EVIDENCE_GAP, "coverage missing", 90),))
    changed = apply_proposal(plan, proposal)
    assert changed.state is PlanState.DRAFT
    assert "verify:validate" in {s.name for s in changed.steps}
    with pytest.raises(ValueError):
        apply_proposal(plan, ReplanProposal("0" * 64, (), (), (), 0.5))


def test_state_machine_is_fail_closed():
    plan = sample_plan()
    ready = with_state(plan, PlanState.READY)
    approved = with_state(ready, PlanState.APPROVED)
    with pytest.raises(ValueError):
        with_state(approved, PlanState.READY)
