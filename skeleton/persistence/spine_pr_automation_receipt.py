"""Build one externally attestable PR Automation runner receipt."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Mapping


class SpinePrAutomationReceiptError(RuntimeError):
    """Runner report could not form an exact-target operational receipt."""


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATES = frozenset({"ready", "held", "ignored", "merged"})
_ALLOWED_DECISIONS = frozenset({"ignore", "hold", "ready", "merge"})
_ALLOWED_MODES = frozenset({"observe", "apply"})


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _positive(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpinePrAutomationReceiptError(f"{field} is invalid")
    return value


def _non_negative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SpinePrAutomationReceiptError(f"{field} is invalid")
    return value


def _digest_text(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise SpinePrAutomationReceiptError(f"{field} is invalid")
    return value


class SpinePrAutomationReceiptBuilder:
    """Reduce one exact-target runner report to the qualification receipt contract."""

    def build(
        self,
        *,
        report: Mapping[str, Any],
        expected_head_sha: str,
        expected_pr_number: int,
        run_id: int,
        run_attempt: int,
        mode: str,
        attest: Callable[[dict[str, Any]], str],
    ) -> dict[str, Any]:
        if not isinstance(report, Mapping):
            raise SpinePrAutomationReceiptError("runner report must be an object")
        if not isinstance(expected_head_sha, str) or _SHA_RE.fullmatch(expected_head_sha) is None:
            raise SpinePrAutomationReceiptError("expected head SHA is invalid")
        expected_pr = _positive(expected_pr_number, "expected PR number")
        automation_run_id = _positive(run_id, "PR Automation run id")
        automation_attempt = _positive(run_attempt, "PR Automation run attempt")
        if mode not in _ALLOWED_MODES:
            raise SpinePrAutomationReceiptError("PR Automation mode is invalid")
        if not callable(attest):
            raise SpinePrAutomationReceiptError("PR Automation attestor must be callable")

        identity = report.get("identity")
        if not isinstance(identity, Mapping):
            raise SpinePrAutomationReceiptError("runner identity is missing")
        if identity.get("workflow_name") != "Merge Readiness":
            raise SpinePrAutomationReceiptError("runner source workflow changed")
        if identity.get("head_sha") != expected_head_sha:
            raise SpinePrAutomationReceiptError("runner report is not exact-head")

        targets = report.get("targets")
        if not isinstance(targets, Mapping) or targets.get("complete") is not True:
            raise SpinePrAutomationReceiptError("runner target discovery is incomplete")
        target_rows = targets.get("targets")
        if not isinstance(target_rows, list) or len(target_rows) != 1:
            raise SpinePrAutomationReceiptError("runner receipt requires exactly one target")
        target = target_rows[0]
        if not isinstance(target, Mapping) or target.get("number") != expected_pr:
            raise SpinePrAutomationReceiptError("runner target is not the expected PR")

        results = report.get("results")
        if not isinstance(results, list) or len(results) != 1:
            raise SpinePrAutomationReceiptError("runner receipt requires exactly one result")
        result = results[0]
        if not isinstance(result, Mapping) or result.get("number") != expected_pr:
            raise SpinePrAutomationReceiptError("runner result is not the expected PR")
        if result.get("error") not in (None, ""):
            raise SpinePrAutomationReceiptError("runner result contains an error")
        target_state = result.get("state")
        decision = result.get("decision")
        if target_state not in _ALLOWED_STATES:
            raise SpinePrAutomationReceiptError("runner target state is not operational")
        if decision not in _ALLOWED_DECISIONS:
            raise SpinePrAutomationReceiptError("runner decision is invalid")
        reasons = result.get("reasons")
        if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
            raise SpinePrAutomationReceiptError("runner reasons are invalid")

        policy_fingerprint = _digest_text(
            report.get("policy_fingerprint"),
            "runner policy fingerprint",
        )
        snapshot_fingerprint = _digest_text(
            result.get("snapshot_fingerprint"),
            "runner snapshot fingerprint",
        )
        failures = _non_negative(report.get("failures"), "runner failures")
        mutations_attempted = _non_negative(
            report.get("mutations_attempted"),
            "runner mutations attempted",
        )
        mutations_applied = _non_negative(
            report.get("mutations_applied"),
            "runner mutations applied",
        )
        transport = report.get("transport")
        if not isinstance(transport, Mapping):
            raise SpinePrAutomationReceiptError("runner transport summary is missing")
        transport_failures = _non_negative(
            transport.get("failures"),
            "runner transport failures",
        )
        if failures or transport_failures:
            raise SpinePrAutomationReceiptError("runner report contains failures")
        if mutations_applied > mutations_attempted:
            raise SpinePrAutomationReceiptError("runner mutation counts are inconsistent")
        if mode == "observe" and (mutations_attempted or mutations_applied):
            raise SpinePrAutomationReceiptError("observe runner report contains mutations")

        receipt: dict[str, Any] = {
            "kind": "spine_pr_automation_runner_receipt",
            "authority_domain": "pr-automation-runner",
            "workflow_name": "PR Automation Index",
            "source_workflow": "Merge Readiness",
            "head_sha": expected_head_sha,
            "pr_number": expected_pr,
            "run_id": automation_run_id,
            "run_attempt": automation_attempt,
            "conclusion": "success",
            "report_digest": _digest(report),
            "policy_fingerprint": policy_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint,
            "reason_digest": _digest(reasons),
            "reason_count": len(reasons),
            "mode": mode,
            "target_state": target_state,
            "decision": decision,
            "failures": failures,
            "transport_failures": transport_failures,
            "mutations_attempted": mutations_attempted,
            "mutations_applied": mutations_applied,
            "exact_head": True,
            "evidence_complete": True,
        }
        try:
            attestation = attest(dict(receipt))
        except Exception as exc:
            raise SpinePrAutomationReceiptError(
                "PR Automation receipt attestation failed closed"
            ) from exc
        if not isinstance(attestation, str) or _DIGEST_RE.fullmatch(attestation) is None:
            raise SpinePrAutomationReceiptError("PR Automation attestation digest is invalid")
        receipt["attestation_digest"] = attestation
        return receipt


__all__ = [
    "SpinePrAutomationReceiptBuilder",
    "SpinePrAutomationReceiptError",
]
