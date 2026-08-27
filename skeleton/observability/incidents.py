"""Incident tracking — from alert firing to resolution.

AlertingEngine says something is wrong; incidents assign ownership.
Each alert transition opens an Incident; a responder acknowledges it;
resolving closes it. Dashboards list open incidents by severity.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError


class IncidentError(KernelError):
    code = "OBS.INCIDENT"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


@dataclass
class Incident:
    incident_id: str
    alert_rule: str
    severity: str
    status: IncidentStatus = IncidentStatus.OPEN
    assignee: Optional[str] = None
    opened_at: float = 0.0
    resolved_at: Optional[float] = None
    notes: List[str] = field(default_factory=list)


class IncidentTracker:
    """Lifecycle register for incidents opened by alerts."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.monotonic
        self._incidents: Dict[str, Incident] = {}
        self._counter = 0

    def open(self, *, alert_rule: str, severity: str) -> Incident:
        self._counter += 1
        incident = Incident(
            incident_id=f"INC-{self._counter}",
            alert_rule=alert_rule,
            severity=severity,
            opened_at=self._now(),
        )
        self._incidents[incident.incident_id] = incident
        return incident

    def acknowledge(self, incident_id: str, assignee: str) -> Incident:
        incident = self._require(incident_id)
        incident.status = IncidentStatus.ACKNOWLEDGED
        incident.assignee = assignee
        return incident

    def resolve(self, incident_id: str, *, note: str = "") -> Incident:
        incident = self._require(incident_id)
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = self._now()
        if note:
            incident.notes.append(note)
        return incident

    def open_incidents(self) -> Tuple[Incident, ...]:
        return tuple(
            inc
            for inc in self._incidents.values()
            if inc.status is not IncidentStatus.RESOLVED
        )

    def _require(self, incident_id: str) -> Incident:
        incident = self._incidents.get(incident_id)
        if incident is None:
            raise IncidentError("unknown incident", context={"incident": incident_id})
        return incident
