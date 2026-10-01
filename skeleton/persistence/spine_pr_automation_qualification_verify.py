"""Independent verifier for P2 PR-automation qualification evidence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from skeleton.persistence.spine_pr_automation_policy import (
    TRUSTED_AUTOMATION_EVENT,
    TRUSTED_AUTOMATION_STATUS,
    TRUSTED_AUTOMATION_WORKFLOW_ID,
    TRUSTED_AUTOMATION_WORKFLOW_NAME,
    TRUSTED_AUTOMATION_WORKFLOW_PATH,
    TRUSTED_SOURCE_CONCLUSION,
    TRUSTED_SOURCE_EVENT,
    TRUSTED_SOURCE_STATUS,
    TRUSTED_SOURCE_WORKFLOW_ID,
    TRUSTED_SOURCE_WORKFLOW_NAME,
    TRUSTED_SOURCE_WORKFLOW_PATH,
)


class SpinePrAutomationQualificationVerifyError(RuntimeError):
    """PR-automation qualification verification failed closed."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
)
_ALLOWED_STATES = frozenset({"ready", "held", "ignored", "merged"})
_ALLOWED_DECISIONS = frozenset({"ignore", "hold", "ready", "merge"})
_ALLOWED_MODES = frozenset({"observe", "apply"})
_VALID_STATE_DECISIONS = {
    "ready": frozenset({"ready", "merge"}),
    "held": frozenset({"hold"}),
    "ignored": frozenset({"ignore"}),
    "merged": frozenset({"merge"}),
}


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpinePrAutomationQualificationVerify:
    """Verify operational runner health without granting merge authority."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_pr_automation_qualification"
        ):
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation qualification kind mismatch"
            )
        if card.get("authority_domain") != "pr-automation-runner":
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation authority domain changed"
            )
        if card.get("workflow_name") != TRUSTED_AUTOMATION_WORKFLOW_NAME:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation workflow identity changed"
            )
        automation_workflow_id = card.get(
            "automation_workflow_id"
        )
        if (
            isinstance(automation_workflow_id, bool)
            or not isinstance(automation_workflow_id, int)
            or automation_workflow_id != TRUSTED_AUTOMATION_WORKFLOW_ID
        ):
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation producer workflow id changed"
            )
        if (
            card.get("automation_workflow_path")
            != TRUSTED_AUTOMATION_WORKFLOW_PATH
        ):
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation producer workflow path changed"
            )
        if card.get("automation_event") != TRUSTED_AUTOMATION_EVENT:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation producer event changed"
            )
        if card.get("automation_status") != TRUSTED_AUTOMATION_STATUS:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation producer status changed"
            )
        automation_head_sha = card.get("automation_head_sha")
        if (
            not isinstance(automation_head_sha, str)
            or _SHA_RE.fullmatch(automation_head_sha) is None
        ):
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation producer head SHA is invalid"
            )
        if card.get("source_workflow") != TRUSTED_SOURCE_WORKFLOW_NAME:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow changed"
            )
        if card.get("source_workflow_path") != TRUSTED_SOURCE_WORKFLOW_PATH:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow path changed"
            )
        if card.get("source_event") != TRUSTED_SOURCE_EVENT:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow event changed"
            )
        repository = card.get("repository")
        if (
            not isinstance(repository, str)
            or _REPOSITORY_RE.fullmatch(repository) is None
            or card.get("source_head_repository") != repository
            or card.get("automation_head_repository") != repository
        ):
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source or producer repository changed"
            )
        if card.get("source_status") != TRUSTED_SOURCE_STATUS:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow is not completed"
            )
        if card.get("source_conclusion") != TRUSTED_SOURCE_CONCLUSION:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow did not succeed"
            )
        if card.get("conclusion") != "success":
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation runner evaluation did not complete successfully"
            )
        head_sha = card.get("head_sha")
        if not isinstance(head_sha, str) or _SHA_RE.fullmatch(head_sha) is None:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation head SHA is invalid"
            )
        pr_number = card.get("pr_number")
        if isinstance(pr_number, bool) or not isinstance(pr_number, int) or pr_number < 1:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation PR number is invalid"
            )
        if card.get("source_pr_number") != pr_number:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow targets the wrong PR"
            )
        for field in (
            "report_digest",
            "policy_fingerprint",
            "snapshot_fingerprint",
            "reason_digest",
            "attestation_digest",
        ):
            value = card.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpinePrAutomationQualificationVerifyError(
                    f"{field} is invalid"
                )
        for field in (
            "run_id",
            "run_attempt",
            "source_workflow_id",
            "source_run_id",
            "source_run_attempt",
        ):
            value = card.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SpinePrAutomationQualificationVerifyError(
                    f"{field} is invalid"
                )
        if card["source_workflow_id"] != TRUSTED_SOURCE_WORKFLOW_ID:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation source workflow id changed"
            )
        for field in (
            "reason_count",
            "failures",
            "transport_failures",
            "mutations_attempted",
            "mutations_applied",
        ):
            value = card.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SpinePrAutomationQualificationVerifyError(
                    f"{field} is invalid"
                )
        if card["mutations_applied"] > card["mutations_attempted"]:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation mutation counts are inconsistent"
            )
        if card.get("mode") == "observe" and (
            card["mutations_attempted"] != 0
            or card["mutations_applied"] != 0
        ):
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation observe mode cannot mutate"
            )
        if card.get("mode") not in _ALLOWED_MODES:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation mode is invalid"
            )
        if card.get("target_state") not in _ALLOWED_STATES:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation target state is not operational"
            )
        decision = card.get("decision")
        if decision not in _ALLOWED_DECISIONS:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation decision is invalid"
            )
        if decision not in _VALID_STATE_DECISIONS[card["target_state"]]:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation state and decision are inconsistent"
            )
        for field in (
            "exact_head",
            "evidence_complete",
            "receipt_authenticated",
            "pr_automation_operational_green",
            "pr_automation_green",
        ):
            if card.get(field) is not True:
                raise SpinePrAutomationQualificationVerifyError(
                    f"PR automation invariant missing: {field}"
                )
        if card.get("merge_authority") is not False:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation qualification cannot grant merge authority"
            )
        expected_eligible = (
            decision in {"ready", "merge"}
            and card.get("target_state") in {"ready", "merged"}
        )
        if card.get("pr_automation_merge_eligible") is not expected_eligible:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation merge eligibility does not match decision"
            )

        evidence = {
            "authority_domain": card["authority_domain"],
            "workflow_name": card["workflow_name"],
            "automation_workflow_id": card["automation_workflow_id"],
            "automation_workflow_path": card["automation_workflow_path"],
            "automation_event": card["automation_event"],
            "automation_status": card["automation_status"],
            "automation_head_repository": card[
                "automation_head_repository"
            ],
            "automation_head_sha": automation_head_sha,
            "repository": repository,
            "source_workflow": card["source_workflow"],
            "source_workflow_path": card["source_workflow_path"],
            "source_event": card["source_event"],
            "source_workflow_id": card["source_workflow_id"],
            "source_run_id": card["source_run_id"],
            "source_run_attempt": card["source_run_attempt"],
            "source_head_repository": card["source_head_repository"],
            "source_pr_number": card["source_pr_number"],
            "source_status": card["source_status"],
            "source_conclusion": card["source_conclusion"],
            "conclusion": card["conclusion"],
            "head_sha": head_sha,
            "pr_number": pr_number,
            "run_id": card["run_id"],
            "run_attempt": card["run_attempt"],
            "report_digest": card["report_digest"],
            "policy_fingerprint": card["policy_fingerprint"],
            "snapshot_fingerprint": card["snapshot_fingerprint"],
            "reason_digest": card["reason_digest"],
            "attestation_digest": card["attestation_digest"],
            "reason_count": card["reason_count"],
            "mode": card["mode"],
            "target_state": card["target_state"],
            "decision": decision,
            "failures": card["failures"],
            "transport_failures": card["transport_failures"],
            "mutations_attempted": card["mutations_attempted"],
            "mutations_applied": card["mutations_applied"],
            "exact_head": card["exact_head"],
            "evidence_complete": card["evidence_complete"],
            "receipt_authenticated": card["receipt_authenticated"],
            "pr_automation_operational_green": card[
                "pr_automation_operational_green"
            ],
            "pr_automation_green": card["pr_automation_green"],
            "pr_automation_merge_eligible": card[
                "pr_automation_merge_eligible"
            ],
            "merge_authority": card["merge_authority"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation qualification digest mismatch"
            )
        return {
            "kind": "spine_pr_automation_qualification_verify",
            "hit": True,
            "law": "automation-health-verification-does-not-grant-merge-authority",
            "citation": "VOL-134",
            "head_sha": head_sha,
            "pr_number": pr_number,
            "qualification_digest": digest,
            "verified": True,
            "pr_automation_operational_green": True,
            "pr_automation_green": True,
            "pr_automation_merge_eligible": expected_eligible,
            "merge_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
