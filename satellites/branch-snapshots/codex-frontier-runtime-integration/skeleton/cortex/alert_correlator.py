"""Alert correlator — groups related alerts into single incidents.

Correlates alerts firing across subsystems within a time window using
shared attributes (trace id, host, dependency chain). Suppresses
symptom alerts when a root-cause alert already fired upstream via the
dependency graph, cutting pager noise. Feeds the incident manager.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class AlertEvent:
    alert_id: str
    subsystem: str
    severity: str
    message: str
    fired_ns: int
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class CorrelationGroup:
    group_id: str
    root_alert: str
    members: List[str] = field(default_factory=list)
    window_start_ns: int = 0
    suppressed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "root_alert": self.root_alert,
            "members": self.members,
            "suppressed": self.suppressed,
            "size": len(self.members),
        }


class AlertCorrelator:
    """Windowed alert grouping with upstream root-cause suppression."""

    def __init__(self, window_s: float = 120.0, dependency_graph: Any = None):
        self.window_s = window_s
        self._graph = dependency_graph
        self._alerts: List[AlertEvent] = []
        self._groups: Dict[str, CorrelationGroup] = {}
        self._counter = 0

    def _shared_keys(self, a: AlertEvent, b: AlertEvent) -> Set[str]:
        shared = set()
        for key in ("trace_id", "host", "region", "deployment"):
            if a.attributes.get(key) and a.attributes.get(key) == b.attributes.get(key):
                shared.add(key)
        return shared

    def _is_upstream(self, a_sub: str, b_sub: str) -> bool:
        if not self._graph:
            return False
        try:
            blast = self._graph.blast_radius(a_sub)
            return b_sub in blast.get("affected", [])
        except Exception:  # noqa: BLE001
            return False

    def ingest(self, alert_id: str, subsystem: str, severity: str,
               message: str, attributes: Optional[Dict[str, str]] = None,
               fired_ns: Optional[int] = None) -> Dict[str, Any]:
        event = AlertEvent(
            alert_id=alert_id, subsystem=subsystem, severity=severity,
            message=message, fired_ns=fired_ns or time.time_ns(),
            attributes=attributes or {},
        )
        cutoff = event.fired_ns - int(self.window_s * 1e9)
        candidates = [a for a in self._alerts if a.fired_ns >= cutoff]
        for other in candidates:
            shared = self._shared_keys(event, other)
            if not shared and event.subsystem != other.subsystem:
                if self._is_upstream(other.subsystem, event.subsystem):
                    group = self._find_group(other.alert_id)
                    if group:
                        group.suppressed.append(event.alert_id)
                        self._alerts.append(event)
                        return {"correlated": True, "group": group.group_id, "suppressed": True, "reason": f"downstream of {other.subsystem}"}
                continue
            group = self._find_group(other.alert_id)
            if group is None:
                self._counter += 1
                group = CorrelationGroup(
                    group_id=f"grp-{self._counter:04d}",
                    root_alert=other.alert_id,
                    members=[other.alert_id],
                    window_start_ns=other.fired_ns,
                )
                self._groups[group.group_id] = group
            group.members.append(event.alert_id)
            self._alerts.append(event)
            return {"correlated": True, "group": group.group_id, "shared": sorted(shared), "suppressed": False}
        self._alerts.append(event)
        if len(self._alerts) > 1000:
            self._alerts.pop(0)
        return {"correlated": False, "group": None}

    def _find_group(self, alert_id: str) -> Optional[CorrelationGroup]:
        for g in self._groups.values():
            if alert_id in g.members:
                return g
        return None

    def noise_reduction(self) -> Dict[str, Any]:
        total = len(self._alerts)
        grouped = sum(len(g.members) for g in self._groups.values())
        suppressed = sum(len(g.suppressed) for g in self._groups.values())
        return {
            "total_alerts": total,
            "in_groups": grouped,
            "suppressed": suppressed,
            "effective_pages": total - suppressed - (grouped - len(self._groups)),
            "reduction_pct": round((suppressed + grouped - len(self._groups)) / total * 100, 1) if total else 0.0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "alert-correlator-card",
            "groups": {g.group_id: g.to_dict() for g in self._groups.values()},
            "noise": self.noise_reduction(),
        }
