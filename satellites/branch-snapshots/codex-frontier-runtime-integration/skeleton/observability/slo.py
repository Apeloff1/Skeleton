"""SLO definitions and error-budget tracking for observability.

Alerts fire on thresholds; SLOs frame the acceptable ratio of bad to
good outcomes over a window. Track remaining budget and burn rate.

- :class:`ServiceLevelObjective` — name, target ratio, window
- :class:`ErrorBudget` — total, used, remaining, burn rate
- :class:`SLOTracker` — per-SLO accounting
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from skeleton.kernel.errors import KernelError


class SLOError(KernelError):
    code = "OBS.SLO"


@dataclass(frozen=True)
class ServiceLevelObjective:
    name: str
    target: float  # e.g. 0.999
    window_s: float = 3600.0 * 24 * 30

    def allowed_error_ratio(self) -> float:
        return 1.0 - self.target


@dataclass
class ErrorBudget:
    total_events: int = 0
    bad_events: int = 0

    @property
    def observed_ratio(self) -> float:
        if self.total_events == 0:
            return 1.0
        return 1.0 - (self.bad_events / self.total_events)


class SLOTracker:
    """Registers SLOs and records outcomes per SLO."""

    def __init__(self) -> None:
        self._slos: Dict[str, ServiceLevelObjective] = {}
        self._budgets: Dict[str, ErrorBudget] = {}

    def register(self, slo: ServiceLevelObjective) -> None:
        self._slos[slo.name] = slo
        self._budgets[slo.name] = ErrorBudget()

    def record(self, slo_name: str, *, bad: bool) -> None:
        if slo_name not in self._slos:
            raise SLOError("unknown SLO", context={"slo": slo_name})
        budget = self._budgets[slo_name]
        budget.total_events += 1
        if bad:
            budget.bad_events += 1

    def remaining(self, slo_name: str) -> float:
        slo = self._slos.get(slo_name)
        budget = self._budgets.get(slo_name)
        if slo is None or budget is None:
            raise SLOError("unknown SLO", context={"slo": slo_name})
        allowed = slo.allowed_error_ratio()
        if budget.total_events == 0:
            return allowed
        bad_ratio = budget.bad_events / budget.total_events
        return max(0.0, allowed - bad_ratio)

    def burn_rate(self, slo_name: str) -> float:
        """Bad events per event averaged — everything > 0 burns budget."""
        budget = self._budgets.get(slo_name)
        if budget is None or budget.total_events == 0:
            return 0.0
        return budget.bad_events / budget.total_events

    def status(self) -> Dict[str, float]:
        return {name: self.remaining(name) for name in self._slos}
