from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.persistence.spine_pr_automation_qualification import (
    SpinePrAutomationQualification,
    SpinePrAutomationQualificationError,
)
from skeleton.persistence.spine_pr_automation_qualification_verify import (
    SpinePrAutomationQualificationVerify,
    SpinePrAutomationQualificationVerifyError,
)


HEAD = "a" * 40
PR = 2333


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _receipt(*, decision: str = "hold", state: str = "held") -> dict[str, object]:
    reasons = ["changed files exceed configured automation budget"]
    return {
        "kind": "spine_pr_automation_runner_receipt",
        "authority_domain": "pr-automation-runner",
        "workflow_name": "PR Automation Index",
        "source_workflow": "Merge Readiness",
        "head_sha": HEAD,
        "pr_number": PR,
        "run_id": 12345,
        "run_attempt": 1,
        "conclusion": "success",
        "report_digest": "a" * 64,
        "policy_fingerprint": "b" * 64,
        "snapshot_fingerprint": "c" * 64,
        "reason_digest": _digest(reasons),
        "reason_count": len(reasons),
        "mode": "observe",
        "target_state": state,
        "decision": decision,
        "failures": 0,
        "transport_failures": 0,
        "mutations_attempted": 0,
        "mutations_applied": 0,
        "evidence_complete": True,
        "exact_head": True,
        "attestation_digest": "d" * 64,
    }


def test_policy_hold_can_prove_runner_operational_without_merge_authority() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: receipt["attestation_digest"] == "d" * 64,
    )
    verified = SpinePrAutomationQualificationVerify().verify(card)

    assert card["pr_automation_operational_green"] is True
    assert card["pr_automation_green"] is True
    assert card["pr_automation_merge_eligible"] is False
    assert card["merge_authority"] is False
    assert verified["verified"] is True


def test_ready_decision_is_eligible_but_still_not_merge_authority() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(decision="ready", state="ready"),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: True,
    )
    verified = SpinePrAutomationQualificationVerify().verify(card)

    assert card["pr_automation_merge_eligible"] is True
    assert card["merge_authority"] is False
    assert verified["pr_automation_merge_eligible"] is True


def test_observe_mode_refuses_mutation_counts() -> None:
    mutated = _receipt()
    mutated["mutations_attempted"] = 1
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="observe mode cannot mutate",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=mutated,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda receipt: True,
        )


def test_ready_decision_with_nonready_state_is_not_merge_eligible() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(decision="ready", state="held"),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: True,
    )
    verified = SpinePrAutomationQualificationVerify().verify(card)

    assert card["pr_automation_operational_green"] is True
    assert card["pr_automation_merge_eligible"] is False
    assert verified["pr_automation_merge_eligible"] is False
    assert card["merge_authority"] is False


def test_runner_failures_and_head_drift_fail_closed() -> None:
    failed = _receipt()
    failed["failures"] = 1
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="reported failures",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=failed,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda receipt: True,
        )

    drifted = _receipt()
    drifted["head_sha"] = "b" * 40
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="not exact-head",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=drifted,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda receipt: True,
        )


def test_verifier_rejects_merge_authority_tamper() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["merge_authority"] = True
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="cannot grant merge authority",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)
