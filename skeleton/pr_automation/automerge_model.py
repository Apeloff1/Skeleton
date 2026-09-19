"""Typed immutable contracts for the repository auto-merge control plane.

The module is intentionally side-effect free.  Every decision made by the
runtime is represented as an immutable value that can be fingerprinted,
serialized, replayed, and compared at the mutation boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Iterable, Sequence


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")
_CONTEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")
_LABEL_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,100}$")


def canonical_json(value: Any) -> str:
    """Return deterministic JSON suitable for hashing and durable evidence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: Any) -> str:
    payload = canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def valid_sha(value: str) -> bool:
    return bool(_SHA_RE.fullmatch(value))


def valid_ref(value: str) -> bool:
    if not _REF_RE.fullmatch(value):
        return False
    if value.startswith("/") or value.endswith("/") or value.endswith("."):
        return False
    if ".." in value or "@{" in value:
        return False
    parts = value.split("/")
    if any(part in {"", ".", ".."} or part.endswith(".lock") for part in parts):
        return False
    return True


def valid_context(value: str) -> bool:
    return bool(_CONTEXT_RE.fullmatch(value))


def valid_label(value: str) -> bool:
    return bool(_LABEL_RE.fullmatch(value))


def _tuple_text(values: Iterable[str], *, lower: bool = False) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise TypeError("expected string value")
        value = raw.strip()
        if lower:
            value = value.casefold()
        if not value:
            raise ValueError("empty string is not allowed")
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


class MergeMode(StrEnum):
    OBSERVE = "observe"
    ENABLE_NATIVE = "enable_native"
    MERGE_DIRECT = "merge_direct"


class MergeMethod(StrEnum):
    SQUASH = "squash"
    MERGE = "merge"
    REBASE = "rebase"


class CandidateClass(StrEnum):
    OWNER = "owner"
    DEPENDABOT = "dependabot"
    BOT = "bot"
    UNKNOWN = "unknown"


class GateState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    MISSING = "missing"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class DecisionKind(StrEnum):
    IGNORE = "ignore"
    HOLD = "hold"
    READY = "ready"
    MERGE = "merge"
    ENABLE_AUTO_MERGE = "enable_auto_merge"
    MERGE_STACK_CHILD = "merge_stack_child"


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StackRelation(StrEnum):
    ROOT = "root"
    CHILD = "child"
    ORPHAN = "orphan"
    CYCLE = "cycle"


@dataclass(frozen=True, slots=True)
class WorkflowEvidence:
    name: str
    run_id: int
    run_number: int
    attempt: int
    head_sha: str
    event: str
    status: str
    conclusion: str | None
    created_at: str | None = None
    updated_at: str | None = None
    html_url: str | None = None

    def __post_init__(self) -> None:
        if not valid_context(self.name):
            raise ValueError("invalid workflow name")
        if self.run_id <= 0 or self.run_number < 0 or self.attempt < 0:
            raise ValueError("invalid workflow identity")
        if not valid_sha(self.head_sha):
            raise ValueError("workflow head SHA must be canonical lowercase SHA")
        if not self.event:
            raise ValueError("workflow event is required")

    @property
    def rank(self) -> tuple[int, int, str]:
        return (self.run_number, self.attempt, self.updated_at or self.created_at or "")

    def state(self) -> GateState:
        status = self.status.casefold()
        conclusion = (self.conclusion or "").casefold()
        if status != "completed":
            return GateState.PENDING
        if conclusion == "success":
            return GateState.SUCCESS
        if conclusion == "skipped":
            return GateState.SKIPPED
        if conclusion == "cancelled":
            return GateState.CANCELLED
        if conclusion in {"failure", "timed_out", "action_required", "startup_failure", "stale"}:
            return GateState.FAILURE
        return GateState.UNKNOWN


@dataclass(frozen=True, slots=True)
class ReviewEvidence:
    login: str
    state: str
    submitted_at: str | None = None
    commit_id: str | None = None

    def normalized_state(self) -> str:
        return self.state.upper().strip()


