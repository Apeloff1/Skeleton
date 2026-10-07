"""Deterministic fail-closed response policy for characterization drift."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class DriftPolicySignal:
    signal_id: str
    domain: str
    severity: str

    def __post_init__(self) -> None:
        if not self.signal_id or not self.domain:
            raise ReverseEngineeringError("drift policy signal identity is required")
        if self.severity not in {"observe", "warning", "critical"}:
            raise ReverseEngineeringError("invalid drift policy severity")


@dataclass(frozen=True)
class DriftResponseDecision:
    action: str
    triggered_domains: tuple[str, ...]
    critical_domains: tuple[str, ...]
    requires_revalidation: bool
    freezes_claim_promotion: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "triggered_domains": list(self.triggered_domains),
            "critical_domains": list(self.critical_domains),
            "requires_revalidation": self.requires_revalidation,
            "freezes_claim_promotion": self.freezes_claim_promotion,
            "digest": self.digest,
        }


def decide_drift_response(
    signals: Sequence[DriftPolicySignal],
) -> DriftResponseDecision:
    if not signals:
        raise ReverseEngineeringError("drift response requires signals")
    ids = [signal.signal_id for signal in signals]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("drift policy signal ids must be unique")
    triggered_domains = tuple(sorted({signal.domain for signal in signals}))
    critical_domains = tuple(
        sorted({signal.domain for signal in signals if signal.severity == "critical"})
    )
    warning_count = sum(signal.severity == "warning" for signal in signals)
    if critical_domains:
        action = "freeze_and_revalidate"
        freeze = True
        revalidate = True
    elif warning_count >= 2:
        action = "revalidate"
        freeze = True
        revalidate = True
    elif warning_count == 1:
        action = "targeted_recheck"
        freeze = False
        revalidate = True
    else:
        action = "observe"
        freeze = False
        revalidate = False

    payload = {
        "signals": [
            {"signal_id": signal.signal_id, "domain": signal.domain, "severity": signal.severity}
            for signal in sorted(signals, key=lambda value: value.signal_id)
        ],
        "action": action,
    }
    return DriftResponseDecision(
        action=action,
        triggered_domains=triggered_domains,
        critical_domains=critical_domains,
        requires_revalidation=revalidate,
        freezes_claim_promotion=freeze,
        digest=stable_digest(payload),
    )
