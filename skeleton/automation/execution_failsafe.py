"""Fail-closed worker outcome classification and bounded recovery policy.

This module contains no subprocess, filesystem, network, or mutation primitive.
It turns Secretary worker results into a deterministic failure vocabulary so
recovery decisions never depend on free-form model text or exception messages.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

MAX_ATTEMPTS = 2
MAX_RESULTS = 16


class FailureKind(str, Enum):
    SUCCESS = "success"
    NO_CHANGE = "no-change"
    EXISTING_PR = "existing-pr"
    SETUP_FAILURE = "setup-failure"
    WORKER_FAILURE = "worker-failure"
    WORKER_TIMEOUT = "worker-timeout"
    INVALID_EVIDENCE = "invalid-evidence"
    CUSTODY_FAILURE = "custody-failure"
    POLICY_FAILURE = "policy-failure"
    UNKNOWN_FAILURE = "unknown-failure"


_SUCCESS_STATUSES = frozenset(
    {"pull-request-created", "pull-request-updated"}
)
_NOOP_STATUSES = frozenset({"no-change"})
_DEDUP_STATUSES = frozenset({"existing-pr"})
_RETRYABLE = frozenset({FailureKind.SETUP_FAILURE})


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=lambda item: type(item).__name__,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class FailsafeOutcome:
    worker: str
    kind: FailureKind
    returncode: int
    attempt: int
    terminal: bool
    retryable: bool
    evidence_status: str | None
    failure_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "worker": self.worker,
            "kind": self.kind.value,
            "returncode": self.returncode,
            "attempt": self.attempt,
            "terminal": self.terminal,
            "retryable": self.retryable,
            "evidence_status": self.evidence_status,
            "failure_digest": self.failure_digest,
        }


def _bounded_worker(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("failsafe outcome has invalid worker")
    if not all(char.islower() or char.isdigit() or char == "-" for char in value):
        raise ValueError("failsafe outcome has invalid worker")
    return value


def _bounded_attempt(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("failsafe outcome has invalid attempt")
    if value < 1 or value > MAX_ATTEMPTS:
        raise ValueError("failsafe outcome exceeds attempt budget")
    return value


def classify_result(result: Mapping[str, Any] | object) -> FailsafeOutcome:
    """Classify one admitted Secretary result using a closed vocabulary."""
    if not isinstance(result, Mapping):
        raise ValueError("failsafe outcome must be an object")
    worker = _bounded_worker(result.get("bot"))
    attempt = _bounded_attempt(result.get("attempt", 1))
    returncode = result.get("returncode")
    if isinstance(returncode, bool) or not isinstance(returncode, int):
        raise ValueError("failsafe outcome has invalid return code")

    evidence = result.get("evidence")
    evidence_status: str | None = None
    if isinstance(evidence, Mapping) and isinstance(evidence.get("status"), str):
        evidence_status = evidence["status"][:64]

    supplied_kind = result.get("failure_kind")
    if returncode == 0 and evidence_status in _SUCCESS_STATUSES:
        kind = FailureKind.SUCCESS
    elif returncode == 0 and evidence_status in _NOOP_STATUSES:
        kind = FailureKind.NO_CHANGE
    elif returncode == 0 and evidence_status in _DEDUP_STATUSES:
        kind = FailureKind.EXISTING_PR
    elif returncode == 0:
        kind = FailureKind.INVALID_EVIDENCE
    else:
        try:
            kind = FailureKind(supplied_kind)
        except (TypeError, ValueError):
            kind = FailureKind.UNKNOWN_FAILURE

    retryable = kind in _RETRYABLE and attempt < MAX_ATTEMPTS
    terminal = not retryable
    failure_digest = _digest(
        {
            "worker": worker,
            "kind": kind.value,
            "returncode": returncode,
            "attempt": attempt,
            "evidence_status": evidence_status,
        }
    )
    return FailsafeOutcome(
        worker=worker,
        kind=kind,
        returncode=returncode,
        attempt=attempt,
        terminal=terminal,
        retryable=retryable,
        evidence_status=evidence_status,
        failure_digest=failure_digest,
    )


def summarize_results(results: Iterable[Mapping[str, Any] | object]) -> dict[str, object]:
    """Produce bounded deterministic run evidence for logs and summaries."""
    outcomes = [classify_result(item) for item in list(results)[:MAX_RESULTS]]
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.kind.value] = counts.get(outcome.kind.value, 0) + 1
    terminal_failures = sum(
        outcome.terminal
        and outcome.kind
        not in {FailureKind.SUCCESS, FailureKind.NO_CHANGE, FailureKind.EXISTING_PR}
        for outcome in outcomes
    )
    payload = {
        "version": 1,
        "outcome_count": len(outcomes),
        "terminal_failures": terminal_failures,
        "retryable_count": sum(outcome.retryable for outcome in outcomes),
        "counts": dict(sorted(counts.items())),
        "outcomes": [outcome.as_dict() for outcome in outcomes],
    }
    return {**payload, "summary_digest": _digest(payload)}


def retry_allowed(result: Mapping[str, Any] | object) -> bool:
    """Return true only for a provably pre-execution setup failure."""
    return classify_result(result).retryable


__all__ = [
    "FailureKind",
    "FailsafeOutcome",
    "MAX_ATTEMPTS",
    "classify_result",
    "retry_allowed",
    "summarize_results",
]
