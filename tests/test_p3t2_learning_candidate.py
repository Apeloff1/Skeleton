from __future__ import annotations

import subprocess

import pytest

from scripts.check_p3t2_learning_candidate import validate
from scripts.p3t2_candidate_common import P3T2CandidateError


def head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def test_candidate_valid_on_exact_checkout() -> None:
    result = validate(head=head())
    assert result["task_id"] == "P3T2-LEARNING-01"
    assert result["volume_count"] == 3
    assert result["dependency_task_ids"] == ["P3T2-TRAINING-01"]
    assert result["completion_checkbox"] is False
    assert result["promotion_authority"] is False


def test_candidate_rejects_malformed_reported_head() -> None:
    with pytest.raises(P3T2CandidateError, match="reported exact head is malformed"):
        validate(head="not-a-sha")


def test_candidate_rejects_other_exact_head() -> None:
    other = "a" * 40 if head() != "a" * 40 else "b" * 40
    with pytest.raises(P3T2CandidateError, match="does not match checkout"):
        validate(head=other)
