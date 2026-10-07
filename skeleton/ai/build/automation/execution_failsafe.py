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
MAX_RETRY_DELAY_SECONDS = 8


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


def retry_token(
    *,
    worker: str,
    attempt: int,
    execution_fingerprint: str,
    snapshot_fingerprint: str,
) -> str:
    """Bind one retry attempt to immutable execution and snapshot custody."""
    worker = _bounded_worker(worker)
    attempt = _bounded_attempt(attempt)
    for label, value in (
        ("execution", execution_fingerprint),
        ("snapshot", snapshot_fingerprint),
    ):
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError(f"retry {label} fingerprint is invalid")
    return _digest(
        {
            "version": 1,
            "worker": worker,
            "attempt": attempt,
            "execution_fingerprint": execution_fingerprint,
            "snapshot_fingerprint": snapshot_fingerprint,
        }
    )


def retry_delay_seconds(attempt: int, retry_token_value: str) -> int:
    """Return deterministic bounded backoff with custody-derived jitter."""
    attempt = _bounded_attempt(attempt)
    if (
        not isinstance(retry_token_value, str)
        or len(retry_token_value) != 64
        or any(char not in "0123456789abcdef" for char in retry_token_value)
    ):
        raise ValueError("retry token is invalid")
    base = 1 << (attempt - 1)
    jitter = int(retry_token_value[:2], 16) % 3
    return min(MAX_RETRY_DELAY_SECONDS, base + jitter)


def attach_retry_history(
    final_result: Mapping[str, Any],
    attempts: Iterable[Mapping[str, Any]],
    *,
    execution_fingerprint: str,
    snapshot_fingerprint: str,
) -> dict[str, Any]:
    """Seal an ordered attempt chain onto the final admitted result."""
    items = list(attempts)
    if not items or len(items) > MAX_ATTEMPTS:
        raise ValueError("retry history has invalid length")
    outcomes = [classify_result(item) for item in items]
    worker = outcomes[0].worker
    if any(outcome.worker != worker for outcome in outcomes):
        raise ValueError("retry history crosses worker custody")
    if [outcome.attempt for outcome in outcomes] != list(range(1, len(outcomes) + 1)):
        raise ValueError("retry history attempts are not contiguous")
    if any(not outcome.retryable for outcome in outcomes[:-1]):
        raise ValueError("retry history contains unauthorized transition")
    expected_final = classify_result(final_result)
    if expected_final != outcomes[-1]:
        raise ValueError("retry history final result mismatch")
    tokens = [
        retry_token(
            worker=worker,
            attempt=outcome.attempt,
            execution_fingerprint=execution_fingerprint,
            snapshot_fingerprint=snapshot_fingerprint,
        )
        for outcome in outcomes
    ]
    history = [
        {
            "attempt": outcome.attempt,
            "kind": outcome.kind.value,
            "terminal": outcome.terminal,
            "retryable": outcome.retryable,
            "failure_digest": outcome.failure_digest,
            "retry_token": token,
        }
        for outcome, token in zip(outcomes, tokens, strict=True)
    ]
    chain_payload = {
        "version": 1,
        "worker": worker,
        "execution_fingerprint": execution_fingerprint,
        "snapshot_fingerprint": snapshot_fingerprint,
        "attempts": history,
    }
    return {
        **dict(final_result),
        "attempt_history": history,
        "retry_chain_digest": _digest(chain_payload),
    }


__all__ = [
    "FailureKind",
    "FailsafeOutcome",
    "MAX_ATTEMPTS",
    "attach_retry_history",
    "classify_result",
    "retry_allowed",
    "retry_delay_seconds",
    "retry_token",
    "summarize_results",
]
