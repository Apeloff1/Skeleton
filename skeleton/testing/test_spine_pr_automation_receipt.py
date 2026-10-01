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
            "workflow_name": "Merge Readiness",
            "head_sha": HEAD,
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


def test_runner_receipt_builder_qualifies_single_exact_target() -> None:
    report = _report()
    receipt = SpinePrAutomationReceiptBuilder().build(
        report=report,
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        run_id=123,
        run_attempt=1,
        mode="observe",
        attest=lambda payload: "d" * 64,
    )
    card = SpinePrAutomationQualification().qualify(
        receipt=receipt,
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: candidate["attestation_digest"] == "d" * 64,
    )
    verified = SpinePrAutomationQualificationVerify().verify(card)

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
        SpinePrAutomationReceiptBuilder().build(
            report=report,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_observe_mode_mutation() -> None:
    report = _report()
    report["mutations_attempted"] = 1
    with pytest.raises(SpinePrAutomationReceiptError, match="observe"):
        SpinePrAutomationReceiptBuilder().build(
            report=report,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )


def test_runner_receipt_builder_rejects_head_drift() -> None:
    report = copy.deepcopy(_report())
    report["identity"]["head_sha"] = "f" * 40
    with pytest.raises(SpinePrAutomationReceiptError, match="not exact-head"):
        SpinePrAutomationReceiptBuilder().build(
            report=report,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            run_id=123,
            run_attempt=1,
            mode="observe",
            attest=lambda payload: "d" * 64,
        )
