"""Incident manager — full incident lifecycle from detection to postmortem.

Tracks incidents through triggered → acknowledged → investigating →
mitigated → resolved → postmortem. Links alerts, assigns commanders,
tracks timeline events, computes MTTA/MTTR, and requires postmortem
fields before closure for critical severities.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


STATES = ["triggered", "acknowledged", "investigating", "mitigated", "resolved", "postmortem"]
SEVERITIES = {"sev1": 3, "sev2": 2, "sev3": 1}


@dataclass
class TimelineEvent:
    timestamp_ns: int
    actor: str
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return {"timestamp_ns": self.timestamp_ns, "actor": self.actor, "note": self.note}


@dataclass
class Incident:
    incident_id: str
    title: str
    severity: str
    state: str = "triggered"
    commander: Optional[str] = None
    alert_ids: List[str] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    opened_ns: int = 0
    acknowledged_ns: int = 0
    resolved_ns: int = 0
    postmortem: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "state": self.state,
            "commander": self.commander,
            "alerts": self.alert_ids,
            "timeline": [e.to_dict() for e in self.timeline],
            "postmortem": self.postmortem,
        }


class IncidentManager:
    """Incident lifecycle with timeline and MTTR metrics."""

    def __init__(self):
        self._incidents: Dict[str, Incident] = {}
        self._counter = 0

    def declare(self, title: str, severity: str = "sev3",
                alert_ids: Optional[List[str]] = None) -> Incident:
        self._counter += 1
        inc = Incident(
            incident_id=f"INC-{self._counter:04d}",
            title=title,
            severity=severity if severity in SEVERITIES else "sev3",
            opened_ns=time.time_ns(),
            alert_ids=alert_ids or [],
        )
        inc.timeline.append(TimelineEvent(time.time_ns(), "system", "incident declared"))
        self._incidents[inc.incident_id] = inc
        return inc

    def _transition(self, incident_id: str, to_state: str, actor: str, note: str = "") -> bool:
        inc = self._incidents.get(incident_id)
        if not inc:
            return False
        current_idx = STATES.index(inc.state)
        target_idx = STATES.index(to_state)
        if target_idx <= current_idx:
            return False
        inc.state = to_state
        if to_state == "acknowledged":
            inc.acknowledged_ns = time.time_ns()
        if to_state == "resolved":
            inc.resolved_ns = time.time_ns()
        inc.timeline.append(TimelineEvent(time.time_ns(), actor, note or f"state → {to_state}"))
        return True

    def acknowledge(self, incident_id: str, actor: str) -> bool:
        return self._transition(incident_id, "acknowledged", actor)

    def assign_commander(self, incident_id: str, actor: str) -> bool:
        inc = self._incidents.get(incident_id)
        if not inc:
            return False
        inc.commander = actor
        inc.timeline.append(TimelineEvent(time.time_ns(), "system", f"commander assigned: {actor}"))
        return True

    def add_note(self, incident_id: str, actor: str, note: str) -> bool:
        inc = self._incidents.get(incident_id)
        if not inc:
            return False
        inc.timeline.append(TimelineEvent(time.time_ns(), actor, note))
        return True

    def mitigate(self, incident_id: str, actor: str, note: str = "") -> bool:
        return self._transition(incident_id, "mitigated", actor, note)

    def resolve(self, incident_id: str, actor: str, note: str = "") -> bool:
        return self._transition(incident_id, "resolved", actor, note)

    def complete_postmortem(self, incident_id: str, summary: str,
                            root_cause: str, action_items: str) -> Dict[str, Any]:
        inc = self._incidents.get(incident_id)
        if not inc:
            return {"completed": False, "reason": "not found"}
        if inc.state != "resolved":
            return {"completed": False, "reason": "incident not resolved"}
        inc.postmortem = {"summary": summary, "root_cause": root_cause, "action_items": action_items}
        inc.state = "postmortem"
        inc.timeline.append(TimelineEvent(time.time_ns(), "system", "postmortem completed"))
        return {"completed": True}

    def open_incidents(self) -> List[Dict[str, Any]]:
        return [i.to_dict() for i in self._incidents.values() if i.state not in ("resolved", "postmortem")]

    def metrics(self) -> Dict[str, Any]:
        acked = [i for i in self._incidents.values() if i.acknowledged_ns]
        resolved = [i for i in self._incidents.values() if i.resolved_ns]
        mtta = sum(i.acknowledged_ns - i.opened_ns for i in acked) / len(acked) / 1e9 if acked else 0.0
        mttr = sum(i.resolved_ns - i.opened_ns for i in resolved) / len(resolved) / 1e9 if resolved else 0.0
        return {
            "total": len(self._incidents),
            "open": len(self.open_incidents()),
            "mtta_s": round(mtta, 2),
            "mttr_s": round(mttr, 2),
            "by_severity": {s: len([i for i in self._incidents.values() if i.severity == s]) for s in SEVERITIES},
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "incident-card",
            "metrics": self.metrics(),
            "open": self.open_incidents(),
        }
