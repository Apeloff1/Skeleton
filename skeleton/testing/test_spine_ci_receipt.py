from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_ci_qualification import SpineCiQualification
from skeleton.persistence.spine_ci_qualification_verify import (
    SpineCiQualificationVerify,
)
from skeleton.persistence.spine_ci_policy import (
    CI_PRODUCER_EVENT,
    CI_PRODUCER_STATUS,
    CI_PRODUCER_WORKFLOW_NAME,
    CI_PRODUCER_WORKFLOW_PATH,
    REQUIRED_CHECK_EVENT,
    REQUIRED_CHECKS,
    REQUIRED_CHECK_WORKFLOWS,
)
from skeleton.persistence.spine_ci_receipt import (
    SpineCiReceiptBuilder,
    SpineCiReceiptError,
    SpineCiReceiptIncompleteError,
)


HEAD = "a" * 40


def _runs() -> list[dict[str, object]]:
    return [
        {
            "id": 100 + index,
            "name": name,
            "head_sha": HEAD,
            "path": REQUIRED_CHECK_WORKFLOWS[name],
            "event": REQUIRED_CHECK_EVENT,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
        }
        for index, name in enumerate(REQUIRED_CHECKS)
    ]


def _producer_run() -> dict[str, object]:
    return {
        "id": 900,
        "name": CI_PRODUCER_WORKFLOW_NAME,
        "path": CI_PRODUCER_WORKFLOW_PATH,
        "event": CI_PRODUCER_EVENT,
        "workflow_id": 777777,
        "run_attempt": 1,
        "status": CI_PRODUCER_STATUS,
        "conclusion": None,
        "head_sha": "e" * 40,
        "head_branch": "main",
        "head_repository": {"full_name": "Apeloff1/Skeleton"},
    }


def _build(
    *,
    workflow_runs: list[dict[str, object]],
    expected_head_sha: str = HEAD,
    attest,
) -> dict[str, object]:
    return _build(
        workflow_runs=workflow_runs,
        expected_repository="Apeloff1/Skeleton",
        producer_run=_producer_run(),
        expected_producer_run_id=900,
        expected_producer_run_attempt=1,
        expected_producer_branch="main",
        expected_head_sha=expected_head_sha,
        attest=attest,
    )


def test_ci_receipt_builder_qualifies_complete_exact_head_catalog() -> None:
    receipt = _build(
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
    assert [row["workflow_path"] for row in receipt["checks"]] == [
        REQUIRED_CHECK_WORKFLOWS[name] for name in REQUIRED_CHECKS
    ]
    assert {row["event"] for row in receipt["checks"]} == {
        REQUIRED_CHECK_EVENT
    }
    assert receipt["producer_workflow_name"] == CI_PRODUCER_WORKFLOW_NAME
    assert receipt["producer_workflow_path"] == CI_PRODUCER_WORKFLOW_PATH
    assert receipt["producer_event"] == CI_PRODUCER_EVENT
    assert receipt["producer_status"] == CI_PRODUCER_STATUS
    assert receipt["producer_workflow_id"] == 777777
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

    with pytest.raises(SpineCiReceiptIncompleteError, match="pending="):
        _build(
            workflow_runs=[stale, *runs],
            expected_head_sha=HEAD,
            attest=lambda payload: "d" * 64,
        )


def test_ci_receipt_builder_rejects_missing_exact_head_check() -> None:
    runs = _runs()
    runs[-1]["head_sha"] = "b" * 40
    with pytest.raises(SpineCiReceiptIncompleteError, match="missing="):
        _build(
            workflow_runs=runs,
            expected_head_sha=HEAD,
            attest=lambda payload: "e" * 64,
        )


def test_ci_receipt_builder_rejects_same_name_wrong_workflow_identity() -> None:
    runs = _runs()
    forged = copy.deepcopy(runs[0])
    forged["id"] = 999999
    forged["path"] = ".github/workflows/forged-backend-quality.yml"
    forged["event"] = REQUIRED_CHECK_EVENT

    with pytest.raises(
        SpineCiReceiptError,
        match="workflow identity mismatch",
    ):
        _build(
            workflow_runs=[forged, *runs],
            expected_head_sha=HEAD,
            attest=lambda payload: "f" * 64,
        )


def test_ci_receipt_builder_rejects_wrong_trigger_event() -> None:
    runs = _runs()
    runs[0]["event"] = "workflow_dispatch"
    with pytest.raises(
        SpineCiReceiptError,
        match="workflow event mismatch",
    ):
        _build(
            workflow_runs=runs,
            expected_head_sha=HEAD,
            attest=lambda payload: "f" * 64,
        )


def test_incomplete_catalog_error_is_distinct_from_integrity_error() -> None:
    runs = _runs()
    runs.pop()
    with pytest.raises(SpineCiReceiptIncompleteError):
        _build(
            workflow_runs=runs,
            expected_head_sha=HEAD,
            attest=lambda payload: "f" * 64,
        )

    forged = _runs()
    forged[0]["path"] = ".github/workflows/forged.yml"
    with pytest.raises(SpineCiReceiptError) as error:
        _build(
            workflow_runs=forged,
            expected_head_sha=HEAD,
            attest=lambda payload: "f" * 64,
        )
    assert not isinstance(error.value, SpineCiReceiptIncompleteError)


def test_ci_receipt_builder_rejects_producer_identity_drift() -> None:
    producer = _producer_run()
    producer["path"] = ".github/workflows/forged-p2-ci-qualification.yml"
    with pytest.raises(
        SpineCiReceiptError,
        match="producer workflow path changed",
    ):
        SpineCiReceiptBuilder().build(
            workflow_runs=_runs(),
            expected_repository="Apeloff1/Skeleton",
            producer_run=producer,
            expected_producer_run_id=900,
            expected_producer_run_attempt=1,
            expected_producer_branch="main",
            expected_head_sha=HEAD,
            attest=lambda payload: "f" * 64,
        )


def test_ci_receipt_builder_rejects_producer_run_drift() -> None:
    producer = _producer_run()
    producer["id"] = 901
    with pytest.raises(
        SpineCiReceiptError,
        match="producer run identity changed",
    ):
        SpineCiReceiptBuilder().build(
            workflow_runs=_runs(),
            expected_repository="Apeloff1/Skeleton",
            producer_run=producer,
            expected_producer_run_id=900,
            expected_producer_run_attempt=1,
            expected_producer_branch="main",
            expected_head_sha=HEAD,
            attest=lambda payload: "f" * 64,
        )
