from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping

from .models import PlanItem, WorkerState
from .plan_store import InMemoryPlanStore
from .squads import SQUAD_ROLES


class IntegritySeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class IntegrityFinding:
    code: str
    severity: IntegritySeverity
    subject: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class SupervisorIntegrityReport:
    checked_at: datetime
    findings: tuple[IntegrityFinding, ...]

    @property
    def critical_count(self) -> int:
        return sum(f.severity is IntegritySeverity.CRITICAL for f in self.findings)

    @property
    def error_count(self) -> int:
        return sum(f.severity is IntegritySeverity.ERROR for f in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(f.severity is IntegritySeverity.WARNING for f in self.findings)

    @property
    def healthy(self) -> bool:
        return self.critical_count == 0 and self.error_count == 0

    @property
    def digest(self) -> str:
        payload = {
            "checked_at": self.checked_at.astimezone(timezone.utc).isoformat(),
            "findings": [finding.as_dict() for finding in self.findings],
            "version": 1,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at.astimezone(timezone.utc).isoformat(),
            "healthy": self.healthy,
            "critical": self.critical_count,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "digest": self.digest,
            "findings": [finding.as_dict() for finding in self.findings],
        }


class SupervisorIntegrityError(RuntimeError):
    def __init__(self, report: SupervisorIntegrityReport) -> None:
        self.report = report
        codes = ", ".join(f.code for f in report.findings if f.severity is IntegritySeverity.CRITICAL)
        super().__init__(f"critical shift-supervisor integrity failure: {codes or 'unknown'}")


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _finding(
    findings: list[IntegrityFinding],
    code: str,
    severity: IntegritySeverity,
    subject: str,
    detail: str,
) -> None:
    findings.append(
        IntegrityFinding(
            code=code,
            severity=severity,
            subject=str(subject)[:300],
            detail=str(detail)[:1000],
        )
    )


def _dependency_findings(
    items: Mapping[str, PlanItem],
    findings: list[IntegrityFinding],
) -> None:
    graph: dict[str, tuple[str, ...]] = {}
    for item in items.values():
        deps = tuple(str(dep).strip() for dep in item.dependencies if str(dep).strip())
        if len(set(deps)) != len(deps):
            _finding(
                findings,
                "duplicate-dependency",
                IntegritySeverity.ERROR,
                item.id,
                "plan item contains duplicate dependencies",
            )
        if item.id in deps:
            _finding(
                findings,
                "self-dependency",
                IntegritySeverity.CRITICAL,
                item.id,
                "plan item depends on itself",
            )
        missing = sorted(dep for dep in deps if dep not in items)
        if missing:
            _finding(
                findings,
                "missing-dependency",
                IntegritySeverity.ERROR,
                item.id,
                f"missing dependencies: {missing[:12]!r}",
            )
        graph[item.id] = tuple(dep for dep in deps if dep in items)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item_id: str, trail: tuple[str, ...]) -> None:
        if item_id in visited:
            return
        if item_id in visiting:
            cycle = trail + (item_id,)
            _finding(
                findings,
                "dependency-cycle",
                IntegritySeverity.CRITICAL,
                item_id,
                " -> ".join(cycle[-16:]),
            )
            return
        visiting.add(item_id)
        for dep in graph.get(item_id, ()):
            visit(dep, trail + (item_id,))
        visiting.discard(item_id)
        visited.add(item_id)

    for item_id in sorted(graph):
        visit(item_id, ())


def _lease_members(item: PlanItem) -> tuple[dict[str, str] | None, datetime | None]:
    raw = item.metadata.get("squad_lease")
    if not isinstance(raw, Mapping):
        return None, None
    members_raw = raw.get("members")
    if not isinstance(members_raw, Mapping):
        return None, None
    members = {str(role): str(worker_id) for role, worker_id in members_raw.items()}
    expires = _parse_time(raw.get("expires_at"))
    return members, expires


