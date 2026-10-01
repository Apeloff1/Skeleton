from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_ci_qualification import SpineCiQualification
from skeleton.persistence.spine_ci_qualification_verify import (
    SpineCiQualificationVerify,
)
from skeleton.persistence.spine_ci_policy import REQUIRED_CHECKS
from skeleton.persistence.spine_ci_receipt import (
    SpineCiReceiptBuilder,
    SpineCiReceiptError,
)


HEAD = "a" * 40


def _runs() -> list[dict[str, object]]:
    return [
        {
            "id": 100 + index,
            "name": name,
            "head_sha": HEAD,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
        }
        for index, name in enumerate(REQUIRED_CHECKS)
    ]


def test_ci_receipt_builder_qualifies_complete_exact_head_catalog() -> None:
    receipt = SpineCiReceiptBuilder().build(
        workflow_runs=_runs(),
        expected_head_sha=HEAD,
        attest=lambda payload: "c" * 64,
    )
    card = SpineCiQualification().qualify(
        receipt=receipt,
        expected_head_sha=HEAD,
        authenticate=lambda candidate: candidate["attestation_digest"] == "c" * 64,
    )
    verified = SpineCiQualificationVerify().verify(card)

    assert [row["name"] for row in receipt["checks"]] == list(REQUIRED_CHECKS)
    assert card["ci_green"] is True
    assert verified["ci_green"] is True
    assert verified["merge_authority"] is False


def test_ci_receipt_builder_prefers_latest_exact_head_run() -> None:
    runs = _runs()
    stale = copy.deepcopy(runs[0])
    stale["id"] = 1
    stale["status"] = "completed"
    stale["conclusion"] = "success"
    runs[0]["id"] = 999
    runs[0]["status"] = "in_progress"
    runs[0]["conclusion"] = None

    with pytest.raises(SpineCiReceiptError, match="pending="):
        SpineCiReceiptBuilder().build(
            workflow_runs=[stale, *runs],
            expected_head_sha=HEAD,
            attest=lambda payload: "d" * 64,
        )


def test_ci_receipt_builder_rejects_missing_exact_head_check() -> None:
    runs = _runs()
    runs[-1]["head_sha"] = "b" * 40
    with pytest.raises(SpineCiReceiptError, match="missing="):
        SpineCiReceiptBuilder().build(
            workflow_runs=runs,
            expected_head_sha=HEAD,
            attest=lambda payload: "e" * 64,
        )
