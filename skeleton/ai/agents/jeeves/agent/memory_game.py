"""Fast cue-card memory for Jeeves interaction acquisition.

This is the L0 memory layer: a bounded, namespace-scoped index of compact cards
queried before working memory and durable context.  It is inspired by results
from retrieval practice, storage-vs-retrieval strength models, activation-based
memory, and spaced repetition, but deliberately does not claim to reproduce a
specific human-memory theory or scheduler.

Cards are *retrieval aids*, not authoritative facts.  They retain provenance,
source trust, and acquisition diagnostics.  Durable promotion remains the job
of the existing memory/context evidence policies.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from .memory import MemoryNamespace
from .probability_lenses import memory_retrieval_probability
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

_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")


class MemoryGameError(AgentContractError):
    pass


def _bounded_history(values: Sequence[float], *, maximum: int = 64) -> tuple[float, ...]:
    normalized = tuple(finite_number("history timestamp", value) for value in values)
    if any(value < 0 for value in normalized):
        raise MemoryGameError("history timestamps must be non-negative")
    if tuple(sorted(normalized)) != normalized:
        raise MemoryGameError("history timestamps must be monotonic")
    return normalized[-maximum:]


@dataclass(frozen=True, slots=True)
class MemoryGamePolicy:
    max_cards: int = 100_000
    max_hits: int = 12
    activation_decay: float = 0.5
    activation_threshold: float = -0.25
    activation_noise: float = 0.85
    lexical_weight: float = 0.34
    retrieval_weight: float = 0.25
    context_weight: float = 0.12
    trust_weight: float = 0.12
    salience_weight: float = 0.08
    surprise_weight: float = 0.05
    recency_weight: float = 0.04
    minimum_score: float = 0.12
    minimum_fast_path_coverage: float = 0.66
    minimum_fast_path_confidence: float = 0.72

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_cards", positive_int("max_cards", self.max_cards, maximum=10_000_000))
        object.__setattr__(self, "max_hits", positive_int("max_hits", self.max_hits, maximum=1000))
        object.__setattr__(self, "activation_decay", finite_number("activation_decay", self.activation_decay))
        if not 0.0 < self.activation_decay <= 2.0:
            raise MemoryGameError("activation_decay must be in (0, 2]")
        object.__setattr__(self, "activation_threshold", finite_number("activation_threshold", self.activation_threshold))
        object.__setattr__(self, "activation_noise", finite_number("activation_noise", self.activation_noise))
        if self.activation_noise <= 0:
            raise MemoryGameError("activation_noise must be positive")
        weight_names = (
            "lexical_weight",
            "retrieval_weight",
            "context_weight",
            "trust_weight",
            "salience_weight",
            "surprise_weight",
            "recency_weight",
        )
        weights = [finite_number(name, getattr(self, name)) for name in weight_names]
        if any(value < 0 for value in weights) or sum(weights) <= 0:
            raise MemoryGameError("memory-game weights must be non-negative and non-zero")
        total = sum(weights)
        for name, value in zip(weight_names, weights):
            object.__setattr__(self, name, value / total)
        for name in ("minimum_score", "minimum_fast_path_coverage", "minimum_fast_path_confidence"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class InteractionCard:
    card_id: str
    namespace: MemoryNamespace
    content: str
    cue_tokens: tuple[str, ...]
    context_tags: tuple[str, ...]
    source: str
    created_at: float
    updated_at: float
    exposure_times: tuple[float, ...]
    recall_times: tuple[float, ...] = ()
    recall_attempts: int = 0
    recall_successes: int = 0
    storage_strength: float = 1.0
    difficulty: float = 0.5
    trust: float = 0.65
    salience: float = 0.5
    surprise_ema: float = 0.0
    prediction_error_ema: float = 0.0
    provenance: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "card_id", require_id("card_id", self.card_id))
        if not isinstance(self.namespace, MemoryNamespace):
            raise MemoryGameError("namespace must be MemoryNamespace")
        object.__setattr__(self, "content", bounded_text("card content", self.content, maximum=16_000))
        cues = tuple(sorted({str(token).casefold() for token in self.cue_tokens if str(token).strip()}))
        if not cues:
            raise MemoryGameError("interaction card requires at least one cue token")
        if len(cues) > 512 or any(len(token) > 128 for token in cues):
            raise MemoryGameError("invalid cue token set")
        object.__setattr__(self, "cue_tokens", cues)
        tags = tuple(sorted({str(tag).strip().casefold() for tag in self.context_tags if str(tag).strip()}))
        if len(tags) > 128 or any(len(tag) > 128 for tag in tags):
            raise MemoryGameError("invalid context tags")
        object.__setattr__(self, "context_tags", tags)
        object.__setattr__(self, "source", bounded_text("card source", self.source, maximum=512))
        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise MemoryGameError("invalid card timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        exposures = _bounded_history(self.exposure_times)
        recalls = _bounded_history(self.recall_times)
        if not exposures:
            raise MemoryGameError("interaction card requires an exposure trace")
        if exposures[0] < created - 1e-9:
            raise MemoryGameError("exposure predates card creation")
        object.__setattr__(self, "exposure_times", exposures)
        object.__setattr__(self, "recall_times", recalls)
        for name in ("recall_attempts", "recall_successes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise MemoryGameError(f"{name} must be a non-negative integer")
        if self.recall_successes > self.recall_attempts:
            raise MemoryGameError("recall successes exceed attempts")
        storage = finite_number("storage_strength", self.storage_strength)
        if storage < 0:
            raise MemoryGameError("storage_strength must be non-negative")
        object.__setattr__(self, "storage_strength", storage)
        for name in ("difficulty", "trust", "salience", "surprise_ema", "prediction_error_ema"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "provenance", tuple(sorted({str(item) for item in self.provenance if str(item)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def content_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace.key,
                "content": self.content,
                "source": self.source,
                "provenance": self.provenance,
            }
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "namespace": self.namespace.key,
            "content": self.content,
            "cue_tokens": list(self.cue_tokens),
            "context_tags": list(self.context_tags),
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "exposure_times": list(self.exposure_times),
            "recall_times": list(self.recall_times),
            "recall_attempts": self.recall_attempts,
            "recall_successes": self.recall_successes,
            "storage_strength": self.storage_strength,
            "difficulty": self.difficulty,
            "trust": self.trust,
            "salience": self.salience,
            "surprise_ema": self.surprise_ema,
            "prediction_error_ema": self.prediction_error_ema,
            "provenance": list(self.provenance),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CardHit:
    card: InteractionCard
    score: float
    lexical: float
    context_match: float
    activation: float
    retrieval_probability: float
    recency: float

    def __post_init__(self) -> None:
        for name in ("score", "lexical", "context_match", "retrieval_probability", "recency"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "activation", finite_number("activation", self.activation))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "card": self.card.card_id,
                "score": round(self.score, 12),
                "lexical": round(self.lexical, 12),
                "context": round(self.context_match, 12),
                "activation": round(self.activation, 12),
                "retrieval_probability": round(self.retrieval_probability, 12),
            }
        )


@dataclass(frozen=True, slots=True)
class RecallFeedback:
    card_id: str
    predicted_probability: float
    success: bool
    prediction_error: float
    surprise: float
    storage_delta: float
    updated_fingerprint: str


class IndexCardStore:
    """Thread-safe bounded store with namespace and content deduplication."""

    def __init__(self, *, max_cards: int = 100_000) -> None:
        self.max_cards = positive_int("max_cards", max_cards, maximum=10_000_000)
        self._cards: dict[str, InteractionCard] = {}
        self._fingerprints: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def put(self, card: InteractionCard) -> InteractionCard:
        if not isinstance(card, InteractionCard):
            raise TypeError("card must be InteractionCard")
        key = (card.namespace.key, card.content_fingerprint)
        with self._lock:
            duplicate = self._fingerprints.get(key)
            if duplicate is not None and duplicate != card.card_id:
                return self._cards[duplicate]
            if card.card_id not in self._cards and len(self._cards) >= self.max_cards:
                self._evict_one()
            previous = self._cards.get(card.card_id)
            if previous is not None:
                self._fingerprints.pop((previous.namespace.key, previous.content_fingerprint), None)
            self._cards[card.card_id] = card
            self._fingerprints[key] = card.card_id
            return card

    def get(self, card_id: str) -> InteractionCard | None:
        with self._lock:
            return self._cards.get(require_id("card_id", card_id))

    def namespace_cards(self, namespace: MemoryNamespace, *, include_parent: bool = True) -> tuple[InteractionCard, ...]:
        keys = {namespace.key}
        if include_parent and namespace.session_id is not None:
            keys.add(namespace.parent().key)
        with self._lock:
            cards = [card for card in self._cards.values() if card.namespace.key in keys]
        return tuple(sorted(cards, key=lambda card: (card.updated_at, card.card_id), reverse=True))

    def count(self) -> int:
        with self._lock:
            return len(self._cards)

    def _evict_one(self) -> None:
        if not self._cards:
            return
        victim = min(
            self._cards.values(),
            key=lambda card: (
                card.storage_strength * 0.30
                + card.trust * 0.25
                + card.salience * 0.15
                + min(1.0, card.recall_successes / 8.0) * 0.15
                + card.surprise_ema * 0.15,
                card.updated_at,
                card.card_id,
            ),
        )
        self._cards.pop(victim.card_id, None)
        self._fingerprints.pop((victim.namespace.key, victim.content_fingerprint), None)


class MemoryGameIndex:
    """L0 interaction-memory index with retrieval practice feedback."""

    def __init__(
        self,
        store: IndexCardStore | None = None,
        *,
        policy: MemoryGamePolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or MemoryGamePolicy()
        self.store = store or IndexCardStore(max_cards=self.policy.max_cards)
        self._clock = clock
        self._lock = threading.RLock()

    @staticmethod
    def _tokens(text: str) -> Counter[str]:
        return Counter(token.casefold() for token in _TOKEN_RE.findall(text or ""))

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(count * right.get(token, 0) for token, count in left.items())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return max(0.0, min(1.0, dot / (left_norm * right_norm)))

    def capture_interaction(
        self,
        namespace: MemoryNamespace,
        content: str,
        *,
        context_tags: Sequence[str] = (),
        source: str = "user-interaction",
        trust: float = 0.65,
        salience: float = 0.65,
        surprise: float = 0.0,
        provenance: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> InteractionCard:
        if not isinstance(namespace, MemoryNamespace):
            raise TypeError("namespace must be MemoryNamespace")
        text = bounded_text("interaction content", content, maximum=16_000)
        now = self._clock()
        tokens = tuple(sorted(self._tokens(text)))
        payload = {"namespace": namespace.key, "content": text.casefold(), "source": source}
        card_id = stable_id("card", payload, length=32)
        with self._lock:
            existing = self.store.get(card_id)
            if existing is not None:
                traces = _bounded_history((*existing.exposure_times, now))
                merged_tags = tuple(sorted(set(existing.context_tags) | {str(tag).strip().casefold() for tag in context_tags if str(tag).strip()}))
                merged_provenance = tuple(sorted(set(existing.provenance) | {str(item) for item in provenance if str(item)}))
                # Re-exposure grows storage, but with diminishing returns.
                storage_delta = 1.0 / math.sqrt(1.0 + len(existing.exposure_times))
                updated = replace(
                    existing,
                    updated_at=now,
                    exposure_times=traces,
                    context_tags=merged_tags,
                    provenance=merged_provenance,
                    storage_strength=existing.storage_strength + storage_delta,
                    trust=max(existing.trust, probability("trust", trust)),
                    salience=max(existing.salience, probability("salience", salience)),
                    surprise_ema=0.8 * existing.surprise_ema + 0.2 * probability("surprise", surprise),
                    metadata={**dict(existing.metadata), **dict(metadata or {})},
                )
                return self.store.put(updated)
            card = InteractionCard(
                card_id=card_id,
                namespace=namespace,
                content=text,
                cue_tokens=tokens,
                context_tags=tuple(context_tags),
                source=source,
                created_at=now,
                updated_at=now,
                exposure_times=(now,),
                storage_strength=1.0,
                difficulty=0.5,
                trust=trust,
                salience=salience,
                surprise_ema=surprise,
                prediction_error_ema=0.0,
                provenance=tuple(provenance),
                metadata=metadata or {},
            )
            return self.store.put(card)

    def activation(self, card: InteractionCard, *, now: float | None = None) -> float:
        current = self._clock() if now is None else finite_number("now", now)
        traces = [max(1.0, current - timestamp) for timestamp in card.exposure_times]
        base = math.log(sum(age ** (-self.policy.activation_decay) for age in traces))
        practice = math.log1p(card.recall_successes) * 0.18
        storage = math.log1p(card.storage_strength) * 0.22
        difficulty_penalty = card.difficulty * 0.45
        return base + practice + storage - difficulty_penalty

    def predicted_retrieval(self, card: InteractionCard, *, now: float | None = None) -> float:
        activation = self.activation(card, now=now)
        assessment = memory_retrieval_probability(
            activation,
            threshold=self.policy.activation_threshold,
            noise_scale=self.policy.activation_noise,
            storage_strength=card.storage_strength,
            provenance=(card.card_id,),
        )
        assert assessment.estimate is not None
        return assessment.estimate

    def search(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        limit: int | None = None,
        include_parent: bool = True,
        minimum_score: float | None = None,
    ) -> tuple[CardHit, ...]:
        limit_value = self.policy.max_hits if limit is None else positive_int("limit", limit, maximum=1000)
        floor = self.policy.minimum_score if minimum_score is None else probability("minimum_score", minimum_score)
        query_tokens = self._tokens(query)
        requested_tags = {str(tag).strip().casefold() for tag in context_tags if str(tag).strip()}
        now = self._clock()
        hits: list[CardHit] = []
        for card in self.store.namespace_cards(namespace, include_parent=include_parent):
            card_tokens = Counter({token: 1 for token in card.cue_tokens})
            lexical = self._cosine(query_tokens, card_tokens)
            card_tags = set(card.context_tags)
            context_match = (
                len(requested_tags & card_tags) / len(requested_tags)
                if requested_tags
                else 0.5
            )
            activation = self.activation(card, now=now)
            retrieval = self.predicted_retrieval(card, now=now)
            age = max(0.0, now - card.updated_at)
            recency = math.exp(-math.log(2.0) * age / (7.0 * 24.0 * 3600.0))
            surprise_signal = min(1.0, 0.65 * card.surprise_ema + 0.35 * card.prediction_error_ema)
            score = (
                self.policy.lexical_weight * lexical
                + self.policy.retrieval_weight * retrieval
                + self.policy.context_weight * context_match
                + self.policy.trust_weight * card.trust
                + self.policy.salience_weight * card.salience
                + self.policy.surprise_weight * surprise_signal
                + self.policy.recency_weight * recency
            )
            score = max(0.0, min(1.0, score))
            if score >= floor:
                hits.append(CardHit(card, score, lexical, context_match, activation, retrieval, recency))
        hits.sort(key=lambda hit: (hit.score, hit.retrieval_probability, hit.card.updated_at, hit.card.card_id), reverse=True)
        return tuple(hits[:limit_value])

    def coverage(self, query: str, hits: Sequence[CardHit]) -> float:
        query_tokens = set(self._tokens(query))
        if not query_tokens:
            return 0.0
        covered: set[str] = set()
        for hit in hits:
            if hit.score < self.policy.minimum_score:
                continue
            covered.update(query_tokens & set(hit.card.cue_tokens))
        return len(covered) / len(query_tokens)

    def fast_path_ready(self, query: str, hits: Sequence[CardHit]) -> bool:
        if not hits:
            return False
        coverage = self.coverage(query, hits)
        weighted = sum(hit.score * hit.retrieval_probability for hit in hits) / len(hits)
        return (
            coverage >= self.policy.minimum_fast_path_coverage
            and weighted >= self.policy.minimum_fast_path_confidence
        )

    def record_feedback(
        self,
        card_id: str,
        *,
        success: bool,
        predicted_probability: float | None = None,
        surprise: float | None = None,
    ) -> RecallFeedback:
        with self._lock:
            card = self.store.get(card_id)
            if card is None:
                raise MemoryGameError("unknown card")
            now = self._clock()
            predicted = self.predicted_retrieval(card, now=now) if predicted_probability is None else probability("predicted_probability", predicted_probability)
            actual = 1.0 if bool(success) else 0.0
            error = abs(actual - predicted)
            event_surprise = (
                -math.log(max(_EPS, predicted if success else 1.0 - predicted)) / 27.631021115928547
            )
            event_surprise = max(0.0, min(1.0, event_surprise))
            if surprise is not None:
                event_surprise = max(event_surprise, probability("surprise", surprise))
            attempts = card.recall_attempts + 1
            successes = card.recall_successes + (1 if success else 0)
            # Difficult successful retrieval is valuable acquisition. Failure
            # raises difficulty and triggers deeper context routing upstream.
            if success:
                storage_delta = 0.25 + 0.75 * (1.0 - predicted)
                difficulty = max(0.0, card.difficulty - 0.04 * (1.0 - predicted))
                exposures = _bounded_history((*card.exposure_times, now))
                recall_times = _bounded_history((*card.recall_times, now))
            else:
                storage_delta = 0.0
                difficulty = min(1.0, card.difficulty + 0.10 * predicted + 0.03)
                exposures = card.exposure_times
                recall_times = _bounded_history((*card.recall_times, now))
            updated = replace(
                card,
                updated_at=now,
                exposure_times=exposures,
                recall_times=recall_times,
                recall_attempts=attempts,
                recall_successes=successes,
                storage_strength=card.storage_strength + storage_delta,
                difficulty=difficulty,
                prediction_error_ema=0.85 * card.prediction_error_ema + 0.15 * error,
                surprise_ema=0.85 * card.surprise_ema + 0.15 * event_surprise,
            )
            updated = self.store.put(updated)
            return RecallFeedback(
                card_id=card_id,
                predicted_probability=predicted,
                success=bool(success),
                prediction_error=error,
                surprise=event_surprise,
                storage_delta=storage_delta,
                updated_fingerprint=stable_fingerprint(updated.as_json()),
            )

    @property
    def fingerprint(self) -> str:
        rows = [card.as_json() for card in self.store.namespace_cards(MemoryNamespace("system", "system"), include_parent=False)]
        # The store is intentionally namespace-partitioned; global state is not
        # exposed through public iteration.  Policy identity is still useful
        # for deterministic configuration fingerprints.
        return stable_fingerprint({"policy": self.policy, "sentinel_rows": rows})
