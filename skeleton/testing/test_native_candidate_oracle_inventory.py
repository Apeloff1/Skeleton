"""The supervised source gate must evaluate the complete original corpus."""
from dataclasses import replace

import pytest

from skeleton.ai.runtime.operational_ai.native_candidate.catalog import iter_examples
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected
from skeleton.ai.runtime.operational_ai.native_candidate.semantic_oracle import verify_all


def test_original_complete_inventory_is_evaluated():
    items = tuple(iter_examples())
    result = verify_all(items)
    assert result["count"] == result["correct_count"] == 576
    assert result["complete"] is True
    assert result["all_correct"] is True


def test_incomplete_inventory_is_not_qualified():
    items = tuple(iter_examples())
    assert verify_all(())["all_correct"] is False
    assert verify_all(items[:-1])["all_correct"] is False


def test_changed_completion_is_never_qualified():
    items = tuple(iter_examples())
    changed = replace(items[0], completion=items[0].completion + " incorrect")
    result = verify_all((changed, *items[1:]))
    assert result["incorrect_count"] == 1
    assert result["all_correct"] is False


def test_duplicate_inventory_fails_closed():
    items = tuple(iter_examples())
    with pytest.raises(CandidateRejected, match="oracle-duplicate"):
        verify_all((items[0], items[0], *items[2:]))
