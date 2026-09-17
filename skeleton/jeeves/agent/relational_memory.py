"""Relational fast memory for Jeeves.

The ordinary memory-game index stores compact interaction cards. This module
adds the missing relational substrate: what tended to occur beside, before,
after, against, or around a card.

Relations are non-authoritative. They accelerate retrieval and prediction but
never upgrade an interpretation into evidence.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .memory import MemoryNamespace
from .memory_game import CardHit, InteractionCard, MemoryGameIndex
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
_TOKEN_CHARS = frozenset("_-'")


class RelationalMemoryError(AgentContractError):
    """Raised when relational-memory state violates its contract."""


class RelationKind(str, Enum):
    CO_OCCURRENCE = "co_occurrence"
    ADJACENCY = "adjacency"
    SUCCESSION = "succession"
    PRECEDENCE = "precedence"
    JUXTAPOSITION = "juxtaposition"
    CONTRAST = "contrast"
    REINFORCEMENT = "reinforcement"
    REVERSAL = "reversal"
    TRIAD = "triad"
    RECURRENCE = "recurrence"
    MOTIF = "motif"
    ANALOGY = "analogy"
    EVENT_BOUNDARY = "event_boundary"
    CAUSAL_CANDIDATE = "causal_candidate"


_ORDERED_KINDS = frozenset(
    {
        RelationKind.SUCCESSION,
        RelationKind.PRECEDENCE,
        RelationKind.JUXTAPOSITION,
        RelationKind.REVERSAL,
        RelationKind.TRIAD,
        RelationKind.MOTIF,
        RelationKind.EVENT_BOUNDARY,
        RelationKind.CAUSAL_CANDIDATE,
    }
)
_TRIAD_KINDS = frozenset({RelationKind.TRIAD, RelationKind.MOTIF})
_PAIR_ONLY_KINDS = frozenset(
    {
        RelationKind.CO_OCCURRENCE,
        RelationKind.ADJACENCY,
        RelationKind.SUCCESSION,
        RelationKind.PRECEDENCE,
        RelationKind.JUXTAPOSITION,
        RelationKind.CONTRAST,
        RelationKind.REINFORCEMENT,
        RelationKind.REVERSAL,
        RelationKind.ANALOGY,
        RelationKind.EVENT_BOUNDARY,
        RelationKind.CAUSAL_CANDIDATE,
    }
)


@dataclass(frozen=True, slots=True)
class RelationalMemoryPolicy:
    max_relations: int = 200_000
    maximum_hits: int = 12
    maximum_seed_cards: int = 8
    maximum_card_chars: int = 2_000
    minimum_score: float = 0.16
    event_boundary_surprise: float = 0.60
    surprisal_scale_nats: float = 6.0
    dirichlet_alpha: float = 0.5
    half_life_seconds: float = 21.0 * 24.0 * 3600.0

    cue_weight: float = 0.20
    lexical_weight: float = 0.18
    support_weight: float = 0.16
    transition_weight: float = 0.16
    context_weight: float = 0.08
    trust_weight: float = 0.10
    surprise_weight: float = 0.07
    recency_weight: float = 0.05

    def __post_init__(self) -> None:
        for name in ("max_relations", "maximum_hits", "maximum_seed_cards", "maximum_card_chars"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=10_000_000))
        for name in ("minimum_score", "event_boundary_surprise"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        surprisal_scale = finite_number("surprisal_scale_nats", self.surprisal_scale_nats)
        if surprisal_scale <= 0:
            raise RelationalMemoryError("surprisal_scale_nats must be positive")
        object.__setattr__(self, "surprisal_scale_nats", surprisal_scale)
        alpha = finite_number("dirichlet_alpha", self.dirichlet_alpha)
        if alpha <= 0:
            raise RelationalMemoryError("dirichlet_alpha must be positive")
        object.__setattr__(self, "dirichlet_alpha", alpha)
        half_life = finite_number("half_life_seconds", self.half_life_seconds)
        if half_life <= 0:
            raise RelationalMemoryError("half_life_seconds must be positive")
        object.__setattr__(self, "half_life_seconds", half_life)

        names = (
            "cue_weight",
            "lexical_weight",
            "support_weight",
            "transition_weight",
            "context_weight",
            "trust_weight",
            "surprise_weight",
            "recency_weight",
        )
        values = [finite_number(name, getattr(self, name)) for name in names]
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise RelationalMemoryError("relation retrieval weights must be non-negative and non-zero")
        total = sum(values)
        for name, value in zip(names, values):
            object.__setattr__(self, name, value / total)


@dataclass(frozen=True, slots=True)
class RelationTrace:
    relation_id: str
    namespace: MemoryNamespace
    kind: RelationKind
    card_ids: tuple[str, ...]
    created_at: float
    updated_at: float
    occurrence_count: int = 1
    support_weight: float = 1.0
    trust: float = 0.65
    salience: float = 0.55
    surprise_ema: float = 0.0
    prediction_error_ema: float = 0.0
    prediction_attempts: int = 0
    prediction_hits: int = 0
    context_tags: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    rationale: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_id", require_id("relation_id", self.relation_id))
        if not isinstance(self.namespace, MemoryNamespace):
            raise RelationalMemoryError("namespace must be MemoryNamespace")
        if not isinstance(self.kind, RelationKind):
            object.__setattr__(self, "kind", RelationKind(str(self.kind)))
        ids = tuple(require_id("card_id", item) for item in self.card_ids)
        if len(ids) < 2 or len(ids) > 3:
            raise RelationalMemoryError("relations require two or three cards")
        if self.kind in _PAIR_ONLY_KINDS and len(ids) != 2:
            raise RelationalMemoryError(f"{self.kind.value} requires exactly two cards")
        if self.kind in _TRIAD_KINDS and len(ids) != 3:
            raise RelationalMemoryError(f"{self.kind.value} requires exactly three cards")
        if self.kind not in _ORDERED_KINDS:
            ids = tuple(sorted(ids))
        object.__setattr__(self, "card_ids", ids)

        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise RelationalMemoryError("invalid relation timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        if isinstance(self.occurrence_count, bool) or not isinstance(self.occurrence_count, int) or self.occurrence_count < 1:
            raise RelationalMemoryError("occurrence_count must be a positive integer")
        weight = finite_number("support_weight", self.support_weight)
        if weight <= 0:
            raise RelationalMemoryError("support_weight must be positive")
        object.__setattr__(self, "support_weight", weight)
        for name in ("trust", "salience", "surprise_ema", "prediction_error_ema"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("prediction_attempts", "prediction_hits"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RelationalMemoryError(f"{name} must be a non-negative integer")
        if self.prediction_hits > self.prediction_attempts:
            raise RelationalMemoryError("prediction_hits cannot exceed prediction_attempts")
        tags = tuple(sorted({str(tag).strip().casefold() for tag in self.context_tags if str(tag).strip()}))
        object.__setattr__(self, "context_tags", tags)
        object.__setattr__(self, "provenance", tuple(sorted({str(item) for item in self.provenance if str(item)})))
        object.__setattr__(self, "rationale", bounded_text("relation rationale", self.rationale, maximum=4096, allow_empty=True))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def ordered(self) -> bool:
        return self.kind in _ORDERED_KINDS

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "namespace": self.namespace.key,
            "kind": self.kind.value,
            "card_ids": list(self.card_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "occurrence_count": self.occurrence_count,
            "support_weight": self.support_weight,
            "trust": self.trust,
            "salience": self.salience,
            "surprise_ema": self.surprise_ema,
            "prediction_error_ema": self.prediction_error_ema,
            "prediction_attempts": self.prediction_attempts,
            "prediction_hits": self.prediction_hits,
            "context_tags": list(self.context_tags),
            "provenance": list(self.provenance),
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RelationPrediction:
    source_card_id: str
    target_card_id: str
    probability: float
    support_count: int
    support_weight: float
    trust: float
    conditional_entropy: float
    closed_support: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_card_id", require_id("source_card_id", self.source_card_id))
        object.__setattr__(self, "target_card_id", require_id("target_card_id", self.target_card_id))
        object.__setattr__(self, "probability", probability("transition probability", self.probability))
        support_weight = finite_number("transition support_weight", self.support_weight)
        if support_weight < 0:
            raise RelationalMemoryError("support_weight must be non-negative")
        object.__setattr__(self, "support_weight", support_weight)
        object.__setattr__(self, "trust", probability("transition trust", self.trust))
        object.__setattr__(self, "conditional_entropy", probability("conditional entropy", self.conditional_entropy))
        if isinstance(self.support_count, bool) or not isinstance(self.support_count, int) or self.support_count < 0:
            raise RelationalMemoryError("support_count must be non-negative")


@dataclass(frozen=True, slots=True)
class RelationalHit:
    trace: RelationTrace
    content: str
    score: float
    cue_match: float
    lexical: float
    support: float
    transition_probability: float
    context_match: float
    recency: float
    retrieval_confidence: float
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", bounded_text("relation hit content", self.content, maximum=16_000))
        for name in (
            "score",
            "cue_match",
            "lexical",
            "support",
            "transition_probability",
            "context_match",
            "recency",
            "retrieval_confidence",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(item) for item in self.evidence_ids if str(item)})))


@dataclass(frozen=True, slots=True)
class SequenceObservation:
    created_relation_ids: tuple[str, ...]
    event_boundary_ids: tuple[str, ...]
    transition_predictions: tuple[RelationPrediction, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class TransitionFeedback:
    source_card_id: str
    observed_target_card_id: str
    predicted_probability: float
    surprise: float
    brier_error: float
    prediction_available: bool
    relation_id: str
    relation_fingerprint: str


class RelationStore:
    """Thread-safe bounded store partitioned by namespace."""

    def __init__(self, *, max_relations: int = 200_000) -> None:
        self.max_relations = positive_int("max_relations", max_relations, maximum=10_000_000)
        self._relations: dict[str, RelationTrace] = {}
        self._lock = threading.RLock()

    def put(self, trace: RelationTrace) -> RelationTrace:
        if not isinstance(trace, RelationTrace):
            raise TypeError("trace must be RelationTrace")
        with self._lock:
            if trace.relation_id not in self._relations and len(self._relations) >= self.max_relations:
                self._evict_one()
            self._relations[trace.relation_id] = trace
            return trace

    def get(self, relation_id: str) -> RelationTrace | None:
        with self._lock:
            return self._relations.get(require_id("relation_id", relation_id))

    def list_namespace(self, namespace: MemoryNamespace, *, include_parent: bool = True) -> tuple[RelationTrace, ...]:
        keys = {namespace.key}
        if include_parent and namespace.session_id is not None:
            keys.add(namespace.parent().key)
        with self._lock:
            rows = [trace for trace in self._relations.values() if trace.namespace.key in keys]
        return tuple(sorted(rows, key=lambda item: (item.updated_at, item.relation_id), reverse=True))

    def touching(
        self,
        namespace: MemoryNamespace,
        card_ids: Sequence[str],
        *,
        include_parent: bool = True,
    ) -> tuple[RelationTrace, ...]:
        seeds = {require_id("card_id", item) for item in card_ids}
        if not seeds:
            return ()
        return tuple(
            trace
            for trace in self.list_namespace(namespace, include_parent=include_parent)
            if seeds.intersection(trace.card_ids)
        )

    def count(self) -> int:
        with self._lock:
            return len(self._relations)

    def _evict_one(self) -> None:
        if not self._relations:
            return
        victim = min(
            self._relations.values(),
            key=lambda trace: (
                trace.trust * 0.25
                + trace.salience * 0.20
                + min(1.0, math.log1p(trace.occurrence_count) / math.log(17.0)) * 0.30
                + trace.surprise_ema * 0.10
                + min(1.0, trace.prediction_hits / max(1, trace.prediction_attempts)) * 0.15,
                trace.updated_at,
                trace.relation_id,
            ),
        )
        self._relations.pop(victim.relation_id, None)


class RelationalMemoryIndex:
    """Fast relation graph over memory-game cards."""

    def __init__(
        self,
        cards: MemoryGameIndex,
        store: RelationStore | None = None,
        *,
        policy: RelationalMemoryPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(cards, MemoryGameIndex):
            raise TypeError("cards must be MemoryGameIndex")
        self.cards = cards
        self.policy = policy or RelationalMemoryPolicy()
        self.store = store or RelationStore(max_relations=self.policy.max_relations)
        self._clock = clock
        self._lock = threading.RLock()

    @staticmethod
    def _tokens(text: str) -> Counter[str]:
        token = ""
        result: Counter[str] = Counter()
        for char in (text or "").casefold():
            if char.isalnum() or char in _TOKEN_CHARS:
                token += char
            elif token:
                result[token] += 1
                token = ""
        if token:
            result[token] += 1
        return result

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(count * right.get(token, 0) for token, count in left.items())
        ln = math.sqrt(sum(value * value for value in left.values()))
        rn = math.sqrt(sum(value * value for value in right.values()))
        return 0.0 if not ln or not rn else max(0.0, min(1.0, dot / (ln * rn)))

    def _card(self, card_id: str) -> InteractionCard:
        card = self.cards.store.get(card_id)
        if card is None:
            raise RelationalMemoryError(f"unknown interaction card: {card_id}")
        return card

    @staticmethod
    def _canonical_ids(kind: RelationKind, card_ids: Sequence[str]) -> tuple[str, ...]:
        ids = tuple(require_id("card_id", item) for item in card_ids)
        return ids if kind in _ORDERED_KINDS else tuple(sorted(ids))

    def _relation_id(self, namespace: MemoryNamespace, kind: RelationKind, card_ids: Sequence[str]) -> str:
        ids = self._canonical_ids(kind, card_ids)
        return stable_id(
            "relation",
            {"namespace": namespace.key, "kind": kind.value, "cards": ids},
            length=32,
        )

    def link(
        self,
        namespace: MemoryNamespace,
        kind: RelationKind,
        card_ids: Sequence[str],
        *,
        trust: float = 0.65,
        salience: float = 0.55,
        surprise: float = 0.0,
        support_weight: float = 1.0,
        context_tags: Sequence[str] = (),
        provenance: Sequence[str] = (),
        rationale: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> RelationTrace:
        if not isinstance(namespace, MemoryNamespace):
            raise TypeError("namespace must be MemoryNamespace")
        if not isinstance(kind, RelationKind):
            kind = RelationKind(str(kind))
        ids = self._canonical_ids(kind, card_ids)
        for card_id in ids:
            card = self._card(card_id)
            valid_keys = {namespace.key}
            if namespace.session_id is not None:
                valid_keys.add(namespace.parent().key)
            if card.namespace.key not in valid_keys:
                raise RelationalMemoryError("cannot link cards outside the requested namespace")
        now = self._clock()
        relation_id = self._relation_id(namespace, kind, ids)
        trust_value = probability("relation trust", trust)
        salience_value = probability("relation salience", salience)
        surprise_value = probability("relation surprise", surprise)
        support_value = finite_number("support_weight", support_weight)
        if support_value <= 0:
            raise RelationalMemoryError("support_weight must be positive")
        tags = {str(tag).strip().casefold() for tag in context_tags if str(tag).strip()}
        prov = {str(item) for item in provenance if str(item)}

        with self._lock:
            existing = self.store.get(relation_id)
            if existing is None:
                return self.store.put(
                    RelationTrace(
                        relation_id=relation_id,
                        namespace=namespace,
                        kind=kind,
                        card_ids=ids,
                        created_at=now,
                        updated_at=now,
                        occurrence_count=1,
                        support_weight=support_value,
                        trust=trust_value,
                        salience=salience_value,
                        surprise_ema=surprise_value,
                        context_tags=tuple(tags),
                        provenance=tuple(prov),
                        rationale=rationale,
                        metadata=metadata or {},
                    )
                )
            updated = replace(
                existing,
                updated_at=now,
                occurrence_count=existing.occurrence_count + 1,
                support_weight=existing.support_weight + support_value,
                trust=max(existing.trust, trust_value),
                salience=max(existing.salience, salience_value),
                surprise_ema=0.85 * existing.surprise_ema + 0.15 * surprise_value,
                context_tags=tuple(sorted(set(existing.context_tags) | tags)),
                provenance=tuple(sorted(set(existing.provenance) | prov)),
                rationale=existing.rationale or rationale,
                metadata={**dict(existing.metadata), **dict(metadata or {})},
            )
            return self.store.put(updated)

    def predictions(
        self,
        namespace: MemoryNamespace,
        source_card_id: str,
        *,
        limit: int = 8,
        include_parent: bool = True,
    ) -> tuple[RelationPrediction, ...]:
        """Smoothed next-card distribution over successor types observed so far."""

        source = require_id("source_card_id", source_card_id)
        limit = positive_int("prediction limit", limit, maximum=1000)
        outgoing = [
            trace
            for trace in self.store.list_namespace(namespace, include_parent=include_parent)
            if trace.kind is RelationKind.SUCCESSION and trace.card_ids[0] == source
        ]
        if not outgoing:
            return ()
        alpha = self.policy.dirichlet_alpha
        total = sum(trace.support_weight for trace in outgoing)
        denominator = total + alpha * len(outgoing)
        probs = [(trace, (trace.support_weight + alpha) / denominator) for trace in outgoing]
        entropy_raw = -sum(p * math.log(max(_EPS, p)) for _, p in probs)
        entropy_max = math.log(len(probs)) if len(probs) > 1 else 1.0
        entropy = max(0.0, min(1.0, entropy_raw / entropy_max)) if len(probs) > 1 else 0.0
        result = [
            RelationPrediction(
                source_card_id=source,
                target_card_id=trace.card_ids[1],
                probability=p,
                support_count=trace.occurrence_count,
                support_weight=trace.support_weight,
                trust=trace.trust,
                conditional_entropy=entropy,
                closed_support=False,
            )
            for trace, p in probs
        ]
        result.sort(key=lambda item: (-item.probability, -item.support_count, item.target_card_id))
        return tuple(result[:limit])

    def transition_probability(
        self,
        namespace: MemoryNamespace,
        source_card_id: str,
        target_card_id: str,
    ) -> float:
        target = require_id("target_card_id", target_card_id)
        for item in self.predictions(namespace, source_card_id, limit=1000):
            if item.target_card_id == target:
                return item.probability
        return 0.0

    def record_transition(
        self,
        namespace: MemoryNamespace,
        source_card_id: str,
        observed_target_card_id: str,
        *,
        context_tags: Sequence[str] = (),
        trust: float = 0.70,
        salience: float = 0.60,
        provenance: Sequence[str] = (),
    ) -> TransitionFeedback:
        """Score a transition before learning the observed outcome."""

        source = require_id("source_card_id", source_card_id)
        target = require_id("observed_target_card_id", observed_target_card_id)
        existing_predictions = self.predictions(namespace, source, limit=1000)
        prediction_available = bool(existing_predictions)
        probability_before = next(
            (item.probability for item in existing_predictions if item.target_card_id == target),
            0.0,
        )
        if prediction_available and probability_before <= 0.0:
            outgoing_support = sum(item.support_weight for item in existing_predictions)
            k = len(existing_predictions)
            alpha = self.policy.dirichlet_alpha
            probability_before = alpha / (outgoing_support + alpha * (k + 1))
        if prediction_available:
            probability_before = max(_EPS, min(1.0, probability_before))
            surprise = min(1.0, -math.log(probability_before) / self.policy.surprisal_scale_nats)
            brier = (1.0 - probability_before) ** 2
        else:
            # No forecast existed, so there is no forecast error to score.
            probability_before = 0.5
            surprise = 0.0
            brier = 0.0

        with self._lock:
            for prediction in existing_predictions:
                relation_id = self._relation_id(
                    namespace,
                    RelationKind.SUCCESSION,
                    (source, prediction.target_card_id),
                )
                trace = self.store.get(relation_id)
                if trace is None:
                    continue
                actual = 1.0 if prediction.target_card_id == target else 0.0
                error = (actual - prediction.probability) ** 2
                self.store.put(
                    replace(
                        trace,
                        prediction_attempts=trace.prediction_attempts + 1,
                        prediction_hits=trace.prediction_hits + (1 if actual == 1.0 else 0),
                        prediction_error_ema=0.90 * trace.prediction_error_ema + 0.10 * min(1.0, error),
                    )
                )

        learned = self.link(
            namespace,
            RelationKind.SUCCESSION,
            (source, target),
            trust=trust,
            salience=salience,
            surprise=surprise,
            context_tags=context_tags,
            provenance=provenance,
            rationale="observed ordered interaction transition",
            metadata={"learned_from_prediction_scoring": True},
        )
        return TransitionFeedback(
            source_card_id=source,
            observed_target_card_id=target,
            predicted_probability=probability_before,
            surprise=surprise,
            brier_error=min(1.0, brier),
            prediction_available=prediction_available,
            relation_id=learned.relation_id,
            relation_fingerprint=learned.fingerprint,
        )

    def observe_sequence(
        self,
        namespace: MemoryNamespace,
        card_ids: Sequence[str],
        *,
        context_tags: Sequence[str] = (),
        surprise_by_transition: Sequence[float] = (),
        provenance: Sequence[str] = (),
    ) -> SequenceObservation:
        ids = tuple(require_id("card_id", item) for item in card_ids)
        if len(ids) < 2:
            raise RelationalMemoryError("observe_sequence needs at least two cards")
        for card_id in ids:
            self._card(card_id)

        surprises = tuple(probability("transition surprise", item) for item in surprise_by_transition)
        if surprises and len(surprises) != len(ids) - 1:
            raise RelationalMemoryError("surprise_by_transition must match pair count")

        created: list[str] = []
        boundaries: list[str] = []
        initial_predictions = self.predictions(namespace, ids[-2], limit=8)

        for index, (left, right) in enumerate(zip(ids, ids[1:])):
            surprise = surprises[index] if surprises else 0.0
            for kind, rationale in (
                (RelationKind.SUCCESSION, "observed temporal succession"),
                (RelationKind.ADJACENCY, "observed interaction adjacency"),
                (RelationKind.CO_OCCURRENCE, "observed local co-occurrence"),
            ):
                trace = self.link(
                    namespace,
                    kind,
                    (left, right),
                    context_tags=context_tags,
                    surprise=surprise,
                    provenance=provenance,
                    rationale=rationale,
                )
                created.append(trace.relation_id)
            if surprise >= self.policy.event_boundary_surprise:
                boundary = self.link(
                    namespace,
                    RelationKind.EVENT_BOUNDARY,
                    (left, right),
                    context_tags=context_tags,
                    surprise=surprise,
                    salience=max(0.70, surprise),
                    provenance=provenance,
                    rationale="high prediction-error transition marks candidate event boundary",
                    metadata={"prediction_error_boundary": True},
                )
                boundaries.append(boundary.relation_id)
                created.append(boundary.relation_id)

        for triple in zip(ids, ids[1:], ids[2:]):
            triad = self.link(
                namespace,
                RelationKind.TRIAD,
                triple,
                context_tags=context_tags,
                provenance=provenance,
                rationale="observed ordered three-card sequence",
            )
            created.append(triad.relation_id)
            if triple[0] == triple[2]:
                motif = self.link(
                    namespace,
                    RelationKind.MOTIF,
                    triple,
                    context_tags=context_tags,
                    salience=0.72,
                    provenance=provenance,
                    rationale="A-B-A recurrence motif",
                    metadata={"aba": True},
                )
                created.append(motif.relation_id)

        fingerprint = stable_fingerprint(
            {
                "namespace": namespace.key,
                "cards": ids,
                "created": sorted(set(created)),
                "boundaries": sorted(set(boundaries)),
                "predictions": [
                    (item.target_card_id, round(item.probability, 12))
                    for item in initial_predictions
                ],
            }
        )
        return SequenceObservation(
            created_relation_ids=tuple(dict.fromkeys(created)),
            event_boundary_ids=tuple(dict.fromkeys(boundaries)),
            transition_predictions=initial_predictions,
            fingerprint=fingerprint,
        )

    def observe_stream_step(
        self,
        namespace: MemoryNamespace,
        current_card_id: str,
        *,
        previous_card_ids: Sequence[str] = (),
        context_tags: Sequence[str] = (),
        provenance: Sequence[str] = (),
    ) -> SequenceObservation:
        """Learn one chronological interaction step without lookahead leakage.

        The immediate previous-card transition is scored first, then learned.
        Adjacency/co-occurrence, event-boundary state, and a length-three motif
        are added afterwards.  If the card index exposes the older associative
        mesh, the same observed sequence is mirrored there as the lower-level
        spreading-activation representation.
        """

        current = require_id("current_card_id", current_card_id)
        self._card(current)
        history = tuple(require_id("previous_card_id", item) for item in previous_card_ids if str(item))
        if not history:
            return SequenceObservation(
                created_relation_ids=(),
                event_boundary_ids=(),
                transition_predictions=(),
                fingerprint=stable_fingerprint(
                    {"namespace": namespace.key, "current": current, "history": ()}
                ),
            )
        for card_id in history:
            self._card(card_id)

        previous = history[-1]
        predictions_before = self.predictions(namespace, previous, limit=8)
        feedback = self.record_transition(
            namespace,
            previous,
            current,
            context_tags=context_tags,
            provenance=provenance,
        )
        created = [feedback.relation_id]
        boundaries: list[str] = []

        for kind, rationale in (
            (RelationKind.ADJACENCY, "observed neighboring interaction turns"),
            (RelationKind.CO_OCCURRENCE, "observed local interaction co-occurrence"),
        ):
            trace = self.link(
                namespace,
                kind,
                (previous, current),
                context_tags=context_tags,
                surprise=feedback.surprise,
                provenance=provenance,
                rationale=rationale,
            )
            created.append(trace.relation_id)

        if feedback.prediction_available and feedback.surprise >= self.policy.event_boundary_surprise:
            boundary = self.link(
                namespace,
                RelationKind.EVENT_BOUNDARY,
                (previous, current),
                context_tags=context_tags,
                surprise=feedback.surprise,
                salience=max(0.70, feedback.surprise),
                provenance=provenance,
                rationale="prequential transition surprise marks candidate event boundary",
                metadata={
                    "prediction_error_boundary": True,
                    "predicted_probability": feedback.predicted_probability,
                    "prediction_available": feedback.prediction_available,
                    "brier_error": feedback.brier_error,
                },
            )
            boundaries.append(boundary.relation_id)
            created.append(boundary.relation_id)

        if len(history) >= 2:
            triple = (history[-2], previous, current)
            triad = self.link(
                namespace,
                RelationKind.TRIAD,
                triple,
                context_tags=context_tags,
                surprise=feedback.surprise,
                provenance=provenance,
                rationale="observed ordered three-turn interaction",
            )
            created.append(triad.relation_id)
            if triple[0] == triple[2]:
                motif = self.link(
                    namespace,
                    RelationKind.MOTIF,
                    triple,
                    context_tags=context_tags,
                    salience=max(0.72, feedback.surprise),
                    surprise=feedback.surprise,
                    provenance=provenance,
                    rationale="A-B-A interaction recurrence motif",
                    metadata={"aba": True},
                )
                created.append(motif.relation_id)

        # Synchronize with the pre-existing associative mesh when available.
        # The mesh remains the cheap spreading-activation/ngram layer; this
        # class remains the typed/prequential relational layer.
        mesh = getattr(self.cards, "mesh", None)
        if mesh is not None and hasattr(mesh, "observe_sequence"):
            mesh.observe_sequence(
                namespace,
                (*history[-2:], current),
                evidence_ids=provenance,
                tags=context_tags,
            )

        return SequenceObservation(
            created_relation_ids=tuple(dict.fromkeys(created)),
            event_boundary_ids=tuple(dict.fromkeys(boundaries)),
            transition_predictions=predictions_before,
            fingerprint=stable_fingerprint(
                {
                    "namespace": namespace.key,
                    "history": history[-2:],
                    "current": current,
                    "predicted_probability": feedback.predicted_probability,
                    "prediction_available": feedback.prediction_available,
                    "surprise": feedback.surprise,
                    "brier": feedback.brier_error,
                    "created": sorted(set(created)),
                }
            ),
        )

    def _relation_text(self, trace: RelationTrace) -> tuple[str, tuple[str, ...]]:
        cards = [self._card(card_id) for card_id in trace.card_ids]
        arrow = " -> " if trace.ordered else " <-> "
        pieces = []
        evidence: set[str] = set(trace.provenance)
        for card in cards:
            text = card.content
            if len(text) > self.policy.maximum_card_chars:
                text = text[: self.policy.maximum_card_chars - 1] + "…"
            pieces.append(f"[{card.card_id}] {text}")
            evidence.update(card.provenance)
        content = (
            f"relation={trace.kind.value}; occurrences={trace.occurrence_count}; "
            f"cards={arrow.join(trace.card_ids)}\n" + "\n".join(pieces)
        )
        return content, tuple(sorted(evidence))

    def search(
        self,
        namespace: MemoryNamespace,
        query: str,
        seed_hits: Sequence[CardHit],
        *,
        context_tags: Sequence[str] = (),
        relation_kinds: Sequence[RelationKind] | None = None,
        limit: int | None = None,
        include_parent: bool = True,
    ) -> tuple[RelationalHit, ...]:
        if not seed_hits:
            return ()
        maximum = self.policy.maximum_hits if limit is None else positive_int("relation hit limit", limit, maximum=1000)
        seeds = tuple(hit.card.card_id for hit in seed_hits[: self.policy.maximum_seed_cards])
        seed_set = set(seeds)
        query_tokens = self._tokens(query)
        requested_tags = {str(tag).strip().casefold() for tag in context_tags if str(tag).strip()}
        kind_set = None if relation_kinds is None else {
            kind if isinstance(kind, RelationKind) else RelationKind(str(kind)) for kind in relation_kinds
        }
        now = self._clock()
        rows: list[RelationalHit] = []

        transition_cache: dict[str, dict[str, float]] = {}
        for source in seeds:
            transition_cache[source] = {
                item.target_card_id: item.probability
                for item in self.predictions(namespace, source, limit=1000, include_parent=include_parent)
            }

        for trace in self.store.touching(namespace, seeds, include_parent=include_parent):
            if kind_set is not None and trace.kind not in kind_set:
                continue
            cue_match = len(seed_set.intersection(trace.card_ids)) / len(trace.card_ids)
            content, evidence = self._relation_text(trace)
            lexical = self._cosine(query_tokens, self._tokens(content))
            support = min(1.0, math.log1p(trace.support_weight) / math.log(17.0))
            transition = 0.0
            if trace.kind is RelationKind.SUCCESSION and trace.card_ids[0] in transition_cache:
                transition = transition_cache[trace.card_ids[0]].get(trace.card_ids[1], 0.0)
            trace_tags = set(trace.context_tags)
            context_match = (
                len(requested_tags & trace_tags) / len(requested_tags)
                if requested_tags
                else 0.5
            )
            age = max(0.0, now - trace.updated_at)
            recency = math.exp(-math.log(2.0) * age / self.policy.half_life_seconds)
            surprise = min(1.0, 0.65 * trace.surprise_ema + 0.35 * trace.prediction_error_ema)
            score = (
                self.policy.cue_weight * cue_match
                + self.policy.lexical_weight * lexical
                + self.policy.support_weight * support
                + self.policy.transition_weight * transition
                + self.policy.context_weight * context_match
                + self.policy.trust_weight * trace.trust
                + self.policy.surprise_weight * surprise
                + self.policy.recency_weight * recency
            )
            score = max(0.0, min(1.0, score))
            if score < self.policy.minimum_score:
                continue
            confidence = min(
                1.0,
                0.35 * support
                + 0.25 * trace.trust
                + 0.20 * (1.0 - trace.prediction_error_ema)
                + 0.20 * max(transition, cue_match),
            )
            rows.append(
                RelationalHit(
                    trace=trace,
                    content=content,
                    score=score,
                    cue_match=cue_match,
                    lexical=lexical,
                    support=support,
                    transition_probability=transition,
                    context_match=context_match,
                    recency=recency,
                    retrieval_confidence=confidence,
                    evidence_ids=evidence,
                )
            )
        rows.sort(
            key=lambda hit: (
                hit.score,
                hit.transition_probability,
                hit.support,
                hit.trace.updated_at,
                hit.trace.relation_id,
            ),
            reverse=True,
        )
        return tuple(rows[:maximum])

    def register_semantic_pair(
        self,
        namespace: MemoryNamespace,
        left_card_id: str,
        right_card_id: str,
        *,
        relation: RelationKind,
        rationale: str,
        confidence: float,
        salience: float = 0.65,
        context_tags: Sequence[str] = (),
        provenance: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> RelationTrace:
        if relation not in {
            RelationKind.JUXTAPOSITION,
            RelationKind.CONTRAST,
            RelationKind.REINFORCEMENT,
            RelationKind.REVERSAL,
            RelationKind.ANALOGY,
            RelationKind.CAUSAL_CANDIDATE,
        }:
            raise RelationalMemoryError("register_semantic_pair requires a semantic relation kind")
        return self.link(
            namespace,
            relation,
            (left_card_id, right_card_id),
            trust=confidence,
            salience=salience,
            context_tags=context_tags,
            provenance=provenance,
            rationale=rationale,
            metadata={"semantic_hypothesis": True, **dict(metadata or {})},
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "policy": self.policy,
                "relation_count": self.store.count(),
                "card_index": self.cards.fingerprint,
            }
        )
