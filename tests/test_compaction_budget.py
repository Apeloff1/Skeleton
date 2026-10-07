"""A non-positive context budget is not a compaction plan."""

import pytest

from skeleton.memory.compaction import ContextCompactor, Turn


def test_token_budget_must_be_positive() -> None:
    with pytest.raises(ValueError):
        ContextCompactor(token_budget=0)
    compactor = ContextCompactor(token_budget=8)
    short = [Turn("user", "hi")]
    kept = compactor.compact(short)
    assert kept.compacted is False
    assert kept.turns == short
