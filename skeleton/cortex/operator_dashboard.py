"""Operator dashboard — real-time streaming health and control surface.

Aggregates nervous, doctor, product, and all subsystem cards into
a single live dashboard model. Supports WebSocket-style push
updates, alert firing, and operator action dispatch.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.organism.doctor import doctor_card
from skeleton.organism.nervous import nervous_card
from skeleton.organism.product import product_card


@dataclass
class DashboardAlert:
    id: str
    severity: str
    subsystem: str
    message: str
    fired_at_ns: int
    acknowledged: bool = False
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "subsystem": self.subsystem,
            "message": self.message,
            "fired_at_ns": self.fired_at_ns,
            "acknowledged": self.acknowledged,
            "resolved": self.resolved,
        }


class OperatorDashboard:
    """Live dashboard aggregating all subsystem cards and alerts."""

    def __init__(self, root=None):
        self.root = root
        self._alerts: List[DashboardAlert] = []
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._alert_counter = 0
        self._last_update_ns = time.time_ns()

    def _next_alert_id(self) -> str:
        self._alert_counter += 1
        return f"alert-{self._alert_counter}"

    def refresh(self) -> Dict[str, Any]:
        self._last_update_ns = time.time_ns()
        card = self.card()
        for sub in self._subscribers:
            try:
                sub(card)
            except Exception:
                pass
        return card

    def fire_alert(self, severity: str, subsystem: str, message: str) -> DashboardAlert:
        alert = DashboardAlert(
            id=self._next_alert_id(),
            severity=severity,
            subsystem=subsystem,
            message=message,
            fired_at_ns=time.time_ns(),
        )
        self._alerts.append(alert)
        self.refresh()
        return alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        for a in self._alerts:
            if a.id == alert_id:
                a.acknowledged = True
                self.refresh()
                return True
        return False

    def resolve_alert(self, alert_id: str) -> bool:
        for a in self._alerts:
            if a.id == alert_id:
                a.resolved = True
                self.refresh()
                return True
        return False

    def active_alerts(self, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        alerts = [a for a in self._alerts if not a.resolved]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return [a.to_dict() for a in alerts]

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._subscribers.append(callback)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "operator-dashboard",
            "updated_at_ns": self._last_update_ns,
            "product": product_card(root=self.root),
            "nervous": nervous_card(root=self.root),
            "doctor": doctor_card(root=self.root),
            "alerts": self.active_alerts(),
            "alert_counts": {
                "critical": len([a for a in self._alerts if a.severity == "critical" and not a.resolved]),
                "warning": len([a for a in self._alerts if a.severity == "warning" and not a.resolved]),
                "info": len([a for a in self._alerts if a.severity == "info" and not a.resolved]),
            },
            "stored_prose": 0,
        }
