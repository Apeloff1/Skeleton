import subprocess

import pytest

from scripts.check_p3t2_data_candidate import DataCandidateError, validate


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
    ).strip()


def test_candidate_valid_on_exact_head() -> None:
    result = validate(head=_head())
    assert result["volume_count"] == 6
    assert len(result["source_tree_sha"]) == 40


def test_bad_head_rejected() -> None:
    with pytest.raises(DataCandidateError, match="invalid exact head"):
        validate(head="bad")


def test_mismatched_exact_head_rejected() -> None:
    with pytest.raises(DataCandidateError, match="exact head mismatch"):
        validate(head="a" * 40)
