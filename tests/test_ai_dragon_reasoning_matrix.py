"""Fail-closed evidence reasoning extracted from the Dragon wisdom draft."""
from __future__ import annotations

from datetime import datetime
import pytest

from skeleton.ai.webcrawler.dragon_reasoning_matrix import (
    Truth, EvidenceFact, MatrixRule, conjunction, disjunction, negate,
    evaluate_matrix, exception_action,
)


def _fact(key: str, truth: Truth, *, expires: float = 200.0) -> EvidenceFact:
    return EvidenceFact(key, truth, "evidence://" + key, expires)


def test_four_valued_logic_preserves_unknown_and_conflict() -> None:
    assert conjunction((Truth.TRUE, Truth.UNKNOWN)) is Truth.UNKNOWN
    assert conjunction((Truth.CONFLICT, Truth.TRUE)) is Truth.CONFLICT
    assert conjunction((Truth.FALSE, Truth.CONFLICT)) is Truth.FALSE
    assert disjunction((Truth.FALSE, Truth.UNKNOWN)) is Truth.UNKNOWN
    assert disjunction((Truth.TRUE, Truth.CONFLICT)) is Truth.TRUE
    assert negate(Truth.UNKNOWN) is Truth.UNKNOWN
    assert negate(Truth.CONFLICT) is Truth.CONFLICT


def test_positive_evidence_requires_false_exception_and_bound_slots() -> None:
    rule = MatrixRule(
        "release_gate",
        all_of=("source_verified",),
        any_of=("owner_approved",),
        unless=("rights_blocked",),
        required_slots=("where",),
    )
    facts = (
        _fact("source_verified", Truth.TRUE),
        _fact("owner_approved", Truth.TRUE),
        _fact("rights_blocked", Truth.FALSE),
    )
    accepted = evaluate_matrix(
        rule, facts, {"where": "approved game context"},
        now=100.0, genre="rpg", era="modern", engine="godot",
    )
    assert accepted.truth is Truth.TRUE
    assert accepted.eligible is True
    assert accepted.missing == ()
    assert accepted.incomplete == ()
    assert accepted.search_queries == ()
    assert len(accepted.evidence_refs) == 3

    unbound = evaluate_matrix(
        rule, facts, {}, now=100.0, genre="rpg", era="modern", engine="godot",
    )
    assert unbound.truth is Truth.UNKNOWN
    assert not unbound.eligible
    assert "where" in unbound.incomplete
    assert any("where primary evidence" in q for q in unbound.search_queries)


def test_stale_exception_and_contradictions_fail_closed() -> None:
    rule = MatrixRule("rights", all_of=("licence",), unless=("blocked",))
    stale = evaluate_matrix(
        rule, (_fact("licence", Truth.TRUE, expires=10), _fact("blocked", Truth.FALSE)),
        {}, now=20, genre="puzzle", era="retro", engine="native",
    )
    assert stale.truth is Truth.UNKNOWN
    assert not stale.eligible
    assert "licence" in stale.incomplete

    unknown_exception = evaluate_matrix(
        rule, (_fact("licence", Truth.TRUE),),
        {}, now=20, genre="puzzle", era="retro", engine="native",
    )
    assert unknown_exception.truth is Truth.UNKNOWN
    assert "blocked" in unknown_exception.missing

    conflicted = evaluate_matrix(
        rule, (_fact("licence", Truth.CONFLICT), _fact("blocked", Truth.FALSE)),
        {}, now=20, genre="puzzle", era="retro", engine="native",
    )
    assert conflicted.truth is Truth.CONFLICT
    assert not conflicted.eligible


@pytest.mark.parametrize("value", ["tomorrow", object(), None, True, -1.0, float("nan"), float("inf")])
def test_evidence_expiry_rejects_untyped_or_non_finite_values(value: object) -> None:
    with pytest.raises(ValueError):
        EvidenceFact("checked", Truth.TRUE, "evidence://primary", value)


@pytest.mark.parametrize("value", [None, "now", [], 7, True, -1.0, float("nan"), float("inf")])
def test_evaluator_rejects_untyped_timestamps(value: object) -> None:
    with pytest.raises(ValueError):
        evaluate_matrix(MatrixRule("g", all_of=("x",)), (), {}, now=value,
                        genre="rpg", era="2026", engine="native")


def test_schema_rejects_non_tuple_predicates_and_untyped_facts() -> None:
    with pytest.raises(ValueError):
        MatrixRule("bad", all_of="fact")
    with pytest.raises(ValueError):
        MatrixRule("bad", all_of=("fact",), required_slots=("unsafe",))
    with pytest.raises(ValueError):
        MatrixRule("bad", all_of=("fact", "fact"))
    with pytest.raises(ValueError):
        evaluate_matrix(MatrixRule("safe", all_of=("x",)), ("bad",), {}, now=1.0,
                        genre="rpg", era="2026", engine="native")
    with pytest.raises(ValueError):
        evaluate_matrix(MatrixRule("safe", all_of=("x",)), (), ["when"], now=1.0,
                        genre="rpg", era="2026", engine="native")
    with pytest.raises(ValueError):
        evaluate_matrix(MatrixRule("safe", all_of=("x",)),
                        (_fact("x", Truth.TRUE), _fact("x", Truth.FALSE)), {},
                        now=1.0, genre="rpg", era="2026", engine="native")


def test_exception_retries_are_strictly_bounded() -> None:
    assert exception_action("transient_network", 0) == ("bounded_backoff", True)
    assert exception_action("transient_network", 1) == ("bounded_backoff", True)
    assert exception_action("transient_network", 2) == ("bounded_backoff", False)
    assert exception_action("privacy", 0) == ("deny_and_redact", False)
    assert exception_action("unsupported", 0) == ("stop_operator_review", False)
    with pytest.raises(ValueError):
        exception_action("transient_network", True)
