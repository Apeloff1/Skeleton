"""Deterministic admission control for repository automation traffic.

The traffic manager is deliberately non-mutating. It observes bounded GitHub
Actions/PR/issue state and decides whether the repository has enough spare
capacity to admit one Supervisor execution. It never dispatches workers itself
and never grants build authority.

Routine authority remains one-way::

    Traffic Manager (observe/admit)
        -> Supervisor (read/plan)
        -> Secretary (admit/dispatch)
        -> Worker (mutate)

The manager collapses redundant scheduled work, protects scarce runner capacity
for CI/security gates, and provides predictable backpressure when the Actions
queue is congested.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .automation_safety import AutomationSafety, load_automation_safety
from .build_authority import APPROVED_BUILD_LABELS
from .free_model import redact_secrets

MAX_ITEMS = 100
MAX_OUTPUT_BYTES = 16_000
MAX_REPOSITORY_LENGTH = 200

ACTIVE_STATUSES = frozenset(
    {"queued", "in_progress", "waiting", "requested", "pending"}
)

CRITICAL_WORKFLOW_MARKERS = (
    "merge readiness",
    "workflow input security",
    "ci/cd",
    "repository hygiene",
    "secret scanning",
    "malware gate",
    "provenance policy",
    "arm64",
    "frontier contracts",
)

MANAGED_WORKFLOW_MARKERS = (
    "automation traffic manager",
    "repository supervisor",
    "repository secretary",
)


# Immutable owner-reviewed GitHub run identities with independent HTTP 409/403
# provider refusals. A pinned identity alone never authorizes exclusion: every
# observation must also verify that GitHub reports zero jobs for that run.
# Do not add future/unknown runs based only on age or workflow name.
PROVIDER_ORPHAN_EVIDENCE: dict[int, tuple[str, str, str, str]] = {
    37539069375: ("3048d670be32bf3720a5efcb90be20d5479060d6", "2026-10-06T22:12:20Z", "Secret scanning", "pull_request"),
    37539069791: ("3048d670be32bf3720a5efcb90be20d5479060d6", "2026-10-06T22:12:20Z", "VOL-004 Runtime Supervision Closure", "pull_request"),
    37642345734: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:06:59Z", "P2 CI Qualification Evidence", "workflow_run"),
    37642355681: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:07:13Z", "P2 CI Qualification Evidence", "workflow_run"),
    37642358530: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:07:17Z", "P2 CI Qualification Evidence", "workflow_run"),
    37642383890: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:09:04Z", "P2 CI Qualification Evidence", "workflow_run"),
    37642388873: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:10:03Z", "Automated Repair Intake", "workflow_run"),
    37642398158: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:11:13Z", "Automated Repair Intake", "workflow_run"),
    37642398159: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:11:13Z", "PR Automation Index", "workflow_run"),
    37642398161: ("cd6693a1dfc4ddccac3efb9dcb8c17d601cff656", "2026-10-07T15:11:13Z", "Auto-Merge Control Plane", "workflow_run"),
    37655496094: ("cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b", "2026-10-07T16:52:54Z", "P2 CI Qualification Evidence", "workflow_run"),
    37655496139: ("cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b", "2026-10-07T16:52:54Z", "Autonomous Build Feedback", "workflow_run"),
    37655521563: ("cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b", "2026-10-07T16:55:06Z", "Autonomous Build Feedback", "workflow_run"),
    37655522865: ("cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b", "2026-10-07T16:55:13Z", "Autonomous Build Feedback", "workflow_run"),
    37655530898: ("cfd5229a9c5f511ce8b8b9cf30dd4f4e622e045b", "2026-10-07T16:56:55Z", "P2 CI Qualification Evidence", "workflow_run"),
    38320296726: ("3293dff9480994d538a10b9e55983c65d649fb1d", "2026-10-12T23:05:35Z", "Backend Quality", "pull_request"),
    38320664775: ("eb71db3ab303d20cfcfeb1f2d67770db560d44f9", "2026-10-12T23:09:53Z", "Competitive AI Engineering Ladder", "pull_request"),
    38320664778: ("eb71db3ab303d20cfcfeb1f2d67770db560d44f9", "2026-10-12T23:09:53Z", "CI/CD", "pull_request"),
    38320665862: ("eb71db3ab303d20cfcfeb1f2d67770db560d44f9", "2026-10-12T23:09:53Z", "AI Chat Story Continuity Closure", "pull_request"),
    40470377670: ("75b9f280e90e2eff07253b0bfc281f67252d526e", "2026-10-27T07:58:28Z", "CodeQL", "dynamic"),
}


class TrafficManagerError(RuntimeError):
    """Observation, validation, or output failure."""


@dataclass(frozen=True, slots=True)
class TrafficPolicy:
    """Hard capacity and anti-thrash limits."""

    max_active_runs: int = 8
    max_queued_runs: int = 6
    max_critical_active: int = 3
    cooldown_seconds: int = 5 * 60
    maintenance_interval_seconds: int = 10 * 60
    failure_window_seconds: int = 6 * 60 * 60
    stale_queued_seconds: int = 15 * 60
    max_stale_queued_runs: int = 2
    provider_tombstone_seconds: int = 24 * 60 * 60

    def __post_init__(self) -> None:
        values = (
            self.max_active_runs,
            self.max_queued_runs,
            self.max_critical_active,
            self.cooldown_seconds,
            self.maintenance_interval_seconds,
            self.failure_window_seconds,
            self.stale_queued_seconds,
            self.max_stale_queued_runs,
            self.provider_tombstone_seconds,
        )
        # Queue capacity, admission thresholds and cooldown periods are
        # discrete bounded counts. NaN/fractional values can defeat the
        # positive-only check and make later comparisons non-deterministic.
        if any(type(value) is not int or value <= 0 for value in values):
            raise TrafficManagerError("traffic policy values must be positive integers")


@dataclass(frozen=True, slots=True)
class TrafficSnapshot:
    repository: str
    base_sha: str
    observed_at: int
    current_run_id: str
    workflow_runs: tuple[dict[str, Any], ...]
    pull_requests: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if (
            not self.repository
            or len(self.repository) > MAX_REPOSITORY_LENGTH
            or self.repository.count("/") != 1
        ):
            raise TrafficManagerError("repository must be bounded owner/name")
        owner, name = self.repository.split("/", 1)
        allowed = frozenset(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-_."
        )
        if (
            not owner
            or not name
            or owner.startswith("-")
            or owner in {".", ".."}
            or name.startswith(".")
            or name in {".", ".."}
            or any(ch not in allowed for ch in owner)
            or any(ch not in allowed for ch in name)
        ):
            raise TrafficManagerError("repository contains unsafe characters")
        if len(self.base_sha) != 40 or any(
            ch not in "0123456789abcdefABCDEF" for ch in self.base_sha
        ):
            raise TrafficManagerError("base_sha must be a 40-character hex SHA")
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, int)
            or self.observed_at <= 0
        ):
            raise TrafficManagerError("observed_at must be a positive epoch")


@dataclass(frozen=True, slots=True)
class TrafficDecision:
    admit: bool
    reason: str
    lane: str
    base_sha: str
    observed_at: int
    decision_fingerprint: str
    active_runs: int
    queued_runs: int
    critical_active: int
    managed_active: int
    recent_failures: int
    blocked_pull_requests: int
    authorized_issues: int
    seconds_since_success: int | None
    stale_queued_runs: int
    provider_tombstones: int
    oldest_queued_age_seconds: int | None
    inventory_saturated: bool
    relieve: bool
    relief_reason: str
    forced: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "admit": self.admit,
            "reason": self.reason,
            "lane": self.lane,
            "base_sha": self.base_sha,
            "observed_at": self.observed_at,
            "decision_fingerprint": self.decision_fingerprint,
            "active_runs": self.active_runs,
            "queued_runs": self.queued_runs,
            "critical_active": self.critical_active,
            "managed_active": self.managed_active,
            "recent_failures": self.recent_failures,
            "blocked_pull_requests": self.blocked_pull_requests,
            "authorized_issues": self.authorized_issues,
            "seconds_since_success": self.seconds_since_success,
            "stale_queued_runs": self.stale_queued_runs,
            "provider_tombstones": self.provider_tombstones,
            "oldest_queued_age_seconds": self.oldest_queued_age_seconds,
            "inventory_saturated": self.inventory_saturated,
            "relieve": self.relieve,
            "relief_reason": self.relief_reason,
            "forced": self.forced,
        }


def _gh_json(args: list[str]) -> list[dict[str, Any]]:
    """Run one bounded GitHub CLI read and validate its top-level shape."""
    if not args or len(args) > 20:
        raise TrafficManagerError("invalid GitHub CLI argument vector")
    if any(
        not isinstance(arg, str)
        or not arg
        or "\x00" in arg
        or len(arg) > 1_000
        for arg in args
    ):
        raise TrafficManagerError("unsafe GitHub CLI argument")
    try:
        raw = subprocess.check_output(
            ["gh", *args],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        value = json.loads(raw)
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ) as exc:
        raise TrafficManagerError("repository traffic observation failed") from exc

    if not isinstance(value, list):
        raise TrafficManagerError(
            "repository traffic observation returned invalid shape"
        )
    return [item for item in value[:MAX_ITEMS] if isinstance(item, dict)]


def _labels(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    names: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = item
        if isinstance(name, str) and name.strip():
            names.add(name.strip().casefold())
    return frozenset(names)


def _timestamp(value: object) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _run_status(run: dict[str, Any]) -> str:
    return str(run.get("status", "")).strip().casefold()


def _run_name(run: dict[str, Any]) -> str:
    return redact_secrets(str(run.get("name", ""))).strip().casefold()


def _run_id(run: dict[str, Any]) -> str:
    value = run.get("databaseId", run.get("id", ""))
    return str(value).strip()


def _is_marker_workflow(
    run: dict[str, Any], markers: Iterable[str]
) -> bool:
    name = _run_name(run)
    return any(marker in name for marker in markers)


def _visible_runs(
    snapshot: TrafficSnapshot,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        run
        for run in snapshot.workflow_runs
        if not snapshot.current_run_id
        or _run_id(run) != snapshot.current_run_id
    )


def _active_runs(
    snapshot: TrafficSnapshot,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        run
        for run in _visible_runs(snapshot)
        if _run_status(run) in ACTIVE_STATUSES
    )


def _queued_age_seconds(
    snapshot: TrafficSnapshot,
    run: dict[str, Any],
) -> int | None:
    created = _timestamp(run.get("createdAt"))
    if created is None:
        return None
    age = snapshot.observed_at - created
    return age if age >= 0 else None



def _matches_pinned_provider_orphan(run: dict[str, Any]) -> bool:
    """Exact ID, SHA, immutable timestamps, event, and name are required."""
    run_id = run.get("databaseId")
    if type(run_id) is not int:
        return False
    pinned = PROVIDER_ORPHAN_EVIDENCE.get(run_id)
    if pinned is None:
        return False
    sha, timestamp, name, event = pinned
    return (
        _run_status(run) == "queued"
        and run.get("conclusion") is None
        and run.get("headSha") == sha
        and run.get("createdAt") == timestamp
        and run.get("updatedAt") == timestamp
        and run.get("name") == name
        and run.get("event") == event
    )




def _recent_success_age(snapshot: TrafficSnapshot) -> int | None:
    ages: list[int] = []
    for run in _visible_runs(snapshot):
        if not _is_marker_workflow(
            run, ("repository supervisor",)
        ):
            continue
        if str(run.get("conclusion", "")).casefold() != "success":
            continue
        head = str(run.get("headSha", "")).strip()
        if head and head != snapshot.base_sha:
            continue
        updated = _timestamp(run.get("updatedAt"))
        if updated is None:
            updated = _timestamp(run.get("createdAt"))
        if updated is None:
            continue
        age = snapshot.observed_at - updated
        if age >= 0:
            ages.append(age)
    return min(ages) if ages else None


def _recent_failures(
    snapshot: TrafficSnapshot, policy: TrafficPolicy
) -> int:
    cutoff = snapshot.observed_at - policy.failure_window_seconds
    seen: set[tuple[str, str]] = set()
    count = 0
    for run in _visible_runs(snapshot):
        if str(run.get("conclusion", "")).casefold() != "failure":
            continue
        when = _timestamp(run.get("updatedAt"))
        if when is None:
            when = _timestamp(run.get("createdAt"))
        if when is not None and when < cutoff:
            continue
        key = (
            _run_name(run),
            str(run.get("headSha", "")).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        count += 1
    return count


def _blocked_pull_requests(snapshot: TrafficSnapshot) -> int:
    blocked = {"blocked", "dirty", "behind", "unstable"}
    return sum(
        1
        for pr in snapshot.pull_requests
        if str(
            pr.get("mergeStateStatus", "")
        ).strip().casefold() in blocked
        and not bool(pr.get("isDraft", False))
    )


def _authorized_issues(snapshot: TrafficSnapshot) -> int:
    approved = {
        label.casefold()
        for label in APPROVED_BUILD_LABELS
    }
    return sum(
        1
        for issue in snapshot.issues
        if approved.intersection(_labels(issue.get("labels")))
    )


def evaluate(
    snapshot: TrafficSnapshot,
    *,
    policy: TrafficPolicy | None = None,
    force: bool = False,
) -> TrafficDecision:
    """Return one fail-closed deterministic admission decision."""
    policy = policy or TrafficPolicy()
    observed_active = _active_runs(snapshot)
    provider_tombstones = tuple(
        run
        for run in observed_active
        if _matches_pinned_provider_orphan(run)
        and run.get("providerOrphanJobsVerified") is True
        and (
            (age := _queued_age_seconds(snapshot, run)) is not None
            and age >= policy.provider_tombstone_seconds
        )
    )
    tombstone_ids = {id(run) for run in provider_tombstones}
    active = tuple(
        run
        for run in observed_active
        if id(run) not in tombstone_ids
    )
    queued = tuple(
        run
        for run in active
        if _run_status(run) == "queued"
    )
    critical = tuple(
        run
        for run in active
        if _is_marker_workflow(run, CRITICAL_WORKFLOW_MARKERS)
    )
    managed = tuple(
        run
        for run in active
        if _is_marker_workflow(run, MANAGED_WORKFLOW_MARKERS)
    )
    queue_ages = tuple(
        age
        for run in queued
        if (age := _queued_age_seconds(snapshot, run)) is not None
    )
    stale_queued = tuple(
        run
        for run in queued
        if (
            (age := _queued_age_seconds(snapshot, run)) is not None
            and age >= policy.stale_queued_seconds
        )
    )
    oldest_queue_age = max(queue_ages) if queue_ages else None
    # Reaching the observation history limit is normal on an active repository.
    # Only fail closed when the bounded window itself is entirely occupied by
    # active work; completed history must never permanently suppress stewardship.
    inventory_saturated = len(active) >= MAX_ITEMS
    failures = _recent_failures(snapshot, policy)
    blocked = _blocked_pull_requests(snapshot)
    authorized = _authorized_issues(snapshot)
    success_age = _recent_success_age(snapshot)

    relieve = False
    relief_reason = "none"
    if inventory_saturated:
        relieve = True
        relief_reason = "run-inventory-saturated"
    elif len(stale_queued) >= policy.max_stale_queued_runs:
        relieve = True
        relief_reason = "stale-queue-pressure"
    elif len(queued) >= policy.max_queued_runs:
        relieve = True
        relief_reason = "queue-capacity-exhausted"

    decision_fingerprint = decision_identity_fingerprint(
        snapshot.repository,
        snapshot.base_sha,
        snapshot.observed_at,
    )
    common = {
        "base_sha": snapshot.base_sha.lower(),
        "observed_at": snapshot.observed_at,
        "decision_fingerprint": decision_fingerprint,
        "active_runs": len(active),
        "queued_runs": len(queued),
        "critical_active": len(critical),
        "managed_active": len(managed),
        "recent_failures": failures,
        "blocked_pull_requests": blocked,
        "authorized_issues": authorized,
        "seconds_since_success": success_age,
        "stale_queued_runs": len(stale_queued),
        "provider_tombstones": len(provider_tombstones),
        "oldest_queued_age_seconds": oldest_queue_age,
        "inventory_saturated": inventory_saturated,
        "relieve": relieve,
        "relief_reason": relief_reason,
        "forced": bool(force),
    }

    if inventory_saturated:
        return TrafficDecision(
            False,
            "run-inventory-saturated",
            "hold",
            **common,
        )
    if len(stale_queued) >= policy.max_stale_queued_runs:
        return TrafficDecision(
            False,
            "stale-queue-pressure",
            "hold",
            **common,
        )
    if len(queued) >= policy.max_queued_runs:
        return TrafficDecision(
            False,
            "queue-capacity-exhausted",
            "hold",
            **common,
        )
    if len(active) >= policy.max_active_runs:
        return TrafficDecision(
            False,
            "active-capacity-exhausted",
            "hold",
            **common,
        )
    if len(critical) >= policy.max_critical_active:
        return TrafficDecision(
            False,
            "critical-lane-contention",
            "hold",
            **common,
        )
    if managed:
        return TrafficDecision(
            False,
            "managed-automation-already-active",
            "hold",
            **common,
        )

    lane = "maintenance"
    if failures:
        lane = "repair"
    elif authorized:
        lane = "build"
    elif blocked:
        lane = "integration"

    if (
        not force
        and success_age is not None
        and success_age < policy.cooldown_seconds
    ):
        return TrafficDecision(
            False,
            "same-head-cooldown",
            "hold",
            **common,
        )

    demand = failures + blocked + authorized
    maintenance_due = (
        success_age is None
        or success_age >= policy.maintenance_interval_seconds
    )
    if not force and demand == 0 and not maintenance_due:
        return TrafficDecision(
            False,
            "no-actionable-demand",
            "hold",
            **common,
        )

    reason = "forced-admission" if force else f"{lane}-demand"
    return TrafficDecision(
        True,
        reason,
        lane,
        **common,
    )


def _observe_runs(repository: str) -> list[dict[str, Any]]:
    """Return recent history plus a complete bounded view of active statuses.

    A mixed latest-N history can hide old queued/in-progress runs after enough
    completed runs arrive. Query each active status separately and merge by
    GitHub run id so admission never mistakes hidden live work for spare
    capacity.
    """
    # GitHub CLI's 'gh run list' history query can fail under Actions queue
    # congestion, independently of the authenticated REST Actions listing.
    # The REST API is also used for status-scoped reads: give all of its rows
    # one canonical shape so status, createdAt and updatedAt retain meaning.
    projection = (
        ".workflow_runs | map({"
        "databaseId: .id, name: .name, event: .event, "
        "status: .status, conclusion: .conclusion, "
        "headBranch: .head_branch, headSha: .head_sha, "
        "createdAt: .created_at, updatedAt: .updated_at"
        "})"
    )
    history = _gh_json(
        [
            "api",
            f"/repos/{repository}/actions/runs?per_page={MAX_ITEMS}",
            "--jq",
            projection,
        ]
    )
    merged: dict[str, dict[str, Any]] = {}

    def add(run: dict[str, Any]) -> None:
        run_id = run.get("databaseId")
        created = run.get("createdAt")
        updated = run.get("updatedAt")
        status = run.get("status")
        if (
            type(run_id) is not int
            or run_id <= 0
            or not isinstance(status, str)
            or not status
            or _timestamp(created) is None
            or _timestamp(updated) is None
        ):
            raise TrafficManagerError(
                "repository traffic observation contains an invalid Actions run"
            )
        merged[str(run_id)] = run

    for run in history:
        add(run)
    # A single page is not a complete queue inventory: real congestion can
    # exceed 100 queued runs. Scan bounded pages so old queued work remains
    # visible to stale-age and relief decisions. Refuse admission if the
    # active inventory exceeds the bounded observation budget.
    for status in sorted(ACTIVE_STATUSES):
        for page in range(1, 11):
            page_runs = _gh_json(
                [
                    "api",
                    (
                        f"/repos/{repository}/actions/runs"
                        f"?status={status}&per_page={MAX_ITEMS}&page={page}"
                    ),
                    "--jq",
                    projection,
                ]
            )
            for run in page_runs:
                add(run)
            if len(page_runs) < MAX_ITEMS:
                break
        else:
            raise TrafficManagerError(
                "repository traffic observation exceeded bounded active page limit"
            )
    # Independently recheck every pinned candidate with GitHub's jobs API.
    # Any API failure, unexpected count, or missing row leaves the queued run
    # visible in capacity/admission metrics (fail closed, not a false pass).
    for run in merged.values():
        if not _matches_pinned_provider_orphan(run):
            continue
        run_id = run["databaseId"]
        try:
            jobs = _gh_json([
                "api",
                f"/repos/{repository}/actions/runs/{run_id}/jobs?per_page=1",
                "--jq",
                "[{totalCount: .total_count}]",
            ])
        except TrafficManagerError:
            continue
        if (
            len(jobs) == 1
            and type(jobs[0].get("totalCount")) is int
            and jobs[0]["totalCount"] == 0
        ):
            run["providerOrphanJobsVerified"] = True
    return list(merged.values())


def observe(
    repository: str,
    base_sha: str,
    *,
    current_run_id: str = "",
    now: int | None = None,
) -> TrafficSnapshot:
    """Capture a bounded repository traffic snapshot."""
    runs = _observe_runs(repository)
    prs = _gh_json(
        [
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--limit",
            "40",
            "--json",
            (
                "number,title,isDraft,mergeStateStatus,"
                "headRefName,updatedAt"
            ),
        ]
    )
    issues = _gh_json(
        [
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--limit",
            "40",
            "--json",
            "number,title,labels,updatedAt",
        ]
    )
    return TrafficSnapshot(
        repository=repository,
        base_sha=base_sha,
        observed_at=int(time.time()) if now is None else now,
        current_run_id=current_run_id,
        workflow_runs=tuple(runs),
        pull_requests=tuple(prs),
        issues=tuple(issues),
    )


def decision_identity_fingerprint(
    repository: str,
    base_sha: str,
    observed_at: int,
) -> str:
    """Return the canonical digest used to bind admission evidence."""
    snapshot = TrafficSnapshot(
        repository=repository,
        base_sha=base_sha,
        observed_at=observed_at,
        current_run_id="",
        workflow_runs=(),
        pull_requests=(),
        issues=(),
    )
    payload = json.dumps(
        {
            "repository": snapshot.repository,
            "base_sha": snapshot.base_sha.lower(),
            "observed_at": snapshot.observed_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bool_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().casefold()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise TrafficManagerError(f"{name} must be a boolean")


def emit_github_output(
    decision: TrafficDecision, output_path: str
) -> None:
    if not output_path or "\x00" in output_path:
        raise TrafficManagerError("missing GitHub output path")
    path = Path(output_path)
    if not path.is_absolute():
        raise TrafficManagerError(
            "GitHub output path must be absolute"
        )

    payload = json.dumps(
        decision.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise TrafficManagerError(
            "traffic decision output exceeds byte budget"
        )

    oldest_queued_age = (
        ""
        if decision.oldest_queued_age_seconds is None
        else str(decision.oldest_queued_age_seconds)
    )
    inventory_saturated = (
        "true" if decision.inventory_saturated else "false"
    )
    relieve = "true" if decision.relieve else "false"
    lines = (
        f"admit={'true' if decision.admit else 'false'}\n"
        f"reason={decision.reason}\n"
        f"lane={decision.lane}\n"
        f"base_sha={decision.base_sha}\n"
        f"observed_at={decision.observed_at}\n"
        f"decision_fingerprint={decision.decision_fingerprint}\n"
        f"active_runs={decision.active_runs}\n"
        f"queued_runs={decision.queued_runs}\n"
        f"critical_active={decision.critical_active}\n"
        f"stale_queued_runs={decision.stale_queued_runs}\n"
        f"provider_tombstones={decision.provider_tombstones}\n"
        f"oldest_queued_age_seconds={oldest_queued_age}\n"
        f"inventory_saturated={inventory_saturated}\n"
        f"relieve={relieve}\n"
        f"relief_reason={decision.relief_reason}\n"
        f"decision_json={payload}\n"
    )
    with path.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(lines)


def write_step_summary(decision: TrafficDecision) -> None:
    summary_path = os.environ.get(
        "GITHUB_STEP_SUMMARY", ""
    ).strip()
    if not summary_path or "\x00" in summary_path:
        return
    path = Path(summary_path)
    if not path.is_absolute():
        return
    rows = [
        "# Automation traffic manager",
        "",
        (
            "- Decision: **"
            + ("ADMIT" if decision.admit else "HOLD")
            + "**"
        ),
        f"- Reason: `{decision.reason}`",
        f"- Lane: `{decision.lane}`",
        f"- Admitted base SHA: `{decision.base_sha}`",
        f"- Observation epoch: `{decision.observed_at}`",
        f"- Decision fingerprint: `{decision.decision_fingerprint}`",
        (
            "- Active / queued runs: "
            f"`{decision.active_runs}` / "
            f"`{decision.queued_runs}`"
        ),
        (
            "- Critical active runs: "
            f"`{decision.critical_active}`"
        ),
        (
            "- Stale queued runs: "
            f"`{decision.stale_queued_runs}`"
        ),
        (
            "- Verified provider orphans (pinned ID, SHA, zero jobs, 24h+): "
            f"`{decision.provider_tombstones}`"
        ),
        (
            "- Oldest queued age (seconds): "
            f"`{decision.oldest_queued_age_seconds}`"
        ),
        (
            "- Run inventory saturated: "
            f"`{decision.inventory_saturated}`"
        ),
        (
            "- Relief required: "
            f"`{decision.relieve}` ({decision.relief_reason})"
        ),
        (
            "- Managed automation active: "
            f"`{decision.managed_active}`"
        ),
        (
            "- Recent failures: "
            f"`{decision.recent_failures}`"
        ),
        (
            "- Blocked pull requests: "
            f"`{decision.blocked_pull_requests}`"
        ),
        (
            "- Authorized issues: "
            f"`{decision.authorized_issues}`"
        ),
    ]
    path.write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )



def enforce_operator_safety(
    decision: TrafficDecision, safety: AutomationSafety
) -> TrafficDecision:
    """Operator holds fence both new admissions and bounded Actions relief.

    Preserve measured repository pressure and the original immutable decision
    fingerprint so the hold cannot fabricate a healthy queue snapshot.
    """
    if not isinstance(decision, TrafficDecision) or not isinstance(safety, AutomationSafety):
        raise TrafficManagerError("operator safety requires typed admission records")
    if not safety.blocked:
        return decision
    return replace(
        decision,
        admit=False,
        relieve=False,
        reason="operator-" + safety.status,
        lane="hold",
        relief_reason="operator-hold",
        forced=False,
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--emit-github-output",
        default="",
    )
    args = parser.parse_args()

    repository = os.environ.get(
        "GITHUB_REPOSITORY", ""
    ).strip()
    base_sha = os.environ.get(
        "GITHUB_SHA", ""
    ).strip()
    run_id = os.environ.get(
        "GITHUB_RUN_ID", ""
    ).strip()
    force = _bool_env("TRAFFIC_FORCE")
    # Fail before queue observation if an operator safety control is malformed.
    # A force flag can never override a pause or quarantine.
    safety = load_automation_safety()

    snapshot = observe(
        repository,
        base_sha,
        current_run_id=run_id,
    )
    decision = evaluate(
        snapshot,
        force=force,
    )
    decision = enforce_operator_safety(decision, safety)

    print(
        json.dumps(
            decision.as_dict(),
            sort_keys=True,
        )
    )
    if args.emit_github_output:
        emit_github_output(
            decision,
            args.emit_github_output,
        )
    write_step_summary(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
