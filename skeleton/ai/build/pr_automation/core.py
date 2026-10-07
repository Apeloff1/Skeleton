"""Deterministic policy engine for pull-request automation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Any


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CIState(StrEnum):
    PASSING = "passing"
    FAILING = "failing"
    PENDING = "pending"
    MISSING = "missing"
    UNKNOWN = "unknown"


class Decision(StrEnum):
    IGNORE = "ignore"
    HOLD = "hold"
    READY = "ready"
    MERGE = "merge"


class Mode(StrEnum):
    OBSERVE = "observe"
    APPLY = "apply"


@dataclass(frozen=True, slots=True)
class PRSnapshot:
    repository: str
    number: int
    head_sha: str
    base_sha: str
    base_ref: str
    head_ref: str
    state: str = "open"
    merged: bool = False
    draft: bool = False
    from_fork: bool = False
    mergeable: bool | None = None
    mergeable_state: str = "unknown"
    ci_state: CIState = CIState.UNKNOWN
    approvals: int | None = 0
    changes_requested: int | None = 0
    unresolved_threads: int | None = None
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0
    sensitive_paths: tuple[str, ...] | None = ()
    labels: tuple[str, ...] = ()
    updated_at: str | None = None

    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class Policy:
    allowed_bases: tuple[str, ...] = ("main",)
    required_approvals: int = 0
    require_no_changes_requested: bool = True
    require_resolved_threads: bool = True
    require_checks: bool = True
    allow_fork_merge: bool = False
    max_changed_files: int = 250
    max_total_line_delta: int = 20_000
    merge_when_ready: bool = False

    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


@dataclass(frozen=True, slots=True)
class PlannedAction:
    kind: str
    expected_head_sha: str
    idempotency_key: str
    reason: str

    @classmethod
    def make(cls, snapshot: PRSnapshot, kind: str, reason: str) -> "PlannedAction":
        raw = f"{snapshot.repository}:{snapshot.number}:{snapshot.head_sha}:{kind}"
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return cls(kind=kind, expected_head_sha=snapshot.head_sha, idempotency_key=key, reason=reason)


@dataclass(frozen=True, slots=True)
class Evaluation:
    decision: Decision
    reasons: tuple[str, ...]
    actions: tuple[PlannedAction, ...] = ()
    snapshot_fingerprint: str = ""
    policy_fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _evaluation(
    snapshot: PRSnapshot,
    policy: Policy,
    decision: Decision,
    reasons: tuple[str, ...],
    actions: tuple[PlannedAction, ...] = (),
) -> Evaluation:
    return Evaluation(
        decision=decision,
        reasons=reasons,
        actions=actions,
        snapshot_fingerprint=snapshot.fingerprint(),
        policy_fingerprint=policy.fingerprint(),
    )


def _hold(snapshot: PRSnapshot, policy: Policy, *reasons: str) -> Evaluation:
    return _evaluation(snapshot, policy, Decision.HOLD, tuple(reasons))


def evaluate(snapshot: PRSnapshot, policy: Policy) -> Evaluation:
    """Evaluate one immutable PR snapshot without side effects.

    Only explicitly known state can become merge-ready. Unknown enum values and
    incomplete data fail closed. Changes to the automation trust surface may
    satisfy normal merge gates but never produce an automated mutation action.
    """

    if snapshot.state != "open" or snapshot.merged:
        return _evaluation(snapshot, policy, Decision.IGNORE, ("pull request is not open",))

    if not snapshot.head_sha or len(snapshot.head_sha) < 7:
        return _hold(snapshot, policy, "head SHA is missing or invalid")
    if not snapshot.base_sha or len(snapshot.base_sha) < 7:
        return _hold(snapshot, policy, "base SHA is missing or invalid")
    if snapshot.base_ref not in policy.allowed_bases:
        return _hold(snapshot, policy, f"base branch {snapshot.base_ref!r} is outside policy")
    if snapshot.draft:
        return _hold(snapshot, policy, "pull request is draft")
    if snapshot.from_fork and not policy.allow_fork_merge:
        return _hold(snapshot, policy, "fork pull requests are observe-only by policy")

    merge_state = snapshot.mergeable_state.casefold()
    if snapshot.mergeable is not True:
        return _hold(snapshot, policy, "mergeability is not affirmatively true")
    if merge_state != "clean":
        return _hold(snapshot, policy, f"branch merge state is not clean: {merge_state or 'missing'}")

    if policy.require_checks:
        if snapshot.ci_state is CIState.FAILING:
            return _hold(snapshot, policy, "required CI is failing")
        if snapshot.ci_state is CIState.PENDING:
            return _hold(snapshot, policy, "required CI is still pending")
        if snapshot.ci_state is CIState.MISSING:
            return _hold(snapshot, policy, "required CI is missing")
        if snapshot.ci_state is not CIState.PASSING:
            return _hold(snapshot, policy, "required CI state is unknown")

    if snapshot.approvals is None:
        return _hold(snapshot, policy, "approval state is incomplete")
    if snapshot.approvals < policy.required_approvals:
        return _hold(
            snapshot,
            policy,
            f"approvals {snapshot.approvals} below required {policy.required_approvals}",
        )

    if policy.require_no_changes_requested:
        if snapshot.changes_requested is None:
            return _hold(snapshot, policy, "blocking-review state is incomplete")
        if snapshot.changes_requested:
            return _hold(snapshot, policy, f"{snapshot.changes_requested} active change request(s)")

    if policy.require_resolved_threads:
        if snapshot.unresolved_threads is None:
            return _hold(snapshot, policy, "review-thread state is unknown")
        if snapshot.unresolved_threads:
            return _hold(snapshot, policy, f"{snapshot.unresolved_threads} unresolved review thread(s)")

    if snapshot.sensitive_paths is None:
        return _hold(snapshot, policy, "changed-file trust-surface scan is incomplete")

    if snapshot.changed_files < 0 or snapshot.additions < 0 or snapshot.deletions < 0:
        return _hold(snapshot, policy, "change metrics are invalid")
    if snapshot.changed_files > policy.max_changed_files:
        return _hold(snapshot, policy, "changed-file count exceeds policy")
    if snapshot.additions + snapshot.deletions > policy.max_total_line_delta:
        return _hold(snapshot, policy, "line delta exceeds policy")

    if snapshot.sensitive_paths:
        return _evaluation(
            snapshot,
            policy,
            Decision.READY,
            (
                f"automation trust surface changed in {len(snapshot.sensitive_paths)} path(s); "
                "human merge required",
            ),
        )

    if policy.merge_when_ready:
        action = PlannedAction.make(
            snapshot,
            "merge",
            "all policy gates satisfied on immutable snapshot",
        )
        return _evaluation(
            snapshot,
            policy,
            Decision.MERGE,
            ("all policy gates satisfied",),
            (action,),
        )

    return _evaluation(snapshot, policy, Decision.READY, ("all policy gates satisfied",))
