from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AbsorbSignals:
    novelty: float
    relevance: float
    information_gain: float
    evidence_quality: float
    urgency: float
    downstream_utility: float
    estimated_compute_cost: float = 1.0


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def score(signals: AbsorbSignals) -> float:
    weighted = (
        _clip(signals.novelty) * 0.25
        + _clip(signals.relevance) * 0.20
        + _clip(signals.information_gain) * 0.20
        + _clip(signals.evidence_quality) * 0.15
        + _clip(signals.urgency) * 0.10
        + _clip(signals.downstream_utility) * 0.10
    )
    cost = max(float(signals.estimated_compute_cost), 1e-6)
    return weighted / cost
