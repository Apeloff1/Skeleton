"""Associative L0 memory mesh layered over Jeeves index cards.

``MemoryGameIndex`` already gives Jeeves a fast cue-card layer ahead of durable
memory and context stores. This module adds the missing relational machinery:
items can be remembered by what preceded them, what followed them, what was
juxtaposed with them, which context changed their interpretation, and which
short sequences repeatedly co-occurred.

The mesh is deliberately *non-authoritative*. Association strength changes
retrieval order, never factual trust. Cross-user edges are impossible because
every edge and n-gram is namespace scoped. Deep stores remain responsible for
provenance, evidence and durable semantic promotion.

Critically, relation observation is not retrieval validation. ``observations``
counts how often a relation was seen; ``tested_retrievals`` counts occasions on
which the relation actually participated in a retrieval test. Untested evidence
therefore remains neutral rather than being silently counted as failure.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .memory import MemoryNamespace
from .memory_game import CardHit, InteractionCard, MemoryGameIndex
from .probability_frontier import retrieval_competition_probability
from .types import AgentContractError, finite_number, json_safe, positive_int, probability, stable_fingerprint, stable_id


class AssociationKind(str, Enum):
    TEMPORAL_FORWARD = "temporal_forward"
    TEMPORAL_BACKWARD = "temporal_backward"
    JUXTAPOSITION = "juxtaposition"
    CONTEXT_SHIFT = "context_shift"
    CONTRAST = "contrast"
    CORRECTION = "correction"
    TASK_SEQUENCE = "task_sequence"
    USER_PREFERENCE = "user_preference"
    CAUSAL_CANDIDATE = "causal_candidate"


@dataclass(frozen=True, slots=True)
class MemoryAssociation:
    association_id: str
    namespace: MemoryNamespace
    source_card_id: str
    target_card_id: str
    kind: AssociationKind
    created_at: float
    updated_at: float
    observations: int = 1
    tested_retrievals: int = 0
    successes: int = 0
    strength: float = 0.5
    surprise_ema: float = 0.0
    direction_confidence: float = 0.5
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, MemoryNamespace):
            raise AgentContractError("association namespace must be MemoryNamespace")
        for name in ("association_id", "source_card_id", "target_card_id"):
            if not str(getattr(self, name)).strip():
                raise AgentContractError(f"{name} is required")
        if self.source_card_id == self.target_card_id:
            raise AgentContractError("self-association is not allowed")
        if not isinstance(self.kind, AssociationKind):
            object.__setattr__(self, "kind", AssociationKind(str(self.kind)))
        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise AgentContractError("invalid association timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        if isinstance(self.observations, bool) or not isinstance(self.observations, int) or self.observations <= 0:
            raise AgentContractError("association observations must be positive")
        if isinstance(self.tested_retrievals, bool) or not isinstance(self.tested_retrievals, int) or self.tested_retrievals < 0:
            raise AgentContractError("tested_retrievals must be non-negative")
        if self.tested_retrievals > self.observations:
            raise AgentContractError("tested_retrievals cannot exceed observations")
        if isinstance(self.successes, bool) or not isinstance(self.successes, int) or self.successes < 0:
            raise AgentContractError("successes must be non-negative")
        if self.successes > self.tested_retrievals:
            raise AgentContractError("successes cannot exceed tested_retrievals")
        for name in ("strength", "surprise_ema", "direction_confidence"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "tags", tuple(sorted({str(x).strip().casefold() for x in self.tags if str(x).strip()})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def retrieval_success_probability(self) -> float:
        if self.tested_retrievals == 0:
            return 0.5
        return (self.successes + 1.0) / (self.tested_retrievals + 2.0)

    @property
    def posterior_strength(self) -> float:
        # Relation strength and measured retrieval utility are distinct signals.
        # Untested retrievals remain neutral at 0.5 rather than becoming failures.
        empirical = self.retrieval_success_probability
        return max(0.0, min(1.0, 0.55 * self.strength + 0.45 * empirical))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace.key,
                "source": self.source_card_id,
                "target": self.target_card_id,
                "kind": self.kind.value,
                "observations": self.observations,
                "tested_retrievals": self.tested_retrievals,
                "successes": self.successes,
                "strength": self.strength,
                "surprise": self.surprise_ema,
                "direction": self.direction_confidence,
                "evidence": self.evidence_ids,
                "tags": self.tags,
            }
        )


@dataclass(frozen=True, slots=True)
class AssociationHit:
    association: MemoryAssociation
    score: float
    recency: float
    posterior_strength: float

    def __post_init__(self) -> None:
        for name in ("score", "recency", "posterior_strength"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class SequencePrediction:
    namespace_key: str
    prefix: tuple[str, ...]
    candidates: tuple[tuple[str, float], ...]
    entropy_bits: float
    evidence_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AssociationPolicy:
    max_associations: int = 500_000
    max_neighbors: int = 12
    recency_half_life_seconds: float = 30 * 24 * 3600
    strength_weight: float = 0.55
    recency_weight: float = 0.15
    frequency_weight: float = 0.15
    surprise_weight: float = 0.10
    direction_weight: float = 0.05
    association_boost_cap: float = 0.28
    minimum_seed_lexical: float = 0.05
    ngram_max_order: int = 3

    def __post_init__(self) -> None:
        for name in ("max_associations", "max_neighbors", "ngram_max_order"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=10_000_000))
        half_life = finite_number("recency_half_life_seconds", self.recency_half_life_seconds)
        if half_life <= 0:
            raise AgentContractError("recency_half_life_seconds must be positive")
        object.__setattr__(self, "recency_half_life_seconds", half_life)
        names = ("strength_weight", "recency_weight", "frequency_weight", "surprise_weight", "direction_weight")
        values = [finite_number(name, getattr(self, name)) for name in names]
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise AgentContractError("association scoring weights must be non-negative and non-zero")
        total = sum(values)
        for name, value in zip(names, values):
            object.__setattr__(self, name, value / total)
        object.__setattr__(self, "association_boost_cap", probability("association_boost_cap", self.association_boost_cap))
        object.__setattr__(self, "minimum_seed_lexical", probability("minimum_seed_lexical", self.minimum_seed_lexical))
        if self.ngram_max_order < 2 or self.ngram_max_order > 5:
            raise AgentContractError("ngram_max_order must be in [2, 5]")


class AssociativeMemoryMesh:
    """Namespace-scoped graph plus short-sequence index."""

    def __init__(self, *, policy: AssociationPolicy | None = None, clock: Callable[[], float] = time.time) -> None:
        self.policy = policy or AssociationPolicy()
        self._clock = clock
        self._edges: dict[str, MemoryAssociation] = {}
        self._outgoing: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
        self._ngrams: Counter[tuple[str, tuple[str, ...]]] = Counter()
        self._lock = threading.RLock()

    @staticmethod
    def _edge_id(namespace: MemoryNamespace, source: str, target: str, kind: AssociationKind) -> str:
        return stable_id(
            "memory-edge",
            {"namespace": namespace.key, "source": source, "target": target, "kind": kind.value},
            length=32,
        )

    def observe(
        self,
        namespace: MemoryNamespace,
        source_card_id: str,
        target_card_id: str,
        *,
        kind: AssociationKind,
        strength: float = 0.5,
        success: bool | None = None,
        surprise: float = 0.0,
        direction_confidence: float = 0.7,
        evidence_ids: Sequence[str] = (),
        tags: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryAssociation:
        if not isinstance(namespace, MemoryNamespace):
            raise TypeError("namespace must be MemoryNamespace")
        if not isinstance(kind, AssociationKind):
            kind = AssociationKind(str(kind))
        strength = probability("strength", strength)
        surprise = probability("surprise", surprise)
        direction_confidence = probability("direction_confidence", direction_confidence)
        edge_id = self._edge_id(namespace, source_card_id, target_card_id, kind)
        now = self._clock()
        with self._lock:
            existing = self._edges.get(edge_id)
            if existing is None:
                if len(self._edges) >= self.policy.max_associations:
                    self._evict_one()
                association = MemoryAssociation(
                    association_id=edge_id,
                    namespace=namespace,
                    source_card_id=source_card_id,
                    target_card_id=target_card_id,
                    kind=kind,
                    created_at=now,
                    updated_at=now,
                    observations=1,
                    tested_retrievals=1 if success is not None else 0,
                    successes=1 if success is True else 0,
                    strength=strength,
                    surprise_ema=surprise,
                    direction_confidence=direction_confidence,
                    evidence_ids=tuple(evidence_ids),
                    tags=tuple(tags),
                    metadata=metadata or {},
                )
            else:
                observations = existing.observations + 1
                tested = existing.tested_retrievals + (1 if success is not None else 0)
                successes = existing.successes + (1 if success is True else 0)
                rate = min(0.25, 1.0 / math.sqrt(observations))
                association = replace(
                    existing,
                    updated_at=now,
                    observations=observations,
                    tested_retrievals=tested,
                    successes=successes,
                    strength=(1.0 - rate) * existing.strength + rate * strength,
                    surprise_ema=0.85 * existing.surprise_ema + 0.15 * surprise,
                    direction_confidence=max(existing.direction_confidence, direction_confidence),
                    evidence_ids=tuple(sorted(set(existing.evidence_ids) | {str(x) for x in evidence_ids if str(x)})),
                    tags=tuple(sorted(set(existing.tags) | {str(x).strip().casefold() for x in tags if str(x).strip()})),
                    metadata={**dict(existing.metadata), **dict(metadata or {})},
                )
            self._edges[edge_id] = association
            self._outgoing[(namespace.key, source_card_id)].add(edge_id)
            return association

    def observe_sequence(
        self,
        namespace: MemoryNamespace,
        card_ids: Sequence[str],
        *,
        kind: AssociationKind = AssociationKind.TEMPORAL_FORWARD,
        evidence_ids: Sequence[str] = (),
        tags: Sequence[str] = (),
    ) -> tuple[MemoryAssociation, ...]:
        ids = tuple(str(item) for item in card_ids if str(item))
        if len(ids) < 2 or len(set(ids)) < 2:
            return ()
        edges: list[MemoryAssociation] = []
        for left, right in zip(ids, ids[1:]):
            edges.append(
                self.observe(
                    namespace,
                    left,
                    right,
                    kind=kind,
                    strength=0.65,
                    direction_confidence=0.85,
                    evidence_ids=evidence_ids,
                    tags=tags,
                    metadata={"sequence": True},
                )
            )
            edges.append(
                self.observe(
                    namespace,
                    right,
                    left,
                    kind=AssociationKind.TEMPORAL_BACKWARD,
                    strength=0.35,
                    direction_confidence=0.65,
                    evidence_ids=evidence_ids,
                    tags=tags,
                    metadata={"sequence": True, "reverse": True},
                )
            )
        with self._lock:
            for order in range(2, min(self.policy.ngram_max_order, len(ids)) + 1):
                for start in range(0, len(ids) - order + 1):
                    gram = ids[start : start + order]
                    self._ngrams[(namespace.key, gram)] += 1
        return tuple(edges)

    def observe_higher_order_sequence(
        self,
        namespace: MemoryNamespace,
        card_ids: Sequence[str],
        *,
        minimum_order: int = 3,
    ) -> int:
        """Record higher-order n-grams without replaying pairwise graph edges.

        observe_sequence remains the authoritative path for adjacent temporal
        edges and order-2 n-grams. This edge-free path lets a streaming
        acquisition loop extend order-3+ sequence memory without artificially
        inflating pair frequencies each time the rolling window grows.
        """
        if not isinstance(namespace, MemoryNamespace):
            raise TypeError("namespace must be MemoryNamespace")
        minimum = positive_int("minimum_order", minimum_order, maximum=5)
        if minimum < 3:
            raise AgentContractError("higher-order sequence minimum_order must be at least 3")
        ids = tuple(str(item) for item in card_ids if str(item))
        maximum = min(self.policy.ngram_max_order, len(ids))
        if maximum < minimum:
            return 0
        updates = 0
        with self._lock:
            for order in range(minimum, maximum + 1):
                for start in range(0, len(ids) - order + 1):
                    gram = ids[start : start + order]
                    self._ngrams[(namespace.key, gram)] += 1
                    updates += 1
        return updates

    def observe_juxtaposition(
        self,
        namespace: MemoryNamespace,
        left_card_id: str,
        right_card_id: str,
        *,
        changed_interpretation: bool,
        evidence_ids: Sequence[str] = (),
        tags: Sequence[str] = (),
    ) -> tuple[MemoryAssociation, MemoryAssociation]:
        strength = 0.80 if changed_interpretation else 0.35
        surprise = 0.65 if changed_interpretation else 0.15
        common = {
            "kind": AssociationKind.JUXTAPOSITION,
            "strength": strength,
            "success": None,
            "surprise": surprise,
            "direction_confidence": 0.55,
            "evidence_ids": evidence_ids,
            "tags": tuple(tags) + ("juxtaposition",),
            "metadata": {
                "interpretation_changed": bool(changed_interpretation),
                "symmetric_pair": True,
                "retrieval_test": False,
            },
        }
        left = self.observe(namespace, left_card_id, right_card_id, **common)
        right = self.observe(namespace, right_card_id, left_card_id, **common)
        return left, right

    def neighbors(
        self,
        namespace: MemoryNamespace,
        source_card_id: str,
        *,
        kinds: Sequence[AssociationKind] = (),
        limit: int | None = None,
    ) -> tuple[AssociationHit, ...]:
        limit_value = self.policy.max_neighbors if limit is None else positive_int("limit", limit, maximum=1000)
        kind_set = {kind if isinstance(kind, AssociationKind) else AssociationKind(str(kind)) for kind in kinds}
        now = self._clock()
        with self._lock:
            ids = tuple(self._outgoing.get((namespace.key, source_card_id), ()))
            edges = [self._edges[edge_id] for edge_id in ids]
        hits: list[AssociationHit] = []
        for edge in edges:
            if kind_set and edge.kind not in kind_set:
                continue
            age = max(0.0, now - edge.updated_at)
            recency = math.exp(-math.log(2.0) * age / self.policy.recency_half_life_seconds)
            frequency = 1.0 - math.exp(-edge.observations / 4.0)
            posterior = edge.posterior_strength
            score = (
                self.policy.strength_weight * posterior
                + self.policy.recency_weight * recency
                + self.policy.frequency_weight * frequency
                + self.policy.surprise_weight * edge.surprise_ema
                + self.policy.direction_weight * edge.direction_confidence
            )
            hits.append(AssociationHit(edge, max(0.0, min(1.0, score)), recency, posterior))
        hits.sort(
            key=lambda item: (
                item.score,
                item.association.observations,
                item.association.updated_at,
                item.association.association_id,
            ),
            reverse=True,
        )
        return tuple(hits[:limit_value])

    def predict_next(self, namespace: MemoryNamespace, prefix: Sequence[str], *, limit: int = 8) -> SequencePrediction:
        limit = positive_int("limit", limit, maximum=1000)
        prefix_ids = tuple(str(item) for item in prefix if str(item))
        if not prefix_ids:
            raise AgentContractError("prediction prefix cannot be empty")
        use_prefix = prefix_ids[-(self.policy.ngram_max_order - 1) :]
        counts: Counter[str] = Counter()
        evidence = 0
        with self._lock:
            for (namespace_key, gram), count in self._ngrams.items():
                if namespace_key != namespace.key or len(gram) < 2:
                    continue
                gram_prefix = gram[:-1]
                if len(gram_prefix) > len(use_prefix):
                    continue
                if tuple(use_prefix[-len(gram_prefix) :]) == gram_prefix:
                    counts[gram[-1]] += count
                    evidence += count
        if not counts:
            return SequencePrediction(
                namespace.key,
                use_prefix,
                (),
                0.0,
                0,
                stable_fingerprint((namespace.key, use_prefix, ())),
            )
        total = sum(counts.values())
        ranked = tuple((card_id, count / total) for card_id, count in counts.most_common(limit))
        normalized = [count / total for count in counts.values()]
        entropy = -sum(value * math.log2(value) for value in normalized if value > 0)
        return SequencePrediction(
            namespace_key=namespace.key,
            prefix=use_prefix,
            candidates=ranked,
            entropy_bits=entropy,
            evidence_count=evidence,
            fingerprint=stable_fingerprint(
                {"namespace": namespace.key, "prefix": use_prefix, "counts": sorted(counts.items())}
            ),
        )

    def record_retrieval_outcome(
        self,
        namespace: MemoryNamespace,
        source_card_id: str,
        chosen_target_id: str,
        *,
        success: bool,
    ) -> tuple[MemoryAssociation, ...]:
        updated: list[MemoryAssociation] = []
        for hit in self.neighbors(namespace, source_card_id, limit=self.policy.max_neighbors):
            edge = hit.association
            if edge.target_card_id != chosen_target_id:
                continue
            updated.append(
                self.observe(
                    namespace,
                    edge.source_card_id,
                    edge.target_card_id,
                    kind=edge.kind,
                    strength=edge.strength,
                    success=success,
                    surprise=abs((1.0 if success else 0.0) - hit.posterior_strength),
                    direction_confidence=edge.direction_confidence,
                    evidence_ids=edge.evidence_ids,
                    tags=edge.tags,
                    metadata={**dict(edge.metadata), "retrieval_test": True},
                )
            )
        return tuple(updated)

    def _evict_one(self) -> None:
        if not self._edges:
            return
        victim = min(
            self._edges.values(),
            key=lambda edge: (edge.posterior_strength, edge.observations, edge.updated_at, edge.association_id),
        )
        self._edges.pop(victim.association_id, None)
        self._outgoing[(victim.namespace.key, victim.source_card_id)].discard(victim.association_id)

    @property
    def fingerprint(self) -> str:
        with self._lock:
            edges = [(key, edge.fingerprint) for key, edge in sorted(self._edges.items())]
            grams = [(namespace, gram, count) for (namespace, gram), count in sorted(self._ngrams.items())]
        return stable_fingerprint({"edges": edges, "ngrams": grams})


class AssociativeMemoryGameIndex(MemoryGameIndex):
    """Drop-in L0 index that augments direct cue hits with learned neighbors."""

    def __init__(
        self,
        *args: Any,
        mesh: AssociativeMemoryMesh | None = None,
        association_policy: AssociationPolicy | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.mesh = mesh or AssociativeMemoryMesh(policy=association_policy, clock=self._clock)
        self.association_policy = self.mesh.policy

    def capture_sequence(
        self,
        namespace: MemoryNamespace,
        contents: Sequence[str],
        *,
        context_tags: Sequence[str] = (),
        source: str = "user-interaction",
        trust: float = 0.65,
        salience: float = 0.65,
        provenance: Sequence[str] = (),
    ) -> tuple[InteractionCard, ...]:
        cards = tuple(
            self.capture_interaction(
                namespace,
                content,
                context_tags=context_tags,
                source=source,
                trust=trust,
                salience=salience,
                provenance=provenance,
                metadata={"captured_as_sequence": True},
            )
            for content in contents
        )
        self.mesh.observe_sequence(
            namespace,
            [card.card_id for card in cards],
            kind=AssociationKind.TEMPORAL_FORWARD,
            evidence_ids=provenance,
            tags=context_tags,
        )
        return cards

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
        direct = list(
            super().search(
                namespace,
                query,
                context_tags=context_tags,
                limit=limit_value,
                include_parent=include_parent,
                minimum_score=minimum_score,
            )
        )
        by_id: dict[str, CardHit] = {hit.card.card_id: hit for hit in direct}
        query_tokens = self._tokens(query)
        requested_tags = {str(tag).strip().casefold() for tag in context_tags if str(tag).strip()}
        now = self._clock()

        seeds = [
            hit
            for hit in direct
            if hit.lexical >= self.association_policy.minimum_seed_lexical or hit.context_match > 0.5
        ]
        allowed_namespaces = {namespace.key}
        if namespace.session_id:
            allowed_namespaces.add(namespace.parent().key)
        for seed in seeds[:4]:
            for relation in self.mesh.neighbors(
                namespace,
                seed.card.card_id,
                limit=self.association_policy.max_neighbors,
            ):
                card = self.store.get(relation.association.target_card_id)
                if card is None or card.namespace.key not in allowed_namespaces:
                    continue
                card_tokens = Counter({token: 1 for token in card.cue_tokens})
                lexical = self._cosine(query_tokens, card_tokens)
                card_tags = set(card.context_tags)
                context_match = (
                    len(requested_tags & card_tags) / len(requested_tags) if requested_tags else 0.5
                )
                activation = self.activation(card, now=now)
                retrieval = self.predicted_retrieval(card, now=now)
                age = max(0.0, now - card.updated_at)
                recency = math.exp(-math.log(2.0) * age / (7.0 * 24.0 * 3600.0))
                native = (
                    self.policy.lexical_weight * lexical
                    + self.policy.retrieval_weight * retrieval
                    + self.policy.context_weight * context_match
                    + self.policy.trust_weight * card.trust
                    + self.policy.salience_weight * card.salience
                    + self.policy.surprise_weight
                    * min(1.0, 0.65 * card.surprise_ema + 0.35 * card.prediction_error_ema)
                    + self.policy.recency_weight * recency
                )
                association_boost = min(
                    self.association_policy.association_boost_cap,
                    self.association_policy.association_boost_cap * seed.score * relation.score,
                )
                score = max(0.0, min(1.0, native + association_boost))
                candidate = CardHit(card, score, lexical, context_match, activation, retrieval, recency)
                existing = by_id.get(card.card_id)
                if existing is None or candidate.score > existing.score:
                    by_id[card.card_id] = candidate

        hits = sorted(
            by_id.values(),
            key=lambda hit: (
                hit.score,
                hit.retrieval_probability,
                hit.card.updated_at,
                hit.card.card_id,
            ),
            reverse=True,
        )
        return tuple(hits[:limit_value])

    def retrieval_competition(self, hits: Sequence[CardHit], target_card_id: str) -> float:
        if not hits:
            return 0.0
        ids = [hit.card.card_id for hit in hits]
        if target_card_id not in ids:
            return 0.0
        assessment = retrieval_competition_probability(
            [hit.activation + hit.score for hit in hits],
            ids.index(target_card_id),
            provenance=tuple(ids),
        )
        assert assessment.estimate is not None
        return assessment.estimate

    @property
    def associative_fingerprint(self) -> str:
        return stable_fingerprint(
            {"base_policy": self.policy.__class__.__name__, "mesh": self.mesh.fingerprint}
        )
