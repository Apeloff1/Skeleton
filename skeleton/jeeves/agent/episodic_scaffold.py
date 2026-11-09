"""Stable multi-cue episodic scaffold around Jeeves L0 memory-game cards.

Cards remain the fast memory atom. The scaffold records each exposure as a
separate episode with stable ordinal, temporal, context and entity anchors.
Repeated content can therefore share a card while retaining distinct sequence
positions. Scaffold data is retrieval metadata, never durable truth.

Prospective probes are explicitly retrieval-only. They may suggest where to
look next but cannot become evidence or a factual forecast without the normal
evidence path.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .memory import MemoryNamespace
from .memory_game import CardHit, InteractionCard, MemoryGameIndex, MemoryGamePolicy, RecallFeedback
from .types import bounded_text, finite_number, json_safe, positive_int, probability, stable_fingerprint, stable_id


class ScaffoldError(RuntimeError):
    pass


class AnchorKind(str, Enum):
    POSITION = "position"
    TOKEN = "token"
    CONTEXT = "context"
    ENTITY = "entity"
    TEMPORAL = "temporal"
    SOURCE = "source"
    PROSPECTIVE = "prospective"


@dataclass(frozen=True, slots=True)
class EpisodicScaffoldPolicy:
    maximum_episodes: int = 250_000
    maximum_anchors_per_episode: int = 96
    maximum_token_anchors: int = 48
    maximum_window_radius: int = 64
    maximum_hits: int = 16
    cue_weight: float = 0.35
    position_weight: float = 0.18
    recency_weight: float = 0.12
    retrieval_weight: float = 0.15
    trust_weight: float = 0.10
    salience_weight: float = 0.10
    scaffold_bonus_weight: float = 0.40
    reinforcement_rate: float = 0.16
    forgetting_half_life_seconds: float = 30 * 24 * 3600
    temporal_bucket_seconds: int = 24 * 3600

    def __post_init__(self) -> None:
        for name in (
            "maximum_episodes", "maximum_anchors_per_episode", "maximum_token_anchors",
            "maximum_window_radius", "maximum_hits", "temporal_bucket_seconds",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=10_000_000))
        names = ("cue_weight", "position_weight", "recency_weight", "retrieval_weight", "trust_weight", "salience_weight")
        values = [finite_number(name, getattr(self, name)) for name in names]
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise ScaffoldError("scaffold weights must be non-negative and non-zero")
        total = sum(values)
        for name, value in zip(names, values):
            object.__setattr__(self, name, value / total)
        object.__setattr__(self, "scaffold_bonus_weight", probability("scaffold_bonus_weight", self.scaffold_bonus_weight))
        object.__setattr__(self, "reinforcement_rate", probability("reinforcement_rate", self.reinforcement_rate))
        half_life = finite_number("forgetting_half_life_seconds", self.forgetting_half_life_seconds)
        if half_life <= 0:
            raise ScaffoldError("forgetting half-life must be positive")
        object.__setattr__(self, "forgetting_half_life_seconds", half_life)


@dataclass(frozen=True, slots=True)
class EpisodicAnchor:
    anchor_id: str
    episode_id: str
    namespace_key: str
    kind: AnchorKind
    cue: str
    strength: float
    created_at: float
    last_reinforced_at: float
    reinforcement_count: int = 0
    provenance_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.anchor_id or not self.episode_id or not self.namespace_key:
            raise ScaffoldError("anchor identity is required")
        if not isinstance(self.kind, AnchorKind):
            object.__setattr__(self, "kind", AnchorKind(str(self.kind)))
        cue = str(self.cue).strip().casefold()
        if not cue or len(cue) > 512:
            raise ScaffoldError("invalid anchor cue")
        object.__setattr__(self, "cue", cue)
        object.__setattr__(self, "strength", probability("anchor strength", self.strength))
        created = finite_number("created_at", self.created_at)
        reinforced = finite_number("last_reinforced_at", self.last_reinforced_at)
        if reinforced < created:
            raise ScaffoldError("anchor reinforcement predates creation")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "last_reinforced_at", reinforced)
        if isinstance(self.reinforcement_count, bool) or not isinstance(self.reinforcement_count, int) or self.reinforcement_count < 0:
            raise ScaffoldError("invalid reinforcement count")
        object.__setattr__(self, "provenance_ids", tuple(sorted({str(x) for x in self.provenance_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ScaffoldEpisode:
    episode_id: str
    namespace: MemoryNamespace
    card_id: str
    ordinal: int
    observed_at: float
    previous_episode_id: str | None = None
    source: str = "user-interaction"
    context_tags: tuple[str, ...] = ()
    entity_cues: tuple[str, ...] = ()
    anchor_ids: tuple[str, ...] = ()
    content_fingerprint: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, MemoryNamespace):
            raise ScaffoldError("namespace must be MemoryNamespace")
        if not self.episode_id or not self.card_id:
            raise ScaffoldError("episode identity is required")
        object.__setattr__(self, "ordinal", positive_int("ordinal", self.ordinal, maximum=2_000_000_000))
        timestamp = finite_number("observed_at", self.observed_at)
        if timestamp < 0:
            raise ScaffoldError("observed_at must be non-negative")
        object.__setattr__(self, "observed_at", timestamp)
        object.__setattr__(self, "source", bounded_text("source", self.source, maximum=512))
        object.__setattr__(self, "context_tags", tuple(sorted({str(x).strip().casefold() for x in self.context_tags if str(x).strip()})))
        object.__setattr__(self, "entity_cues", tuple(sorted({str(x).strip().casefold() for x in self.entity_cues if str(x).strip()})))
        object.__setattr__(self, "anchor_ids", tuple(sorted({str(x) for x in self.anchor_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "episode": self.episode_id, "namespace": self.namespace.key, "card": self.card_id,
            "ordinal": self.ordinal, "observed": self.observed_at, "previous": self.previous_episode_id,
            "anchors": self.anchor_ids, "content": self.content_fingerprint,
        })


@dataclass(frozen=True, slots=True)
class ScaffoldHit:
    episode: ScaffoldEpisode
    card: InteractionCard
    score: float
    cue_match: float
    position_match: float
    recency: float
    retrieval_probability: float
    matched_anchor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("score", "cue_match", "position_match", "recency", "retrieval_probability"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ProspectiveProbe:
    probe_id: str
    source_episode_id: str
    successor_episode_id: str
    cues: tuple[str, ...]
    rationale: str
    retrieval_only: bool = True

    def __post_init__(self) -> None:
        if not self.retrieval_only:
            raise ScaffoldError("prospective probes must remain retrieval-only")


class EpisodicScaffoldStore:
    def __init__(self, *, maximum_episodes: int = 250_000) -> None:
        self.maximum_episodes = positive_int("maximum_episodes", maximum_episodes, maximum=10_000_000)
        self._episodes: dict[str, ScaffoldEpisode] = {}
        self._anchors: dict[str, EpisodicAnchor] = {}
        self._by_namespace: dict[str, list[str]] = defaultdict(list)
        self._by_card: dict[str, set[str]] = defaultdict(set)
        self._anchor_index: dict[tuple[str, AnchorKind, str], set[str]] = defaultdict(set)
        self._successor: dict[str, str] = {}
        self._lock = threading.RLock()

    def next_ordinal(self, namespace: MemoryNamespace) -> int:
        with self._lock:
            return len(self._by_namespace[namespace.key]) + 1

    def latest(self, namespace: MemoryNamespace) -> ScaffoldEpisode | None:
        with self._lock:
            ids = self._by_namespace.get(namespace.key, ())
            return self._episodes.get(ids[-1]) if ids else None

    def put(self, episode: ScaffoldEpisode, anchors: Sequence[EpisodicAnchor]) -> ScaffoldEpisode:
        if {a.anchor_id for a in anchors} != set(episode.anchor_ids):
            raise ScaffoldError("episode/anchor identity mismatch")
        with self._lock:
            if episode.episode_id in self._episodes:
                if self._episodes[episode.episode_id] != episode:
                    raise ScaffoldError("episode id collision")
                return self._episodes[episode.episode_id]
            if len(self._episodes) >= self.maximum_episodes:
                raise ScaffoldError("scaffold capacity reached; consolidate or rotate store")
            ids = self._by_namespace[episode.namespace.key]
            if episode.ordinal != len(ids) + 1:
                raise ScaffoldError("episode ordinal must be contiguous")
            if episode.previous_episode_id is not None:
                if not ids or ids[-1] != episode.previous_episode_id:
                    raise ScaffoldError("previous episode is not namespace tail")
                self._successor[episode.previous_episode_id] = episode.episode_id
            self._episodes[episode.episode_id] = episode
            ids.append(episode.episode_id)
            self._by_card[episode.card_id].add(episode.episode_id)
            for anchor in anchors:
                if anchor.episode_id != episode.episode_id:
                    raise ScaffoldError("anchor references wrong episode")
                self._anchors[anchor.anchor_id] = anchor
                self._anchor_index[(episode.namespace.key, anchor.kind, anchor.cue)].add(episode.episode_id)
            return episode

    def get(self, episode_id: str) -> ScaffoldEpisode | None:
        with self._lock:
            return self._episodes.get(str(episode_id))

    def successor(self, episode_id: str) -> ScaffoldEpisode | None:
        with self._lock:
            successor_id = self._successor.get(str(episode_id))
            return self._episodes.get(successor_id) if successor_id else None

    def anchors(self, episode_id: str) -> tuple[EpisodicAnchor, ...]:
        with self._lock:
            episode = self._episodes.get(str(episode_id))
            if episode is None:
                return ()
            return tuple(self._anchors[x] for x in episode.anchor_ids if x in self._anchors)

    def update_anchor(self, anchor: EpisodicAnchor) -> None:
        with self._lock:
            if anchor.anchor_id not in self._anchors:
                raise ScaffoldError("unknown anchor")
            self._anchors[anchor.anchor_id] = anchor

    def episodes_for_card(self, card_id: str) -> tuple[ScaffoldEpisode, ...]:
        with self._lock:
            ids = self._by_card.get(str(card_id), ())
            return tuple(sorted((self._episodes[x] for x in ids), key=lambda e: (e.observed_at, e.ordinal)))

    def namespace_episodes(self, namespace: MemoryNamespace) -> tuple[ScaffoldEpisode, ...]:
        with self._lock:
            return tuple(self._episodes[x] for x in self._by_namespace.get(namespace.key, ()))

    def candidate_ids(self, namespace: MemoryNamespace, cues: Mapping[AnchorKind, Sequence[str]]) -> tuple[str, ...]:
        keys = {namespace.key}
        if namespace.session_id is not None:
            keys.add(namespace.parent().key)
        result: set[str] = set()
        with self._lock:
            for ns_key in keys:
                for kind, values in cues.items():
                    for cue in values:
                        result.update(self._anchor_index.get((ns_key, kind, str(cue).strip().casefold()), ()))
            return tuple(sorted(result, key=lambda x: (self._episodes[x].observed_at, self._episodes[x].ordinal), reverse=True))

    def chronological_window(self, episode_id: str, *, radius: int) -> tuple[ScaffoldEpisode, ...]:
        with self._lock:
            center = self._episodes.get(str(episode_id))
            if center is None:
                return ()
            ids = self._by_namespace.get(center.namespace.key, ())
            i = center.ordinal - 1
            return tuple(self._episodes[x] for x in ids[max(0, i-radius): min(len(ids), i+radius+1)])


class EpisodicScaffoldIndex:
    def __init__(
        self,
        cards: MemoryGameIndex,
        *,
        store: EpisodicScaffoldStore | None = None,
        policy: EpisodicScaffoldPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(cards, MemoryGameIndex):
            raise TypeError("cards must be MemoryGameIndex")
        self.cards = cards
        self.policy = policy or EpisodicScaffoldPolicy()
        self.store = store or EpisodicScaffoldStore(maximum_episodes=self.policy.maximum_episodes)
        self._clock = clock
        self._lock = threading.RLock()

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        return tuple(sorted(MemoryGameIndex._tokens(text)))

    def _make_anchors(
        self,
        episode_id: str,
        namespace: MemoryNamespace,
        card: InteractionCard,
        ordinal: int,
        observed_at: float,
        context_tags: Sequence[str],
        entity_cues: Sequence[str],
        prospective_cues: Sequence[str],
        provenance: Sequence[str],
    ) -> tuple[EpisodicAnchor, ...]:
        rows: list[tuple[AnchorKind, str, float]] = [
            (AnchorKind.POSITION, str(ordinal), 1.0),
            (AnchorKind.TEMPORAL, str(int(observed_at // self.policy.temporal_bucket_seconds)), 0.85),
            (AnchorKind.SOURCE, card.source.casefold(), 0.75),
        ]
        rows += [(AnchorKind.TOKEN, token, 0.70) for token in card.cue_tokens[:self.policy.maximum_token_anchors]]
        rows += [(AnchorKind.CONTEXT, str(x).strip().casefold(), 0.82) for x in context_tags if str(x).strip()]
        rows += [(AnchorKind.ENTITY, str(x).strip().casefold(), 0.90) for x in entity_cues if str(x).strip()]
        rows += [(AnchorKind.PROSPECTIVE, str(x).strip().casefold(), 0.62) for x in prospective_cues if str(x).strip()]
        best: dict[tuple[AnchorKind, str], float] = {}
        for kind, cue, strength in rows:
            best[(kind, cue)] = max(best.get((kind, cue), 0.0), strength)
        chosen = sorted(best.items(), key=lambda item: (-item[1], item[0][0].value, item[0][1]))[:self.policy.maximum_anchors_per_episode]
        return tuple(
            EpisodicAnchor(
                anchor_id=stable_id("anchor", {"episode": episode_id, "kind": kind.value, "cue": cue}, length=32),
                episode_id=episode_id,
                namespace_key=namespace.key,
                kind=kind,
                cue=cue,
                strength=strength,
                created_at=observed_at,
                last_reinforced_at=observed_at,
                provenance_ids=tuple(provenance),
            )
            for (kind, cue), strength in chosen
        )

    def capture_interaction(
        self,
        namespace: MemoryNamespace,
        content: str,
        *,
        context_tags: Sequence[str] = (),
        entity_cues: Sequence[str] = (),
        prospective_cues: Sequence[str] = (),
        source: str = "user-interaction",
        trust: float = 0.65,
        salience: float = 0.65,
        surprise: float = 0.0,
        provenance: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[InteractionCard, ScaffoldEpisode]:
        now = self._clock()
        card = self.cards.capture_interaction(
            namespace, content, context_tags=context_tags, source=source, trust=trust,
            salience=salience, surprise=surprise, provenance=provenance, metadata=metadata,
        )
        with self._lock:
            ordinal = self.store.next_ordinal(namespace)
            previous = self.store.latest(namespace)
            episode_id = stable_id("episode", {
                "namespace": namespace.key, "ordinal": ordinal, "card": card.card_id, "observed_at": now,
            }, length=32)
            anchors = self._make_anchors(
                episode_id, namespace, card, ordinal, now, context_tags,
                entity_cues, prospective_cues, provenance,
            )
            episode = ScaffoldEpisode(
                episode_id=episode_id, namespace=namespace, card_id=card.card_id,
                ordinal=ordinal, observed_at=now,
                previous_episode_id=previous.episode_id if previous else None,
                source=source, context_tags=tuple(context_tags), entity_cues=tuple(entity_cues),
                anchor_ids=tuple(a.anchor_id for a in anchors),
                content_fingerprint=card.content_fingerprint,
                metadata={**dict(metadata or {}), "prospective_cues_retrieval_only": tuple(prospective_cues)},
            )
            self.store.put(episode, anchors)
            return card, episode

    def search(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        entity_cues: Sequence[str] = (),
        around_ordinal: int | None = None,
        temporal_bucket: int | None = None,
        prospective_cues: Sequence[str] = (),
        limit: int | None = None,
    ) -> tuple[ScaffoldHit, ...]:
        query = bounded_text("scaffold query", query, maximum=32_000)
        maximum = self.policy.maximum_hits if limit is None else positive_int("limit", limit, maximum=1000)
        cues: dict[AnchorKind, tuple[str, ...]] = {AnchorKind.TOKEN: self._tokens(query)}
        if context_tags:
            cues[AnchorKind.CONTEXT] = tuple(sorted({str(x).strip().casefold() for x in context_tags if str(x).strip()}))
        if entity_cues:
            cues[AnchorKind.ENTITY] = tuple(sorted({str(x).strip().casefold() for x in entity_cues if str(x).strip()}))
        if around_ordinal is not None:
            cues[AnchorKind.POSITION] = (str(int(around_ordinal)),)
        if temporal_bucket is not None:
            cues[AnchorKind.TEMPORAL] = (str(int(temporal_bucket)),)
        if prospective_cues:
            cues[AnchorKind.PROSPECTIVE] = tuple(sorted({str(x).strip().casefold() for x in prospective_cues if str(x).strip()}))
        candidates = self.store.candidate_ids(namespace, cues)
        if not candidates:
            candidates = tuple(e.episode_id for e in self.store.namespace_episodes(namespace)[-maximum*2:])
        query_keys = {(kind, cue) for kind, values in cues.items() for cue in values}
        now = self._clock()
        hits: list[ScaffoldHit] = []
        for episode_id in candidates:
            episode = self.store.get(episode_id)
            if episode is None:
                continue
            card = self.cards.store.get(episode.card_id)
            if card is None:
                continue
            anchors = self.store.anchors(episode_id)
            amap = {(a.kind, a.cue): a for a in anchors}
            matched = [amap[key] for key in query_keys if key in amap]
            cue_match = min(1.0, sum(a.strength for a in matched) / max(1.0, len(query_keys))) if query_keys else 0.0
            position = 0.5 if around_ordinal is None else math.exp(-abs(episode.ordinal-int(around_ordinal))/4.0)
            age = max(0.0, now-episode.observed_at)
            recency = math.exp(-math.log(2.0)*age/self.policy.forgetting_half_life_seconds)
            retrieval = self.cards.predicted_retrieval(card, now=now)
            score = (
                self.policy.cue_weight*cue_match + self.policy.position_weight*position +
                self.policy.recency_weight*recency + self.policy.retrieval_weight*retrieval +
                self.policy.trust_weight*card.trust + self.policy.salience_weight*card.salience
            )
            hits.append(ScaffoldHit(
                episode, card, max(0.0, min(1.0, score)), cue_match, position,
                recency, retrieval, tuple(sorted(a.anchor_id for a in matched)),
            ))
        hits.sort(key=lambda h: (h.score, h.cue_match, h.episode.observed_at, h.episode.ordinal), reverse=True)
        return tuple(hits[:maximum])

    def chronological_window(self, episode_id: str, *, radius: int = 2) -> tuple[ScaffoldEpisode, ...]:
        if radius <= 0 or radius > self.policy.maximum_window_radius:
            raise ScaffoldError("radius outside policy")
        return self.store.chronological_window(episode_id, radius=radius)

    def prospective_probes(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        entity_cues: Sequence[str] = (),
        limit: int = 4,
    ) -> tuple[ProspectiveProbe, ...]:
        limit = positive_int("limit", limit, maximum=100)
        probes: list[ProspectiveProbe] = []
        for hit in self.search(namespace, query, context_tags=context_tags, entity_cues=entity_cues, limit=max(limit, 1)):
            successor = self.store.successor(hit.episode.episode_id)
            if successor is None:
                continue
            cues = tuple(sorted({
                a.cue for a in self.store.anchors(successor.episode_id)
                if a.kind in {AnchorKind.CONTEXT, AnchorKind.ENTITY, AnchorKind.TOKEN, AnchorKind.PROSPECTIVE}
            }))[:12]
            if not cues:
                continue
            probes.append(ProspectiveProbe(
                stable_id("prospective-probe", {"source": hit.episode.episode_id, "successor": successor.episode_id, "cues": cues}, length=32),
                hit.episode.episode_id, successor.episode_id, cues,
                "Historically adjacent cues for retrieval only; not evidence or predicted truth.",
            ))
            if len(probes) >= limit:
                break
        return tuple(probes)

    def record_recall(
        self,
        card_id: str,
        *,
        success: bool,
        predicted_probability: float | None = None,
        surprise: float | None = None,
    ) -> RecallFeedback:
        feedback = self.cards.record_feedback(
            card_id, success=success, predicted_probability=predicted_probability, surprise=surprise,
        )
        now = self._clock()
        for episode in self.store.episodes_for_card(card_id):
            for anchor in self.store.anchors(episode.episode_id):
                target = 1.0 if success else max(0.0, 1.0-feedback.prediction_error)
                plasticity = min(1.0, self.policy.reinforcement_rate*(1.0+feedback.surprise))
                strength = (1.0-plasticity)*anchor.strength + plasticity*target
                self.store.update_anchor(replace(
                    anchor, strength=max(0.0, min(1.0, strength)),
                    last_reinforced_at=now, reinforcement_count=anchor.reinforcement_count+1,
                ))
        return feedback


class ScaffoldedMemoryGameIndex:
    """MemoryGameIndex-compatible facade with scaffold-aware ranking."""

    def __init__(
        self,
        base: MemoryGameIndex | None = None,
        *,
        scaffold: EpisodicScaffoldIndex | None = None,
        policy: MemoryGamePolicy | None = None,
        scaffold_policy: EpisodicScaffoldPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.base = base or MemoryGameIndex(policy=policy, clock=clock)
        self.scaffold = scaffold or EpisodicScaffoldIndex(self.base, policy=scaffold_policy, clock=clock)
        self.policy = self.base.policy
        self.store = self.base.store

    def capture_interaction(self, namespace: MemoryNamespace, content: str, **kwargs: Any) -> InteractionCard:
        entity_cues = tuple(kwargs.pop("entity_cues", ()))
        prospective_cues = tuple(kwargs.pop("prospective_cues", ()))
        card, _ = self.scaffold.capture_interaction(
            namespace, content, entity_cues=entity_cues, prospective_cues=prospective_cues, **kwargs
        )
        return card

    def predicted_retrieval(self, card: InteractionCard, *, now: float | None = None) -> float:
        return self.base.predicted_retrieval(card, now=now)

    def record_feedback(self, card_id: str, **kwargs: Any) -> RecallFeedback:
        return self.scaffold.record_recall(card_id, **kwargs)

    def coverage(self, query: str, hits: Sequence[CardHit]) -> float:
        return self.base.coverage(query, hits)

    def fast_path_ready(self, query: str, hits: Sequence[CardHit]) -> bool:
        return self.base.fast_path_ready(query, hits)

    def search(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        limit: int | None = None,
    ) -> tuple[CardHit, ...]:
        maximum = self.policy.max_hits if limit is None else positive_int("limit", limit, maximum=1000)
        base_hits = self.base.search(namespace, query, context_tags=context_tags, limit=max(maximum*2, maximum))
        scaffold_hits = self.scaffold.search(namespace, query, context_tags=context_tags, limit=max(maximum*2, maximum))
        best_scaffold: dict[str, ScaffoldHit] = {}
        for hit in scaffold_hits:
            old = best_scaffold.get(hit.card.card_id)
            if old is None or hit.score > old.score:
                best_scaffold[hit.card.card_id] = hit
        merged: dict[str, CardHit] = {}
        for hit in base_hits:
            episode_hit = best_scaffold.get(hit.card.card_id)
            if episode_hit is None:
                merged[hit.card.card_id] = hit
                continue
            bonus = self.scaffold.policy.scaffold_bonus_weight*episode_hit.score
            score = 1.0-(1.0-hit.score)*(1.0-min(1.0, bonus))
            merged[hit.card.card_id] = CardHit(
                hit.card, max(0.0, min(1.0, score)), hit.lexical,
                max(hit.context_match, episode_hit.cue_match), hit.activation,
                max(hit.retrieval_probability, episode_hit.retrieval_probability),
                max(hit.recency, episode_hit.recency),
            )
        for card_id, episode_hit in best_scaffold.items():
            if card_id not in merged:
                merged[card_id] = CardHit(
                    episode_hit.card, episode_hit.score, 0.0, episode_hit.cue_match,
                    0.0, episode_hit.retrieval_probability, episode_hit.recency,
                )
        return tuple(sorted(
            merged.values(),
            key=lambda h: (h.score, h.retrieval_probability, h.card.updated_at, h.card.card_id),
            reverse=True,
        )[:maximum])
