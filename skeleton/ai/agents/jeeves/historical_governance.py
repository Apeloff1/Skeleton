"""Versioned promotion state and rollback for Jeeves historical champions.

Ranking and holdout evaluation stay immutable; this module only records which
validated model revision is currently active. Every activation is tied to a
promotion-decision fingerprint, history is bounded, duplicate decisions are
rejected, and rollback restores a prior active model without rewriting evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Final

from skeleton.jeeves.historical_evaluation import PromotionAction, PromotionDecision
from skeleton.jeeves.historical_models import ModelIdentity, canonical_fingerprint
from skeleton.jeeves.historical_routing import HistoricalRoutingError, ProviderCatalog


DEFAULT_MAX_PROMOTION_HISTORY: Final = 64


class HistoricalGovernanceError(HistoricalRoutingError):
    code = "JVS.HISTORICAL_GOVERNANCE"
    http_status = 409


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalGovernanceError(
            f"{name} must be a positive integer",
            context={"reason": "invalid_integer", "field": name},
        )
    return value


def _timestamp(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalGovernanceError("clock must return a number", context={"reason": "invalid_clock"})
    number = float(value)
    if number < 0.0 or not math.isfinite(number):
        raise HistoricalGovernanceError("clock must return a finite non-negative number", context={"reason": "invalid_clock"})
    return number


def _decision_consumption_fingerprint(decision: PromotionDecision) -> str:
    """Bind replay protection to the full evaluated content, not only IDs."""

    def evaluation_payload(evaluation):
        if evaluation is None:
            return None
        return {
            "model": evaluation.model.key,
            "score": evaluation.score,
            "coverage": evaluation.coverage,
            "samples": evaluation.samples,
            "max_volatility": evaluation.max_volatility,
            "max_latest_drop": evaluation.max_latest_drop,
            "missing_required_domains": [domain.value for domain in evaluation.missing_required_domains],
            "evidence_fingerprint": evaluation.evidence_fingerprint,
            "domains": [
                {
                    "domain": item.domain.value,
                    "score": item.score,
                    "samples": item.samples,
                    "volatility": item.volatility,
                    "latest_score": item.latest_score,
                    "historical_score": item.historical_score,
                    "latest_drop": item.latest_drop,
                    "snapshot_ids": list(item.snapshot_ids),
                }
                for item in evaluation.domains
            ],
        }

    return canonical_fingerprint(
        {
            "decision_fingerprint": decision.decision_fingerprint,
            "action": decision.action.value,
            "candidate": evaluation_payload(decision.candidate),
            "incumbent": evaluation_payload(decision.incumbent),
            "reasons": list(decision.reasons),
            "margin": decision.margin,
            "suite_fingerprint": decision.suite_fingerprint,
            "policy_fingerprint": decision.policy_fingerprint,
        }
    )


@dataclass(frozen=True, slots=True)
class ChampionState:
    version: int
    model: ModelIdentity | None
    activated_at: float
    decision_fingerprint: str | None
    previous_version: int | None
    rollback_of: int | None = None

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "version": self.version,
                "model": self.model.key if self.model is not None else None,
                "activated_at": self.activated_at,
                "decision_fingerprint": self.decision_fingerprint,
                "previous_version": self.previous_version,
                "rollback_of": self.rollback_of,
            }
        )


@dataclass(frozen=True, slots=True)
class ActiveChampionRoute:
    state: ChampionState
    provider: Any


class HistoricalChampionLedger:
    """Small append-only state machine for validated model activation."""

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        max_history: int = DEFAULT_MAX_PROMOTION_HISTORY,
    ) -> None:
        if not callable(clock):
            raise HistoricalGovernanceError("clock must be callable", context={"reason": "invalid_clock"})
        self._clock = clock
        self._max_history = _positive_int("max_history", max_history)
        self._states: list[ChampionState] = []
        self._by_version: dict[int, ChampionState] = {}
        self._used_decisions: set[str] = set()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    @property
    def active(self) -> ChampionState | None:
        return self._states[-1] if self._states else None

    @property
    def active_model(self) -> ModelIdentity | None:
        state = self.active
        return state.model if state is not None else None

    def history(self) -> tuple[ChampionState, ...]:
        return tuple(self._states)

    def activate(self, decision: PromotionDecision) -> ChampionState:
        if not isinstance(decision, PromotionDecision):
            raise HistoricalGovernanceError(
                "decision must be PromotionDecision",
                context={"reason": "invalid_decision"},
            )
        if decision.action is not PromotionAction.PROMOTE or not decision.promotable:
            raise HistoricalGovernanceError(
                "only promotable decisions may activate a champion",
                context={"reason": "decision_not_promotable"},
            )
        candidate = decision.candidate.model
        if self.active_model == candidate:
            raise HistoricalGovernanceError(
                "candidate is already the active champion",
                context={"reason": "already_active", "model": candidate.key},
            )
        consumption_fingerprint = _decision_consumption_fingerprint(decision)
        if consumption_fingerprint in self._used_decisions:
            raise HistoricalGovernanceError(
                "promotion decision has already been consumed",
                context={
                    "reason": "duplicate_decision",
                    "decision_fingerprint": decision.decision_fingerprint,
                    "consumption_fingerprint": consumption_fingerprint,
                },
            )
        previous = self.active.version if self.active is not None else None
        state = self._append(
            model=candidate,
            decision_fingerprint=decision.decision_fingerprint,
            previous_version=previous,
            rollback_of=None,
        )
        self._used_decisions.add(consumption_fingerprint)
        return state

    def rollback(self, target_version: int) -> ChampionState:
        target_version = _positive_int("target_version", target_version)
        target = self._by_version.get(target_version)
        if target is None:
            raise HistoricalGovernanceError(
                "target promotion version is unavailable",
                context={"reason": "unknown_or_evicted_version", "target_version": target_version},
            )
        if self.active is not None and self.active.version == target_version:
            raise HistoricalGovernanceError(
                "target version is already active",
                context={"reason": "already_active_version", "target_version": target_version},
            )
        previous = self.active.version if self.active is not None else None
        return self._append(
            model=target.model,
            decision_fingerprint=target.decision_fingerprint,
            previous_version=previous,
            rollback_of=target_version,
        )

    def route_active(self, catalog: ProviderCatalog) -> ActiveChampionRoute:
        if not isinstance(catalog, ProviderCatalog):
            raise HistoricalGovernanceError(
                "catalog must be ProviderCatalog",
                context={"reason": "invalid_catalog"},
            )
        state = self.active
        if state is None or state.model is None:
            raise HistoricalGovernanceError(
                "no champion has been activated",
                context={"reason": "no_active_champion"},
            )
        binding = catalog.binding(state.model)
        provider = binding.instantiate()
        try:
            available = provider.available()
        except Exception as exc:
            raise HistoricalGovernanceError(
                "active champion provider availability check failed",
                context={"reason": "provider_probe_failed", "model": state.model.key},
                cause=exc,
            ) from exc
        if available is not True:
            raise HistoricalGovernanceError(
                "active champion provider is unavailable",
                context={"reason": "active_provider_unavailable", "model": state.model.key},
            )
        return ActiveChampionRoute(state=state, provider=provider)

    def _append(
        self,
        *,
        model: ModelIdentity | None,
        decision_fingerprint: str | None,
        previous_version: int | None,
        rollback_of: int | None,
    ) -> ChampionState:
        self._version += 1
        state = ChampionState(
            version=self._version,
            model=model,
            activated_at=_timestamp(self._clock()),
            decision_fingerprint=decision_fingerprint,
            previous_version=previous_version,
            rollback_of=rollback_of,
        )
        self._states.append(state)
        self._by_version[state.version] = state
        while len(self._states) > self._max_history:
            evicted = self._states.pop(0)
            self._by_version.pop(evicted.version, None)
        return state


def summarize_champion_state(state: ChampionState) -> dict[str, object]:
    return {
        "version": state.version,
        "model": state.model.key if state.model is not None else None,
        "activated_at": state.activated_at,
        "decision_fingerprint": state.decision_fingerprint,
        "previous_version": state.previous_version,
        "rollback_of": state.rollback_of,
        "state_fingerprint": state.fingerprint,
    }