@dataclass(frozen=True, slots=True)
class PullRequestIdentity:
    repository: str
    number: int
    node_id: str
    state: str
    draft: bool
    author: str
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    head_repo: str
    mergeable: bool | None
    mergeable_state: str
    created_at: str | None
    updated_at: str | None

    def __post_init__(self) -> None:
        if self.repository.count("/") != 1:
            raise ValueError("repository must be owner/name")
        if self.number <= 0:
            raise ValueError("pull request number must be positive")
        if not self.node_id:
            raise ValueError("node id is required")
        if not valid_ref(self.base_ref):
            raise ValueError("invalid base ref")
        if not valid_ref(self.head_ref):
            raise ValueError("invalid head ref")
        if not valid_sha(self.base_sha) or not valid_sha(self.head_sha):
            raise ValueError("base/head SHA must be canonical lowercase SHA")
        if self.head_repo.count("/") != 1:
            raise ValueError("head repository must be owner/name")

    @property
    def from_fork(self) -> bool:
        return self.repository.casefold() != self.head_repo.casefold()

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class DiffSummary:
    files: tuple[str, ...]
    additions: int
    deletions: int
    changed_files: int

    def __post_init__(self) -> None:
        if self.additions < 0 or self.deletions < 0 or self.changed_files < 0:
            raise ValueError("negative diff metric")
        if self.changed_files != len(self.files):
            raise ValueError("changed file count must equal file inventory")
        if len(set(self.files)) != len(self.files):
            raise ValueError("duplicate changed path")

    @property
    def line_delta(self) -> int:
        return self.additions + self.deletions

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    identity: PullRequestIdentity
    diff: DiffSummary
    labels: tuple[str, ...]
    reviews: tuple[ReviewEvidence, ...]
    unresolved_threads: int | None
    workflow_runs: tuple[WorkflowEvidence, ...]
    base_contains_head_parent: bool | None = None
    head_contains_base: bool | None = None
    candidate_class: CandidateClass = CandidateClass.UNKNOWN
    stack_relation: StackRelation = StackRelation.ROOT
    parent_pr: int | None = None
    sensitive_paths: tuple[str, ...] = ()
    risk_tier: RiskTier = RiskTier.MEDIUM
    captured_at: str = field(default_factory=lambda: utc_now().isoformat())

    def __post_init__(self) -> None:
        if self.unresolved_threads is not None and self.unresolved_threads < 0:
            raise ValueError("unresolved thread count must be non-negative")
        for label in self.labels:
            if not valid_label(label):
                raise ValueError("invalid label")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("duplicate labels")
        if self.parent_pr is not None and self.parent_pr <= 0:
            raise ValueError("parent PR must be positive")
        if self.parent_pr == self.identity.number:
            raise ValueError("pull request cannot parent itself")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class GateRequirement:
    name: str
    allow_skipped: bool = False
    require_pull_request_event: bool = True

    def __post_init__(self) -> None:
        if not valid_context(self.name):
            raise ValueError("invalid required workflow name")


@dataclass(frozen=True, slots=True)
class GateResult:
    name: str
    state: GateState
    run_id: int | None
    reason: str

    def __post_init__(self) -> None:
        if not valid_context(self.name):
            raise ValueError("invalid gate result name")


