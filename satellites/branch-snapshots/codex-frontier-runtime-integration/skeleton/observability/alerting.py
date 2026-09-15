"""Alerting — threshold-based notification dispatch for the observability stack.

Metrics and health probes produce numbers; alerting turns those numbers into
action. This module provides:

- AlertRule: metric name, threshold operator, severity, cooldown
- AlertingEngine: evaluates rules against a MetricsRegistry snapshot
- NotificationRouter: dispatches to console, webhook, or bus event
- AlertState: tracks firing / resolved / acknowledged per rule
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError


class AlertError(KernelError):
    code = "OBS.ALERT"


class Severity(str, Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Operator(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"


@dataclass
class AlertRule:
    rule_id: str
    metric_name: str
    operator: Operator
    threshold: float
    severity: Severity = Severity.WARNING
    cooldown_s: float = 300.0
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertState:
    rule_id: str
    firing: bool = False
    last_fired_at: float = 0.0
    last_resolved_at: float = 0.0
    fired_count: int = 0


class NotificationRouter:
    """Pluggable notification backend."""

    def __init__(self) -> None:
        self._channels: List[Callable[[Dict[str, Any]], None]] = []

    def register(self, channel: Callable[[Dict[str, Any]], None]) -> None:
        self._channels.append(channel)

    def dispatch(self, payload: Dict[str, Any]) -> None:
        for ch in self._channels:
            try:
                ch(payload)
            except Exception:
                pass  # best-effort


class AlertingEngine:
    """Evaluates rules against metric snapshots."""

    def __init__(
        self,
        *,
        router: Optional[NotificationRouter] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.router = router or NotificationRouter()
        self._now = clock or time.monotonic
        self._rules: Dict[str, AlertRule] = {}
        self._states: Dict[str, AlertState] = {}

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.rule_id] = rule
        self._states.setdefault(rule.rule_id, AlertState(rule_id=rule.rule_id))

    def remove_rule(self, rule_id: str) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def evaluate(self, snapshot: Dict[str, float]) -> Tuple[AlertState, ...]:
        """Snapshot is {metric_name: value}. Returns any changed states."""
        changed: List[AlertState] = []
        for rule in self._rules.values():
            raw = snapshot.get(rule.metric_name)
            if raw is None:
                continue
            state = self._states[rule.rule_id]
            should_fire = self._compare(raw, rule.operator, rule.threshold)
            if should_fire and not state.firing:
                if self._now() - state.last_fired_at >= rule.cooldown_s:
                    state.firing = True
                    state.last_fired_at = self._now()
                    state.fired_count += 1
                    self._notify(rule, state, "firing")
                    changed.append(state)
            elif not should_fire and state.firing:
                state.firing = False
                state.last_resolved_at = self._now()
                self._notify(rule, state, "resolved")
                changed.append(state)
        return tuple(changed)

    @staticmethod
    def _compare(value: float, op: Operator, threshold: float) -> bool:
        if op is Operator.GT:
            return value > threshold
        if op is Operator.GTE:
            return value >= threshold
        if op is Operator.LT:
            return value < threshold
        if op is Operator.LTE:
            return value <= threshold
        return value == threshold

    def _notify(self, rule: AlertRule, state: AlertState, transition: str) -> None:
        self.router.dispatch(
            {
                "rule": rule.rule_id,
                "metric": rule.metric_name,
                "severity": rule.severity.value,
                "transition": transition,
                "threshold": rule.threshold,
                "fired_count": state.fired_count,
                "at": self._now(),
            }
        )

    def status(self) -> Dict[str, Any]:
        return {
            "rules": len(self._rules),
            "firing": sum(1 for s in self._states.values() if s.firing),
            "states": [
                {
                    "rule": s.rule_id,
                    "firing": s.firing,
                    "count": s.fired_count,
                }
                for s in self._states.values()
            ],
        }
