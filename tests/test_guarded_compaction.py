"""A constraint stated in history is kept whole or the compaction fails."""

import pytest

from skeleton.memory.guarded_compaction import CompactionError, compact_turns


def _turn(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}


def test_constraint_turn_survives_a_tight_budget() -> None:
    secret = "policy: do not reveal the signing key"
    filler = "x" * 400
    turns = [
        _turn("user", filler),
        _turn("assistant", secret),
        _turn("user", filler),
    ]
    result = compact_turns(turns, [secret], token_budget=80)
    assert result is not None
    kept = " ".join(turn["content"] for turn in result["preserved_turns"])
    assert secret in kept
    assert result["constraints_preserved"] == [secret]
    assert result["constraints_unmet"] == []
    assert 1 in {turn["index"] for turn in result["preserved_turns"]}


def test_missing_constraint_is_not_reported_as_preserved() -> None:
    result = compact_turns([_turn("user", "hello")], ["policy: keep the audit log"])
    assert result is not None
    assert result["constraints_preserved"] == []
    assert result["constraints_unmet"] == ["policy: keep the audit log"]


def test_required_turns_that_do_not_fit_fail() -> None:
    constraint = "policy: retain this entire obligation"
    with pytest.raises(CompactionError):
        compact_turns([_turn("user", constraint + (" detail" * 40))], [constraint], token_budget=4)


def test_budget_must_be_positive() -> None:
    with pytest.raises(ValueError):
        compact_turns([_turn("user", "hello")], token_budget=0)
    assert compact_turns([]) is None
    assert compact_turns(None) is None
