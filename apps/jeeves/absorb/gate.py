from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionSignals:
    confidence: float
    contradiction: float
    source_risk: float
    freshness: float
    duplicate_ratio: float
    has_provenance: bool


@dataclass(frozen=True)
class PromotionResult:
    accepted: bool
    reasons: tuple[str, ...]


def evaluate(signals: PromotionSignals) -> PromotionResult:
    reasons: list[str] = []
    if not signals.has_provenance:
        reasons.append("missing_provenance")
    if signals.confidence < 0.72:
        reasons.append("confidence_below_threshold")
    if signals.contradiction > 0.35:
        reasons.append("contradiction_above_threshold")
    if signals.source_risk > 0.30:
        reasons.append("source_risk_above_threshold")
    if signals.freshness < 0.50:
        reasons.append("stale_candidate")
    if signals.duplicate_ratio > 0.85:
        reasons.append("duplicate_candidate")
    return PromotionResult(accepted=not reasons, reasons=tuple(reasons))
