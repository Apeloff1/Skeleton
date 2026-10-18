"""Self-learn practice stays off the holdouts and reviews weak concepts first."""
from __future__ import annotations

from skeleton.ai.runtime.inference.english_game_pareto import holdout_documents
from skeleton.ai.runtime.inference.game_self_learn import (
    leaks_holdout,
    practice_by_concept,
    practice_documents,
    review_documents,
    review_order,
)


def test_practice_is_large_and_holdout_free():
    docs = practice_documents()
    assert len(docs) >= 400
    assert len(docs) == len(set(docs))
    for text in docs:
        assert len(text) >= 40
        assert leaks_holdout(text) is False
    for held in holdout_documents():
        assert held not in "\n".join(docs)


def test_review_puts_the_weakest_concept_first():
    grouped = practice_by_concept()
    losses = {name: 1.0 for name in grouped}
    losses["tick"] = 3.5
    losses["scale"] = 2.2
    order = review_order(losses)
    assert order[0] == "tick"
    assert order[1] == "scale"
    reviewed = review_documents(losses, rounds=2)
    assert reviewed[0] in grouped["tick"]
    assert len(reviewed) == 2 * sum(len(lines) for lines in grouped.values())


def test_a_holdout_window_is_rejected():
    sample = holdout_documents()[0]
    assert leaks_holdout(sample) is True
    assert leaks_holdout(sample[:40]) is True
