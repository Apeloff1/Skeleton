"""Fast memory-game index for Jeeves context acquisition.

The index is deliberately *not* the canonical memory store.  It is a compact
cue/retrieval layer in front of durable context, journals, logs, diaries,
annals, chronicles, databases, caches, files, and other repositories.

Design rules:
- every card points back to a source reference and source fingerprint;
- a card may contain a bounded preview, never an authoritative replacement;
- user interactions are acquired immediately as cue cards;
- retrieval strength is updated by use, spacing, success/failure and
  interference;
- pair/triad/sequence relations can encode juxtaposition and narrative order;
- source truth and interpretive relations stay separate;
- deep storage is consulted when fast recall is weak, conflicted or asks for
  canonical content.

This gives Jeeves a "matching-card" front door without flattening the richer
context VCS behind it.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .probability_lenses import memory_retrieval_probability
from .types import (
    AgentContractError,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    stable_fingerprint,
    stable_id,
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")


class IndexCardError(RuntimeError):
    pass


class SourceTier(str, Enum):
    USER_INTERACTION = "user_interaction"
    CONTEXT_REPOSITORY = "context_repository"
    MEMORY_STORE = "memory_store"
    JOURNAL = "journal"
    LOG = "log"
    DIARY = "diary"
    ANNAL = "annal"
    CHRONICLE = "chronicle"
    DATABASE = "database"
    CACHE = "cache"
    FILE = "file"
    TOOL = "tool"
    EXTERNAL = "external"


class CardKind(str, Enum):
    INTERACTION = "interaction"
    FACT_CUE = "fact_cue"
    EPISODE_CUE = "episode_cue"
    PREFERENCE_CUE = "preference_cue"
    PROCEDURE_CUE = "procedure_cue"
    PREDICTION_CUE = "prediction_cue"
    FAILURE_CUE = "failure_cue"
    QUESTION_CUE = "question_cue"
    TANGENT_CUE = "tangent_cue"
    SOURCE_CUE = "source_cue"


class RelationKind(str, Enum):
    ASSOCIATES = "associates"
    PAIR = "pair"
    TRIAD = "triad"
    BEFORE = "before"
    AFTER = "after"
    SEQUENCE = "sequence"
    JUXTAPOSES = "juxtaposes"
    CONTRASTS = "contrasts"
    FOIL = "foil"
    ANALOGY = "analogy"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CAUSAL_CANDIDATE = "causal_candidate"
    CALLBACK = "callback"
    FORESHADOWS = "foreshadows"
    MOTIF = "motif"
    SAME_ENTITY = "same_entity"
    SAME_GOAL = "same_goal"
    SAME_WORKSPACE = "same_workspace"
    NEXT_TURN = "next_turn"
    PREDICTS = "predicts"


@dataclass(frozen=True, slots=True)
class IndexCard:
    card_id: str
    namespace_key: str
    kind: CardKind
    cue: str
    preview: str
    source_tier: SourceTier
    source_ref: str
    source_fingerprint: str
    created_at: float
    updated_at: float
    source_provider: str = ""
    salience: float = 0.5
    trust: float = 0.5
    confidence: float = 0.5
    retrieval_strength: float = 0.5
    surprise: float = 0.0
    prediction_error: float = 0.0
    access_count: int = 0
    successful_retrievals: int = 0
    failed_retrievals: int = 0
    last_accessed_at: float | None = None
    last_success_at: float | None = None
    sequence: int | None = None
    tags: tuple[str, ...] = ()
    lens_ids: tuple[str, ...] = ()
    continuation_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "card_id", bounded_text("card_id", self.card_id, maximum=256))
        object.__setattr__(self, "namespace_key", bounded_text("namespace_key", self.namespace_key, maximum=512))
        if not isinstance(self.kind, CardKind):
            object.__setattr__(self, "kind", CardKind(str(self.kind)))
        object.__setattr__(self, "cue", bounded_text("cue", self.cue, maximum=8192))
        object.__setattr__(self, "preview", bounded_text("preview", self.preview, maximum=8192, allow_empty=True))
        if not isinstance(self.source_tier, SourceTier):
            object.__setattr__(self, "source_tier", SourceTier(str(self.source_tier)))
        object.__setattr__(self, "source_ref", bounded_text("source_ref", self.source_ref, maximum=2048))
        object.__setattr__(
            self,
            "source_provider",
            bounded_text("source_provider", self.source_provider, maximum=512, allow_empty=True),
        )
        source_fingerprint = str(self.source_fingerprint).strip().lower()
        if not source_fingerprint:
            raise AgentContractError("source_fingerprint cannot be empty")
        object.__setattr__(self, "source_fingerprint", source_fingerprint[:256])
        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise AgentContractError("invalid card timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        for name in (
            "salience",
            "trust",
            "confidence",
            "retrieval_strength",
            "surprise",
            "prediction_error",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("access_count", "successful_retrievals", "failed_retrievals"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AgentContractError(f"{name} must be non-negative integer")
        for name in ("last_accessed_at", "last_success_at"):
            value = getattr(self, name)
            if value is not None:
                parsed = finite_number(name, value)
                if parsed < created:
                    raise AgentContractError(f"{name} predates creation")
                object.__setattr__(self, name, parsed)
        if self.sequence is not None:
            if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
                raise AgentContractError("sequence must be non-negative integer")
        tags = tuple(sorted({str(value).casefold().strip() for value in self.tags if str(value).strip()}))
        lens_ids = tuple(sorted({str(value).strip() for value in self.lens_ids if str(value).strip()}))
        continuation_ids = tuple(sorted({str(value).strip() for value in self.continuation_ids if str(value).strip()}))
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "lens_ids", lens_ids)
        object.__setattr__(self, "continuation_ids", continuation_ids)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def card_fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace_key,
                "kind": self.kind.value,
                "cue": self.cue,
                "preview": self.preview,
                "source_tier": self.source_tier.value,
                "source_ref": self.source_ref,
                "source_provider": self.source_provider,
                "source_fingerprint": self.source_fingerprint,
                "tags": self.tags,
                "lens_ids": self.lens_ids,
                "continuation_ids": self.continuation_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class CardRelation:
    relation_id: str
    namespace_key: str
    kind: RelationKind
    card_ids: tuple[str, ...]
    strength: float
    confidence: float
    created_at: float
    source: str = "runtime"
    evidence_refs: tuple[str, ...] = ()
    interpretive: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_id", bounded_text("relation_id", self.relation_id, maximum=256))
        object.__setattr__(self, "namespace_key", bounded_text("namespace_key", self.namespace_key, maximum=512))
        if not isinstance(self.kind, RelationKind):
            object.__setattr__(self, "kind", RelationKind(str(self.kind)))
        card_ids = tuple(dict.fromkeys(str(value) for value in self.card_ids))
        if len(card_ids) < 2 or len(card_ids) > 8:
            raise AgentContractError("card relation must connect 2..8 cards")
        object.__setattr__(self, "card_ids", card_ids)
        object.__setattr__(self, "strength", probability("strength", self.strength))
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        object.__setattr__(self, "created_at", finite_number("created_at", self.created_at))
        object.__setattr__(self, "source", bounded_text("relation source", self.source, maximum=512))
        object.__setattr__(self, "evidence_refs", tuple(sorted({str(value)[:512] for value in self.evidence_refs})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace_key,
                "kind": self.kind.value,
                "cards": self.card_ids,
                "strength": self.strength,
                "confidence": self.confidence,
                "source": self.source,
                "evidence_refs": self.evidence_refs,
                "interpretive": self.interpretive,
            }
        )


@dataclass(frozen=True, slots=True)
class RecallHit:
    card: IndexCard
    score: float
    cue_score: float
    recency_score: float
    strength_score: float
    utility_score: float
    surprise_score: float
    relation_score: float
    retrieval_probability: float
    matched_relations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "score",
            "cue_score",
            "recency_score",
            "strength_score",
            "utility_score",
            "surprise_score",
            "relation_score",
            "retrieval_probability",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class RecallPacket:
    query: str
    direct_hits: tuple[RecallHit, ...]
    associative_hits: tuple[RecallHit, ...]
    source_refs: tuple[str, ...]
    source_tiers: tuple[SourceTier, ...]
    lens_hints: tuple[str, ...]
    continuation_ids: tuple[str, ...]
    fallback_to_deep_context: bool
    conflict_detected: bool
    fingerprint: str

    @property
    def all_hits(self) -> tuple[RecallHit, ...]:
        seen: set[str] = set()
        values: list[RecallHit] = []
        for hit in (*self.direct_hits, *self.associative_hits):
            if hit.card.card_id not in seen:
                seen.add(hit.card.card_id)
                values.append(hit)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class MemoryGamePolicy:
    maximum_cards: int = 100_000
    direct_limit: int = 8
    associative_limit: int = 8
    half_life_seconds: float = 14 * 24 * 3600
    deep_fallback_score: float = 0.46
    minimum_trust: float = 0.15
    cue_weight: float = 0.35
    recency_weight: float = 0.10
    strength_weight: float = 0.17
    trust_weight: float = 0.12
    salience_weight: float = 0.08
    utility_weight: float = 0.08
    surprise_weight: float = 0.05
    relation_weight: float = 0.05

    def __post_init__(self) -> None:
        object.__setattr__(self, "maximum_cards", positive_int("maximum_cards", self.maximum_cards, maximum=10_000_000))
        object.__setattr__(self, "direct_limit", positive_int("direct_limit", self.direct_limit, maximum=1000))
        object.__setattr__(self, "associative_limit", positive_int("associative_limit", self.associative_limit, maximum=1000))
        half_life = finite_number("half_life_seconds", self.half_life_seconds)
        if half_life <= 0:
            raise AgentContractError("half_life_seconds must be positive")
        object.__setattr__(self, "half_life_seconds", half_life)
        for name in ("deep_fallback_score", "minimum_trust"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        names = (
            "cue_weight",
            "recency_weight",
            "strength_weight",
            "trust_weight",
            "salience_weight",
            "utility_weight",
            "surprise_weight",
            "relation_weight",
        )
        raw = [finite_number(name, getattr(self, name)) for name in names]
        if any(value < 0 for value in raw) or sum(raw) <= 0:
            raise AgentContractError("memory game weights must be non-negative and non-zero")
        total = sum(raw)
        for name, value in zip(names, raw):
            object.__setattr__(self, name, value / total)


class MemoryGameIndex:
    """Thread-safe cue-card layer in front of canonical context stores."""

    def __init__(
        self,
        *,
        policy: MemoryGamePolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or MemoryGamePolicy()
        self._clock = clock
        self._cards: dict[str, IndexCard] = {}
        self._source_to_cards: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._token_to_cards: dict[tuple[str, str], set[str]] = defaultdict(set)
        self._relations: dict[str, CardRelation] = {}
        self._relations_by_card: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def put_card(self, card: IndexCard) -> IndexCard:
        if not isinstance(card, IndexCard):
            raise TypeError("card must be IndexCard")
        with self._lock:
            prior = self._cards.get(card.card_id)
            if prior is None and len(self._cards) >= self.policy.maximum_cards:
                self._evict_one()
            if prior is not None:
                self._source_to_cards[(prior.namespace_key, prior.source_ref)].discard(prior.card_id)
                self._remove_token_index(prior)
            self._cards[card.card_id] = card
            self._source_to_cards[(card.namespace_key, card.source_ref)].add(card.card_id)
            self._add_token_index(card)
            return card

    def index_source(
        self,
        *,
        namespace_key: str,
        source_tier: SourceTier,
        source_ref: str,
        source_fingerprint: str,
        cue: str,
        source_provider: str = "",
        preview: str,
        kind: CardKind = CardKind.SOURCE_CUE,
        salience: float = 0.5,
        trust: float = 0.5,
        confidence: float = 0.5,
        surprise: float = 0.0,
        prediction_error: float = 0.0,
        sequence: int | None = None,
        tags: Sequence[str] = (),
        lens_ids: Sequence[str] = (),
        continuation_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> IndexCard:
        now = self._clock()
        payload = {
            "namespace": namespace_key,
            "source_tier": source_tier.value if isinstance(source_tier, SourceTier) else str(source_tier),
            "source_ref": source_ref,
            "source_provider": source_provider,
            "source_fingerprint": source_fingerprint,
            "cue": cue,
            "kind": kind.value if isinstance(kind, CardKind) else str(kind),
        }
        card = IndexCard(
            card_id=stable_id("card", payload, length=28),
            namespace_key=namespace_key,
            kind=kind,
            cue=cue,
            preview=preview,
            source_tier=source_tier,
            source_ref=source_ref,
            source_fingerprint=source_fingerprint,
            created_at=now,
            source_provider=source_provider,
            updated_at=now,
            salience=salience,
            trust=trust,
            confidence=confidence,
            retrieval_strength=max(0.10, min(0.95, 0.25 + salience * 0.30 + trust * 0.25 + confidence * 0.20)),
            surprise=surprise,
            prediction_error=prediction_error,
            sequence=sequence,
            tags=tuple(tags),
            lens_ids=tuple(lens_ids),
            continuation_ids=tuple(continuation_ids),
            metadata=metadata or {},
        )
        return self.put_card(card)

    def remember_interaction(
        self,
        *,
        namespace_key: str,
        turn_id: str,
        text: str,
        source_ref: str,
        source_fingerprint: str,
        sequence: int,
        source_tier: SourceTier = SourceTier.MEMORY_STORE,
        source_provider: str = "",
        role: str = "user",
        salience: float = 0.70,
        trust: float = 1.0,
        surprise: float = 0.0,
        prediction_error: float = 0.0,
        tags: Sequence[str] = (),
        lens_ids: Sequence[str] = (),
        continuation_ids: Sequence[str] = (),
    ) -> IndexCard:
        role = str(role).casefold().strip() or "user"
        return self.index_source(
            namespace_key=namespace_key,
            source_tier=source_tier,
            source_ref=source_ref,
            source_fingerprint=source_fingerprint,
            source_provider=source_provider,
            cue=text,
            preview=text[:8192],
            kind=CardKind.INTERACTION,
            salience=salience,
            trust=trust,
            confidence=1.0,
            surprise=surprise,
            prediction_error=prediction_error,
            sequence=sequence,
            tags=tuple(tags) + ("interaction", role, f"turn:{turn_id}"),
            lens_ids=lens_ids,
            continuation_ids=continuation_ids,
            metadata={"role": role, "turn_id": turn_id, "canonical_source_required": True},
        )

    def link(
        self,
        card_ids: Sequence[str],
        *,
        kind: RelationKind,
        strength: float = 0.5,
        confidence: float = 0.5,
        source: str = "runtime",
        evidence_refs: Sequence[str] = (),
        interpretive: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> CardRelation:
        ids = tuple(dict.fromkeys(str(value) for value in card_ids))
        if len(ids) < 2:
            raise IndexCardError("relation requires at least two cards")
        with self._lock:
            cards = [self._cards.get(card_id) for card_id in ids]
            if any(card is None for card in cards):
                raise IndexCardError("relation references unknown card")
            assert cards[0] is not None
            namespace_key = cards[0].namespace_key
            if any(card is None or card.namespace_key != namespace_key for card in cards):
                raise IndexCardError("relations cannot cross namespaces")
            payload = {
                "namespace": namespace_key,
                "kind": kind.value if isinstance(kind, RelationKind) else str(kind),
                "cards": ids,
                "source": source,
                "evidence_refs": sorted(str(value) for value in evidence_refs),
                "interpretive": bool(interpretive),
            }
            relation = CardRelation(
                relation_id=stable_id("relation", payload, length=28),
                namespace_key=namespace_key,
                kind=kind,
                card_ids=ids,
                strength=strength,
                confidence=confidence,
                created_at=self._clock(),
                source=source,
                evidence_refs=tuple(evidence_refs),
                interpretive=interpretive,
                metadata=metadata or {},
            )
            self._relations[relation.relation_id] = relation
            for card_id in ids:
                self._relations_by_card[card_id].add(relation.relation_id)
            return relation

    def link_sequence(
        self,
        card_ids: Sequence[str],
        *,
        strength: float = 0.75,
        source: str = "runtime",
    ) -> tuple[CardRelation, ...]:
        ids = tuple(card_ids)
        relations: list[CardRelation] = []
        for left, right in zip(ids, ids[1:]):
            relations.append(
                self.link(
                    (left, right),
                    kind=RelationKind.NEXT_TURN,
                    strength=strength,
                    confidence=1.0,
                    source=source,
                    interpretive=False,
                )
            )
        if len(ids) >= 3:
            relations.append(
                self.link(
                    ids[:8],
                    kind=RelationKind.SEQUENCE,
                    strength=strength,
                    confidence=1.0,
                    source=source,
                    interpretive=False,
                )
            )
        return tuple(relations)

    def juxtapose(
        self,
        card_ids: Sequence[str],
        *,
        strength: float = 0.5,
        confidence: float = 0.5,
        source: str = "semantic-lens",
        lens_id: str = "kuleshov_juxtaposition",
    ) -> CardRelation:
        return self.link(
            card_ids,
            kind=RelationKind.JUXTAPOSES,
            strength=strength,
            confidence=confidence,
            source=source,
            interpretive=True,
            metadata={"lens_id": lens_id, "changes_source_truth": False},
        )

    def query(
        self,
        namespace_key: str,
        query: str,
        *,
        limit: int | None = None,
        associative_limit: int | None = None,
        minimum_trust: float | None = None,
        source_tiers: Sequence[SourceTier] = (),
        tags: Sequence[str] = (),
        touch: bool = True,
    ) -> RecallPacket:
        limit = self.policy.direct_limit if limit is None else positive_int("limit", limit, maximum=1000)
        associative_limit = (
            self.policy.associative_limit
            if associative_limit is None
            else positive_int("associative_limit", associative_limit, maximum=1000)
        )
        minimum_trust = self.policy.minimum_trust if minimum_trust is None else probability("minimum_trust", minimum_trust)
        query_tokens = self._tokens(query)
        tier_set = {
            value if isinstance(value, SourceTier) else SourceTier(str(value))
            for value in source_tiers
        }
        tag_set = {str(value).casefold().strip() for value in tags if str(value).strip()}
        now = self._clock()

        with self._lock:
            candidate_ids: set[str] = set()
            for token in query_tokens:
                candidate_ids.update(self._token_to_cards.get((namespace_key, token), ()))
            # Empty/novel lexical queries still need a bounded recency/salience
            # path. The inverted index handles normal recall without O(N^2)
            # scoring across the entire namespace.
            if candidate_ids:
                source_cards = (self._cards[card_id] for card_id in candidate_ids if card_id in self._cards)
            else:
                source_cards = (
                    card for card in self._cards.values() if card.namespace_key == namespace_key
                )
            cards = [
                card
                for card in source_cards
                if card.namespace_key == namespace_key
                and card.trust >= minimum_trust
                and (not tier_set or card.source_tier in tier_set)
                and (not tag_set or tag_set.issubset(set(card.tags)))
            ]
            scored: list[RecallHit] = [self._score_card(card, query_tokens, now) for card in cards]
            scored.sort(key=lambda hit: (hit.score, hit.card.updated_at, hit.card.card_id), reverse=True)
            direct = tuple(scored[:limit])
            direct_ids = {hit.card.card_id for hit in direct}

            relation_candidates: dict[str, tuple[float, list[str]]] = {}
            for hit in direct:
                for relation_id in self._relations_by_card.get(hit.card.card_id, ()):
                    relation = self._relations.get(relation_id)
                    if relation is None:
                        continue
                    relation_weight = relation.strength * relation.confidence
                    if relation.kind in {
                        RelationKind.JUXTAPOSES,
                        RelationKind.CONTRASTS,
                        RelationKind.FOIL,
                        RelationKind.CALLBACK,
                        RelationKind.FORESHADOWS,
                        RelationKind.MOTIF,
                        RelationKind.NEXT_TURN,
                        RelationKind.SEQUENCE,
                    }:
                        relation_weight = min(1.0, relation_weight + 0.10)
                    for card_id in relation.card_ids:
                        if card_id in direct_ids:
                            continue
                        prior = relation_candidates.get(card_id)
                        if prior is None or relation_weight > prior[0]:
                            relation_candidates[card_id] = (relation_weight, [relation_id])
                        elif math.isclose(relation_weight, prior[0], rel_tol=1e-12, abs_tol=1e-12):
                            prior[1].append(relation_id)

            associative: list[RecallHit] = []
            for card_id, (relation_score, relation_ids) in relation_candidates.items():
                card = self._cards.get(card_id)
                if card is None:
                    continue
                base = self._score_card(card, query_tokens, now)
                boosted = min(1.0, base.score * 0.75 + relation_score * 0.25)
                associative.append(
                    RecallHit(
                        card=card,
                        score=boosted,
                        cue_score=base.cue_score,
                        recency_score=base.recency_score,
                        strength_score=base.strength_score,
                        utility_score=base.utility_score,
                        surprise_score=base.surprise_score,
                        relation_score=relation_score,
                        retrieval_probability=base.retrieval_probability,
                        matched_relations=tuple(sorted(set(relation_ids))),
                    )
                )
            associative.sort(key=lambda hit: (hit.score, hit.card.updated_at, hit.card.card_id), reverse=True)
            associative_tuple = tuple(associative[:associative_limit])

            all_hits = (*direct, *associative_tuple)
            best_score = direct[0].score if direct else 0.0
            conflict = self._conflict_detected(all_hits)
            fallback = not direct or best_score < self.policy.deep_fallback_score or conflict
            source_refs = tuple(dict.fromkeys(hit.card.source_ref for hit in all_hits))
            tiers = tuple(sorted({hit.card.source_tier for hit in all_hits}, key=lambda value: value.value))
            lens_hints = tuple(sorted({lens for hit in all_hits for lens in hit.card.lens_ids}))
            continuation_ids = tuple(sorted({item for hit in all_hits for item in hit.card.continuation_ids}))

            if touch:
                for hit in direct:
                    self._touch(hit.card.card_id, success=None, now=now)

            fingerprint = stable_fingerprint(
                {
                    "namespace": namespace_key,
                    "query": query,
                    "direct": [(hit.card.card_id, round(hit.score, 8)) for hit in direct],
                    "associative": [(hit.card.card_id, round(hit.score, 8)) for hit in associative_tuple],
                    "fallback": fallback,
                    "conflict": conflict,
                }
            )
            return RecallPacket(
                query=query,
                direct_hits=direct,
                associative_hits=associative_tuple,
                source_refs=source_refs,
                source_tiers=tiers,
                lens_hints=lens_hints,
                continuation_ids=continuation_ids,
                fallback_to_deep_context=fallback,
                conflict_detected=conflict,
                fingerprint=fingerprint,
            )

    def retrieval_feedback(
        self,
        card_id: str,
        *,
        success: bool,
        prediction_error: float | None = None,
        reward: float | None = None,
    ) -> IndexCard:
        now = self._clock()
        with self._lock:
            card = self._cards.get(str(card_id))
            if card is None:
                raise IndexCardError("unknown card")
            result = self._touch(card.card_id, success=bool(success), now=now)
            if prediction_error is not None:
                error = probability("prediction_error", prediction_error)
                result = replace(result, prediction_error=error)
            if reward is not None:
                utility = probability("reward", reward)
                metadata = dict(result.metadata)
                old_utility = float(metadata.get("retrieval_utility", 0.5))
                metadata["retrieval_utility"] = max(0.0, min(1.0, old_utility * 0.8 + utility * 0.2))
                result = replace(result, metadata=metadata)
            self._cards[result.card_id] = result
            return result

    def review_queue(
        self,
        namespace_key: str,
        *,
        limit: int = 32,
        target_recall: float = 0.75,
    ) -> tuple[IndexCard, ...]:
        limit = positive_int("limit", limit, maximum=1000)
        target_recall = probability("target_recall", target_recall)
        now = self._clock()
        candidates: list[tuple[float, IndexCard]] = []
        with self._lock:
            for card in self._cards.values():
                if card.namespace_key != namespace_key:
                    continue
                estimate = self._retrieval_probability(card, now)
                urgency = max(0.0, target_recall - estimate)
                if urgency <= 0:
                    continue
                importance = card.salience * 0.35 + card.trust * 0.25 + card.confidence * 0.20 + card.surprise * 0.20
                candidates.append((urgency * 0.65 + importance * 0.35, card))
        candidates.sort(key=lambda item: (item[0], item[1].updated_at, item[1].card_id), reverse=True)
        return tuple(card for _, card in candidates[:limit])

    def predicted_next_cards(
        self,
        card_id: str,
        *,
        limit: int = 8,
    ) -> tuple[tuple[IndexCard, float], ...]:
        limit = positive_int("limit", limit, maximum=100)
        with self._lock:
            if card_id not in self._cards:
                raise IndexCardError("unknown card")
            candidates: dict[str, float] = {}
            for relation_id in self._relations_by_card.get(card_id, ()):
                relation = self._relations.get(relation_id)
                if relation is None or relation.kind not in {
                    RelationKind.NEXT_TURN,
                    RelationKind.SEQUENCE,
                    RelationKind.PREDICTS,
                    RelationKind.FORESHADOWS,
                }:
                    continue
                ids = relation.card_ids
                try:
                    index = ids.index(card_id)
                except ValueError:
                    continue
                following = ids[index + 1 :]
                for offset, next_id in enumerate(following, start=1):
                    value = relation.strength * relation.confidence / offset
                    candidates[next_id] = max(candidates.get(next_id, 0.0), value)
            values = [
                (self._cards[next_id], max(0.0, min(1.0, score)))
                for next_id, score in candidates.items()
                if next_id in self._cards
            ]
            values.sort(key=lambda item: (item[1], item[0].updated_at, item[0].card_id), reverse=True)
            return tuple(values[:limit])

    def source_cards(self, namespace_key: str, source_ref: str) -> tuple[IndexCard, ...]:
        with self._lock:
            ids = self._source_to_cards.get((namespace_key, source_ref), set())
            return tuple(sorted((self._cards[value] for value in ids), key=lambda card: card.card_id))

    def delete_card(self, card_id: str) -> bool:
        card_id = str(card_id)
        with self._lock:
            card = self._cards.pop(card_id, None)
            if card is None:
                return False
            self._source_to_cards[(card.namespace_key, card.source_ref)].discard(card.card_id)
            self._remove_token_index(card)
            relation_ids = tuple(self._relations_by_card.pop(card.card_id, set()))
            for relation_id in relation_ids:
                relation = self._relations.pop(relation_id, None)
                if relation is None:
                    continue
                for related_id in relation.card_ids:
                    self._relations_by_card[related_id].discard(relation_id)
            return True

    def prune_tag(self, namespace_key: str, tag: str) -> int:
        normalized = str(tag).casefold().strip()
        if not normalized:
            return 0
        with self._lock:
            victims = [
                card.card_id
                for card in self._cards.values()
                if card.namespace_key == namespace_key and normalized in card.tags
            ]
            for card_id in victims:
                self.delete_card(card_id)
            return len(victims)

    def cards(self, namespace_key: str | None = None) -> tuple[IndexCard, ...]:
        with self._lock:
            values = self._cards.values()
            if namespace_key is not None:
                values = (card for card in values if card.namespace_key == namespace_key)
            return tuple(sorted(values, key=lambda card: (card.updated_at, card.card_id), reverse=True))

    def card(self, card_id: str) -> IndexCard | None:
        with self._lock:
            return self._cards.get(str(card_id))

    def relations(self, card_id: str | None = None) -> tuple[CardRelation, ...]:
        with self._lock:
            if card_id is None:
                values = self._relations.values()
            else:
                values = (
                    self._relations[relation_id]
                    for relation_id in self._relations_by_card.get(str(card_id), ())
                    if relation_id in self._relations
                )
            return tuple(sorted(values, key=lambda relation: relation.relation_id))

    def count(self, namespace_key: str | None = None) -> int:
        with self._lock:
            if namespace_key is None:
                return len(self._cards)
            return sum(1 for card in self._cards.values() if card.namespace_key == namespace_key)

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint(
                {
                    "cards": [
                        (card.card_id, card.card_fingerprint, card.retrieval_strength, card.access_count)
                        for card in sorted(self._cards.values(), key=lambda value: value.card_id)
                    ],
                    "relations": [
                        (relation.relation_id, relation.fingerprint)
                        for relation in sorted(self._relations.values(), key=lambda value: value.relation_id)
                    ],
                }
            )

    def _score_card(self, card: IndexCard, query_tokens: Counter[str], now: float) -> RecallHit:
        cue_tokens = self._tokens(card.cue + " " + card.preview + " " + " ".join(card.tags))
        cue_score = self._cosine(query_tokens, cue_tokens)
        age = max(0.0, now - card.updated_at)
        recency = math.exp(-math.log(2.0) * age / self.policy.half_life_seconds)
        retrieval_probability = self._retrieval_probability(card, now)
        strength = card.retrieval_strength
        utility = float(card.metadata.get("retrieval_utility", 0.5))
        utility = max(0.0, min(1.0, utility))
        surprise = max(card.surprise, card.prediction_error)
        relation_score = min(1.0, len(self._relations_by_card.get(card.card_id, ())) / 8.0)
        score = (
            self.policy.cue_weight * cue_score
            + self.policy.recency_weight * recency
            + self.policy.strength_weight * ((strength + retrieval_probability) / 2.0)
            + self.policy.trust_weight * card.trust
            + self.policy.salience_weight * card.salience
            + self.policy.utility_weight * utility
            + self.policy.surprise_weight * surprise
            + self.policy.relation_weight * relation_score
        )
        return RecallHit(
            card=card,
            score=max(0.0, min(1.0, score)),
            cue_score=cue_score,
            recency_score=recency,
            strength_score=strength,
            utility_score=utility,
            surprise_score=surprise,
            relation_score=relation_score,
            retrieval_probability=retrieval_probability,
        )

    def _retrieval_probability(self, card: IndexCard, now: float) -> float:
        elapsed_hours = max(0.0, now - (card.last_success_at or card.created_at)) / 3600.0
        # Activation is deliberately transparent.  Strength and successful
        # spaced retrieval increase activation; time, failures and interference
        # lower it.
        spacing_bonus = math.log1p(card.successful_retrievals) * 0.30
        failure_penalty = math.log1p(card.failed_retrievals) * 0.35
        time_penalty = math.log1p(elapsed_hours / 24.0) * 0.18
        similar_cards = self._interference_count(card)
        interference_penalty = math.log1p(similar_cards) * 0.08
        activation = (
            (card.retrieval_strength - 0.5) * 3.0
            + spacing_bonus
            - failure_penalty
            - time_penalty
            - interference_penalty
        )
        assessment = memory_retrieval_probability(
            activation,
            threshold=0.0,
            noise_scale=1.0,
            storage_strength=card.retrieval_strength,
            provenance=(card.card_id,),
        )
        return float(assessment.estimate or 0.0)

    def _touch(self, card_id: str, *, success: bool | None, now: float) -> IndexCard:
        card = self._cards[card_id]
        success_count = card.successful_retrievals
        failure_count = card.failed_retrievals
        strength = card.retrieval_strength
        last_success = card.last_success_at
        if success is True:
            spacing = 0.0 if last_success is None else max(0.0, now - last_success)
            spacing_quality = min(1.0, math.log1p(spacing / 3600.0) / math.log1p(14 * 24))
            strength = min(1.0, strength + 0.04 + 0.08 * spacing_quality)
            success_count += 1
            last_success = now
        elif success is False:
            strength = max(0.0, strength * 0.82 - 0.03)
            failure_count += 1
        touched = replace(
            card,
            updated_at=max(card.updated_at, now),
            access_count=card.access_count + 1,
            successful_retrievals=success_count,
            failed_retrievals=failure_count,
            retrieval_strength=strength,
            last_accessed_at=now,
            last_success_at=last_success,
        )
        self._cards[card_id] = touched
        return touched

    def _interference_count(self, card: IndexCard) -> int:
        card_tokens = set(self._tokens(card.cue))
        if not card_tokens:
            return 0
        count = 0
        for other in self._cards.values():
            if other.card_id == card.card_id or other.namespace_key != card.namespace_key:
                continue
            other_tokens = set(self._tokens(other.cue))
            if not other_tokens:
                continue
            jaccard = len(card_tokens & other_tokens) / max(1, len(card_tokens | other_tokens))
            if jaccard >= 0.55:
                count += 1
        return count

    def _conflict_detected(self, hits: Sequence[RecallHit]) -> bool:
        ids = {hit.card.card_id for hit in hits}
        for hit in hits:
            if "contradiction" in hit.card.tags or "conflict" in hit.card.tags:
                return True
            for relation_id in self._relations_by_card.get(hit.card.card_id, ()):
                relation = self._relations.get(relation_id)
                if relation is None or relation.kind is not RelationKind.CONTRADICTS:
                    continue
                if len(ids.intersection(relation.card_ids)) >= 2:
                    return True
        return False

    def _add_token_index(self, card: IndexCard) -> None:
        for token in self._tokens(card.cue + " " + card.preview + " " + " ".join(card.tags)):
            self._token_to_cards[(card.namespace_key, token)].add(card.card_id)

    def _remove_token_index(self, card: IndexCard) -> None:
        for token in self._tokens(card.cue + " " + card.preview + " " + " ".join(card.tags)):
            key = (card.namespace_key, token)
            bucket = self._token_to_cards.get(key)
            if bucket is None:
                continue
            bucket.discard(card.card_id)
            if not bucket:
                self._token_to_cards.pop(key, None)

    @staticmethod
    def _tokens(text: str) -> Counter[str]:
        return Counter(token.casefold() for token in _TOKEN_RE.findall(text or ""))

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(count * right.get(token, 0) for token, count in left.items())
        ln = math.sqrt(sum(value * value for value in left.values()))
        rn = math.sqrt(sum(value * value for value in right.values()))
        if not ln or not rn:
            return 0.0
        return max(0.0, min(1.0, dot / (ln * rn)))

    def _evict_one(self) -> None:
        if not self._cards:
            return
        victim = min(
            self._cards.values(),
            key=lambda card: (
                card.trust * 0.20
                + card.salience * 0.20
                + card.confidence * 0.15
                + card.retrieval_strength * 0.20
                + min(1.0, card.access_count / 20.0) * 0.15
                + max(card.surprise, card.prediction_error) * 0.10,
                card.updated_at,
                card.card_id,
            ),
        )
        self._cards.pop(victim.card_id, None)
        self._source_to_cards[(victim.namespace_key, victim.source_ref)].discard(victim.card_id)
        self._remove_token_index(victim)
        relation_ids = tuple(self._relations_by_card.pop(victim.card_id, set()))
        for relation_id in relation_ids:
            relation = self._relations.pop(relation_id, None)
            if relation is None:
                continue
            for card_id in relation.card_ids:
                self._relations_by_card[card_id].discard(relation_id)


__all__ = [
    "CardKind",
    "CardRelation",
    "IndexCard",
    "IndexCardError",
    "MemoryGameIndex",
    "MemoryGamePolicy",
    "RecallHit",
    "RecallPacket",
    "RelationKind",
    "SourceTier",
]
