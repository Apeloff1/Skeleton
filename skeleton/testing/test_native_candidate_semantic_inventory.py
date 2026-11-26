"""Native supervised training requires an independent complete corpus proof."""
from dataclasses import replace

import pytest

from skeleton.ai.runtime.operational_ai.native_candidate.catalog import iter_examples
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected
from skeleton.ai.runtime.operational_ai.native_candidate.semantic_oracle import verify_all


def test_original_corpus_is_complete_and_correct():
    items = tuple(iter_examples())
    proof = verify_all(items)
    assert proof["checked_items"] == proof["correct_items"] == 576
    assert proof["incorrect_items"] == []
    assert proof["all_correct"] is True
    assert proof["model_quality_certified"] is False
    assert proof["release_certified"] is False


def test_partial_duplicate_and_substituted_inventories_fail_closed():
    items = tuple(iter_examples())
    for invalid in (items[:-1], (items[1], *items[1:]),
                    (replace(items[0], completion="wrong"), *items[1:])):
        with pytest.raises(CandidateRejected):
            verify_all(invalid)