@dataclass(frozen=True, slots=True)
class MergeBudget:
    max_merges: int = 3
    max_stack_merges: int = 2
    max_changed_files: int = 250
    max_line_delta: int = 20_000
    stability_seconds: int = 30
    max_open_pr_scan: int = 250

    def __post_init__(self) -> None:
        values = (
            self.max_merges,
            self.max_stack_merges,
            self.max_changed_files,
            self.max_line_delta,
            self.max_open_pr_scan,
        )
        if any(isinstance(v, bool) or v <= 0 for v in values):
            raise ValueError("merge budget integer fields must be positive non-bool integers")
        if isinstance(self.stability_seconds, bool) or self.stability_seconds < 0:
            raise ValueError("stability_seconds must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class AutoMergePolicy:
    default_branch: str = "main"
    mode: MergeMode = MergeMode.MERGE_DIRECT
    merge_method: MergeMethod = MergeMethod.SQUASH
    required_workflows: tuple[GateRequirement, ...] = ()
    required_approvals: int = 0
    require_resolved_threads: bool = True
    require_no_changes_requested: bool = True
    same_repository_only: bool = True
    owner_logins: tuple[str, ...] = ()
    trusted_bot_logins: tuple[str, ...] = ("dependabot[bot]",)
    opt_in_labels: tuple[str, ...] = ("automerge",)
    opt_out_labels: tuple[str, ...] = ("do-not-merge", "automerge:off")
    allow_owner_without_opt_in: bool = False
    allow_dependabot_without_opt_in: bool = True
    allow_stack_child_merge: bool = True
    sensitive_prefixes: tuple[str, ...] = (
        ".github/workflows/",
        ".github/actions/",
        "skeleton/pr_automation/",
        "scripts/check_merge_readiness_contract.py",
    )
    critical_prefixes: tuple[str, ...] = (
        ".github/workflows/",
        ".github/actions/",
        "skeleton/pr_automation/",
    )
    budget: MergeBudget = field(default_factory=MergeBudget)

    def __post_init__(self) -> None:
        if not valid_ref(self.default_branch):
            raise ValueError("invalid default branch")
        if isinstance(self.required_approvals, bool) or not 0 <= self.required_approvals <= 10:
            raise ValueError("required_approvals must be between 0 and 10")
        object.__setattr__(self, "owner_logins", _tuple_text(self.owner_logins, lower=True))
        object.__setattr__(self, "trusted_bot_logins", _tuple_text(self.trusted_bot_logins, lower=True))
        object.__setattr__(self, "opt_in_labels", _tuple_text(self.opt_in_labels, lower=True))
        object.__setattr__(self, "opt_out_labels", _tuple_text(self.opt_out_labels, lower=True))
        if len({gate.name for gate in self.required_workflows}) != len(self.required_workflows):
            raise ValueError("duplicate required workflows")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class MergeAction:
    kind: DecisionKind
    pr_number: int
    expected_head_sha: str
    expected_base_sha: str
    target_base_ref: str
    merge_method: MergeMethod
    reason: str
    idempotency_key: str

    @classmethod
    def make(
        cls,
        *,
        kind: DecisionKind,
        snapshot: CandidateSnapshot,
        merge_method: MergeMethod,
        reason: str,
    ) -> "MergeAction":
        identity = snapshot.identity
        raw = {
            "kind": kind.value,
            "repository": identity.repository,
            "pr": identity.number,
            "head": identity.head_sha,
            "base": identity.base_sha,
            "base_ref": identity.base_ref,
            "method": merge_method.value,
        }
        return cls(
            kind=kind,
            pr_number=identity.number,
            expected_head_sha=identity.head_sha,
            expected_base_sha=identity.base_sha,
            target_base_ref=identity.base_ref,
            merge_method=merge_method,
            reason=reason,
            idempotency_key=fingerprint(raw),
        )


@dataclass(frozen=True, slots=True)
class MergeDecision:
    pr_number: int
    kind: DecisionKind
    reasons: tuple[str, ...]
    gates: tuple[GateResult, ...]
    actions: tuple[MergeAction, ...]
    snapshot_fingerprint: str
    policy_fingerprint: str
    risk_tier: RiskTier

    @property
    def mutating(self) -> bool:
        return bool(self.actions)

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class MutationReceipt:
    pr_number: int
    action_key: str
    requested_head_sha: str
    observed_head_sha: str
    base_ref: str
    merged: bool
    merge_sha: str | None
    message: str
    recorded_at: str = field(default_factory=lambda: utc_now().isoformat())

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    repository: str
    default_branch: str
    policy_fingerprint: str
    scanned: int
    decisions: tuple[MergeDecision, ...]
    receipts: tuple[MutationReceipt, ...]
    base_head_before: str
    base_head_after: str
    started_at: str
    finished_at: str

    def __post_init__(self) -> None:
        if self.scanned < 0:
            raise ValueError("scanned must be non-negative")
        if not valid_sha(self.base_head_before) or not valid_sha(self.base_head_after):
            raise ValueError("report base heads must be canonical SHAs")

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


def immutable_identity_equal(left: PullRequestIdentity, right: PullRequestIdentity) -> bool:
    """Return whether every mutation-relevant PR identity field is unchanged."""
    return (
        left.repository == right.repository
        and left.number == right.number
        and left.node_id == right.node_id
        and left.state == right.state
        and left.draft == right.draft
        and left.author.casefold() == right.author.casefold()
        and left.base_ref == right.base_ref
        and left.base_sha == right.base_sha
        and left.head_ref == right.head_ref
        and left.head_sha == right.head_sha
        and left.head_repo.casefold() == right.head_repo.casefold()
    )


def labels_normalized(labels: Sequence[str]) -> tuple[str, ...]:
    return _tuple_text(labels, lower=True)


__all__ = [
    "AutoMergePolicy",
    "CandidateClass",
    "CandidateSnapshot",
    "DecisionKind",
    "DiffSummary",
    "GateRequirement",
    "GateResult",
    "GateState",
    "MergeAction",
    "MergeBudget",
    "MergeDecision",
    "MergeMethod",
    "MergeMode",
    "MutationReceipt",
    "PullRequestIdentity",
    "ReconcileReport",
    "ReviewEvidence",
    "RiskTier",
    "StackRelation",
    "WorkflowEvidence",
    "canonical_json",
    "fingerprint",
    "immutable_identity_equal",
    "labels_normalized",
    "parse_timestamp",
    "utc_now",
    "valid_context",
    "valid_ref",
    "valid_sha",
]
