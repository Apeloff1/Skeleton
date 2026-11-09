"""Multi-signal drift alarms for long-running characterization campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class DriftSignal:
    signal_id: str
    domain: str
    magnitude: float
    threshold: float
    critical: bool = False

    def __post_init__(self) -> None:
        if not self.signal_id or not self.domain:
            raise ReverseEngineeringError("drift signal identity is required")
        if not isfinite(self.magnitude) or self.magnitude < 0.0:
            raise ReverseEngineeringError("drift magnitude must be finite and non-negative")
        if not isfinite(self.threshold) or self.threshold < 0.0:
            raise ReverseEngineeringError("drift threshold must be finite and non-negative")

    @property
    def triggered(self) -> bool:
        return self.magnitude > self.threshold

    @property
    def normalized_excess(self) -> float:
        if self.threshold == 0.0:
            return self.magnitude if self.magnitude > 0.0 else 0.0
        return max(0.0, self.magnitude / self.threshold - 1.0)


@dataclass(frozen=True)
class DriftAlarmReport:
    signal_count: int
    triggered_count: int
    triggered_domain_count: int
    critical_trigger_count: int
    mean_normalized_excess: float
    severity: str
    triggered_signals: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_count": self.signal_count,
            "triggered_count": self.triggered_count,
            "triggered_domain_count": self.triggered_domain_count,
            "critical_trigger_count": self.critical_trigger_count,
            "mean_normalized_excess": self.mean_normalized_excess,
            "severity": self.severity,
            "triggered_signals": list(self.triggered_signals),
            "digest": self.digest,
        }


def evaluate_drift_alarm(
    signals: Sequence[DriftSignal],
    *,
    minimum_domains_for_warning: int = 2,
) -> DriftAlarmReport:
    if not signals:
        raise ReverseEngineeringError("drift alarm requires signals")
    if minimum_domains_for_warning < 1:
        raise ReverseEngineeringError("minimum_domains_for_warning must be positive")
    ids = [signal.signal_id for signal in signals]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("drift signal ids must be unique")
    triggered = [signal for signal in signals if signal.triggered]
    domains = {signal.domain for signal in triggered}
    critical = [signal for signal in triggered if signal.critical]
    severity = "none"
    if critical:
        severity = "critical"
    elif len(domains) >= minimum_domains_for_warning:
        severity = "warning"
    elif triggered:
        severity = "observe"
    excesses = [signal.normalized_excess for signal in triggered]
    payload = {
        "minimum_domains_for_warning": minimum_domains_for_warning,
        "signals": [
            {
                "signal_id": signal.signal_id,
                "domain": signal.domain,
                "magnitude": signal.magnitude,
                "threshold": signal.threshold,
                "critical": signal.critical,
            }
            for signal in sorted(signals, key=lambda item: item.signal_id)
        ],
    }
    return DriftAlarmReport(
        signal_count=len(signals),
        triggered_count=len(triggered),
        triggered_domain_count=len(domains),
        critical_trigger_count=len(critical),
        mean_normalized_excess=(sum(excesses) / len(excesses) if excesses else 0.0),
        severity=severity,
        triggered_signals=tuple(sorted(signal.signal_id for signal in triggered)),
        digest=stable_digest(payload),
    )
