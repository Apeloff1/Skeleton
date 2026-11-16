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


def test_reordered_original_catalog_preserves_exact_identity():
    items = tuple(iter_examples())
    forward = verify_all(items)
    assert verify_all(tuple(reversed(items))) == forward


@pytest.mark.parametrize("field,value", [
    ("prompt", "Compute 1 plus 2"),
    ("completion", "foreign completion"),
    ("group_id", "foreign_group"),
])
def test_source_changes_with_same_record_identifier_are_rejected(field, value):
    items = tuple(iter_examples())
    changed = replace(items[0], **{field: value})
    assert changed.item_id == items[0].item_id
    assert changed.source_digest != items[0].source_digest
    with pytest.raises(CandidateRejected, match="oracle-source-identity"):
        verify_all((changed, *items[1:]))
