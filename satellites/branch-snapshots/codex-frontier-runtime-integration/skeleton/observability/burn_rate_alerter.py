"""Burn rate alerter — multi-window SLO burn alerting.

Implements Google SRE multi-window burn-rate alerts: a fast-burn
alert (1h window, 14.4x rate, 2% budget in 2d) and a slow-burn
alert (6h window, 6x rate, 5% budget in 5d). Reads from the SLA
tracker and routes alerts through escalation policies with proper
severity per burn class.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BurnAlert:
    slo: str
    kind: str
    burn_rate: float
    window_s: float
    budget_consumed_pct: float
    fired_ns: int
    severity: str
    acknowledged: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slo": self.slo,
            "kind": self.kind,
            "burn_rate": round(self.burn_rate, 2),
            "window_s": self.window_s,
            "budget_consumed_pct": round(self.budget_consumed_pct, 1),
            "severity": self.severity,
            "acknowledged": self.acknowledged,
        }


FAST_BURN = (3600.0, 14.4, 0.02, 2, "critical")
SLOW_BURN = (21600.0, 6.0, 0.05, 5, "warning")


class BurnRateAlerter:
    """Multi-window SLO burn-rate alerting."""

    def __init__(self, sla_tracker: Any = None):
        self._sla = sla_tracker
        self._alerts: List[BurnAlert] = []
        self._silenced: Dict[str, int] = {}

    def silence(self, slo: str, duration_s: float) -> None:
        self._silenced[slo] = time.time_ns() + int(duration_s * 1e9)

    def _is_silenced(self, slo: str) -> bool:
        until = self._silenced.get(slo)
        return bool(until and time.time_ns() < until)

    def evaluate(self, subsystem: str, metric: str, target: float = 0.999) -> List[Dict[str, Any]]:
        slo = f"{subsystem}.{metric}"
        if self._is_silenced(slo):
            return []
        fired: List[BurnAlert] = []
        for (window_s, threshold, budget_frac, window_days, severity) in (FAST_BURN, SLOW_BURN):
            rate = self._burn_rate(subsystem, metric, target, window_s)
            if rate >= threshold:
                kind = "fast_burn" if window_s == FAST_BURN[0] else "slow_burn"
                consumed = rate * (1 - target) * (window_days * 86400 / window_s) * 100
                existing = [a for a in self._alerts if a.slo == slo and a.kind == kind and not a.acknowledged]
                if existing:
                    continue
                alert = BurnAlert(
                    slo=slo, kind=kind, burn_rate=rate, window_s=window_s,
                    budget_consumed_pct=consumed, fired_ns=time.time_ns(), severity=severity,
                )
                self._alerts.append(alert)
                fired.append(alert)
        return [a.to_dict() for a in fired]

    def _burn_rate(self, subsystem: str, metric: str, target: float, window_s: float) -> float:
        if self._sla:
            return self._sla.burn_rate(subsystem, metric, short_window_s=window_s)
        return 0.0

    def acknowledge(self, slo: str, kind: str) -> bool:
        for a in self._alerts:
            if a.slo == slo and a.kind == kind and not a.acknowledged:
                a.acknowledged = True
                return True
        return False

    def active(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._alerts if not a.acknowledged]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "burn-rate-card",
            "active_alerts": self.active(),
            "total_fired": len(self._alerts),
            "silenced": [s for s in self._silenced if self._is_silenced(s)],
            "config": {
                "fast_burn": {"window_s": FAST_BURN[0], "threshold": FAST_BURN[1]},
                "slow_burn": {"window_s": SLOW_BURN[0], "threshold": SLOW_BURN[1]},
            },
        }
