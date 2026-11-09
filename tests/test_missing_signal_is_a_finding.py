"""A missing blocking signal is a finding, and the catalog rules load."""

import pytest

from skeleton.jeeves.planning.catalog import PlanningSignal, blocking_rules, evaluate_signals, rules_for


def test_an_empty_reading_does_not_pass_blocking_rules() -> None:
    blocking = blocking_rules()
    assert blocking
    findings = evaluate_signals({})
    assert set(findings) == {rule.name for rule in blocking}
    with pytest.raises(ValueError):
        rules_for("cost")
    cost = rules_for(PlanningSignal.COST)
    assert cost
    quiet = {signal: 0.0 for signal in PlanningSignal}
    assert evaluate_signals(quiet)
    clear = {signal: 1.0 for signal in PlanningSignal}
    assert evaluate_signals(clear) == ()
    with pytest.raises(TypeError):
        evaluate_signals({PlanningSignal.COST: True})
