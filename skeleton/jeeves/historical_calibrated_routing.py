"""Calibrated domain-aware runtime routing for Jeeves historical portfolios.

An ``ExpertPortfolio`` is descriptive holdout evidence. Before a specialist is
used at runtime this module can apply model-specific transparent calibration to
the specialist and fallback scores, require a minimum calibrated advantage, and
resolve the chosen identity through the trusted ``ProviderCatalog``.

Calibration never rewrites benchmark evidence. Missing calibration, a collapsed
calibrated margin, or an unavailable specialist can deterministically fall back
to the portfolio's general model. The fallback itself must be explicitly bound
and available or routing fails closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from skeleton.jeeves.historical_calibration import CalibrationModel
from skeleton.jeeves.historical_models import BenchmarkDomain, ModelIdentity, canonical_fingerprint
from skeleton.jeeves.historical_portfolio import ExpertAssignment, ExpertPortfolio
from skeleton.jeeves.historical_routing import HistoricalRoutingError, ProviderCatalog


class HistoricalCalibratedRoutingError(HistoricalRoutingError):
    code = "JVS.HISTORICAL_CALIBRATED_ROUTING"
    http_status = 503


@dataclass(frozen=True, slots=True)
class CalibratedRoutingPolicy:
    min_calibrated_specialist_margin: float = 0.01
    require_specialist_calibration: bool = True
    fallback_on_specialist_unavailable: bool = True

    def __post_init__(self) -> None:
        margin = self.min_calibrated_specialist_margin
        if isinstance(margin, bool) or not isinstance(margin, (int, float)):
            raise HistoricalCalibratedRoutingError(
                "min_calibrated_specialist_margin must be numeric",
                context={"reason": "invalid_margin"},
            )
        margin = float(margin)
        if not 0.0 <= margin <= 1.0:
            raise HistoricalCalibratedRoutingError(
                "min_calibrated_specialist_margin must be between 0 and 1",
                context={"reason": "invalid_margin"},
            )
        object.__setattr__(self, "min_calibrated_specialist_margin", margin)
        if not isinstance(self.require_specialist_calibration, bool):
            raise HistoricalCalibratedRoutingError(
                "require_specialist_calibration must be boolean",
                context={"reason": "invalid_policy"},
            )
        if not isinstance(self.fallback_on_specialist_unavailable, bool):
            raise HistoricalCalibratedRoutingError(
                "fallback_on_specialist_unavailable must be boolean",
                context={"reason": "invalid_policy"},
            )

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "min_calibrated_specialist_margin": self.min_calibrated_specialist_margin,
                "require_specialist_calibration": self.require_specialist_calibration,
                "fallback_on_specialist_unavailable": self.fallback_on_specialist_unavailable,
            }
        )


@dataclass(frozen=True, slots=True)
class CalibratedRouteDecision:
    domain: BenchmarkDomain
    planned_model: ModelIdentity
    selected_model: ModelIdentity
    fallback_model: ModelIdentity
    raw_specialist_score: float
    raw_fallback_score: float
    calibrated_specialist_score: float
    calibrated_fallback_score: float
    calibrated_margin: float
    reason: str
    portfolio_fingerprint: str
    policy_fingerprint: str
    calibration_fingerprints: tuple[str, ...]
    decision_fingerprint: str
    provider: Any

    @property
    def used_specialist(self) -> bool:
        return self.selected_model != self.fallback_model


class CalibratedPortfolioRouter:
    """Route a portfolio assignment through calibration and trusted bindings."""

    def __init__(
        self,
        *,
        portfolio: ExpertPortfolio,
        catalog: ProviderCatalog,
        calibrations: Mapping[ModelIdentity, CalibrationModel] | None = None,
        policy: CalibratedRoutingPolicy | None = None,
    ) -> None:
        if not isinstance(portfolio, ExpertPortfolio):
            raise HistoricalCalibratedRoutingError(
                "portfolio must be ExpertPortfolio",
                context={"reason": "invalid_portfolio"},
            )
        if not isinstance(catalog, ProviderCatalog):
            raise HistoricalCalibratedRoutingError(
                "catalog must be ProviderCatalog",
                context={"reason": "invalid_catalog"},
            )
        calibrations = {} if calibrations is None else dict(calibrations)
        for model, calibration in calibrations.items():
            if not isinstance(model, ModelIdentity) or not isinstance(calibration, CalibrationModel):
                raise HistoricalCalibratedRoutingError(
                    "calibrations must map ModelIdentity to CalibrationModel",
                    context={"reason": "invalid_calibration_map"},
                )
        self.portfolio = portfolio
        self.catalog = catalog
        self.calibrations = calibrations
        self.policy = policy or CalibratedRoutingPolicy()
        if not isinstance(self.policy, CalibratedRoutingPolicy):
            raise HistoricalCalibratedRoutingError(
                "policy must be CalibratedRoutingPolicy",
                context={"reason": "invalid_policy"},
            )

    def route(self, domain: BenchmarkDomain) -> CalibratedRouteDecision:
        if not isinstance(domain, BenchmarkDomain):
            raise HistoricalCalibratedRoutingError(
                "domain must be BenchmarkDomain",
                context={"reason": "invalid_domain"},
            )
        assignment = self._assignment_for(domain)
        fallback = self.portfolio.fallback_model
        planned = assignment.model if assignment is not None else fallback
        raw_specialist = assignment.domain_score if assignment is not None else self.portfolio.fallback_evaluation.score
        raw_fallback = assignment.fallback_score if assignment is not None else raw_specialist

        specialist_calibration = self.calibrations.get(planned)
        fallback_calibration = self.calibrations.get(fallback)
        calibrated_specialist = (
            specialist_calibration.calibrate(raw_specialist) if specialist_calibration is not None else raw_specialist
        )
        calibrated_fallback = (
            fallback_calibration.calibrate(raw_fallback) if fallback_calibration is not None else raw_fallback
        )
        calibrated_margin = calibrated_specialist - calibrated_fallback
        selected = planned
        reason = "fallback_assignment" if planned == fallback else "specialist_selected"

        if planned != fallback:
            if self.policy.require_specialist_calibration and specialist_calibration is None:
                selected = fallback
                reason = "missing_specialist_calibration"
            elif calibrated_margin + 1e-12 < self.policy.min_calibrated_specialist_margin:
                selected = fallback
                reason = "calibrated_margin_below_threshold"

        provider = None
        if selected != fallback:
            provider = self._instantiate_available(selected)
            if provider is None:
                if not self.policy.fallback_on_specialist_unavailable:
                    raise HistoricalCalibratedRoutingError(
                        "selected specialist provider is unavailable",
                        context={"reason": "specialist_unavailable", "model": selected.key},
                    )
                selected = fallback
                reason = "specialist_unavailable"

        if selected == fallback:
            provider = self._instantiate_available(fallback)
            if provider is None:
                raise HistoricalCalibratedRoutingError(
                    "fallback provider is unavailable",
                    context={"reason": "fallback_unavailable", "model": fallback.key},
                )

        calibration_fingerprints = tuple(
            sorted(
                {
                    calibration.source_fingerprint
                    for calibration in (specialist_calibration, fallback_calibration)
                    if calibration is not None
                }
            )
        )
        payload = {
            "domain": domain.value,
            "planned_model": planned.key,
            "selected_model": selected.key,
            "fallback_model": fallback.key,
            "raw_specialist_score": raw_specialist,
            "raw_fallback_score": raw_fallback,
            "calibrated_specialist_score": calibrated_specialist,
            "calibrated_fallback_score": calibrated_fallback,
            "calibrated_margin": calibrated_margin,
            "reason": reason,
            "portfolio_fingerprint": self.portfolio.portfolio_fingerprint,
            "policy_fingerprint": self.policy.fingerprint,
            "calibration_fingerprints": calibration_fingerprints,
        }
        return CalibratedRouteDecision(
            domain=domain,
            planned_model=planned,
            selected_model=selected,
            fallback_model=fallback,
            raw_specialist_score=raw_specialist,
            raw_fallback_score=raw_fallback,
            calibrated_specialist_score=calibrated_specialist,
            calibrated_fallback_score=calibrated_fallback,
            calibrated_margin=calibrated_margin,
            reason=reason,
            portfolio_fingerprint=self.portfolio.portfolio_fingerprint,
            policy_fingerprint=self.policy.fingerprint,
            calibration_fingerprints=calibration_fingerprints,
            decision_fingerprint=canonical_fingerprint(payload),
            provider=provider,
        )

    def _assignment_for(self, domain: BenchmarkDomain) -> ExpertAssignment | None:
        for assignment in self.portfolio.assignments:
            if assignment.domain is domain:
                return assignment
        return None

    def _instantiate_available(self, model: ModelIdentity) -> Any | None:
        try:
            binding = self.catalog.binding(model)
            provider = binding.instantiate()
            available = provider.available()
        except Exception:
            # Provider implementations are third-party runtime boundaries. Any
            # probe failure is treated as unavailable rather than escaping the
            # deterministic routing contract.
            return None
        return provider if available is True else None


def summarize_calibrated_route(decision: CalibratedRouteDecision) -> dict[str, object]:
    return {
        "domain": decision.domain.value,
        "planned_model": decision.planned_model.key,
        "selected_model": decision.selected_model.key,
        "fallback_model": decision.fallback_model.key,
        "used_specialist": decision.used_specialist,
        "raw_specialist_score": decision.raw_specialist_score,
        "raw_fallback_score": decision.raw_fallback_score,
        "calibrated_specialist_score": decision.calibrated_specialist_score,
        "calibrated_fallback_score": decision.calibrated_fallback_score,
        "calibrated_margin": decision.calibrated_margin,
        "reason": decision.reason,
        "portfolio_fingerprint": decision.portfolio_fingerprint,
        "policy_fingerprint": decision.policy_fingerprint,
        "calibration_fingerprints": list(decision.calibration_fingerprints),
        "decision_fingerprint": decision.decision_fingerprint,
    }