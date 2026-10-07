"""Typed contracts for the second-generation PR automation runner.

The runner is deliberately split into deterministic, side-effect-free contracts
and narrow adapters.  This module defines the values that cross those
boundaries.  Every value that can authorize a mutation is immutable,
serializable, bounded, and fingerprintable.

These contracts coexist with :mod:`skeleton.pr_automation.core` so existing
callers keep their stable public surface while the runtime gains richer
execution evidence, budgets, scheduling, transport telemetry, and transaction
semantics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .core import CIState, Decision, Evaluation, Mode, PRSnapshot, Policy


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")
_CONTEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")
_DELIVERY_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,240}$")


def canonical_json(value: Any) -> str:
    """Encode a JSON-compatible value deterministically."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def fingerprint(value: Any) -> str:
    """Return a SHA-256 fingerprint of canonical JSON."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def valid_sha(value: str) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def valid_repository(value: str) -> bool:
    return isinstance(value, str) and _REPOSITORY_RE.fullmatch(value) is not None


def valid_ref(value: str) -> bool:
    if not isinstance(value, str) or _REF_RE.fullmatch(value) is None:
        return False
    if value.startswith("/") or value.endswith("/") or value.endswith("."):
        return False
    if ".." in value or "@{" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} and not part.endswith(".lock") for part in value.split("/"))


def valid_context(value: str) -> bool:
    return isinstance(value, str) and _CONTEXT_RE.fullmatch(value) is not None


def bounded_text(value: object, *, limit: int) -> str:
    text = str(value)
    if limit < 0:
        raise ValueError("text bound must be non-negative")
    return text[:limit]


def unique_text(
    values: Iterable[str],
    *,
    casefold: bool = False,
    max_items: int = 1000,
) -> tuple[str, ...]:
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise TypeError("expected string")
        value = raw.strip()
        if not value:
            raise ValueError("empty string is not allowed")
        if casefold:
            value = value.casefold()
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) > max_items:
            raise ValueError("too many values")
    return tuple(result)


class RunTrigger(StrEnum):
    EXPLICIT = "explicit"
    WORKFLOW_COMPLETION = "workflow_completion"
    DEFAULT_BRANCH_COMPLETION = "default_branch_completion"
    SCHEDULED_SWEEP = "scheduled_sweep"
    MANUAL_SWEEP = "manual_sweep"
    RECOVERY = "recovery"


class AdmissionState(StrEnum):
    ADMIT = "admit"
    OBSERVE_ONLY = "observe_only"
    DROP = "drop"
    HOLD = "hold"


class WorkState(StrEnum):
    DISCOVERED = "discovered"
    COLLECTING = "collecting"
    EVALUATED = "evaluated"
    READY = "ready"
    MUTATING = "mutating"
    MERGED = "merged"
    HELD = "held"
    IGNORED = "ignored"
    FAILED = "failed"
    DEFERRED = "deferred"


class RunnerReason(StrEnum):
    READY = "ready"
    BUDGET = "budget"
    DEADLINE = "deadline"
    QUEUE_PRESSURE = "queue_pressure"
    RATE_LIMIT = "rate_limit"
    STALE_SNAPSHOT = "stale_snapshot"
    BASE_MOVED = "base_moved"
    HEAD_MOVED = "head_moved"
    POLICY_CHANGED = "policy_changed"
    CI_CHANGED = "ci_changed"
    REVIEW_CHANGED = "review_changed"
    TRUST_SURFACE = "trust_surface"
    DUPLICATE_ACTION = "duplicate_action"
    RETRY_LATER = "retry_later"
    EVENT_REJECTED = "event_rejected"
    TARGET_AMBIGUOUS = "target_ambiguous"
    TARGET_MISSING = "target_missing"
    TRANSPORT = "transport"
    INTERNAL = "internal"


class RequestKind(StrEnum):
    READ = "read"
    MUTATE = "mutate"
    GRAPHQL = "graphql"


class RequestOutcome(StrEnum):
    SUCCESS = "success"
    RETRY = "retry"
    RATE_LIMITED = "rate_limited"
    FAILURE = "failure"


class CheckState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    PENDING = "pending"
    MISSING = "missing"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class MutationKind(StrEnum):
    MERGE = "merge"
    STATUS = "status"
    DISPATCH = "dispatch"


class MutationState(StrEnum):
    PLANNED = "planned"
    CLAIMED = "claimed"
    APPLIED = "applied"
    REJECTED = "rejected"
    ABORTED = "aborted"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    DUPLICATE = "duplicate"


class PriorityBand(StrEnum):
    INTERACTIVE = "interactive"
    COMPLETION = "completion"
    RECOVERY = "recovery"
    SWEEP = "sweep"


@dataclass(frozen=True, slots=True)
class RunnerLimits:
    """Hard bounds for one process invocation."""

    max_targets: int = 250
    max_requests: int = 2000
    max_graphql_requests: int = 200
    max_mutations: int = 3
    max_pages: int = 20
    max_response_bytes: int = 8 * 1024 * 1024
    max_changed_files: int = 3000
    max_events_exported: int = 100_000
    deadline_seconds: int = 900
    per_target_request_budget: int = 100
    queue_pressure_threshold: int = 100
    minimum_rate_remaining: int = 50
    retry_attempts: int = 3
    retry_ceiling_seconds: int = 30

    def __post_init__(self) -> None:
        positive = {
            "max_targets": self.max_targets,
            "max_requests": self.max_requests,
            "max_graphql_requests": self.max_graphql_requests,
            "max_pages": self.max_pages,
            "max_response_bytes": self.max_response_bytes,
            "max_changed_files": self.max_changed_files,
            "max_events_exported": self.max_events_exported,
            "deadline_seconds": self.deadline_seconds,
            "per_target_request_budget": self.per_target_request_budget,
            "minimum_rate_remaining": self.minimum_rate_remaining,
            "retry_ceiling_seconds": self.retry_ceiling_seconds,
        }
        for name, value in positive.items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.max_mutations) is not int or self.max_mutations < 0:
            raise ValueError("max_mutations must be a non-negative integer")
        if (
            type(self.queue_pressure_threshold) is not int
            or self.queue_pressure_threshold < 0
        ):
            raise ValueError("queue_pressure_threshold must be a non-negative integer")
        if (
            type(self.retry_attempts) is not int
            or not 0 <= self.retry_attempts <= 10
        ):
            raise ValueError("retry_attempts must be an integer between 0 and 10")


@dataclass(frozen=True, slots=True)
class RunnerPolicy:
    core: Policy
    mode: Mode
    required_checks: tuple[str, ...]
    merge_method: str = "squash"
    allowed_authors: tuple[str, ...] = ()
    denied_labels: tuple[str, ...] = ("do-not-merge", "automerge:off")
    required_labels: tuple[str, ...] = ()
    protected_base_required: bool = True
    exact_base_head_required: bool = True
    queue_pressure_hold: bool = True
    publish_gate_status: bool = True
    require_same_repository_head: bool = True
    require_latest_reviews_on_head: bool = True
    limits: RunnerLimits = field(default_factory=RunnerLimits)

    def __post_init__(self) -> None:
        authority_flags = (
            "protected_base_required",
            "exact_base_head_required",
            "queue_pressure_hold",
            "publish_gate_status",
            "require_same_repository_head",
            "require_latest_reviews_on_head",
        )
        for name in authority_flags:
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        if self.merge_method not in {"merge", "squash", "rebase"}:
            raise ValueError("merge_method must be merge, squash, or rebase")
        for context in self.required_checks:
            if not valid_context(context):
                raise ValueError(f"invalid required check context: {context!r}")
        object.__setattr__(
            self,
            "required_checks",
            unique_text(self.required_checks, max_items=500),
        )
        object.__setattr__(
            self,
            "allowed_authors",
            unique_text(self.allowed_authors, casefold=True, max_items=500),
        )
        object.__setattr__(
            self,
            "denied_labels",
            unique_text(self.denied_labels, casefold=True, max_items=500),
        )
        object.__setattr__(
            self,
            "required_labels",
            unique_text(self.required_labels, casefold=True, max_items=500),
        )

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class RunIdentity:
    repository: str
    delivery_id: str
    trigger: RunTrigger
    workflow_name: str | None = None
    workflow_run_id: int | None = None
    head_sha: str | None = None
    head_ref: str | None = None
    default_branch: str = "main"
    explicit_pr: int | None = None
    hinted_prs: tuple[int, ...] = ()
    actor: str | None = None
    event_name: str | None = None

    def __post_init__(self) -> None:
        if not valid_repository(self.repository):
            raise ValueError("repository must be owner/name")
        if not self.delivery_id or _DELIVERY_RE.fullmatch(self.delivery_id) is None:
            raise ValueError("delivery_id is invalid")
        if self.workflow_run_id is not None and (
            isinstance(self.workflow_run_id, bool) or self.workflow_run_id <= 0
        ):
            raise ValueError("workflow_run_id must be positive")
        if self.head_sha is not None and not valid_sha(self.head_sha):
            raise ValueError("head_sha must be canonical lowercase SHA")
        if self.head_ref is not None and not valid_ref(self.head_ref):
            raise ValueError("head_ref is invalid")
        if not valid_ref(self.default_branch):
            raise ValueError("default_branch is invalid")
        if bool(self.head_sha) != bool(self.head_ref):
            raise ValueError("head_sha and head_ref must be supplied together")
        if self.explicit_pr is not None and (
            isinstance(self.explicit_pr, bool) or self.explicit_pr <= 0
        ):
            raise ValueError("explicit_pr must be positive")
        if len(self.hinted_prs) > 100:
            raise ValueError("too many PR hints")
        if any(isinstance(item, bool) or item <= 0 for item in self.hinted_prs):
            raise ValueError("hinted PRs must be positive integers")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    state: AdmissionState
    reasons: tuple[str, ...]
    mutation_authorized: bool
    priority: PriorityBand
    identity_fingerprint: str

    @property
    def dropped(self) -> bool:
        return self.state is AdmissionState.DROP

    @property
    def observe_only(self) -> bool:
        return self.state is AdmissionState.OBSERVE_ONLY


@dataclass(frozen=True, slots=True)
class RequestRecord:
    sequence: int
    method: str
    url: str
    kind: RequestKind
    outcome: RequestOutcome
    status_code: int | None
    attempt: int
    started_at: str
    finished_at: str
    response_bytes: int
    rate_limit_remaining: int | None
    retry_after_seconds: int | None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.sequence <= 0:
            raise ValueError("request sequence must be positive")
        if self.attempt <= 0:
            raise ValueError("attempt must be positive")
        if self.response_bytes < 0:
            raise ValueError("response bytes must be non-negative")
        if self.rate_limit_remaining is not None and self.rate_limit_remaining < 0:
            raise ValueError("rate limit remaining must be non-negative")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry-after must be non-negative")


@dataclass(frozen=True, slots=True)
class TransportSummary:
    requests: int
    graphql_requests: int
    retries: int
    bytes_received: int
    rate_limited: int
    failures: int
    minimum_remaining_seen: int | None
    records: tuple[RequestRecord, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "requests",
            "graphql_requests",
            "retries",
            "bytes_received",
            "rate_limited",
            "failures",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class CheckEvidence:
    name: str
    provider: str
    state: CheckState
    source: str
    source_id: int
    head_sha: str
    started_at: str | None
    completed_at: str | None
    updated_at: str | None
    details_url: str | None = None

    def __post_init__(self) -> None:
        if not valid_context(self.name):
            raise ValueError("check name is invalid")
        if not self.provider:
            raise ValueError("check provider is required")
        if self.source_id < 0:
            raise ValueError("source_id must be non-negative")
        if not valid_sha(self.head_sha):
            raise ValueError("check head SHA is invalid")

    def recency(self) -> tuple[str, int]:
        return (
            self.completed_at or self.updated_at or self.started_at or "",
            self.source_id,
        )


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    login: str
    state: str
    review_id: int
    commit_id: str | None
    submitted_at: str | None

    def __post_init__(self) -> None:
        if not self.login:
            raise ValueError("review login is required")
        if self.review_id < 0:
            raise ValueError("review_id must be non-negative")
        if self.commit_id is not None and not valid_sha(self.commit_id):
            raise ValueError("review commit ID must be canonical SHA")


@dataclass(frozen=True, slots=True)
class FileEvidence:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    previous_filename: str | None = None

    def __post_init__(self) -> None:
        if not self.filename or self.filename.startswith("/"):
            raise ValueError("filename must be repository-relative")
        for name in ("additions", "deletions", "changes"):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class EvidenceCompleteness:
    pull_request: bool
    checks: bool
    statuses: bool
    reviews: bool
    threads: bool
    files: bool
    base_branch: bool
    base_head: bool

    @property
    def complete(self) -> bool:
        return all(asdict(self).values())

    def missing(self) -> tuple[str, ...]:
        return tuple(name for name, value in asdict(self).items() if not value)


@dataclass(frozen=True, slots=True)
class RunnerSnapshot:
    core: PRSnapshot
    pr_node_id: str
    author: str
    head_repository: str | None
    base_head_sha: str | None
    labels: tuple[str, ...]
    files: tuple[FileEvidence, ...]
    checks: tuple[CheckEvidence, ...]
    reviews: tuple[ReviewEvidence, ...]
    required_check_states: tuple[tuple[str, CheckState], ...]
    completeness: EvidenceCompleteness
    captured_at: str
    source_request_count: int
    etag: str | None = None

    def __post_init__(self) -> None:
        if not self.pr_node_id:
            raise ValueError("PR node id is required")
        if not self.author:
            raise ValueError("PR author is required")
        if self.base_head_sha is not None and not valid_sha(self.base_head_sha):
            raise ValueError("base head SHA must be canonical")
        if self.source_request_count < 0:
            raise ValueError("source request count must be non-negative")
        if len(self.files) != self.core.changed_files and self.completeness.files:
            raise ValueError("complete file evidence must match changed_files count")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))

    @property
    def same_repository_head(self) -> bool:
        return (
            self.head_repository is not None
            and self.head_repository.casefold() == self.core.repository.casefold()
        )

    @property
    def exact_base_head(self) -> bool:
        return self.base_head_sha == self.core.base_sha


@dataclass(frozen=True, slots=True)
class Target:
    number: int
    reason: str
    priority: PriorityBand
    hinted: bool = False
    associated_by_sha: bool = False
    associated_by_branch: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.number, bool) or self.number <= 0:
            raise ValueError("target PR number must be positive")


@dataclass(frozen=True, slots=True)
class TargetSet:
    repository: str
    targets: tuple[Target, ...]
    complete: bool
    reason: str
    requests_used: int

    def __post_init__(self) -> None:
        if not valid_repository(self.repository):
            raise ValueError("repository must be owner/name")
        if self.requests_used < 0:
            raise ValueError("requests_used must be non-negative")
        if len({target.number for target in self.targets}) != len(self.targets):
            raise ValueError("duplicate target PR number")


@dataclass(frozen=True, slots=True)
class WorkItem:
    target: Target
    snapshot: RunnerSnapshot
    evaluation: Evaluation
    state: WorkState
    score: int
    reasons: tuple[str, ...]
    observed_queue_depth: int | None
    observed_rate_remaining: int | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if self.score < -1_000_000 or self.score > 1_000_000:
            raise ValueError("work score is outside bound")


@dataclass(frozen=True, slots=True)
class RunBudget:
    request_limit: int
    graphql_limit: int
    mutation_limit: int
    target_limit: int
    deadline_at: str
    request_used: int = 0
    graphql_used: int = 0
    mutations_used: int = 0
    targets_used: int = 0

    def __post_init__(self) -> None:
        pairs = (
            ("request", self.request_limit, self.request_used),
            ("graphql", self.graphql_limit, self.graphql_used),
            ("mutation", self.mutation_limit, self.mutations_used),
            ("target", self.target_limit, self.targets_used),
        )
        for name, limit, used in pairs:
            if type(limit) is not int or limit < 0:
                raise ValueError(f"{name} limit must be a non-negative integer")
            if type(used) is not int or used < 0 or used > limit:
                raise ValueError(f"{name} usage must be an integer within its limit")

    def remaining_requests(self) -> int:
        return self.request_limit - self.request_used

    def remaining_graphql(self) -> int:
        return self.graphql_limit - self.graphql_used

    def remaining_mutations(self) -> int:
        return self.mutation_limit - self.mutations_used

    def remaining_targets(self) -> int:
        return self.target_limit - self.targets_used

    def deadline(self) -> datetime:
        parsed = parse_time(self.deadline_at)
        if parsed is None:
            raise ValueError("deadline_at is invalid")
        return parsed


@dataclass(frozen=True, slots=True)
class Preconditions:
    protected_base: bool | None
    base_head_matches: bool
    head_matches: bool
    snapshot_matches: bool
    policy_matches: bool
    checks_still_passing: bool
    reviews_still_valid: bool
    queue_within_limit: bool
    rate_limit_safe: bool

    @property
    def satisfied(self) -> bool:
        return (
            self.protected_base is True
            and self.base_head_matches
            and self.head_matches
            and self.snapshot_matches
            and self.policy_matches
            and self.checks_still_passing
            and self.reviews_still_valid
            and self.queue_within_limit
            and self.rate_limit_safe
        )

    def failed(self) -> tuple[str, ...]:
        return tuple(name for name, value in asdict(self).items() if value is not True)


@dataclass(frozen=True, slots=True)
class MutationIntent:
    key: str
    kind: MutationKind
    repository: str
    pr_number: int
    expected_head_sha: str
    expected_base_sha: str
    snapshot_fingerprint: str
    policy_fingerprint: str
    merge_method: str
    created_at: str

    def __post_init__(self) -> None:
        if len(self.key) != 64:
            raise ValueError("mutation key must be a SHA-256 hex digest")
        if not valid_repository(self.repository):
            raise ValueError("invalid repository")
        if self.pr_number <= 0:
            raise ValueError("pr_number must be positive")
        if not valid_sha(self.expected_head_sha) or not valid_sha(self.expected_base_sha):
            raise ValueError("expected SHAs must be canonical")
        if self.merge_method not in {"merge", "squash", "rebase"}:
            raise ValueError("invalid merge method")

    @classmethod
    def from_work_item(
        cls,
        item: WorkItem,
        policy: RunnerPolicy,
    ) -> "MutationIntent":
        snapshot = item.snapshot
        policy_snapshot_fingerprint = snapshot_policy_fingerprint(snapshot)
        material = {
            "repository": snapshot.core.repository,
            "pr": snapshot.core.number,
            "head": snapshot.core.head_sha,
            "base": snapshot.core.base_sha,
            "snapshot": policy_snapshot_fingerprint,
            "policy": policy.fingerprint(),
            "kind": "merge",
            "method": policy.merge_method,
        }
        return cls(
            key=fingerprint(material),
            kind=MutationKind.MERGE,
            repository=snapshot.core.repository,
            pr_number=snapshot.core.number,
            expected_head_sha=snapshot.core.head_sha,
            expected_base_sha=snapshot.core.base_sha,
            snapshot_fingerprint=policy_snapshot_fingerprint,
            policy_fingerprint=policy.fingerprint(),
            merge_method=policy.merge_method,
            created_at=utcnow().isoformat(),
        )


@dataclass(frozen=True, slots=True)
class MutationReceipt:
    intent: MutationIntent
    state: MutationState
    observed_head_sha: str | None
    observed_base_sha: str | None
    merge_sha: str | None
    message: str
    preconditions: Preconditions | None
    started_at: str
    finished_at: str

    @property
    def applied(self) -> bool:
        return self.state is MutationState.APPLIED


@dataclass(frozen=True, slots=True)
class TargetResult:
    number: int
    state: WorkState
    decision: Decision
    reasons: tuple[str, ...]
    snapshot_fingerprint: str | None
    mutations: tuple[MutationReceipt, ...]
    request_count: int
    duration_ms: int
    error: str | None = None

    def __post_init__(self) -> None:
        if self.number <= 0:
            raise ValueError("target result number must be positive")
        if self.request_count < 0 or self.duration_ms < 0:
            raise ValueError("result counters must be non-negative")


@dataclass(frozen=True, slots=True)
class RunnerReport:
    identity: RunIdentity
    admission: AdmissionDecision
    policy_fingerprint: str
    started_at: str
    finished_at: str
    targets: TargetSet
    results: tuple[TargetResult, ...]
    transport: TransportSummary
    mutations_attempted: int
    mutations_applied: int
    failures: int
    deferred: int
    final_queue_depth: int | None
    final_rate_remaining: int | None

    def __post_init__(self) -> None:
        for name in (
            "mutations_attempted",
            "mutations_applied",
            "failures",
            "deferred",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


def core_evaluation_ready(evaluation: Evaluation) -> bool:
    return evaluation.decision in {Decision.READY, Decision.MERGE}


def ci_state_from_checks(states: Sequence[CheckState]) -> CIState:
    if not states:
        return CIState.MISSING
    values = set(states)
    if CheckState.FAILING in values or CheckState.CANCELLED in values:
        return CIState.FAILING
    if CheckState.MISSING in values:
        return CIState.MISSING
    if CheckState.PENDING in values:
        return CIState.PENDING
    if CheckState.UNKNOWN in values or CheckState.SKIPPED in values:
        return CIState.UNKNOWN
    if values == {CheckState.PASSING}:
        return CIState.PASSING
    return CIState.UNKNOWN


def snapshot_policy_identity(snapshot: RunnerSnapshot) -> Mapping[str, Any]:
    """Return the fields that must remain stable across mutation revalidation."""
    core = snapshot.core
    return {
        "repository": core.repository,
        "number": core.number,
        "head_sha": core.head_sha,
        "base_sha": core.base_sha,
        "base_ref": core.base_ref,
        "head_ref": core.head_ref,
        "state": core.state,
        "merged": core.merged,
        "draft": core.draft,
        "from_fork": core.from_fork,
        "mergeable": core.mergeable,
        "mergeable_state": core.mergeable_state,
        "ci_state": core.ci_state.value,
        "approvals": core.approvals,
        "changes_requested": core.changes_requested,
        "unresolved_threads": core.unresolved_threads,
        "changed_files": core.changed_files,
        "additions": core.additions,
        "deletions": core.deletions,
        "sensitive_paths": core.sensitive_paths,
        "labels": core.labels,
        "author": snapshot.author.casefold(),
        "head_repository": (
            snapshot.head_repository.casefold()
            if snapshot.head_repository is not None
            else None
        ),
        "base_head_sha": snapshot.base_head_sha,
        "required_check_states": tuple(
            (name, state.value) for name, state in snapshot.required_check_states
        ),
        "completeness": asdict(snapshot.completeness),
    }


def snapshot_policy_fingerprint(snapshot: RunnerSnapshot) -> str:
    return fingerprint(snapshot_policy_identity(snapshot))


__all__ = [
    "AdmissionDecision",
    "AdmissionState",
    "CheckEvidence",
    "CheckState",
    "EvidenceCompleteness",
    "FileEvidence",
    "MutationIntent",
    "MutationKind",
    "MutationReceipt",
    "MutationState",
    "Preconditions",
    "PriorityBand",
    "RequestKind",
    "RequestOutcome",
    "RequestRecord",
    "ReviewEvidence",
    "RunBudget",
    "RunIdentity",
    "RunTrigger",
    "RunnerLimits",
    "RunnerPolicy",
    "RunnerReason",
    "RunnerReport",
    "RunnerSnapshot",
    "Target",
    "TargetResult",
    "TargetSet",
    "TransportSummary",
    "WorkItem",
    "WorkState",
    "bounded_text",
    "canonical_json",
    "ci_state_from_checks",
    "core_evaluation_ready",
    "fingerprint",
    "parse_time",
    "snapshot_policy_fingerprint",
    "snapshot_policy_identity",
    "unique_text",
    "utcnow",
    "valid_context",
    "valid_ref",
    "valid_repository",
    "valid_sha",
]
