"""Escalation policy — multi-level alert escalation with time windows.

When an alert fires, the policy pages level 1; if unacknowledged
within the window, it escalates to level 2, then management. Tracks
acknowledgments, timeouts, and full escalation chains per alert so
nothing pages into a void. Pairs with the incident manager.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class EscalationLevel:
    level: int
    targets: List[str]
    timeout_s: float = 300.0


@dataclass
class Escalation:
    alert_id: str
    policy: str
    current_level: int = 0
    status: str = "active"
    started_ns: int = 0
    last_escalation_ns: int = 0
    notified: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "policy": self.policy,
            "current_level": self.current_level,
            "status": self.status,
            "notified": self.notified,
        }


class EscalationPolicy:
    """Level-based escalation with timeout advancement."""

    def __init__(self, notify: Optional[Callable[[str, str, str], None]] = None):
        self._policies: Dict[str, List[EscalationLevel]] = {}
        self._escalations: Dict[str, Escalation] = {}
        self._notify = notify or (lambda target, alert_id, msg: None)

    def define(self, name: str, levels: List[Dict[str, Any]]) -> None:
        self._policies[name] = [
            EscalationLevel(level=i, targets=l["targets"], timeout_s=l.get("timeout_s", 300.0))
            for i, l in enumerate(levels)
        ]

    def trigger(self, alert_id: str, policy: str, message: str = "") -> Dict[str, Any]:
        levels = self._policies.get(policy)
        if not levels:
            return {"triggered": False, "reason": "unknown policy"}
        esc = Escalation(alert_id=alert_id, policy=policy, started_ns=time.time_ns(),
                         last_escalation_ns=time.time_ns())
        self._escalations[alert_id] = esc
        self._page(esc, levels[0], message)
        return {"triggered": True, "level": 0, "targets": levels[0].targets}

    def _page(self, esc: Escalation, level: EscalationLevel, message: str) -> None:
        for target in level.targets:
            self._notify(target, esc.alert_id, message)
            esc.notified.append(target)

    def acknowledge(self, alert_id: str, actor: str) -> bool:
        esc = self._escalations.get(alert_id)
        if not esc or esc.status != "active":
            return False
        esc.status = "acknowledged"
        esc.notified.append(f"ack:{actor}")
        return True

    def tick(self) -> List[Dict[str, Any]]:
        now = time.time_ns()
        advanced: List[Dict[str, Any]] = []
        for esc in self._escalations.values():
            if esc.status != "active":
                continue
            levels = self._policies.get(esc.policy, [])
            if esc.current_level >= len(levels):
                continue
            current = levels[esc.current_level]
            if (now - esc.last_escalation_ns) / 1e9 >= current.timeout_s:
                if esc.current_level + 1 < len(levels):
                    esc.current_level += 1
                    esc.last_escalation_ns = now
                    self._page(esc, levels[esc.current_level], "escalated")
                    advanced.append({"alert_id": esc.alert_id, "new_level": esc.current_level})
                else:
                    esc.status = "expired"
                    advanced.append({"alert_id": esc.alert_id, "status": "expired"})
        return advanced

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "escalation-card",
            "policies": {n: len(l) for n, l in self._policies.items()},
            "active": [e.to_dict() for e in self._escalations.values() if e.status == "active"],
            "acknowledged": len([e for e in self._escalations.values() if e.status == "acknowledged"]),
            "expired": len([e for e in self._escalations.values() if e.status == "expired"]),
        }
