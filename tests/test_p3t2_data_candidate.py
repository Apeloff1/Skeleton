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


def test_unsigned_masterplan_volume_cannot_claim_verification(monkeypatch) -> None:
    import scripts.check_p3t2_data_candidate as checker

    real_load = checker.load

    def altered(root, path):
        result = real_load(root, path)
        if path == "machine/ai_master_plan.json":
            row = next(v for v in result["volumes"] if v["key"] == "VOL-137")
            row["completion_checkbox"] = False
            row["completion_checkbox_mark"] = "[ ]"
        return result

    monkeypatch.setattr(checker, "load", altered)
    with pytest.raises(DataCandidateError, match="unsigned volume claims verification"):
        checker.validate()


def test_candidate_cannot_forge_own_completion(monkeypatch) -> None:
    import scripts.check_p3t2_data_candidate as checker

    real_load = checker.load

    def altered(root, path):
        result = real_load(root, path)
        if path == "machine/ai_p3t2_data_candidate.json":
            result["promotion_state"]["verification_signed"] = True
        return result

    monkeypatch.setattr(checker, "load", altered)
    with pytest.raises(DataCandidateError, match="illegal promotion"):
        checker.validate()


def test_bad_head_rejected() -> None:
    with pytest.raises(DataCandidateError, match="invalid exact head"):
        validate(head="bad")


def test_mismatched_exact_head_rejected() -> None:
    with pytest.raises(DataCandidateError, match="exact head mismatch"):
        validate(head="a" * 40)
