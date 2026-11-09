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
        "automation_workflow_id": 359670100,
        "automation_workflow_path": ".github/workflows/pr-automation-index.yml",
        "automation_event": "workflow_run",
        "automation_status": "in_progress",
        "automation_head_repository": "Apeloff1/Skeleton",
        "automation_head_sha": "e" * 40,
        "repository": "Apeloff1/Skeleton",
        "source_workflow": "Merge Readiness",
        "source_workflow_path": ".github/workflows/merge-readiness.yml",
        "source_event": "pull_request",
        "source_workflow_digest": "f" * 64,
        "source_workflow_id": 358774735,
        "source_run_id": 777,
        "source_run_attempt": 1,
        "source_head_repository": "Apeloff1/Skeleton",
        "source_pr_number": PR,
        "source_status": "completed",
        "source_conclusion": "success",
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

    assert card["authority_domain"] == "pr-automation-runner"
    assert card["workflow_name"] == "PR Automation Index"
    assert card["source_workflow"] == "Merge Readiness"
    assert card["pr_automation_operational_green"] is True
    assert card["pr_automation_green"] is True
    assert card["pr_automation_merge_eligible"] is False
    assert card["attestation_digest"] == "d" * 64
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


def test_inconsistent_state_and_decision_fail_closed() -> None:
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="state and decision are inconsistent",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=_receipt(decision="ready", state="held"),
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda receipt: True,
        )

    impossible = _receipt()
    impossible["target_state"] = "evaluated"
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="target state is not operational",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=impossible,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda receipt: True,
        )


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


def test_verifier_rejects_workflow_identity_tamper() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["workflow_name"] = "Other Workflow"
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="workflow identity changed",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


def test_verifier_rejects_state_decision_tamper() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["decision"] = "ready"
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="state and decision are inconsistent",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


def test_verifier_rejects_attestation_detachment() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda receipt: True,
    )
    tampered = copy.deepcopy(card)
    tampered["attestation_digest"] = "e" * 64
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="digest mismatch",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


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


def test_qualification_rejects_source_path_tamper() -> None:
    receipt = _receipt()
    receipt["source_workflow_path"] = (
        ".github/workflows/forged-merge-readiness.yml"
    )
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="source workflow path changed",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=receipt,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda candidate: True,
        )


def test_verifier_rejects_source_event_tamper() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: True,
    )
    tampered = copy.deepcopy(card)
    tampered["source_event"] = "workflow_dispatch"
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="source workflow event changed",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


def test_qualification_rejects_source_workflow_id_drift() -> None:
    receipt = _receipt()
    receipt["source_workflow_id"] = 999999999
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="source workflow id changed",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=receipt,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda candidate: True,
        )


def test_verifier_rejects_source_workflow_id_drift() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: True,
    )
    tampered = copy.deepcopy(card)
    tampered["source_workflow_id"] = 999999999
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="source workflow id changed",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


def test_qualification_rejects_source_pr_identity_drift() -> None:
    receipt = _receipt()
    receipt["source_pr_number"] = PR + 1
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="source workflow targets the wrong PR",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=receipt,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda candidate: True,
        )


def test_verifier_rejects_source_pr_identity_drift() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: True,
    )
    tampered = copy.deepcopy(card)
    tampered["source_pr_number"] = PR + 1
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="source workflow targets the wrong PR",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


def test_qualification_rejects_producer_workflow_identity_drift() -> None:
    receipt = _receipt()
    receipt["automation_workflow_id"] = 999999999
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="producer workflow id changed",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=receipt,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda candidate: True,
        )


def test_verifier_rejects_producer_workflow_identity_drift() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: True,
    )
    tampered = copy.deepcopy(card)
    tampered["automation_workflow_path"] = (
        ".github/workflows/forged-pr-automation-index.yml"
    )
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="producer workflow path changed",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)


def test_qualification_rejects_source_workflow_digest_tamper() -> None:
    receipt = _receipt()
    receipt["source_workflow_digest"] = "not-a-digest"
    with pytest.raises(
        SpinePrAutomationQualificationError,
        match="source workflow digest",
    ):
        SpinePrAutomationQualification().qualify(
            receipt=receipt,
            expected_head_sha=HEAD,
            expected_pr_number=PR,
            authenticate=lambda candidate: True,
        )


def test_verifier_rejects_source_workflow_digest_tamper() -> None:
    card = SpinePrAutomationQualification().qualify(
        receipt=_receipt(),
        expected_head_sha=HEAD,
        expected_pr_number=PR,
        authenticate=lambda candidate: True,
    )
    tampered = copy.deepcopy(card)
    tampered["source_workflow_digest"] = "0" * 64
    with pytest.raises(
        SpinePrAutomationQualificationVerifyError,
        match="qualification digest mismatch",
    ):
        SpinePrAutomationQualificationVerify().verify(tampered)