def audit_store(
    store: InMemoryPlanStore,
    *,
    now: datetime | None = None,
    heartbeat_stale_after: timedelta = timedelta(minutes=20),
) -> SupervisorIntegrityReport:
    """Audit canonical Supervisor -> squad -> worker ownership without mutation."""
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    items = {item.id: item for item in store.snapshot_items()}
    workers = {worker.worker_id: worker for worker in store.snapshot_workers()}
    findings: list[IntegrityFinding] = []

    _dependency_findings(items, findings)

    active_domains: dict[str, str] = {}
    squad_membership: dict[str, tuple[str, str]] = {}

    for item in items.values():
        active = item.status in {"assigned", "working", "blocked"}
        owner = str(item.owner or "")

        if item.status == "queued" and item.owner is not None:
            _finding(
                findings,
                "queued-item-owned",
                IntegritySeverity.CRITICAL,
                item.id,
                f"queued item unexpectedly owned by {owner!r}",
            )
        if not active:
            continue
        if not owner:
            _finding(
                findings,
                "active-item-unowned",
                IntegritySeverity.CRITICAL,
                item.id,
                "active plan item has no owner",
            )
            continue

        if owner.startswith("squad-"):
            members, expires = _lease_members(item)
            if members is None:
                _finding(
                    findings,
                    "active-squad-lease-missing",
                    IntegritySeverity.CRITICAL,
                    item.id,
                    "active squad item has no parseable lease membership",
                )
                continue
            if set(members) != set(SQUAD_ROLES):
                _finding(
                    findings,
                    "squad-role-set-invalid",
                    IntegritySeverity.CRITICAL,
                    item.id,
                    f"lease roles are {sorted(members)!r}",
                )
            if len(set(members.values())) != len(members):
                _finding(
                    findings,
                    "squad-worker-reuse",
                    IntegritySeverity.CRITICAL,
                    item.id,
                    "squad lease reuses a worker across roles",
                )
            raw = item.metadata.get("squad_lease")
            if isinstance(raw, Mapping):
                if str(raw.get("squad_id", "")) != owner:
                    _finding(findings, "squad-owner-mismatch", IntegritySeverity.CRITICAL, item.id, "lease squad_id differs from item owner")
                if str(raw.get("task_id", "")) != item.id:
                    _finding(findings, "squad-task-mismatch", IntegritySeverity.CRITICAL, item.id, "lease task_id differs from plan item")
                if str(raw.get("team", "")) != item.target_team:
                    _finding(findings, "squad-team-mismatch", IntegritySeverity.CRITICAL, item.id, "lease team differs from plan target team")
                if not str(raw.get("plan_generation", "")).strip():
                    _finding(findings, "squad-generation-missing", IntegritySeverity.CRITICAL, item.id, "lease has no plan generation")
            if expires is None:
                _finding(
                    findings,
                    "squad-expiry-invalid",
                    IntegritySeverity.CRITICAL,
                    item.id,
                    "active squad lease has no valid expiry",
                )
            elif expires <= moment:
                _finding(
                    findings,
                    "squad-expired",
                    IntegritySeverity.ERROR,
                    item.id,
                    f"lease expired at {expires.isoformat()}",
                )

            domain = str(item.metadata.get("conflict_domain", "")).strip()
            if domain:
                prior = active_domains.get(domain)
                if prior is not None and prior != item.id:
                    _finding(
                        findings,
                        "conflict-domain-collision",
                        IntegritySeverity.CRITICAL,
                        item.id,
                        f"conflict domain {domain!r} already active on {prior!r}",
                    )
                active_domains[domain] = item.id

            for role, worker_id in members.items():
                previous = squad_membership.get(worker_id)
                if previous is not None and previous[0] != item.id:
                    _finding(
                        findings,
                        "worker-multiple-squads",
                        IntegritySeverity.CRITICAL,
                        worker_id,
                        f"worker belongs to {previous[0]!r} and {item.id!r}",
                    )
                squad_membership[worker_id] = (item.id, role)
                worker = workers.get(worker_id)
                if worker is None:
                    _finding(
                        findings,
                        "squad-worker-missing",
                        IntegritySeverity.CRITICAL,
                        item.id,
                        f"{role} worker {worker_id!r} does not exist",
                    )
                    continue
                if worker.current_task_id != item.id:
                    _finding(
                        findings,
                        "squad-worker-task-mismatch",
                        IntegritySeverity.ERROR,
                        worker_id,
                        f"worker task {worker.current_task_id!r} != {item.id!r}",
                    )
                if str(worker.metadata.get("current_squad_id", "")) != owner:
                    _finding(
                        findings,
                        "squad-worker-owner-mismatch",
                        IntegritySeverity.ERROR,
                        worker_id,
                        "worker current_squad_id differs from active lease",
                    )
                if str(worker.metadata.get("current_squad_role", "")) != role:
                    _finding(
                        findings,
                        "squad-worker-role-mismatch",
                        IntegritySeverity.ERROR,
                        worker_id,
                        f"worker role metadata does not match {role!r}",
                    )
        else:
            worker = workers.get(owner)
            if worker is None:
                _finding(
                    findings,
                    "direct-owner-missing",
                    IntegritySeverity.CRITICAL,
                    item.id,
                    f"direct owner {owner!r} does not exist",
                )
            elif worker.current_task_id != item.id:
                _finding(
                    findings,
                    "direct-owner-task-mismatch",
                    IntegritySeverity.CRITICAL,
                    item.id,
                    f"owner points at {worker.current_task_id!r}",
                )

    for worker in workers.values():
        task_id = worker.current_task_id
        if worker.status == "working" and task_id is None:
            _finding(
                findings,
                "working-worker-unassigned",
                IntegritySeverity.ERROR,
                worker.worker_id,
                "worker reports working without canonical task ownership",
            )
        if task_id is not None and worker.status in {"idle", "offline"}:
            _finding(
                findings,
                "assigned-worker-inactive",
                IntegritySeverity.CRITICAL,
                worker.worker_id,
                f"{worker.status} worker retains task {task_id!r}",
            )
        if task_id is not None:
            item = items.get(task_id)
            if item is None:
                _finding(
                    findings,
                    "worker-task-missing",
                    IntegritySeverity.CRITICAL,
                    worker.worker_id,
                    f"worker references missing task {task_id!r}",
                )
            elif str(item.owner or "").startswith("squad-"):
                membership = squad_membership.get(worker.worker_id)
                if membership is None or membership[0] != task_id:
                    _finding(
                        findings,
                        "worker-squad-membership-missing",
                        IntegritySeverity.CRITICAL,
                        worker.worker_id,
                        "worker references squad task without lease membership",
                    )
            elif item.owner != worker.worker_id:
                _finding(
                    findings,
                    "worker-owner-mismatch",
                    IntegritySeverity.CRITICAL,
                    worker.worker_id,
                    f"task owner is {item.owner!r}",
                )

        if worker.status != "offline":
            heartbeat = worker.last_heartbeat_at
            if heartbeat is None:
                _finding(
                    findings,
                    "active-worker-heartbeat-missing",
                    IntegritySeverity.WARNING if task_id is None else IntegritySeverity.ERROR,
                    worker.worker_id,
                    "active worker has no heartbeat timestamp",
                )
            else:
                age = moment - heartbeat.astimezone(timezone.utc)
                if age > heartbeat_stale_after:
                    _finding(
                        findings,
                        "active-worker-heartbeat-stale",
                        IntegritySeverity.ERROR,
                        worker.worker_id,
                        f"last heartbeat is {int(age.total_seconds())} seconds old",
                    )

    ordered = tuple(
        sorted(
            findings,
            key=lambda f: (f.severity.value, f.code, f.subject, f.detail),
        )
    )
    return SupervisorIntegrityReport(moment, ordered)


def require_no_critical_integrity(report: SupervisorIntegrityReport) -> None:
    if report.critical_count:
        raise SupervisorIntegrityError(report)
