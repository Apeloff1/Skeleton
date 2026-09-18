"""Bayesian predictive memory loop for Jeeves.

The fast card index is not only a retrieval cache.  This module treats card
sequences as a small, explicit prediction problem:

1. predict which indexed card/state is likely to follow the current cue;
2. observe the next canonical card;
3. score log loss / surprise and bounded prediction error;
4. update a Dirichlet transition posterior;
5. feed prediction error back into the memory-game strength machinery;
6. prioritize review where uncertainty and importance imply high learning value.

The model never changes source truth.  It only learns transition/retrieval
statistics over source-backed cards.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from .memory_game_index import IndexCard, MemoryGameIndex
from .types import AgentContractError, finite_number, positive_int, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class TransitionEstimate:
    source_card_id: str
    target_card_id: str
    probability: float
    observations: int
    posterior_mass: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "probability", probability("transition probability", self.probability))
        if self.observations < 0:
            raise AgentContractError("observations must be non-negative")
        if self.posterior_mass <= 0:
            raise AgentContractError("posterior_mass must be positive")


@dataclass(frozen=True, slots=True)
class MemoryPrediction:
    source_card_id: str
    candidates: tuple[TransitionEstimate, ...]
    entropy_bits: float
    support: int
    fingerprint: str

    @property
    def top(self) -> TransitionEstimate | None:
        return self.candidates[0] if self.candidates else None


@dataclass(frozen=True, slots=True)
class PredictionUpdate:
    stream_id: str
    previous_card_id: str | None
    observed_card_id: str
    prior_probability: float
    prediction_error: float
    surprise_bits: float
    log_loss_nats: float
    transition_observations: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PredictiveMemoryPolicy:
    """Controls Bayesian smoothing and review behavior."""

    dirichlet_alpha: float = 0.5
    unseen_floor: float = 1e-6
    max_candidates: int = 16
    relation_prior_weight: float = 0.35
    feedback_reward_scale: float = 0.5
    review_uncertainty_weight: float = 0.45
    review_importance_weight: float = 0.35
    review_error_weight: float = 0.20

    def __post_init__(self) -> None:
        alpha = finite_number("dirichlet_alpha", self.dirichlet_alpha)
        if alpha <= 0:
            raise AgentContractError("dirichlet_alpha must be positive")
        object.__setattr__(self, "dirichlet_alpha", alpha)
        floor = finite_number("unseen_floor", self.unseen_floor)
        if floor <= 0 or floor >= 1:
            raise AgentContractError("unseen_floor must be in (0,1)")
        object.__setattr__(self, "unseen_floor", floor)
        object.__setattr__(self, "max_candidates", positive_int("max_candidates", self.max_candidates, maximum=10_000))
        for name in (
            "relation_prior_weight",
            "feedback_reward_scale",
            "review_uncertainty_weight",
            "review_importance_weight",
            "review_error_weight",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        total = (
            self.review_uncertainty_weight
            + self.review_importance_weight
            + self.review_error_weight
        )
        if total <= 0:
            raise AgentContractError("review weights cannot all be zero")
        object.__setattr__(self, "review_uncertainty_weight", self.review_uncertainty_weight / total)
        object.__setattr__(self, "review_importance_weight", self.review_importance_weight / total)
        object.__setattr__(self, "review_error_weight", self.review_error_weight / total)


class PredictiveMemoryEngine:
    """Online Dirichlet transition learner over memory-game cards.

    Streams are explicit so dialogue turns, runtime analysis, games, or other
    event channels can learn separate temporal grammars even inside one
    namespace.
    """

    def __init__(
        self,
        index: MemoryGameIndex,
        *,
        policy: PredictiveMemoryPolicy | None = None,
    ) -> None:
        if not isinstance(index, MemoryGameIndex):
            raise TypeError("index must be MemoryGameIndex")
        self.index = index
        self.policy = policy or PredictiveMemoryPolicy()
        self._counts: dict[str, dict[str, float]] = defaultdict(dict)
        self._totals: dict[str, float] = defaultdict(float)
        self._last_by_stream: dict[str, str] = {}
        self._observations_by_source: dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    @staticmethod
    def _state_key(card_id: str) -> str:
        return str(card_id)

    def _candidate_ids(self, source_card_id: str) -> tuple[str, ...]:
        ids = set(self._counts.get(self._state_key(source_card_id), {}))
        for card, _ in self.index.predicted_next_cards(source_card_id, limit=self.policy.max_candidates):
            ids.add(card.card_id)
        return tuple(sorted(ids))

    def predict(self, source_card_id: str, *, limit: int | None = None) -> MemoryPrediction:
        source = self.index.card(source_card_id)
        if source is None:
            raise AgentContractError("unknown source card")
        limit = self.policy.max_candidates if limit is None else positive_int("limit", limit, maximum=10_000)
        with self._lock:
            state = self._state_key(source_card_id)
            counts = dict(self._counts.get(state, {}))
            candidate_ids = self._candidate_ids(source_card_id)
            relation_prior = {
                card.card_id: weight
                for card, weight in self.index.predicted_next_cards(source_card_id, limit=self.policy.max_candidates)
            }
            if not candidate_ids:
                return MemoryPrediction(
                    source_card_id=source_card_id,
                    candidates=(),
                    entropy_bits=0.0,
                    support=0,
                    fingerprint=stable_fingerprint({"source": source_card_id, "candidates": []}),
                )

            alpha = self.policy.dirichlet_alpha
            masses: dict[str, float] = {}
            for target_id in candidate_ids:
                mass = counts.get(target_id, 0.0) + alpha
                relation = relation_prior.get(target_id, 0.0)
                mass += self.policy.relation_prior_weight * relation
                masses[target_id] = mass
            total_mass = sum(masses.values())
            estimates = [
                TransitionEstimate(
                    source_card_id=source_card_id,
                    target_card_id=target_id,
                    probability=masses[target_id] / total_mass,
                    observations=int(round(counts.get(target_id, 0.0))),
                    posterior_mass=masses[target_id],
                )
                for target_id in masses
            ]
            estimates.sort(key=lambda item: (item.probability, item.observations, item.target_card_id), reverse=True)
            selected = tuple(estimates[:limit])
            # Entropy is computed on the full posterior candidate support.
            entropy = -sum(
                (mass / total_mass) * math.log2(mass / total_mass)
                for mass in masses.values()
                if mass > 0
            )
            return MemoryPrediction(
                source_card_id=source_card_id,
                candidates=selected,
                entropy_bits=entropy,
                support=self._observations_by_source.get(source_card_id, 0),
                fingerprint=stable_fingerprint(
                    {
                        "source": source_card_id,
                        "counts": sorted(counts.items()),
                        "relation_prior": sorted(relation_prior.items()),
                        "alpha": alpha,
                    }
                ),
            )

    def observe(
        self,
        observed_card_id: str,
        *,
        stream_id: str,
    ) -> PredictionUpdate:
        observed = self.index.card(observed_card_id)
        if observed is None:
            raise AgentContractError("unknown observed card")
        stream = str(stream_id).strip()
        if not stream:
            raise AgentContractError("stream_id cannot be empty")

        with self._lock:
            previous_id = self._last_by_stream.get(stream)
            prior_probability = 1.0
            transition_observations = 0
            if previous_id is not None and previous_id != observed_card_id:
                prediction = self.predict(previous_id)
                by_target = {item.target_card_id: item.probability for item in prediction.candidates}
                prior_probability = max(self.policy.unseen_floor, by_target.get(observed_card_id, self.policy.unseen_floor))
                error = 1.0 - prior_probability
                surprise_bits = -math.log2(prior_probability)
                log_loss = -math.log(prior_probability)

                state = self._state_key(previous_id)
                counts = self._counts[state]
                counts[observed_card_id] = counts.get(observed_card_id, 0.0) + 1.0
                self._totals[state] += 1.0
                self._observations_by_source[previous_id] += 1
                transition_observations = self._observations_by_source[previous_id]

                # Observed sequence edges are non-interpretive facts about order.
                try:
                    self.index.link_sequence(
                        (previous_id, observed_card_id),
                        strength=min(0.95, 0.55 + 0.05 * min(8, transition_observations)),
                        source="predictive-memory-observed-sequence",
                    )
                except Exception:
                    # Duplicate relation IDs are deterministic; index implementations
                    # may choose to reject a duplicate without invalidating learning.
                    pass

                # Prediction error changes retrievability, not truth or trust.
                self.index.retrieval_feedback(
                    observed_card_id,
                    success=True,
                    prediction_error=error,
                    reward=max(0.0, min(1.0, self.policy.feedback_reward_scale + error * (1.0 - self.policy.feedback_reward_scale))),
                )
            else:
                error = 0.0
                surprise_bits = 0.0
                log_loss = 0.0

            self._last_by_stream[stream] = observed_card_id
            return PredictionUpdate(
                stream_id=stream,
                previous_card_id=previous_id,
                observed_card_id=observed_card_id,
                prior_probability=max(0.0, min(1.0, prior_probability)),
                prediction_error=max(0.0, min(1.0, error)),
                surprise_bits=surprise_bits,
                log_loss_nats=log_loss,
                transition_observations=transition_observations,
                fingerprint=stable_fingerprint(
                    {
                        "stream": stream,
                        "previous": previous_id,
                        "observed": observed_card_id,
                        "prior_probability": prior_probability,
                        "prediction_error": error,
                        "transition_observations": transition_observations,
                    }
                ),
            )

    def review_queue(self, namespace_key: str, *, limit: int = 32) -> tuple[IndexCard, ...]:
        """Prioritize uncertain, important, repeatedly mispredicted cards."""
        limit = positive_int("limit", limit, maximum=10_000)
        rows: list[tuple[float, IndexCard]] = []
        for card in self.index.cards(namespace_key):
            uncertainty = 1.0 - abs(0.5 - card.retrieval_strength) * 2.0
            importance = (
                card.salience * 0.35
                + card.trust * 0.25
                + card.confidence * 0.20
                + card.surprise * 0.20
            )
            score = (
                uncertainty * self.policy.review_uncertainty_weight
                + importance * self.policy.review_importance_weight
                + card.prediction_error * self.policy.review_error_weight
            )
            rows.append((score, card))
        rows.sort(key=lambda item: (item[0], item[1].updated_at, item[1].card_id), reverse=True)
        return tuple(card for _, card in rows[:limit])

    def transition_counts(self, source_card_id: str) -> Mapping[str, float]:
        with self._lock:
            return dict(self._counts.get(self._state_key(source_card_id), {}))

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint(
                {
                    "counts": {
                        key: sorted(values.items())
                        for key, values in sorted(self._counts.items())
                    },
                    "last": sorted(self._last_by_stream.items()),
                    "observations": sorted(self._observations_by_source.items()),
                }
            )


__all__ = [
    "MemoryPrediction",
    "PredictionUpdate",
    "PredictiveMemoryEngine",
    "PredictiveMemoryPolicy",
    "TransitionEstimate",
]
