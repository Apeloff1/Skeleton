from __future__ import annotations

import math

import pytest

from skeleton.jeeves.decision.policy import PolicyKind, RULES as POLICY_RULES
from skeleton.jeeves.decision.provenance import ProvenanceKind, RULES as PROVENANCE_RULES
from skeleton.jeeves.decision.scoring import ScoringKind, RULES as SCORING_RULES


@pytest.mark.parametrize(
    ("rules", "count", "prefix"),
    [
        (POLICY_RULES, 240, "policy"),
        (PROVENANCE_RULES, 180, "provenance"),
        (SCORING_RULES, 220, "scoring"),
    ],
)
def test_generated_decision_rules_have_stable_shape(rules, count, prefix):
    assert len(rules) == count
    assert rules[0].name == f"{prefix}_001"
    assert rules[-1].name == f"{prefix}_{count:03d}"
    assert rules[0].threshold == pytest.approx(0.01)
    assert rules[99].threshold == pytest.approx(1.0)
    if count > 100:
        assert rules[100].threshold == pytest.approx(0.01)


@pytest.mark.parametrize(
    ("rules", "kinds"),
    [
        (POLICY_RULES, tuple(PolicyKind)),
        (PROVENANCE_RULES, tuple(ProvenanceKind)),
        (SCORING_RULES, tuple(ScoringKind)),
    ],
)
def test_generated_decision_rules_rotate_kinds_deterministically(rules, kinds):
    assert tuple(rule.kind for rule in rules[:5]) == (
        kinds[1],
        kinds[2],
        kinds[3],
        kinds[4],
        kinds[0],
    )
    assert all(rule.kind in kinds for rule in rules)


@pytest.mark.parametrize("rules", [POLICY_RULES, PROVENANCE_RULES, SCORING_RULES])
@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf, "0.5"])
def test_decision_rules_reject_non_finite_or_non_numeric_inputs(rules, value):
    with pytest.raises(ValueError, match="finite"):
        rules[0].applies(value)


@pytest.mark.parametrize("rules", [POLICY_RULES, PROVENANCE_RULES, SCORING_RULES])
def test_decision_rules_apply_thresholds(rules):
    rule = rules[49]
    assert rule.threshold == pytest.approx(0.5)
    assert not rule.applies(0.499)
    assert rule.applies(0.5)
