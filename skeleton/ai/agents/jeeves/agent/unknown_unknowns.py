"""Unknown-unknown discovery from predictive residuals.

Jeeves already knows how to research a named uncertainty.  This module handles a
harder case: the system repeatedly sees observations its current predictive
models assigned very low probability to, especially across independent
contexts.  Those residuals are treated as evidence that the current ontology or
mechanism set may be incomplete.

The scout is conservative: a single surprise is not a discovery.  Promotion
requires recurrent surprise, cross-context support, and decision relevance.
Promoted candidates can be converted into KnowledgeObligation objects and fed
back into the epistemic frontier.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .epistemic_frontier import KnowledgeObligation
from .types import (
    AgentContractError,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


_EPS = 1e-12


@dataclass(frozen=True, slots=True)
class SurpriseScoutPolicy:
    surprise_threshold_bits: float = 3.0
    severe_surprise_bits: float = 6.0
    minimum_recurrence: int = 2
    minimum_distinct_contexts: int = 2
    minimum_decision_impact: float = 0.35
    minimum_candidate_score: float = 0.50
    maximum_observations_per_channel: int = 256
    maximum_candidates: int = 64

    def __post_init__(self) -> None:
        for name in ("surprise_threshold_bits", "severe_surprise_bits"):
            value = finite_number(name, getattr(self, name))
            if value <= 0:
                raise AgentContractError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.severe_surprise_bits < self.surprise_threshold_bits:
            raise AgentContractError(
                "severe_surprise_bits must be >= surprise_threshold_bits"
            )
        for name in (
            "minimum_recurrence",
            "minimum_distinct_contexts",
            "maximum_observations_per_channel",
            "maximum_candidates",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=1_000_000),
            )
        for name in ("minimum_decision_impact", "minimum_candidate_score"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class SurpriseObservation:
    observation_id: str
    channel: str
    context_key: str
    expected_probability: float
    decision_impact: float
    observed_at: float
    evidence_ref: str | None = None
    outcome: str = "observed"
    explanation_coverage: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_id",
            require_id("observation_id", self.observation_id),
        )
        object.__setattr__(self, "channel", require_id("channel", self.channel))
        object.__setattr__(
            self,
            "context_key",
            require_id("context_key", self.context_key),
        )
        p = probability("expected_probability", self.expected_probability)
        # Exact zero is allowed at the contract boundary, but all surprise
        # calculations use a bounded floor.
        object.__setattr__(self, "expected_probability", p)
        object.__setattr__(
            self,
            "decision_impact",
            probability("decision_impact", self.decision_impact),
        )
        observed_at = finite_number("observed_at", self.observed_at)
        if observed_at < 0:
            raise AgentContractError("observed_at must be non-negative")
        object.__setattr__(self, "observed_at", observed_at)
        if self.evidence_ref is not None:
            object.__setattr__(
                self,
                "evidence_ref",
                require_id("evidence_ref", self.evidence_ref),
            )
        object.__setattr__(
            self,
            "outcome",
            bounded_text("outcome", self.outcome, maximum=2048),
        )
        object.__setattr__(
            self,
            "explanation_coverage",
            probability("explanation_coverage", self.explanation_coverage),
        )
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def surprise_bits(self) -> float:
        return -math.log2(max(_EPS, self.expected_probability))

    @property
    def unexplained_fraction(self) -> float:
        return 1.0 - self.explanation_coverage

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "channel": self.channel,
            "context_key": self.context_key,
            "expected_probability": self.expected_probability,
            "decision_impact": self.decision_impact,
            "observed_at": self.observed_at,
            "evidence_ref": self.evidence_ref,
            "outcome": self.outcome,
            "explanation_coverage": self.explanation_coverage,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class UnknownUnknownCandidate:
    candidate_id: str
    channel: str
    recurrence_count: int
    distinct_context_count: int
    mean_surprise_bits: float
    maximum_surprise_bits: float
    mean_decision_impact: float
    mean_unexplained_fraction: float
    score: float
    context_keys: tuple[str, ...]
    observation_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    rationale: tuple[str, ...]
    fingerprint: str

    def to_knowledge_obligation(self) -> KnowledgeObligation:
        """Turn the anomaly cluster into a new question for frontier research."""

        coverage = max(
            0.0,
            min(1.0, 1.0 - self.mean_unexplained_fraction),
        )
        confidence = max(
            0.05,
            min(
                0.75,
                0.30
                + 0.08 * min(4, self.recurrence_count)
                + 0.05 * min(3, self.distinct_context_count),
            ),
        )
        return KnowledgeObligation(
            obligation_id=stable_id(
                "unknown-unknown-obligation",
                {
                    "candidate": self.candidate_id,
                    "channel": self.channel,
                },
                length=30,
            ),
            question=(
                f"What missing mechanism explains recurrent low-probability "
                f"outcomes in channel {self.channel}?"
            ),
            decision_impact=self.mean_decision_impact,
            confidence=confidence,
            evidence_coverage=coverage,
            freshness=1.0,
            contradiction_strength=0.0,
            model_disagreement=min(1.0, self.score),
            assumption_load=min(1.0, self.mean_unexplained_fraction),
            novelty=min(1.0, 0.60 + 0.40 * self.score),
            evidence_refs=self.evidence_refs,
            assumptions=(
                "current predictive hypothesis set may be incomplete",
                "recurrent surprise may reflect a latent variable, regime, or omitted mechanism",
            ),
            metadata={
                "unknown_unknown_candidate_id": self.candidate_id,
                "source_channel": self.channel,
                "mean_surprise_bits": self.mean_surprise_bits,
                "maximum_surprise_bits": self.maximum_surprise_bits,
                "distinct_contexts": self.distinct_context_count,
                "observation_ids": list(self.observation_ids),
            },
        )


@dataclass(frozen=True, slots=True)
class SurpriseScoutSnapshot:
    observations: tuple[SurpriseObservation, ...]
    candidates: tuple[UnknownUnknownCandidate, ...]
    promoted_channels: tuple[str, ...]
    fingerprint: str

    def as_json(self) -> dict[str, Any]:
        return {
            "observations": [item.as_json() for item in self.observations],
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "channel": item.channel,
                    "recurrence_count": item.recurrence_count,
                    "distinct_context_count": item.distinct_context_count,
                    "mean_surprise_bits": item.mean_surprise_bits,
                    "maximum_surprise_bits": item.maximum_surprise_bits,
                    "mean_decision_impact": item.mean_decision_impact,
                    "mean_unexplained_fraction": item.mean_unexplained_fraction,
                    "score": item.score,
                    "context_keys": list(item.context_keys),
                    "observation_ids": list(item.observation_ids),
                    "evidence_refs": list(item.evidence_refs),
                    "rationale": list(item.rationale),
                    "fingerprint": item.fingerprint,
                }
                for item in self.candidates
            ],
            "promoted_channels": list(self.promoted_channels),
            "fingerprint": self.fingerprint,
        }


class UnknownUnknownScout:
    """Detect recurrent unexplained predictive failures across contexts."""

    def __init__(
        self,
        *,
        policy: SurpriseScoutPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or SurpriseScoutPolicy()
        self._clock = clock
        self._observations: dict[str, list[SurpriseObservation]] = defaultdict(list)
        self._promoted: set[str] = set()

    def observe(
        self,
        *,
        channel: str,
        context_key: str,
        expected_probability: float,
        decision_impact: float,
        evidence_ref: str | None = None,
        outcome: str = "observed",
        explanation_coverage: float = 0.0,
        observation_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SurpriseObservation:
        channel = require_id("channel", channel)
        context_key = require_id("context_key", context_key)
        observed_at = finite_number("observed_at", self._clock())
        raw_id = observation_id or stable_id(
            "surprise-observation",
            {
                "channel": channel,
                "context": context_key,
                "probability": expected_probability,
                "impact": decision_impact,
                "outcome": outcome,
                "at": observed_at,
            },
            length=30,
        )
        observation = SurpriseObservation(
            observation_id=raw_id,
            channel=channel,
            context_key=context_key,
            expected_probability=expected_probability,
            decision_impact=decision_impact,
            observed_at=observed_at,
            evidence_ref=evidence_ref,
            outcome=outcome,
            explanation_coverage=explanation_coverage,
            metadata=metadata or {},
        )
        bucket = self._observations[channel]
        if any(item.observation_id == observation.observation_id for item in bucket):
            raise AgentContractError("duplicate surprise observation_id")
        bucket.append(observation)
        bucket.sort(key=lambda item: (item.observed_at, item.observation_id))
        if len(bucket) > self.policy.maximum_observations_per_channel:
            del bucket[:-self.policy.maximum_observations_per_channel]
        return observation

    def candidates(self) -> tuple[UnknownUnknownCandidate, ...]:
        values: list[UnknownUnknownCandidate] = []
        for channel, observations in self._observations.items():
            candidate = self._candidate(channel, observations)
            if candidate is not None:
                values.append(candidate)
        values.sort(
            key=lambda item: (
                item.score,
                item.maximum_surprise_bits,
                item.distinct_context_count,
                item.recurrence_count,
                item.channel,
            ),
            reverse=True,
        )
        return tuple(values[: self.policy.maximum_candidates])

    def promote(
        self,
        candidate_id: str,
    ) -> KnowledgeObligation:
        candidate_id = require_id("candidate_id", candidate_id)
        candidate = next(
            (
                item for item in self.candidates()
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise AgentContractError("unknown or ineligible unknown-unknown candidate")
        self._promoted.add(candidate.channel)
        return candidate.to_knowledge_obligation()

    def promote_all(self) -> tuple[KnowledgeObligation, ...]:
        obligations: list[KnowledgeObligation] = []
        for candidate in self.candidates():
            if candidate.channel in self._promoted:
                continue
            self._promoted.add(candidate.channel)
            obligations.append(candidate.to_knowledge_obligation())
        return tuple(obligations)

    def snapshot(self) -> SurpriseScoutSnapshot:
        observations = tuple(
            sorted(
                (
                    item
                    for values in self._observations.values()
                    for item in values
                ),
                key=lambda item: (
                    item.channel,
                    item.observed_at,
                    item.observation_id,
                ),
            )
        )
        candidates = self.candidates()
        promoted = tuple(sorted(self._promoted))
        fingerprint = stable_fingerprint(
            {
                "observations": [item.fingerprint for item in observations],
                "candidates": [item.fingerprint for item in candidates],
                "promoted": promoted,
            }
        )
        return SurpriseScoutSnapshot(
            observations=observations,
            candidates=candidates,
            promoted_channels=promoted,
            fingerprint=fingerprint,
        )

    def dump_state(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "version": 1,
            "policy": {
                name: getattr(self.policy, name)
                for name in self.policy.__dataclass_fields__
            },
            "observations": [item.as_json() for item in snapshot.observations],
            "promoted_channels": list(snapshot.promoted_channels),
            "fingerprint": snapshot.fingerprint,
        }

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, Any],
        *,
        clock: Callable[[], float] = time.time,
    ) -> "UnknownUnknownScout":
        payload = json_safe(dict(state))
        if payload.get("version") != 1:
            raise AgentContractError("unsupported unknown-unknown scout state version")
        scout = cls(
            policy=SurpriseScoutPolicy(**dict(payload.get("policy", {}))),
            clock=clock,
        )
        for raw in payload.get("observations", ()):
            value = dict(raw)
            observation = SurpriseObservation(
                observation_id=value["observation_id"],
                channel=value["channel"],
                context_key=value["context_key"],
                expected_probability=value["expected_probability"],
                decision_impact=value["decision_impact"],
                observed_at=value["observed_at"],
                evidence_ref=value.get("evidence_ref"),
                outcome=value.get("outcome", "observed"),
                explanation_coverage=value.get("explanation_coverage", 0.0),
                metadata=dict(value.get("metadata", {})),
            )
            scout._observations[observation.channel].append(observation)
        for values in scout._observations.values():
            values.sort(key=lambda item: (item.observed_at, item.observation_id))
        scout._promoted = {
            require_id("promoted_channel", item)
            for item in payload.get("promoted_channels", ())
        }
        if scout.snapshot().fingerprint != payload.get("fingerprint"):
            raise AgentContractError(
                "unknown-unknown scout fingerprint mismatch during restore"
            )
        return scout

    def _candidate(
        self,
        channel: str,
        observations: Sequence[SurpriseObservation],
    ) -> UnknownUnknownCandidate | None:
        surprising = tuple(
            item
            for item in observations
            if item.surprise_bits >= self.policy.surprise_threshold_bits
            and item.decision_impact >= self.policy.minimum_decision_impact
        )
        if len(surprising) < self.policy.minimum_recurrence:
            return None
        contexts = tuple(sorted({item.context_key for item in surprising}))
        if len(contexts) < self.policy.minimum_distinct_contexts:
            return None

        mean_surprise = sum(item.surprise_bits for item in surprising) / len(surprising)
        maximum_surprise = max(item.surprise_bits for item in surprising)
        mean_impact = sum(item.decision_impact for item in surprising) / len(surprising)
        mean_unexplained = (
            sum(item.unexplained_fraction for item in surprising)
            / len(surprising)
        )
        recurrence_signal = min(
            1.0,
            len(surprising) / max(1, self.policy.minimum_recurrence * 2),
        )
        context_signal = min(
            1.0,
            len(contexts) / max(1, self.policy.minimum_distinct_contexts * 2),
        )
        surprise_signal = min(
            1.0,
            mean_surprise / self.policy.severe_surprise_bits,
        )
        score = min(
            1.0,
            0.30 * recurrence_signal
            + 0.20 * context_signal
            + 0.25 * surprise_signal
            + 0.15 * mean_unexplained
            + 0.10 * mean_impact,
        )
        if score < self.policy.minimum_candidate_score:
            return None

        evidence_refs = tuple(
            sorted(
                {
                    item.evidence_ref
                    for item in surprising
                    if item.evidence_ref is not None
                }
            )
        )
        observation_ids = tuple(item.observation_id for item in surprising)
        candidate_id = stable_id(
            "unknown-unknown",
            {
                "channel": channel,
                "observations": [item.fingerprint for item in surprising],
                "contexts": contexts,
            },
            length=30,
        )
        rationale = (
            f"recurrent surprise count={len(surprising)}",
            f"distinct contexts={len(contexts)}",
            f"mean surprise={mean_surprise:.3f} bits",
            f"maximum surprise={maximum_surprise:.3f} bits",
            f"mean unexplained fraction={mean_unexplained:.3f}",
            "pattern is promoted as a possible omitted mechanism rather than noise",
        )
        fingerprint = stable_fingerprint(
            {
                "candidate_id": candidate_id,
                "channel": channel,
                "recurrence": len(surprising),
                "contexts": contexts,
                "mean_surprise": mean_surprise,
                "maximum_surprise": maximum_surprise,
                "mean_impact": mean_impact,
                "mean_unexplained": mean_unexplained,
                "score": score,
                "observations": observation_ids,
                "evidence_refs": evidence_refs,
            }
        )
        return UnknownUnknownCandidate(
            candidate_id=candidate_id,
            channel=channel,
            recurrence_count=len(surprising),
            distinct_context_count=len(contexts),
            mean_surprise_bits=mean_surprise,
            maximum_surprise_bits=maximum_surprise,
            mean_decision_impact=mean_impact,
            mean_unexplained_fraction=mean_unexplained,
            score=score,
            context_keys=contexts,
            observation_ids=observation_ids,
            evidence_refs=evidence_refs,
            rationale=rationale,
            fingerprint=fingerprint,
        )
