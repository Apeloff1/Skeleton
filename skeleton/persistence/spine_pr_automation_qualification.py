"""Exact-head live PR-automation operational qualification for P2."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable


class SpinePrAutomationQualificationError(RuntimeError):
    """PR-automation operational evidence failed closed."""


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


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise SpinePrAutomationQualificationError(f"{field} is invalid")
    return value


def _digest_text(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise SpinePrAutomationQualificationError(f"{field} is invalid")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpinePrAutomationQualificationError(f"{field} is invalid")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SpinePrAutomationQualificationError(f"{field} is invalid")
    return value


class SpinePrAutomationQualification:
    """Authenticate one exact-head runner receipt without granting merge authority."""

    def qualify(
        self,
        *,
        receipt: dict[str, Any],
        expected_head_sha: str,
        expected_pr_number: int,
        authenticate: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any]:
        expected_head = _sha(expected_head_sha, "expected head SHA")
        expected_pr = _positive_int(expected_pr_number, "expected PR number")
        if not callable(authenticate):
            raise SpinePrAutomationQualificationError(
                "PR automation authenticator must be callable"
            )
        if (
            not isinstance(receipt, dict)
            or receipt.get("kind") != "spine_pr_automation_runner_receipt"
        ):
            raise SpinePrAutomationQualificationError(
                "PR automation runner receipt is missing"
            )
        if receipt.get("authority_domain") != "pr-automation-runner":
            raise SpinePrAutomationQualificationError(
                "PR automation authority domain changed"
            )
        if receipt.get("workflow_name") != "PR Automation Index":
            raise SpinePrAutomationQualificationError(
                "PR automation workflow identity changed"
            )
        if receipt.get("source_workflow") != "Merge Readiness":
            raise SpinePrAutomationQualificationError(
                "PR automation source workflow changed"
            )
        if receipt.get("conclusion") != "success":
            raise SpinePrAutomationQualificationError(
                "PR automation workflow did not complete successfully"
            )
        if receipt.get("head_sha") != expected_head:
            raise SpinePrAutomationQualificationError(
                "PR automation receipt is not exact-head"
            )
        if receipt.get("pr_number") != expected_pr:
            raise SpinePrAutomationQualificationError(
                "PR automation receipt targets the wrong PR"
            )

        run_id = _positive_int(receipt.get("run_id"), "PR automation run id")
        run_attempt = _positive_int(
            receipt.get("run_attempt"),
            "PR automation run attempt",
        )
        report_digest = _digest_text(
            receipt.get("report_digest"),
            "PR automation report digest",
        )
        policy_fingerprint = _digest_text(
            receipt.get("policy_fingerprint"),
            "PR automation policy fingerprint",
        )
        snapshot_fingerprint = _digest_text(
            receipt.get("snapshot_fingerprint"),
            "PR automation snapshot fingerprint",
        )
        reason_digest = _digest_text(
            receipt.get("reason_digest"),
            "PR automation reason digest",
        )
        mode = receipt.get("mode")
        if mode not in _ALLOWED_MODES:
            raise SpinePrAutomationQualificationError(
                "PR automation mode is invalid"
            )
        target_state = receipt.get("target_state")
        if target_state not in _ALLOWED_STATES:
            raise SpinePrAutomationQualificationError(
                "PR automation target state is not operational"
            )
        decision = receipt.get("decision")
        if decision not in _ALLOWED_DECISIONS:
            raise SpinePrAutomationQualificationError(
                "PR automation decision is invalid"
            )
        failures = _non_negative_int(
            receipt.get("failures"),
            "PR automation failures",
        )
        transport_failures = _non_negative_int(
            receipt.get("transport_failures"),
            "PR automation transport failures",
        )
        mutations_attempted = _non_negative_int(
            receipt.get("mutations_attempted"),
            "PR automation mutations attempted",
        )
        mutations_applied = _non_negative_int(
            receipt.get("mutations_applied"),
            "PR automation mutations applied",
        )
        reason_count = _non_negative_int(
            receipt.get("reason_count"),
            "PR automation reason count",
        )
        if failures != 0 or transport_failures != 0:
            raise SpinePrAutomationQualificationError(
                "PR automation runner reported failures"
            )
        if mutations_applied > mutations_attempted:
            raise SpinePrAutomationQualificationError(
                "PR automation mutation counts are inconsistent"
            )
        if receipt.get("evidence_complete") is not True:
            raise SpinePrAutomationQualificationError(
                "PR automation evidence is incomplete"
            )
        if receipt.get("exact_head") is not True:
            raise SpinePrAutomationQualificationError(
                "PR automation exact-head assertion is missing"
            )
        try:
            authenticated = authenticate(dict(receipt))
        except Exception as exc:
            raise SpinePrAutomationQualificationError(
                "PR automation receipt authentication failed closed"
            ) from exc
        if authenticated is not True:
            raise SpinePrAutomationQualificationError(
                "PR automation receipt was not externally authenticated"
            )

        merge_eligible = decision in {"ready", "merge"}
        evidence = {
            "head_sha": expected_head,
            "pr_number": expected_pr,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "report_digest": report_digest,
            "policy_fingerprint": policy_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint,
            "reason_digest": reason_digest,
            "reason_count": reason_count,
            "mode": mode,
            "target_state": target_state,
            "decision": decision,
            "failures": failures,
            "transport_failures": transport_failures,
            "mutations_attempted": mutations_attempted,
            "mutations_applied": mutations_applied,
            "exact_head": True,
            "evidence_complete": True,
            "receipt_authenticated": True,
            "pr_automation_operational_green": True,
            "pr_automation_green": True,
            "pr_automation_merge_eligible": merge_eligible,
            "merge_authority": False,
        }
        return {
            "kind": "spine_pr_automation_qualification",
            "hit": True,
            "law": "exact-head-runner-health-is-separate-from-merge-eligibility",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
