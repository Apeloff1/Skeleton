"""Health aggregation for worker registries, heartbeats, supervision, and queue state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.queue import ShellWorkQueue
from skeleton.shells.worker_heartbeat import HeartbeatRegistry, WorkerLiveness
from skeleton.shells.worker_identity import WorkerRegistry
from skeleton.shells.worker_supervisor import SupervisionState, WorkerSupervisor


class WorkerHealthSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class WorkerHealthFinding:
    severity: WorkerHealthSeverity
    code: str
    message: str
    worker_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "worker_id": self.worker_id,
        }


@dataclass(frozen=True)
class WorkerHealthReport:
    findings: tuple[WorkerHealthFinding, ...]
    registered: int
    enabled: int
    healthy: int
    late: int
    stale: int
    queued: int
    claimed: int

    @property
    def critical(self) -> int:
        return sum(item.severity is WorkerHealthSeverity.CRITICAL for item in self.findings)

    @property
    def warnings(self) -> int:
        return sum(item.severity is WorkerHealthSeverity.WARNING for item in self.findings)

    @property
    def ok(self) -> bool:
        return self.critical == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "critical": self.critical,
            "warnings": self.warnings,
            "registered": self.registered,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "late": self.late,
            "stale": self.stale,
            "queued": self.queued,
            "claimed": self.claimed,
            "findings": [item.to_dict() for item in self.findings],
        }


class WorkerHealthInspector:
    def __init__(
        self,
        *,
        workers: WorkerRegistry,
        heartbeats: HeartbeatRegistry,
        queue: ShellWorkQueue,
        supervisor: WorkerSupervisor | None = None,
        queue_warning: int = 500,
        queue_critical: int = 2000,
    ) -> None:
        if queue_warning < 0 or queue_critical <= queue_warning:
            raise ValueError("invalid queue health thresholds")
        self.workers = workers
        self.heartbeats = heartbeats
        self.queue = queue
        self.supervisor = supervisor
        self.queue_warning = queue_warning
        self.queue_critical = queue_critical

    def inspect(self) -> WorkerHealthReport:
        registrations = self.workers.snapshot().registrations
        findings: list[WorkerHealthFinding] = []
        healthy = late = stale = 0

        for registration in registrations:
            identity = registration.identity
            view = self.heartbeats.liveness(identity)
            if view.liveness is WorkerLiveness.HEALTHY:
                healthy += 1
            elif view.liveness is WorkerLiveness.LATE:
                late += 1
                findings.append(
                    WorkerHealthFinding(
                        WorkerHealthSeverity.WARNING,
                        "heartbeat_late",
                        "worker heartbeat is late",
                        identity.worker_id,
                    )
                )
            elif view.liveness is WorkerLiveness.STALE:
                stale += 1
                findings.append(
                    WorkerHealthFinding(
                        WorkerHealthSeverity.CRITICAL,
                        "heartbeat_stale",
                        "worker heartbeat is stale",
                        identity.worker_id,
                    )
                )
            else:
                findings.append(
                    WorkerHealthFinding(
                        WorkerHealthSeverity.WARNING,
                        "heartbeat_unknown",
                        "worker has no heartbeat",
                        identity.worker_id,
                    )
                )
            if not registration.enabled:
                findings.append(
                    WorkerHealthFinding(
                        WorkerHealthSeverity.INFO,
                        "worker_disabled",
                        "worker registration is disabled",
                        identity.worker_id,
                    )
                )
            if self.supervisor is not None:
                supervised = self.supervisor.get(identity.worker_id)
                if supervised is not None and supervised.state is SupervisionState.QUARANTINED:
                    findings.append(
                        WorkerHealthFinding(
                            WorkerHealthSeverity.CRITICAL,
                            "worker_quarantined",
                            "worker is quarantined by supervisor",
                            identity.worker_id,
                        )
                    )

        counts = self.queue.counts()
        queued = counts.get("queued", 0)
        claimed = counts.get("claimed", 0)
        if queued >= self.queue_critical:
            findings.append(
                WorkerHealthFinding(
                    WorkerHealthSeverity.CRITICAL,
                    "queue_critical",
                    "worker queue exceeds critical watermark",
                )
            )
        elif queued >= self.queue_warning:
            findings.append(
                WorkerHealthFinding(
                    WorkerHealthSeverity.WARNING,
                    "queue_high",
                    "worker queue exceeds warning watermark",
                )
            )
        if registrations and healthy == 0:
            findings.append(
                WorkerHealthFinding(
                    WorkerHealthSeverity.CRITICAL,
                    "no_healthy_workers",
                    "no registered worker has a healthy heartbeat",
                )
            )

        return WorkerHealthReport(
            findings=tuple(findings),
            registered=len(registrations),
            enabled=sum(item.enabled for item in registrations),
            healthy=healthy,
            late=late,
            stale=stale,
            queued=queued,
            claimed=claimed,
        )
