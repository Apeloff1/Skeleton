"""End-to-end historical model lifecycle coordination for Jeeves.

The coordinator preserves the separation between ranking, validation, activation,
and runtime routing. ``propose`` is read-only. ``activate`` requires the exact
proposal and re-evaluates current evidence before mutating champion state, so a
proposal becomes stale if benchmark evidence, availability, lineage review, or
incumbent state changes between review and activation.

Production lifecycles require a readiness-bound activation authorization by
default. Tests or deliberately lower-level callers can disable that guard
explicitly, but doing so is an opt-out rather than an accidental bypass.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from skeleton.jeeves.historical_drift_guard import LineageAwarePromotionGuard, LineagePromotionReview
from skeleton.jeeves.historical_evaluation import HistoricalPromotionGate, PromotionDecision
from skeleton.jeeves.historical_governance import (
    ActiveChampionRoute,
    ChampionState,
    HistoricalChampionLedger,
    HistoricalGovernanceError,
)
from skeleton.jeeves.historical_models import ChampionDecision, ModelIdentity, canonical_fingerprint
from skeleton.jeeves.historical_routing import HistoricalChampionRouter, ProviderCatalog


class HistoricalLifecycleError(HistoricalGovernanceError):
    code = "JVS.HISTORICAL_LIFECYCLE"
    http_status = 409


@dataclass(frozen=True, slots=True)
class LifecycleProposal:
    ranking: ChampionDecision
    promotion: PromotionDecision
    incumbent: ModelIdentity | None
    candidate_scope: tuple[ModelIdentity, ...] | None
    fingerprint: str
    lineage_review: LineagePromotionReview | None = None

    @property
    def candidate(self) -> ModelIdentity:
        return self.ranking.champion.model

    @property
    def promotable(self) -> bool:
        return self.promotion.promotable and (
            self.lineage_review is None or self.lineage_review.allowed
        )

    @property
    def hold_reasons(self) -> tuple[str, ...]:
        reasons = list(self.promotion.reasons)
        if self.lineage_review is not None:
            reasons.extend(self.lineage_review.reasons)
        return tuple(sorted(set(reasons)))


@dataclass(frozen=True, slots=True)
class LifecycleActivation:
    proposal: LifecycleProposal
    state: ChampionState
    route: ActiveChampionRoute


class HistoricalModelLifecycle:
    """Coordinate rank -> validate -> optional drift guard -> authorize -> activate -> route."""

    def __init__(
        self,
        *,
        router: HistoricalChampionRouter,
        promotion_gate: HistoricalPromotionGate,
        ledger: HistoricalChampionLedger,
        catalog: ProviderCatalog,
        lineage_guard: LineageAwarePromotionGuard | None = None,
        require_activation_authorization: bool = True,
    ) -> None:
        if not isinstance(router, HistoricalChampionRouter):
            raise HistoricalLifecycleError("router must be HistoricalChampionRouter", context={"reason": "invalid_router"})
        if not isinstance(promotion_gate, HistoricalPromotionGate):
            raise HistoricalLifecycleError(
                "promotion_gate must be HistoricalPromotionGate",
                context={"reason": "invalid_promotion_gate"},
            )
        if not isinstance(ledger, HistoricalChampionLedger):
            raise HistoricalLifecycleError("ledger must be HistoricalChampionLedger", context={"reason": "invalid_ledger"})
        if not isinstance(catalog, ProviderCatalog):
            raise HistoricalLifecycleError("catalog must be ProviderCatalog", context={"reason": "invalid_catalog"})
        if lineage_guard is not None and not isinstance(lineage_guard, LineageAwarePromotionGuard):
            raise HistoricalLifecycleError(
                "lineage_guard must be LineageAwarePromotionGuard",
                context={"reason": "invalid_lineage_guard"},
            )
        if not isinstance(require_activation_authorization, bool):
            raise HistoricalLifecycleError(
                "require_activation_authorization must be boolean",
                context={"reason": "invalid_activation_authorization_policy"},
            )
        if router.catalog is not catalog:
            raise HistoricalLifecycleError(
                "router and lifecycle must share the same provider catalog",
                context={"reason": "catalog_mismatch"},
            )
        if router.registry is not promotion_gate.registry:
            raise HistoricalLifecycleError(
                "router and promotion gate must share the same historical registry",
                context={"reason": "registry_mismatch"},
            )
        if lineage_guard is not None and lineage_guard.promotion_gate is not promotion_gate:
            raise HistoricalLifecycleError(
                "lineage guard and lifecycle must share the same promotion gate",
                context={"reason": "lineage_gate_mismatch"},
            )
        self.router = router
        self.promotion_gate = promotion_gate
        self.ledger = ledger
        self.catalog = catalog
        self.lineage_guard = lineage_guard
        self.require_activation_authorization = require_activation_authorization

    def propose(self, *, models: Iterable[ModelIdentity] | None = None) -> LifecycleProposal:
        scope = None if models is None else tuple(sorted(set(models)))
        routed = self.router.route(models=scope)
        incumbent = self.ledger.active_model
        promotion = self.promotion_gate.decide(
            candidate=routed.model,
            incumbent=incumbent,
        )
        lineage_review = None
        if self.lineage_guard is not None:
            lineage_review = self.lineage_guard.review(
                candidate=routed.model,
                incumbent=incumbent,
                base_promotion=promotion,
            )
        fingerprint = self._proposal_fingerprint(
            ranking=routed.decision,
            promotion=promotion,
            incumbent=incumbent,
            candidate_scope=scope,
            lineage_review=lineage_review,
        )
        return LifecycleProposal(
            ranking=routed.decision,
            promotion=promotion,
            incumbent=incumbent,
            candidate_scope=scope,
            fingerprint=fingerprint,
            lineage_review=lineage_review,
        )

    def activate(
        self,
        proposal: LifecycleProposal,
        *,
        readiness: object | None = None,
        authorization: object | None = None,
    ) -> LifecycleActivation:
        """Activate only after optional/required readiness authorization verification.

        The authorization module imports this lifecycle module, so verification is
        imported locally to avoid a module-level cycle. Supplying either readiness
        or authorization opts into verification even when the lifecycle was
        explicitly configured as a low-level, authorization-optional instance.
        """
        must_verify = self.require_activation_authorization or readiness is not None or authorization is not None
        if must_verify:
            if readiness is None or authorization is None:
                raise HistoricalLifecycleError(
                    "readiness-bound activation authorization is required",
                    context={"reason": "activation_authorization_required"},
                )
            from skeleton.jeeves.historical_authorization import HistoricalActivationAuthorizer

            HistoricalActivationAuthorizer.verify(
                proposal=proposal,
                readiness=readiness,  # type: ignore[arg-type]
                authorization=authorization,  # type: ignore[arg-type]
            )
        return self._activate_revalidated(proposal)

    def _activate_revalidated(self, proposal: LifecycleProposal) -> LifecycleActivation:
        """Low-level mutation path after any configured authorization gate has run."""
        if not isinstance(proposal, LifecycleProposal):
            raise HistoricalLifecycleError(
                "proposal must be LifecycleProposal",
                context={"reason": "invalid_proposal"},
            )
        if not proposal.promotable:
            raise HistoricalLifecycleError(
                "held proposal cannot activate a champion",
                context={"reason": "proposal_not_promotable", "reasons": list(proposal.hold_reasons)},
            )
        refreshed = self.propose(models=proposal.candidate_scope)
        if refreshed.fingerprint != proposal.fingerprint:
            raise HistoricalLifecycleError(
                "proposal is stale and must be reviewed again",
                context={
                    "reason": "stale_proposal",
                    "expected": proposal.fingerprint,
                    "current": refreshed.fingerprint,
                    "previous_candidate": proposal.candidate.key,
                    "current_candidate": refreshed.candidate.key,
                },
            )
        state = self.ledger.activate(refreshed.promotion)
        route = self.ledger.route_active(self.catalog)
        return LifecycleActivation(proposal=refreshed, state=state, route=route)

    def route_active(self) -> ActiveChampionRoute:
        return self.ledger.route_active(self.catalog)

    @staticmethod
    def _proposal_fingerprint(
        *,
        ranking: ChampionDecision,
        promotion: PromotionDecision,
        incumbent: ModelIdentity | None,
        candidate_scope: tuple[ModelIdentity, ...] | None,
        lineage_review: LineagePromotionReview | None = None,
    ) -> str:
        """Fingerprint review-relevant state while excluding wall-clock noise."""
        return canonical_fingerprint(
            {
                "ranking": {
                    "champion": ranking.champion.model.key,
                    "champion_score": ranking.champion.score,
                    "champion_conservative_score": ranking.champion.conservative_score,
                    "policy_fingerprint": ranking.policy_fingerprint,
                    "evidence_fingerprint": ranking.evidence_fingerprint,
                    "candidates": [
                        {
                            "model": item.model.key,
                            "score": item.score,
                            "conservative_score": item.conservative_score,
                            "coverage": item.coverage,
                            "effective_samples": item.effective_samples,
                        }
                        for item in ranking.candidates
                    ],
                },
                "promotion": {
                    "action": promotion.action.value,
                    "decision_fingerprint": promotion.decision_fingerprint,
                    "candidate": promotion.candidate.model.key,
                    "candidate_score": promotion.candidate.score,
                    "candidate_samples": promotion.candidate.samples,
                    "candidate_coverage": promotion.candidate.coverage,
                    "incumbent": promotion.incumbent.model.key if promotion.incumbent is not None else None,
                    "incumbent_score": promotion.incumbent.score if promotion.incumbent is not None else None,
                    "margin": promotion.margin,
                    "reasons": list(promotion.reasons),
                },
                "lineage_review": (
                    {
                        "allowed": lineage_review.allowed,
                        "reasons": list(lineage_review.reasons),
                        "review_fingerprint": lineage_review.review_fingerprint,
                    }
                    if lineage_review is not None
                    else None
                ),
                "incumbent": incumbent.key if incumbent is not None else None,
                "candidate_scope": [model.key for model in candidate_scope] if candidate_scope is not None else None,
            }
        )


def summarize_lifecycle_proposal(proposal: LifecycleProposal) -> dict[str, Any]:
    return {
        "candidate": proposal.candidate.key,
        "historical_best_percent": proposal.ranking.historical_best_percent,
        "promotable": proposal.promotable,
        "promotion_action": proposal.promotion.action.value,
        "promotion_reasons": list(proposal.promotion.reasons),
        "lineage_allowed": proposal.lineage_review.allowed if proposal.lineage_review is not None else None,
        "lineage_reasons": list(proposal.lineage_review.reasons) if proposal.lineage_review is not None else [],
        "lineage_review_fingerprint": (
            proposal.lineage_review.review_fingerprint if proposal.lineage_review is not None else None
        ),
        "hold_reasons": list(proposal.hold_reasons),
        "incumbent": proposal.incumbent.key if proposal.incumbent is not None else None,
        "promotion_margin": proposal.promotion.margin,
        "ranking_policy_fingerprint": proposal.ranking.policy_fingerprint,
        "ranking_evidence_fingerprint": proposal.ranking.evidence_fingerprint,
        "promotion_decision_fingerprint": proposal.promotion.decision_fingerprint,
        "proposal_fingerprint": proposal.fingerprint,
    }