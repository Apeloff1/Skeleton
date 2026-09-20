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
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .build_authority import APPROVED_BUILD_LABELS
from .free_model import redact_secrets

MAX_ITEMS = 100
MAX_OUTPUT_BYTES = 16_000

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


class TrafficManagerError(RuntimeError):
    """Observation, validation, or output failure."""


@dataclass(frozen=True, slots=True)
class TrafficPolicy:
    """Hard capacity and anti-thrash limits."""

    max_active_runs: int = 8
    max_queued_runs: int = 6
    max_critical_active: int = 3
    cooldown_seconds: int = 30 * 60
    maintenance_interval_seconds: int = 2 * 60 * 60
    failure_window_seconds: int = 6 * 60 * 60

    def __post_init__(self) -> None:
        values = (
            self.max_active_runs,
            self.max_queued_runs,
            self.max_critical_active,
            self.cooldown_seconds,
            self.maintenance_interval_seconds,
            self.failure_window_seconds,
        )
        if any(isinstance(value, bool) or value <= 0 for value in values):
            raise TrafficManagerError("traffic policy values must be positive")


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
        if not self.repository or self.repository.count("/") != 1:
            raise TrafficManagerError("repository must be owner/name")
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
    active_runs: int
    queued_runs: int
    critical_active: int
    managed_active: int
    recent_failures: int
    blocked_pull_requests: int
    authorized_issues: int
    seconds_since_success: int | None
    forced: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "admit": self.admit,
            "reason": self.reason,
            "lane": self.lane,
            "active_runs": self.active_runs,
            "queued_runs": self.queued_runs,
            "critical_active": self.critical_active,
            "managed_active": self.managed_active,
            "recent_failures": self.recent_failures,
            "blocked_pull_requests": self.blocked_pull_requests,
            "authorized_issues": self.authorized_issues,
            "seconds_since_success": self.seconds_since_success,
            "forced": self.forced,
        }


def _gh_json(args: list[str]) -> list[dict[str, Any]]:
    """Run one bounded GitHub CLI read and validate its top-level shape."""
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
    active = _active_runs(snapshot)
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
    failures = _recent_failures(snapshot, policy)
    blocked = _blocked_pull_requests(snapshot)
    authorized = _authorized_issues(snapshot)
    success_age = _recent_success_age(snapshot)

    common = {
        "active_runs": len(active),
        "queued_runs": len(queued),
        "critical_active": len(critical),
        "managed_active": len(managed),
        "recent_failures": failures,
        "blocked_pull_requests": blocked,
        "authorized_issues": authorized,
        "seconds_since_success": success_age,
        "forced": bool(force),
    }

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


def observe(
    repository: str,
    base_sha: str,
    *,
    current_run_id: str = "",
    now: int | None = None,
) -> TrafficSnapshot:
    """Capture a bounded repository traffic snapshot."""
    runs = _gh_json(
        [
            "run",
            "list",
            "--repo",
            repository,
            "--limit",
            str(MAX_ITEMS),
            "--json",
            (
                "databaseId,name,event,status,conclusion,"
                "headBranch,headSha,createdAt,updatedAt"
            ),
        ]
    )
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

    lines = (
        f"admit={'true' if decision.admit else 'false'}\n"
        f"reason={decision.reason}\n"
        f"lane={decision.lane}\n"
        f"active_runs={decision.active_runs}\n"
        f"queued_runs={decision.queued_runs}\n"
        f"critical_active={decision.critical_active}\n"
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

    snapshot = observe(
        repository,
        base_sha,
        current_run_id=run_id,
    )
    decision = evaluate(
        snapshot,
        force=force,
    )

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
