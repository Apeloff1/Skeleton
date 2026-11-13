import pytest

from skeleton.gameforge.batch_b039 import (
    Budget, EvalFailure, EvalResult, Mutation, RepairLoop, RouteChoice, diagnose,
)


def evaluator(a):
    hp = a.get("hp", 0)
    fails = []
    if "hp" not in a:
        fails.append(EvalFailure("schema.hp", "missing field"))
    elif hp < 10:
        fails.append(EvalFailure("rule.hp_min", "invariant hp>=10"))
    return EvalResult(score=min(hp, 10) / 10, failures=tuple(fails))


def router(diags):
    return RouteChoice("m-small", "local", 0.5)


def inc_proposer(a, diags, route):
    return Mutation("hp", {**a, "hp": a.get("hp", 0) + 4}, cost=1.0)


class Clock:
    def __init__(self, step=1.0):
        self.t, self.step = 0.0, step

    def __call__(self):
        self.t += self.step
        return self.t


def loop(budget, proposer=inc_proposer, clock=None, patience=2):
    return RepairLoop(evaluator, proposer, router, budget, clock or Clock(0.0), patience)


def test_diagnose_categories_ordered():
    r = EvalResult(0, (EvalFailure("rule.x", "bad"), EvalFailure("schema.y", "missing"),
                       EvalFailure("z", "w", "warning"), EvalFailure("q", "???")))
    assert [d.category for d in diagnose(r)] == ["schema", "logic", "unknown"]


def test_already_passing():
    out = loop(Budget(5, 10, 10)).run({"hp": 12})
    assert out.status == "already_passing" and out.steps == 0


def test_repairs_within_budget():
    out = loop(Budget(5, 100, 100)).run({"hp": 1})
    assert out.status == "repaired" and out.artifact["hp"] == 13
    assert out.steps == 3 and out.cost_spent == pytest.approx(4.5)
    assert [p.step for p in out.provenance] == [1, 2, 3]
    assert out.provenance[0].model == "m-small"


def test_mutation_budget():
    out = loop(Budget(1, 100, 100)).run({"hp": 1})
    assert out.status == "exhausted" and out.stop_reason == "mutation budget" and out.steps == 1


def test_cost_budget_never_exceeded():
    out = loop(Budget(10, 100, 2.0)).run({"hp": 1})
    assert out.status == "exhausted" and out.stop_reason == "cost budget"
    assert out.cost_spent <= 2.0


def test_time_budget():
    out = loop(Budget(10, 1.5, 100), clock=Clock(1.0)).run({"hp": 1})
    assert out.stop_reason == "time budget"


def test_stalls_on_no_improvement_and_keeps_best():
    out = loop(Budget(10, 100, 100), proposer=lambda a, d, r: Mutation("hp", {"hp": 0}, 0.1)).run({"hp": 5})
    assert out.status == "stalled" and out.artifact == {"hp": 5} and out.steps == 2


def test_proposer_none_stalls():
    out = loop(Budget(10, 100, 100), proposer=lambda a, d, r: None).run({"hp": 1})
    assert out.status == "stalled" and out.steps == 0


def test_deterministic_provenance():
    a = loop(Budget(5, 100, 100)).run({"hp": 1}).provenance
    b = loop(Budget(5, 100, 100)).run({"hp": 1}).provenance
    assert a == b


def test_invalid_budget_and_patience():
    with pytest.raises(ValueError):
        Budget(-1, 1, 1)
    with pytest.raises(ValueError):
        loop(Budget(1, 1, 1), patience=0)


def test_negative_cost_rejected():
    with pytest.raises(ValueError):
        RepairLoop(evaluator, lambda a, d, r: Mutation("hp", {"hp": 20}, -5), lambda d: RouteChoice("m", "p"),
                   Budget(3, 10, 10), Clock(0.0)).run({"hp": 1})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "unbounded"])
def test_invalid_nonfinite_budget_limits_are_denied(value):
    with pytest.raises(ValueError):
        Budget(1, value, 5)
    with pytest.raises(ValueError):
        Budget(1, 5, value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, -1])
def test_mutation_and_route_costs_fail_closed(value):
    with pytest.raises(ValueError):
        Mutation("hp", {"hp": 10}, value)
    with pytest.raises(ValueError):
        RouteChoice("m", "local", value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "invalid"])
def test_evaluator_score_is_always_finite(value):
    with pytest.raises(ValueError):
        EvalResult(value)


@pytest.mark.parametrize("value", [True, 1.5, -1, "1"])
def test_mutation_count_is_nonnegative_integer(value):
    with pytest.raises(ValueError):
        Budget(value, 1, 1)


def test_nonfinite_clock_rejected_before_repair():
    with pytest.raises(ValueError, match="clock"):
        loop(Budget(1, 10, 10), clock=lambda: float("nan")).run({"hp": 0})


def test_rewinding_clock_rejected_without_spending_budget():
    samples = iter((10.0, 9.0))
    repair = loop(Budget(2, 10, 10), clock=lambda: next(samples))
    with pytest.raises(ValueError, match="monotonically"):
        repair.run({"hp": 0})


def test_budgeted_repair_still_completes_with_exact_finite_cost():
    outcome = loop(Budget(3, 100, 4.5)).run({"hp": 1})
    assert outcome.status == "repaired"
    assert outcome.steps == 3
    assert outcome.cost_spent == pytest.approx(4.5)
    assert outcome.artifact["hp"] >= 10
