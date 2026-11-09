from __future__ import annotations

import subprocess

import pytest

from scripts.check_p3t2_continuation_candidates import EXPECTED_UNION, validate
from scripts.p3t2_candidate_common import P3T2CandidateError


def head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def test_batch_covers_exact_training_learning_multimodal_frontier() -> None:
    result = validate(head=head())
    assert result["task_ids"] == [
        "P3T2-TRAINING-01",
        "P3T2-LEARNING-01",
        "P3T2-MULTIMODAL-01",
    ]
    assert tuple(result["volume_refs"]) == EXPECTED_UNION
    assert result["volume_count"] == 17
    assert result["implementation_module_count"] == 17
    assert result["executable_test_count"] == 17
    assert result["promotion_authority"] is False


def test_batch_rejects_non_checkout_head() -> None:
    other = "c" * 40 if head() != "c" * 40 else "d" * 40
    with pytest.raises(P3T2CandidateError, match="does not match checkout"):
        validate(head=other)
