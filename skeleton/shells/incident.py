"""Incident-state capture for shell-plane failures and operator handoff."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping


class IncidentSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IncidentState(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    MITIGATED = "mitigated"
    CLOSED = "closed"


@dataclass(frozen=True)
class ShellIncident:
    incident_id: str
    severity: IncidentSeverity
    state: IncidentState
    summary: str
    opened_at: float
    correlation_id: str = ""
    command: str = ""
    evidence: Mapping[str, object] = field(default_factory=dict)
    acknowledged_by: str = ""
    closed_at: float | None = None

    def __post_init__(self) -> None:
        if not self.incident_id or len(self.incident_id) > 128:
            raise ValueError("invalid incident_id")
        if not isinstance(self.severity, IncidentSeverity):
            object.__setattr__(self, "severity", IncidentSeverity(self.severity))
        if not isinstance(self.state, IncidentState):
            object.__setattr__(self, "state", IncidentState(self.state))
        if not self.summary or len(self.summary) > 2048:
            raise ValueError("invalid incident summary")
        evidence = dict(self.evidence)
        if len(evidence) > 128:
            raise ValueError("too many incident evidence fields")
        try:
            json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError("incident evidence must be serializable") from exc
        object.__setattr__(self, "evidence", MappingProxyType(evidence))

    def to_dict(self) -> dict[str, object]:
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.value,
            "state": self.state.value,
            "summary": self.summary,
            "opened_at": self.opened_at,
            "correlation_id": self.correlation_id,
            "command": self.command,
            "evidence": dict(self.evidence),
            "acknowledged_by": self.acknowledged_by,
            "closed_at": self.closed_at,
        }


class IncidentRegistry:
    def __init__(
        self,
        *,
        max_incidents: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_incidents <= 0:
            raise ValueError("max_incidents must be positive")
        self.max_incidents = max_incidents
        self._clock = clock
        self._items: dict[str, ShellIncident] = {}
        self._serial = 0
        self._lock = threading.RLock()

    def open(
        self,
        severity: IncidentSeverity,
        summary: str,
        *,
        correlation_id: str = "",
        command: str = "",
        evidence: Mapping[str, object] | None = None,
    ) -> ShellIncident:
        with self._lock:
            if len(self._items) >= self.max_incidents:
                raise RuntimeError("incident registry capacity exhausted")
            self._serial += 1
            now = self._clock()
            raw = f"{severity}:{summary}:{correlation_id}:{command}:{self._serial}:{now}"
            incident_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
            incident = ShellIncident(
                incident_id,
                IncidentSeverity(severity),
                IncidentState.OPEN,
                summary,
                now,
                correlation_id,
                command,
                evidence or {},
            )
            self._items[incident_id] = incident
            return incident

    def _replace(
        self,
        current: ShellIncident,
        *,
        state: IncidentState,
        acknowledged_by: str | None = None,
        closed_at: float | None = None,
    ) -> ShellIncident:
        updated = ShellIncident(
            current.incident_id,
            current.severity,
            state,
            current.summary,
            current.opened_at,
            current.correlation_id,
            current.command,
            current.evidence,
            current.acknowledged_by if acknowledged_by is None else acknowledged_by,
            closed_at,
        )
        self._items[current.incident_id] = updated
        return updated

    def acknowledge(self, incident_id: str, actor: str) -> ShellIncident:
        if not actor or len(actor) > 256:
            raise ValueError("invalid incident actor")
        with self._lock:
            current = self._items[incident_id]
            if current.state is not IncidentState.OPEN:
                raise RuntimeError("incident cannot be acknowledged from current state")
            return self._replace(current, state=IncidentState.ACKNOWLEDGED, acknowledged_by=actor)

    def mitigate(self, incident_id: str) -> ShellIncident:
        with self._lock:
            current = self._items[incident_id]
            if current.state not in {IncidentState.OPEN, IncidentState.ACKNOWLEDGED}:
                raise RuntimeError("incident cannot be mitigated from current state")
            return self._replace(current, state=IncidentState.MITIGATED)

    def close(self, incident_id: str) -> ShellIncident:
        with self._lock:
            current = self._items[incident_id]
            if current.state not in {IncidentState.ACKNOWLEDGED, IncidentState.MITIGATED}:
                raise RuntimeError("incident cannot be closed from current state")
            return self._replace(current, state=IncidentState.CLOSED, closed_at=self._clock())

    def get(self, incident_id: str) -> ShellIncident:
        with self._lock:
            return self._items[incident_id]

    def open_incidents(self) -> tuple[ShellIncident, ...]:
        with self._lock:
            return tuple(
                item
                for item in sorted(self._items.values(), key=lambda value: value.opened_at)
                if item.state is not IncidentState.CLOSED
            )

    def snapshot(self) -> tuple[ShellIncident, ...]:
        with self._lock:
            return tuple(sorted(self._items.values(), key=lambda value: value.opened_at))
