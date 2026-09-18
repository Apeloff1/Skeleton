"""Lineage-aware promotion guard for Jeeves historical models.

The normal promotion gate compares aggregate and per-domain holdout evidence.
This guard adds one independent question for revision upgrades: is the candidate
a direct child of the active incumbent, and does that generation transition avoid
a lineage-defined structural break?

It does not mutate champion state.  It returns a deterministic review envelope
that the historical lifecycle can include in proposal fingerprints and promotion
eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.historical_evaluation import HistoricalPromotionGate, PromotionDecision
from skeleton.jeeves.historical_lineage import GenerationDriftAnalyzer, GenerationDriftReport, HistoricalLineageError
from skeleton.jeeves.historical_models import ModelIdentity, canonical_fingerprint


class HistoricalDriftGuardError(ValueError):
    """Fail-closed drift guard contract violation."""


@dataclass(frozen=True, slots=True)
class LineagePromotionReview:
    candidate: ModelIdentity
    incumbent: ModelIdentity | None
    base_promotion: PromotionDecision
    drift: GenerationDriftReport | None
    allowed: bool
    reasons: tuple[str, ...]
    review_fingerprint: str


class LineageAwarePromotionGuard:
    """Require direct-lineage continuity and no structural generation break."""

    def __init__(
        self,
        *,
        promotion_gate: HistoricalPromotionGate,
        drift_analyzer: GenerationDriftAnalyzer,
        require_direct_lineage: bool = True,
    ) -> None:
        if not isinstance(promotion_gate, HistoricalPromotionGate):
            raise HistoricalDriftGuardError("promotion_gate must be HistoricalPromotionGate")
        if not isinstance(drift_analyzer, GenerationDriftAnalyzer):
            raise HistoricalDriftGuardError("drift_analyzer must be GenerationDriftAnalyzer")
        if drift_analyzer.gate is not promotion_gate:
            raise HistoricalDriftGuardError("drift analyzer and guard must share the same promotion gate")
        if not isinstance(require_direct_lineage, bool):
            raise HistoricalDriftGuardError("require_direct_lineage must be boolean")
        self.promotion_gate = promotion_gate
        self.drift_analyzer = drift_analyzer
        self.require_direct_lineage = require_direct_lineage

    def review(
        self,
        *,
        candidate: ModelIdentity,
        incumbent: ModelIdentity | None,
        base_promotion: PromotionDecision | None = None,
    ) -> LineagePromotionReview:
        if not isinstance(candidate, ModelIdentity):
            raise HistoricalDriftGuardError("candidate must be ModelIdentity")
        if incumbent is not None and not isinstance(incumbent, ModelIdentity):
            raise HistoricalDriftGuardError("incumbent must be ModelIdentity or None")
        promotion = base_promotion or self.promotion_gate.decide(candidate=candidate, incumbent=incumbent)
        if not isinstance(promotion, PromotionDecision):
            raise HistoricalDriftGuardError("base_promotion must be PromotionDecision")
        if promotion.candidate.model != candidate:
            raise HistoricalDriftGuardError("base promotion candidate does not match review candidate")
        if incumbent is None:
            drift = None
            reasons = () if promotion.promotable else ("base_promotion_held",)
            allowed = promotion.promotable
        else:
            if promotion.incumbent is None or promotion.incumbent.model != incumbent:
                raise HistoricalDriftGuardError("base promotion incumbent does not match review incumbent")
            reasons_list: list[str] = []
            drift = None
            try:
                node = self.drift_analyzer.lineage.node(candidate)
                if node.parent != incumbent:
                    if self.require_direct_lineage:
                        reasons_list.append("not_direct_lineage_child")
                else:
                    drift = self.drift_analyzer.compare(candidate)
            except HistoricalLineageError:
                if self.require_direct_lineage:
                    reasons_list.append("lineage_unavailable")
            if not promotion.promotable:
                reasons_list.append("base_promotion_held")
            if drift is not None and drift.structural_break:
                reasons_list.append("generation_structural_break")
            reasons = tuple(sorted(set(reasons_list)))
            allowed = promotion.promotable and not reasons

        payload = {
            "candidate": candidate.key,
            "incumbent": incumbent.key if incumbent is not None else None,
            "promotion_fingerprint": promotion.decision_fingerprint,
            "drift_fingerprint": drift.report_fingerprint if drift is not None else None,
            "require_direct_lineage": self.require_direct_lineage,
            "allowed": allowed,
            "reasons": reasons,
        }
        return LineagePromotionReview(
            candidate=candidate,
            incumbent=incumbent,
            base_promotion=promotion,
            drift=drift,
            allowed=allowed,
            reasons=reasons,
            review_fingerprint=canonical_fingerprint(payload),
        )


def summarize_lineage_promotion_review(review: LineagePromotionReview) -> dict[str, object]:
    return {
        "candidate": review.candidate.key,
        "incumbent": review.incumbent.key if review.incumbent is not None else None,
        "allowed": review.allowed,
        "reasons": list(review.reasons),
        "promotion_fingerprint": review.base_promotion.decision_fingerprint,
        "drift_fingerprint": review.drift.report_fingerprint if review.drift is not None else None,
        "structural_break": review.drift.structural_break if review.drift is not None else None,
        "review_fingerprint": review.review_fingerprint,
    }