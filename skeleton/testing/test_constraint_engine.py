from __future__ import annotations

import pytest

from skeleton.ai.constraints import (
    Constraint,
    ConstraintSet,
    ConstraintStrength,
    explain_conflict,
)


def constraint(cid, strength, predicate, provenance="policy:test"):
    return Constraint(cid, cid + " description", strength, provenance, predicate)


def test_hard_constraint_is_never_tradeable_by_soft_success() -> None:
    rules = ConstraintSet.of((
        constraint("hard-policy", ConstraintStrength.HARD, lambda _: False),
        constraint("soft-quality", ConstraintStrength.SOFT, lambda _: True),
    ))
    result = rules.evaluate(object())
    assert not result.admissible
    assert not result.utility_eligible
    assert [v.constraint_id for v in result.hard_violations] == ["hard-policy"]


def test_soft_violation_remains_admissible_for_later_utility_scoring() -> None:
    result = ConstraintSet.of((
        constraint("soft-quality", ConstraintStrength.SOFT, lambda _: False),
    )).evaluate(object())
    assert result.admissible
    assert result.utility_eligible
    assert [v.constraint_id for v in result.soft_violations] == ["soft-quality"]


def test_hard_predicate_error_fails_closed_and_is_evidence() -> None:
    def broken(_):
        raise RuntimeError("backend unavailable")

    result = ConstraintSet.of((
        constraint("authority", ConstraintStrength.HARD, broken, "authority:independent"),
    )).evaluate(object())
    assert not result.admissible
    assert result.evaluation_errors == ("authority:RuntimeError",)
    assert result.hard_violations[0].provenance == "authority:independent"


def test_non_boolean_predicate_fails_closed() -> None:
    result = ConstraintSet.of((
        constraint("policy", ConstraintStrength.HARD, lambda _: 1),
    )).evaluate(object())
    assert not result.admissible
    assert result.evaluation_errors == ("policy:TypeError",)


def test_evaluation_order_and_violation_evidence_are_deterministic() -> None:
    rules = ConstraintSet.of((
        constraint("z", ConstraintStrength.HARD, lambda _: False, "source:z"),
        constraint("a", ConstraintStrength.HARD, lambda _: False, "source:a"),
    ))
    result = rules.evaluate(None)
    assert [v.constraint_id for v in result.hard_violations] == ["a", "z"]
    assert [v.provenance for v in result.hard_violations] == ["source:a", "source:z"]


def test_duplicate_constraint_identity_fails_closed() -> None:
    with pytest.raises(ValueError):
        ConstraintSet.of((
            constraint("same", ConstraintStrength.HARD, lambda _: True),
            constraint("same", ConstraintStrength.SOFT, lambda _: True),
        ))


def test_conflict_explanation_preserves_both_provenances() -> None:
    left = constraint("retain", ConstraintStrength.HARD, lambda _: True, "user:retention")
    right = constraint("delete", ConstraintStrength.HARD, lambda _: True, "policy:expiry")
    conflict = explain_conflict(left, right, "retention and deletion requirements overlap")
    assert conflict.provenance == ("user:retention", "policy:expiry")


def test_conflict_cannot_be_self_referential_or_unexplained() -> None:
    rule = constraint("one", ConstraintStrength.HARD, lambda _: True)
    with pytest.raises(ValueError):
        explain_conflict(rule, rule, "same")
    other = constraint("two", ConstraintStrength.HARD, lambda _: True)
    with pytest.raises(ValueError):
        explain_conflict(rule, other, "")
