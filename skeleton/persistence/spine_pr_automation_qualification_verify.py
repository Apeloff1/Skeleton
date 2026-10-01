"""Independent verifier for P2 PR-automation qualification evidence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


class SpinePrAutomationQualificationVerifyError(RuntimeError):
    """PR-automation qualification verification failed closed."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATES = frozenset({"evaluated", "ready", "held", "ignored", "merged"})
_ALLOWED_DECISIONS = frozenset({"ignore", "hold", "ready", "merge"})
_ALLOWED_MODES = frozenset({"observe", "apply"})


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
        for field in (
            "report_digest",
            "policy_fingerprint",
            "snapshot_fingerprint",
            "reason_digest",
        ):
            value = card.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpinePrAutomationQualificationVerifyError(
                    f"{field} is invalid"
                )
        for field in ("run_id", "run_attempt"):
            value = card.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SpinePrAutomationQualificationVerifyError(
                    f"{field} is invalid"
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
        expected_eligible = decision in {"ready", "merge"}
        if card.get("pr_automation_merge_eligible") is not expected_eligible:
            raise SpinePrAutomationQualificationVerifyError(
                "PR automation merge eligibility does not match decision"
            )

        evidence = {
            "head_sha": head_sha,
            "pr_number": pr_number,
            "run_id": card["run_id"],
            "run_attempt": card["run_attempt"],
            "report_digest": card["report_digest"],
            "policy_fingerprint": card["policy_fingerprint"],
            "snapshot_fingerprint": card["snapshot_fingerprint"],
            "reason_digest": card["reason_digest"],
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
