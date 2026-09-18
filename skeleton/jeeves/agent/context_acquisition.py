"""Interaction acquisition bridge for cue-first Jeeves context.

This module makes the memory-game layer operational rather than optional.
Every user interaction is captured as a namespace-scoped card, linked to recent
cards through temporal/context/juxtaposition relations, and made available to
the existing LayeredContextResolver before any journal/log/archive lookup.

Associations affect retrieval order only. They never raise factual trust.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .associative_memory import (
    AssociationKind,
    AssociativeMemoryGameIndex,
    MemoryAssociation,
    SequencePrediction,
)
from .context_pipeline import (
    ContextResolution,
    ContextSourceAdapter,
    LayeredContextCompiler,
    LayeredContextResolver,
    ResolutionPolicy,
)
from .context_repository import ContextRepository
from .memory import MemoryManager, MemoryNamespace
from .memory_game import CardHit, InteractionCard
from .semantic_lenses import JuxtapositionAnalyzer, SemanticObservation
from .types import AgentContractError, json_safe, positive_int, probability, stable_fingerprint, stable_id


@dataclass(frozen=True, slots=True)
class InteractionAcquisitionPolicy:
    recent_window: int = 12
    juxtaposition_threshold: float = 0.48
    context_shift_threshold: float = 0.50
    correction_cues: tuple[str, ...] = ("correction", "correct", "actually", "instead", "no,", "not that")
    predict_prefix: int = 3
    recall_limit: int = 12

    def __post_init__(self) -> None:
        object.__setattr__(self, "recent_window", positive_int("recent_window", self.recent_window, maximum=256))
        object.__setattr__(self, "predict_prefix", positive_int("predict_prefix", self.predict_prefix, maximum=5))
        object.__setattr__(self, "recall_limit", positive_int("recall_limit", self.recall_limit, maximum=1000))
        object.__setattr__(self, "juxtaposition_threshold", probability("juxtaposition_threshold", self.juxtaposition_threshold))
        object.__setattr__(self, "context_shift_threshold", probability("context_shift_threshold", self.context_shift_threshold))
        object.__setattr__(self, "correction_cues", tuple(str(x).casefold() for x in self.correction_cues if str(x).strip()))


@dataclass(frozen=True, slots=True)
class AcquisitionTrace:
    trace_id: str
    namespace_key: str
    card: InteractionCard
    relation_ids: tuple[str, ...]
    previous_card_ids: tuple[str, ...]
    juxtaposition_score: float
    context_shift_score: float
    predicted_next: SequencePrediction | None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trace_id or not self.namespace_key:
            raise AgentContractError("acquisition trace requires ids")
        object.__setattr__(self, "juxtaposition_score", probability("juxtaposition_score", self.juxtaposition_score))
        object.__setattr__(self, "context_shift_score", probability("context_shift_score", self.context_shift_score))
        object.__setattr__(self, "relation_ids", tuple(sorted({str(x) for x in self.relation_ids if str(x)})))
        object.__setattr__(self, "previous_card_ids", tuple(str(x) for x in self.previous_card_ids if str(x)))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "trace": self.trace_id,
            "namespace": self.namespace_key,
            "card": self.card.content_fingerprint,
            "relations": self.relation_ids,
            "previous": self.previous_card_ids,
            "juxtaposition": self.juxtaposition_score,
            "context_shift": self.context_shift_score,
            "prediction": None if self.predicted_next is None else self.predicted_next.fingerprint,
        })


@dataclass(frozen=True, slots=True)
class RecallTrace:
    query: str
    card_hits: tuple[CardHit, ...]
    resolution: ContextResolution | None
    used_deep_context: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class CueFirstContextSystem:
    """Correctly shared L0/deep-context wiring for production callers."""

    cards: AssociativeMemoryGameIndex
    resolver: LayeredContextResolver
    compiler: LayeredContextCompiler
    acquisition: "InteractionAcquisitionEngine"

    def __post_init__(self) -> None:
        if self.resolver.cards is not self.cards:
            raise AgentContractError("cue-first resolver must use the associative card index")
        if self.compiler.resolver is not self.resolver:
            raise AgentContractError("cue-first compiler must use the shared resolver")
        if self.acquisition.cards is not self.cards or self.acquisition.resolver is not self.resolver:
            raise AgentContractError("cue-first acquisition must share cards and resolver")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "cards": self.cards.associative_fingerprint,
            "resolver_policy": self.resolver.policy.__class__.__name__,
            "acquisition": self.acquisition.fingerprint,
        })


class InteractionAcquisitionEngine:
    """Store turns as cue cards and learn relational retrieval structure."""

    def __init__(
        self,
        cards: AssociativeMemoryGameIndex | None = None,
        *,
        resolver: LayeredContextResolver | None = None,
        policy: InteractionAcquisitionPolicy | None = None,
    ) -> None:
        self.cards = cards or AssociativeMemoryGameIndex()
        if not isinstance(self.cards, AssociativeMemoryGameIndex):
            raise TypeError("cards must be AssociativeMemoryGameIndex")
        self.resolver = resolver
        if resolver is not None:
            same_index = resolver.cards is self.cards
            same_store = getattr(resolver.cards, "store", None) is self.cards.store
            if not (same_index or same_store):
                raise AgentContractError("resolver must use the same L0 card store as acquisition engine")
        self.policy = policy or InteractionAcquisitionPolicy()
        self._recent: defaultdict[str, deque[str]] = defaultdict(lambda: deque(maxlen=self.policy.recent_window))
        self._positions: defaultdict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    @staticmethod
    def _tag_shift(left: Sequence[str], right: Sequence[str]) -> float:
        a = {str(x).casefold() for x in left if str(x).strip()}
        b = {str(x).casefold() for x in right if str(x).strip()}
        if not a and not b:
            return 0.0
        return 1.0 - len(a & b) / max(1, len(a | b))

    def _semantic_observation(self, card: InteractionCard, position: int) -> SemanticObservation:
        return SemanticObservation(
            observation_id=card.card_id,
            content=card.content,
            position=position,
            source=card.source,
            tags=card.context_tags,
            evidence_ids=card.provenance,
            metadata={"card_fingerprint": card.content_fingerprint},
        )

    def capture(
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
    ) -> AcquisitionTrace:
        """Capture one interaction and update temporal/semantic L0 edges."""
        card = self.cards.capture_interaction(
            namespace,
            content,
            context_tags=context_tags,
            source=source,
            trust=trust,
            salience=salience,
            surprise=surprise,
            provenance=provenance,
            metadata={**dict(metadata or {}), "l0_acquired": True},
        )
        with self._lock:
            key = namespace.key
            recent = self._recent[key]
            previous_ids = tuple(recent)
            position = self._positions[key]
            self._positions[key] += 1
            relations: list[MemoryAssociation] = []
            juxtaposition_score = 0.0
            context_shift_score = 0.0

            if previous_ids:
                previous = self.cards.store.get(previous_ids[-1])
                if previous is not None and previous.card_id != card.card_id:
                    relations.extend(
                        self.cards.mesh.observe_sequence(
                            namespace,
                            (previous.card_id, card.card_id),
                            kind=AssociationKind.TEMPORAL_FORWARD,
                            evidence_ids=tuple(provenance),
                            tags=tuple(context_tags),
                        )
                    )
                    left = self._semantic_observation(previous, max(0, position - 1))
                    right = self._semantic_observation(card, position)
                    signal = JuxtapositionAnalyzer.compare(left, right)
                    juxtaposition_score = max(signal.contrast_signal, signal.novelty_signal)
                    context_shift_score = self._tag_shift(previous.context_tags, card.context_tags)
                    if signal.changed_context and juxtaposition_score >= self.policy.juxtaposition_threshold:
                        relations.extend(
                            self.cards.mesh.observe_juxtaposition(
                                namespace,
                                previous.card_id,
                                card.card_id,
                                changed_interpretation=True,
                                evidence_ids=tuple(provenance),
                                tags=tuple(context_tags),
                            )
                        )
                    if context_shift_score >= self.policy.context_shift_threshold:
                        relations.append(
                            self.cards.mesh.observe(
                                namespace, previous.card_id, card.card_id,
                                kind=AssociationKind.CONTEXT_SHIFT,
                                strength=min(1.0, 0.45 + 0.45 * context_shift_score),
                                surprise=max(surprise, context_shift_score),
                                direction_confidence=0.80,
                                evidence_ids=tuple(provenance),
                                tags=tuple(context_tags),
                                metadata={"context_shift": context_shift_score},
                            )
                        )
                    lower = card.content.casefold()
                    if any(cue in lower for cue in self.policy.correction_cues):
                        relations.append(
                            self.cards.mesh.observe(
                                namespace, previous.card_id, card.card_id,
                                kind=AssociationKind.CORRECTION,
                                strength=0.82,
                                surprise=max(0.55, surprise),
                                direction_confidence=0.90,
                                evidence_ids=tuple(provenance),
                                tags=tuple(context_tags) + ("correction",),
                                metadata={"revision_candidate": True, "authoritative": False},
                            )
                        )

            if not recent or recent[-1] != card.card_id:
                recent.append(card.card_id)
            # Adjacent order-2 evidence was recorded exactly once above.
            # Extend only order-3+ n-grams here so a rolling context window
            # cannot multiply-count the same pair on every subsequent turn.
            prefix_ids = tuple(recent)[-min(len(recent), self.policy.predict_prefix + 1):]
            if len(prefix_ids) >= 3:
                self.cards.mesh.observe_higher_order_sequence(namespace, prefix_ids, minimum_order=3)
            prediction = None
            if recent:
                prefix = tuple(recent)[-min(len(recent), self.policy.predict_prefix):]
                prediction = self.cards.mesh.predict_next(namespace, prefix, limit=8)

        trace_id = stable_id("acquisition-trace", {
            "namespace": namespace.key,
            "card": card.card_id,
            "previous": previous_ids,
            "relations": sorted(edge.association_id for edge in relations),
            "position": position,
        }, length=32)
        return AcquisitionTrace(
            trace_id=trace_id,
            namespace_key=namespace.key,
            card=card,
            relation_ids=tuple(edge.association_id for edge in relations),
            previous_card_ids=previous_ids,
            juxtaposition_score=juxtaposition_score,
            context_shift_score=context_shift_score,
            predicted_next=prediction,
            metadata={
                "position": position,
                "association_count": len(relations),
                "authoritative": False,
                "retrieval_only": True,
            },
        )

    def recall(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        allow_deep: bool = True,
    ) -> RecallTrace:
        """Recall L0 first; optionally continue through the configured deep resolver."""
        hits = self.cards.search(
            namespace, query, context_tags=context_tags, limit=self.policy.recall_limit
        )
        resolution = None
        used_deep = False
        if allow_deep and self.resolver is not None:
            resolution = self.resolver.resolve(namespace, query, context_tags=context_tags)
            used_deep = resolution.stopped_at.value > 0
        fp = stable_fingerprint({
            "query": query,
            "cards": [(hit.card.card_id, round(hit.score, 10)) for hit in hits],
            "resolution": None if resolution is None else resolution.fingerprint,
        })
        return RecallTrace(query, hits, resolution, used_deep, fp)

    def recent_card_ids(self, namespace: MemoryNamespace) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._recent.get(namespace.key, ()))

    @property
    def fingerprint(self) -> str:
        with self._lock:
            recent = {key: tuple(value) for key, value in sorted(self._recent.items())}
        return stable_fingerprint({"cards": self.cards.associative_fingerprint, "recent": recent})

def build_cue_first_context_system(
    *,
    memory: MemoryManager,
    cards: AssociativeMemoryGameIndex | None = None,
    repository: ContextRepository | None = None,
    adapters: Sequence[ContextSourceAdapter] = (),
    resolution_policy: ResolutionPolicy | None = None,
    acquisition_policy: InteractionAcquisitionPolicy | None = None,
) -> CueFirstContextSystem:
    """Build the canonical context path with one shared associative L0 index.

    Retrieval order is inherited from LayeredContextResolver: associative cards
    first, then scoped memory, versioned repository, caches/databases, narrative
    stores, annals/chronicles/archives, and finally optional external adapters.
    """
    if not isinstance(memory, MemoryManager):
        raise TypeError("memory must be MemoryManager")
    index = cards or AssociativeMemoryGameIndex()
    resolver = LayeredContextResolver(
        cards=index,
        memory=memory,
        repository=repository,
        adapters=adapters,
        policy=resolution_policy,
    )
    compiler = LayeredContextCompiler(resolver)
    acquisition = InteractionAcquisitionEngine(
        index,
        resolver=resolver,
        policy=acquisition_policy,
    )
    return CueFirstContextSystem(index, resolver, compiler, acquisition)
