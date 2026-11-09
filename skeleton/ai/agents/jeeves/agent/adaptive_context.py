"""Adaptive value-of-information controller for Jeeves context descent.

The base :mod:`context_pipeline` defines a hard retrieval order whose first
stage is the L0 memory-game/index-card layer. This module adds a learned
controller on how far to descend. It never reorders the hierarchy and cannot
skip L0.

Deeper retrieval is treated as a sequential decision problem: expected marginal
information gain and an uncertainty/exploration bonus are traded against cost.
Learning consumes only the resolver's audited ResolutionStage records and is
namespace scoped.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .context_pipeline import ContextResolution, ContextTier, LayeredContextResolver
from .memory import MemoryNamespace
from .types import AgentContractError, finite_number, json_safe, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class ContextDescentPolicy:
    minimum_expected_value: float = 0.035
    exploration_weight: float = 0.18
    cost_weight: float = 0.20
    unresolved_weight: float = 0.30
    prediction_error_weight: float = 0.20
    gain_success_threshold: float = 0.025
    learning_rate: float = 0.15
    minimum_nonfast_tier: ContextTier = ContextTier.SCOPED_MEMORY
    cold_start_prior_gain: float = 0.08
    cold_start_prior_strength: float = 2.0

    def __post_init__(self) -> None:
        for name in (
            "minimum_expected_value",
            "exploration_weight",
            "cost_weight",
            "unresolved_weight",
            "prediction_error_weight",
            "gain_success_threshold",
            "learning_rate",
            "cold_start_prior_gain",
        ):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        strength = finite_number("cold_start_prior_strength", self.cold_start_prior_strength)
        if strength <= 0:
            raise AgentContractError("cold_start_prior_strength must be positive")
        object.__setattr__(self, "cold_start_prior_strength", strength)
        if not isinstance(self.minimum_nonfast_tier, ContextTier):
            object.__setattr__(
                self,
                "minimum_nonfast_tier",
                ContextTier(int(self.minimum_nonfast_tier)),
            )


@dataclass(frozen=True, slots=True)
class TierBelief:
    tier: ContextTier
    observations: int = 0
    useful: int = 0
    alpha: float = 1.0
    beta: float = 1.0
    gain_ema: float = 0.08
    cost_ema: float = 0.0
    prediction_error_ema: float = 0.0
    last_updated_at: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tier, ContextTier):
            object.__setattr__(self, "tier", ContextTier(int(self.tier)))
        if (
            isinstance(self.observations, bool)
            or not isinstance(self.observations, int)
            or self.observations < 0
        ):
            raise AgentContractError("observations must be a non-negative integer")
        if (
            isinstance(self.useful, bool)
            or not isinstance(self.useful, int)
            or self.useful < 0
            or self.useful > self.observations
        ):
            raise AgentContractError("useful must lie in [0, observations]")
        for name in ("alpha", "beta"):
            value = finite_number(name, getattr(self, name))
            if value <= 0:
                raise AgentContractError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        for name in ("gain_ema", "cost_ema", "prediction_error_ema"):
            value = finite_number(name, getattr(self, name))
            if value < 0:
                raise AgentContractError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if self.last_updated_at is not None:
            object.__setattr__(
                self,
                "last_updated_at",
                finite_number("last_updated_at", self.last_updated_at),
            )

    @property
    def success_probability(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def posterior_variance(self) -> float:
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total * total * (total + 1.0))

    @property
    def uncertainty(self) -> float:
        return min(1.0, 2.0 * math.sqrt(max(0.0, self.posterior_variance)))


@dataclass(frozen=True, slots=True)
class TierDecision:
    tier: ContextTier
    expected_gain: float
    success_probability: float
    uncertainty: float
    estimated_cost: float
    unresolved_pressure: float
    prediction_error_pressure: float
    exploration_bonus: float
    expected_value: float
    descend: bool
    reason: str

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "tier": int(self.tier),
                "gain": self.expected_gain,
                "success": self.success_probability,
                "uncertainty": self.uncertainty,
                "cost": self.estimated_cost,
                "unresolved": self.unresolved_pressure,
                "prediction_error": self.prediction_error_pressure,
                "bonus": self.exploration_bonus,
                "value": self.expected_value,
                "descend": self.descend,
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class AdaptiveContextResolution:
    resolution: ContextResolution
    requested_max_tier: ContextTier
    decisions: tuple[TierDecision, ...]
    learned_from_resolution: bool
    controller_fingerprint: str


class AdaptiveContextGovernor:
    """Learn context depth while preserving the fixed L0 -> deep-store order."""

    _DEFAULT_TIER_COST: Mapping[ContextTier, float] = {
        ContextTier.INDEX_CARD: 0.01,
        ContextTier.SCOPED_MEMORY: 0.05,
        ContextTier.CONTEXT_REPOSITORY: 0.08,
        ContextTier.CACHE: 0.09,
        ContextTier.DATABASE: 0.16,
        ContextTier.LOG: 0.22,
        ContextTier.JOURNAL: 0.30,
        ContextTier.DIARY: 0.34,
        ContextTier.ANNAL: 0.48,
        ContextTier.CHRONICLE: 0.55,
        ContextTier.ARCHIVE: 0.70,
        ContextTier.EXTERNAL: 0.85,
    }

    def __init__(
        self,
        resolver: LayeredContextResolver,
        *,
        policy: ContextDescentPolicy | None = None,
        tier_cost: Mapping[ContextTier, float] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(resolver, LayeredContextResolver):
            raise TypeError("resolver must be LayeredContextResolver")
        self.resolver = resolver
        self.policy = policy or ContextDescentPolicy()
        costs = dict(self._DEFAULT_TIER_COST)
        costs.update(dict(tier_cost or {}))
        self._tier_cost = {
            (tier if isinstance(tier, ContextTier) else ContextTier(int(tier))): probability(
                "tier cost", value
            )
            for tier, value in costs.items()
        }
        self._clock = clock
        self._beliefs: dict[tuple[str, ContextTier], TierBelief] = {}
        self._lock = threading.RLock()

    def _belief(self, namespace: MemoryNamespace, tier: ContextTier) -> TierBelief:
        key = (namespace.key, tier)
        with self._lock:
            current = self._beliefs.get(key)
            if current is not None:
                return current
            prior = self.policy.cold_start_prior_strength
            gain = self.policy.cold_start_prior_gain
            return TierBelief(
                tier=tier,
                alpha=max(1e-6, prior * gain + 1.0),
                beta=max(1e-6, prior * (1.0 - gain) + 1.0),
                gain_ema=gain,
                cost_ema=self._tier_cost.get(tier, 0.5),
            )

    @staticmethod
    def _prediction_error_pressure(card_hits: Sequence[Any]) -> float:
        if not card_hits:
            return 1.0
        weighted = 0.0
        total = 0.0
        for hit in card_hits:
            card = getattr(hit, "card", None)
            if card is None:
                continue
            weight = max(1e-6, float(getattr(hit, "score", 0.0)))
            error = float(getattr(card, "prediction_error_ema", 0.0))
            surprise = float(getattr(card, "surprise_ema", 0.0))
            weighted += weight * min(1.0, 0.65 * error + 0.35 * surprise)
            total += weight
        return 1.0 if total <= 0 else max(0.0, min(1.0, weighted / total))

    def _decision(
        self,
        namespace: MemoryNamespace,
        tier: ContextTier,
        *,
        unresolved_pressure: float,
        prediction_error_pressure: float,
    ) -> TierDecision:
        belief = self._belief(namespace, tier)
        with self._lock:
            total_observations = 1 + sum(
                state.observations
                for (ns, _), state in self._beliefs.items()
                if ns == namespace.key
            )
        exploration = self.policy.exploration_weight * math.sqrt(
            math.log(total_observations + 1.0) / (belief.observations + 1.0)
        )
        cost = max(self._tier_cost.get(tier, 0.5), belief.cost_ema)
        expected_gain = belief.gain_ema * (0.5 + 0.5 * belief.success_probability)
        value = (
            expected_gain
            + self.policy.unresolved_weight * unresolved_pressure * belief.success_probability
            + self.policy.prediction_error_weight
            * prediction_error_pressure
            * belief.success_probability
            + exploration
            - self.policy.cost_weight * cost
        )
        forced = tier <= self.policy.minimum_nonfast_tier
        descend = forced or value >= self.policy.minimum_expected_value
        reason = (
            "minimum durable fallback"
            if forced
            else ("positive value of information" if descend else "marginal value below cost")
        )
        return TierDecision(
            tier=tier,
            expected_gain=max(0.0, expected_gain),
            success_probability=belief.success_probability,
            uncertainty=belief.uncertainty,
            estimated_cost=cost,
            unresolved_pressure=unresolved_pressure,
            prediction_error_pressure=prediction_error_pressure,
            exploration_bonus=exploration,
            expected_value=value,
            descend=descend,
            reason=reason,
        )

    def choose_max_tier(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        hard_max_tier: ContextTier | None = None,
    ) -> tuple[ContextTier, tuple[TierDecision, ...]]:
        """Choose maximum retrieval depth after a read-only L0 probe."""

        cards = self.resolver.cards.search(
            namespace,
            query,
            context_tags=context_tags,
            limit=self.resolver.policy.card_limit,
        )
        if self.resolver.cards.fast_path_ready(query, cards):
            return ContextTier.INDEX_CARD, ()

        coverage = self.resolver.cards.coverage(query, cards)
        unresolved = max(0.0, min(1.0, 1.0 - coverage))
        prediction_error = self._prediction_error_pressure(cards)
        hard_max = (
            hard_max_tier
            if hard_max_tier is not None
            else self.resolver.policy.maximum_tier
        )
        if not isinstance(hard_max, ContextTier):
            hard_max = ContextTier(int(hard_max))

        decisions: list[TierDecision] = []
        selected = ContextTier.INDEX_CARD
        for value in range(int(ContextTier.SCOPED_MEMORY), int(hard_max) + 1):
            tier = ContextTier(value)
            decision = self._decision(
                namespace,
                tier,
                unresolved_pressure=unresolved,
                prediction_error_pressure=prediction_error,
            )
            decisions.append(decision)
            if not decision.descend:
                break
            selected = tier
            unresolved *= 0.92
        return selected, tuple(decisions)

    def observe(self, namespace: MemoryNamespace, resolution: ContextResolution) -> None:
        """Learn tier utility from audited marginal gain, never from truth claims."""

        now = self._clock()
        lr = self.policy.learning_rate
        for stage in resolution.stages:
            if stage.tier is ContextTier.INDEX_CARD:
                continue
            prior = self._belief(namespace, stage.tier)
            useful = stage.marginal_gain >= self.policy.gain_success_threshold
            estimated_cost = self._tier_cost.get(stage.tier, 0.5)
            prediction_error = abs(float(useful) - prior.success_probability)
            updated = TierBelief(
                tier=stage.tier,
                observations=prior.observations + 1,
                useful=prior.useful + int(useful),
                alpha=prior.alpha + (1.0 if useful else 0.0),
                beta=prior.beta + (0.0 if useful else 1.0),
                gain_ema=(1.0 - lr) * prior.gain_ema + lr * stage.marginal_gain,
                cost_ema=(1.0 - lr) * prior.cost_ema + lr * estimated_cost,
                prediction_error_ema=(1.0 - lr) * prior.prediction_error_ema
                + lr * prediction_error,
                last_updated_at=now,
            )
            with self._lock:
                self._beliefs[(namespace.key, stage.tier)] = updated

    def resolve(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        hard_max_tier: ContextTier | None = None,
        learn: bool = True,
    ) -> AdaptiveContextResolution:
        selected, decisions = self.choose_max_tier(
            namespace,
            query,
            context_tags=context_tags,
            hard_max_tier=hard_max_tier,
        )
        resolution = self.resolver.resolve(
            namespace,
            query,
            context_tags=context_tags,
            force_max_tier=selected,
        )
        if learn:
            self.observe(namespace, resolution)
        fingerprint = stable_fingerprint(
            {
                "namespace": namespace.key,
                "query": query,
                "selected": int(selected),
                "resolution": resolution.fingerprint,
                "decisions": [item.fingerprint for item in decisions],
                "beliefs": self.snapshot(namespace),
            }
        )
        return AdaptiveContextResolution(
            resolution=resolution,
            requested_max_tier=selected,
            decisions=decisions,
            learned_from_resolution=learn,
            controller_fingerprint=fingerprint,
        )

    def snapshot(self, namespace: MemoryNamespace) -> Mapping[str, Any]:
        with self._lock:
            rows = {}
            for (ns, tier), belief in sorted(
                self._beliefs.items(), key=lambda item: (item[0][0], int(item[0][1]))
            ):
                if ns != namespace.key:
                    continue
                rows[tier.name.casefold()] = {
                    "observations": belief.observations,
                    "useful": belief.useful,
                    "success_probability": belief.success_probability,
                    "uncertainty": belief.uncertainty,
                    "gain_ema": belief.gain_ema,
                    "cost_ema": belief.cost_ema,
                    "prediction_error_ema": belief.prediction_error_ema,
                    "last_updated_at": belief.last_updated_at,
                }
            return json_safe(rows)
