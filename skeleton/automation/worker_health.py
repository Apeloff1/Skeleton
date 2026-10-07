"""Bounded, non-authoritative health classification for specialist pull requests.

This module deliberately contains no mutation primitives.  It translates GitHub
pull-request observations into a small planning vocabulary that can be consumed
by the planning-only Supervisor without widening Secretary or Worker authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Any, Iterable, Mapping

from .supervisor_runtime import SupervisorRuntimeError, validate_worker_name

BOT_BRANCH_PREFIX = "bot/specialist-"
BASE_PREFIX_LENGTH = 16
MAX_WORKER_NAME = 48
MAX_CHECKS = 64
MAX_ACTIVE_WORKERS = 40
MAX_OBSERVED_PULL_REQUESTS = 256

_PENDING = frozenset({"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED"})
_FAILURE = frozenset({"FAILURE", "FAILED", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"})
_SUCCESS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})


@dataclass(frozen=True, slots=True)
class DurableWorkerHealth:
    """Sanitized planning evidence derived from one open specialist PR."""

    worker: str
    pull_request: int
    base_prefix: str
    merge_state: str
    is_draft: bool
    check_state: str
    check_total: int
    check_failures: int
    check_pending: int
    classification: str

    def as_dict(self) -> dict[str, object]:
        return {
            "worker": self.worker,
            "pull_request": self.pull_request,
            "base_prefix": self.base_prefix,
            "merge_state": self.merge_state,
            "is_draft": self.is_draft,
            "check_state": self.check_state,
            "check_total": self.check_total,
            "check_failures": self.check_failures,
            "check_pending": self.check_pending,
            "classification": self.classification,
        }


def _branch_identity(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.startswith(BOT_BRANCH_PREFIX):
        return None
    remainder = value[len(BOT_BRANCH_PREFIX):]
    worker, separator, base_prefix = remainder.rpartition("-")
    if not separator or not worker or len(worker) > MAX_WORKER_NAME:
        return None
    if len(base_prefix) != BASE_PREFIX_LENGTH:
        return None
    if any(ch not in "0123456789abcdef" for ch in base_prefix):
        return None
    try:
        worker = validate_worker_name(worker)
    except SupervisorRuntimeError:
        return None
    return worker, base_prefix


def _check_status(item: Mapping[str, Any]) -> str:
    """Return one closed status vocabulary for a GitHub check-rollup item."""
    conclusion = item.get("conclusion")
    if isinstance(conclusion, str) and conclusion.strip():
        return conclusion.strip().upper()[:32]
    status = item.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip().upper()[:32]
    state = item.get("state")
    if isinstance(state, str) and state.strip():
        return state.strip().upper()[:32]
    return "UNKNOWN"


def summarize_checks(value: object) -> tuple[str, int, int, int]:
    """Summarize a bounded check rollup without retaining names or URLs."""
    if not isinstance(value, list):
        return "unknown", 0, 0, 0
    statuses: list[str] = []
    for raw in value[:MAX_CHECKS]:
        if isinstance(raw, Mapping):
            statuses.append(_check_status(raw))
    if not statuses:
        return "unknown", 0, 0, 0
    failures = sum(status in _FAILURE for status in statuses)
    pending = sum(status in _PENDING for status in statuses)
    unknown = sum(
        status not in _FAILURE and status not in _PENDING and status not in _SUCCESS
        for status in statuses
    )
    if failures:
        state = "failing"
    elif pending:
        state = "pending"
    elif unknown:
        state = "unknown"
    else:
        state = "passing"
    return state, len(statuses), failures, pending


def classify_worker_pr(pr: Mapping[str, Any] | object) -> DurableWorkerHealth | None:
    """Classify one observed PR; ignore malformed or non-worker records."""
    if not isinstance(pr, Mapping):
        return None
    identity = _branch_identity(pr.get("headRefName"))
    if identity is None:
        return None
    number = pr.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        return None
    worker, base_prefix = identity
    merge_state = str(pr.get("mergeStateStatus", "UNKNOWN")).upper()[:32]
    check_state, total, failures, pending = summarize_checks(
        pr.get("statusCheckRollup")
    )
    is_draft = pr.get("isDraft") is True

    if is_draft:
        classification = "draft"
    elif check_state == "failing":
        classification = "failing-ci"
    elif merge_state == "DIRTY":
        classification = "conflicted"
    elif check_state in {"pending", "unknown"}:
        classification = "awaiting-checks"
    elif merge_state == "BLOCKED":
        classification = "blocked"
    elif check_state == "passing":
        classification = "healthy"
    else:
        classification = "observed"

    return DurableWorkerHealth(
        worker=worker,
        pull_request=number,
        base_prefix=base_prefix,
        merge_state=merge_state,
        is_draft=is_draft,
        check_state=check_state,
        check_total=total,
        check_failures=failures,
        check_pending=pending,
        classification=classification,
    )


def classify_worker_prs(
    pull_requests: Iterable[Mapping[str, Any] | object],
    *,
    limit: int = MAX_ACTIVE_WORKERS,
) -> dict[str, object]:
    """Return bounded GitHub-native worker health evidence.

    Only a fixed number of input records are inspected, so generators and
    oversized iterables cannot turn planning telemetry into an unbounded
    memory/time sink. The Supervisor observation layer is already bounded
    below this ceiling.
    """
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit <= 0
        or limit > MAX_ACTIVE_WORKERS
    ):
        raise ValueError(
            f"limit must be an integer in 1..{MAX_ACTIVE_WORKERS}"
        )
    admitted: list[DurableWorkerHealth] = []
    for pr in islice(pull_requests, MAX_OBSERVED_PULL_REQUESTS):
        health = classify_worker_pr(pr)
        if health is not None:
            admitted.append(health)
    admitted.sort(key=lambda item: (item.worker, item.pull_request))
    admitted = admitted[:limit]
    counts: dict[str, int] = {}
    for item in admitted:
        counts[item.classification] = counts.get(item.classification, 0) + 1
    return {
        "version": 1,
        "non_authoritative": True,
        "source": "github-open-pull-requests",
        "active_count": len(admitted),
        "classification_counts": dict(sorted(counts.items())),
        "active_workers": [item.as_dict() for item in admitted],
    }
