from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_pr_automation_qualification import (
    SpinePrAutomationQualification,
)
from skeleton.persistence.spine_pr_automation_qualification_verify import (
    SpinePrAutomationQualificationVerify,
)
from skeleton.persistence.spine_pr_automation_receipt import (
    SpinePrAutomationReceiptBuilder,
    SpinePrAutomationReceiptError,
)


HEAD = "a" * 40
PR = 2333


def _report() -> dict[str, object]:
    return {
        "identity": {
            "repository": "Apeloff1/Skeleton",
            "trigger": "workflow_completion",
            "workflow_name": "Merge Readiness",
            "workflow_run_id": 777,
            "head_sha": HEAD,
            "event_name": "workflow_run",
        },
        "targets": {
            "complete": True,
            "targets": [{"number": PR}],
        },
        "results": [
            {
                "number": PR,
                "state": "held",
                "decision": "hold",
                "reasons": ["approval state is incomplete"],
                "snapshot_fingerprint": "c" * 64,
                "mutations": [],
                "request_count": 4,
                "duration_ms": 100,
                "error": None,
            }
        ],
        "policy_fingerprint": "b" * 64,
        "transport": {"failures": 0},
        "mutations_attempted": 0,
        "mutations_applied": 0,
        "failures": 0,
        "deferred": 0,
    }


def _source_run() -> dict[str, object]:
    return {
        "id": 777,
        "name": "Merge Readiness",
        "path": ".github/workflows/merge-readiness.yml",
        "event": "pull_request",
        "workflow_id": 358774735,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "head_sha": HEAD,
        "head_repository": {"full_name": "Apeloff1/Skeleton"},
        "pull_requests": [{"number": PR}],
    }


def _automation_run() -> dict[str, object]:
    return {
        "id": 123,
        "name": "PR Automation Index",
        "path": ".github/workflows/pr-automation-index.yml",
        "event": "workflow_run",
        "workflow_id": 359670100,
        "run_attempt": 1,
        "status": "in_progress",
        "conclusion": None,
        "head_sha": "e" * 40,
        "head_repository": {"full_name": "Apeloff1/Skeleton"},
    }


def _build(report: dict[str, object]) -> dict[str, object]:
    return SpinePrAutomationReceiptBuilder().build(
        report=report,
        expected_repository="Apeloff1/Skeleton",
        source_run=_source_run(),
        automation_run=_automation_run(),
        expected_source_run_attempt=1,
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        run_id=123,
        run_attempt=1,
        mode="observe",
        attest=lambda payload: "d" * 64,
    )


def test_runner_receipt_builder_qualifies_single_exact_target() -> None:
    report = _report()
    receipt = _build(report)
    card = SpinePrAutomationQualification().qualify(
        receipt=receipt,
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: candidate["attestation_digest"] == "d" * 64,
    )
    verified = SpinePrAutomationQualificationVerify().verify(card)

    assert receipt["source_pr_number"] == PR
    assert receipt["automation_workflow_id"] == 359670100
    assert (
        receipt["automation_workflow_path"]
        == ".github/workflows/pr-automation-index.yml"
    )
    assert receipt["automation_event"] == "workflow_run"
    assert receipt["automation_status"] == "in_progress"
    assert receipt["target_state"] == "held"
    assert receipt["decision"] == "hold"
    assert verified["pr_automation_operational_green"] is True
    assert verified["pr_automation_merge_eligible"] is False
    assert verified["merge_authority"] is False


def test_runner_receipt_builder_rejects_sweep_or_multi_target_report() -> None:
    report = _report()
    report["targets"]["targets"].append({"number": 2334})
    report["results"].append(
        {
            "number": 2334,
            "state": "held",
            "decision": "hold",
            "reasons": ["queue pressure"],
            "snapshot_fingerprint": "e" * 64,
            "mutations": [],
            "request_count": 1,
            "duration_ms": 10,
            "error": None,
        }
    )
    with pytest.raises(SpinePrAutomationReceiptError, match="exactly one target"):
        _build(report)


def test_runner_receipt_builder_rejects_observe_mode_mutation() -> None:
    report = _report()
    report["mutations_attempted"] = 1
    with pytest.raises(SpinePrAutomationReceiptError, match="observe"):
        _build(report)


def test_runner_receipt_builder_rejects_head_drift() -> None:
    report = copy.deepcopy(_report())
    report["identity"]["head_sha"] = "f" * 40
    with pytest.raises(SpinePrAutomationReceiptError, match="not exact-head"):
        _build(report)


def test_runner_receipt_builder_rejects_source_path_impersonation() -> None:
    source = _source_run()
    source["path"] = ".github/workflows/forged-merge-readiness.yml"
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="source workflow path changed",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=source,
            automation_run=_automation_run(),
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_source_run_identity_drift() -> None:
    report = _report()
    report["identity"]["workflow_run_id"] = 778
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="source run identity changed",
    ):
        _build(report)


def test_runner_receipt_builder_rejects_unsuccessful_source() -> None:
    source = _source_run()
    source["conclusion"] = "failure"
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="did not succeed",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=source,
            automation_run=_automation_run(),
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_source_workflow_id_drift() -> None:
    source = _source_run()
    source["workflow_id"] = 999999999
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="source workflow id changed",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=source,
            automation_run=_automation_run(),
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_source_pr_identity_drift() -> None:
    source = _source_run()
    source["pull_requests"] = [{"number": PR + 1}]
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="targets the wrong PR",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=source,
            automation_run=_automation_run(),
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_ambiguous_source_prs() -> None:
    source = _source_run()
    source["pull_requests"] = [
        {"number": PR},
        {"number": PR + 1},
    ]
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="targets the wrong PR",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=source,
            automation_run=_automation_run(),
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_producer_workflow_id_drift() -> None:
    automation = _automation_run()
    automation["workflow_id"] = 999999999
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="producer workflow id changed",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=_source_run(),
            automation_run=automation,
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_producer_run_identity_drift() -> None:
    automation = _automation_run()
    automation["id"] = 124
    with pytest.raises(
        SpinePrAutomationReceiptError,
        match="producer run identity changed",
    ):
        SpinePrAutomationReceiptBuilder().build(
            report=_report(),
            expected_repository="Apeloff1/Skeleton",
            source_run=_source_run(),
            automation_run=automation,
            expected_source_run_attempt=1,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )
