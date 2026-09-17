"""Hierarchical context acquisition for Jeeves.

Retrieval order is a contract, not an implementation accident:

    L0 interaction/index cards
      -> L1 scoped memory
      -> L2 versioned context repository
      -> L3 caches / structured databases
      -> L4 logs / journals / diaries
      -> L5 annals / chronicles / archives
      -> optional external context adapters

The pipeline stops as soon as the accumulated recall is sufficiently relevant,
trusted, and covering.  Expensive narrative stores therefore do not drown a
high-confidence personal cue.  Conversely, weak cue-card recall cannot block a
deeper search.

The existing ``ContextCompiler`` remains the final bounded prompt compiler.  A
``LayeredContextCompiler`` resolves fast/deep context first and injects audited
sections through its existing ``extra_sections`` contract.  The ordinary
MemoryManager is still allowed to render its native memory section exactly once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Mapping, Sequence

from .cognition import ContextCompiler, ContextPacket, ContextSection, RunScratchpad
from .context_repository import ContextRepository, RetrievalHit
from .evidence import EvidenceLedger
from .memory import MemoryHit, MemoryManager, MemoryNamespace
from .memory_game import CardHit, InteractionCard, MemoryGameIndex
from .relational_memory import RelationalHit, RelationalMemoryIndex
from .types import AgentContractError, Goal, Plan, PlanStep, ToolObservation, bounded_text, json_safe, positive_int, probability, stable_fingerprint


class ContextTier(IntEnum):
    INDEX_CARD = 0
    SCOPED_MEMORY = 1
    CONTEXT_REPOSITORY = 2
    CACHE = 3
    DATABASE = 4
    LOG = 5
    JOURNAL = 6
    DIARY = 7
    ANNAL = 8
    CHRONICLE = 9
    ARCHIVE = 10
    EXTERNAL = 11


class ContextSourceKind(str, Enum):
    CACHE = "cache"
    DATABASE = "database"
    LOG = "log"
    JOURNAL = "journal"
    DIARY = "diary"
    ANNAL = "annal"
    CHRONICLE = "chronicle"
    ARCHIVE = "archive"
    VECTOR_INDEX = "vector_index"
    GRAPH = "graph"
    OBJECT_STORE = "object_store"
    FILESYSTEM = "filesystem"
    EXTERNAL = "external"


_KIND_TIER: dict[ContextSourceKind, ContextTier] = {
    ContextSourceKind.CACHE: ContextTier.CACHE,
    ContextSourceKind.DATABASE: ContextTier.DATABASE,
    ContextSourceKind.LOG: ContextTier.LOG,
    ContextSourceKind.JOURNAL: ContextTier.JOURNAL,
    ContextSourceKind.DIARY: ContextTier.DIARY,
    ContextSourceKind.ANNAL: ContextTier.ANNAL,
    ContextSourceKind.CHRONICLE: ContextTier.CHRONICLE,
    ContextSourceKind.ARCHIVE: ContextTier.ARCHIVE,
    ContextSourceKind.VECTOR_INDEX: ContextTier.DATABASE,
    ContextSourceKind.GRAPH: ContextTier.DATABASE,
    ContextSourceKind.OBJECT_STORE: ContextTier.ARCHIVE,
    ContextSourceKind.FILESYSTEM: ContextTier.ARCHIVE,
    ContextSourceKind.EXTERNAL: ContextTier.EXTERNAL,
}


@dataclass(frozen=True, slots=True)
class SourceRecord:
    record_id: str
    source_name: str
    source_kind: ContextSourceKind
    content: str
    relevance: float
    trust: float
    confidence: float
    cost: float = 0.5
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.record_id).strip() or not str(self.source_name).strip():
            raise AgentContractError("source record requires record_id and source_name")
        if not isinstance(self.source_kind, ContextSourceKind):
            object.__setattr__(self, "source_kind", ContextSourceKind(str(self.source_kind)))
        object.__setattr__(self, "content", bounded_text("source record content", self.content, maximum=128_000))
        for name in ("relevance", "trust", "confidence", "cost"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "tags", tuple(sorted({str(x).casefold() for x in self.tags if str(x).strip()})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def utility(self) -> float:
        return max(0.0, min(1.0, 0.40 * self.relevance + 0.25 * self.trust + 0.25 * self.confidence + 0.10 * (1.0 - self.cost)))


SearchCallback = Callable[[str, int, Sequence[str]], Sequence[SourceRecord]]


@dataclass(frozen=True, slots=True)
class ContextSourceAdapter:
    name: str
    kind: ContextSourceKind
    search_callback: SearchCallback
    enabled: bool = True
    priority: int = 100
    maximum_hits: int = 8

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise AgentContractError("context source adapter requires name")
        if not isinstance(self.kind, ContextSourceKind):
            object.__setattr__(self, "kind", ContextSourceKind(str(self.kind)))
        if not callable(self.search_callback):
            raise AgentContractError("search_callback must be callable")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise AgentContractError("adapter priority must be integer")
        object.__setattr__(self, "maximum_hits", positive_int("maximum_hits", self.maximum_hits, maximum=1000))

    @property
    def tier(self) -> ContextTier:
        return _KIND_TIER[self.kind]

    def search(self, query: str, *, tags: Sequence[str] = ()) -> tuple[SourceRecord, ...]:
        if not self.enabled:
            return ()
        records = tuple(self.search_callback(query, self.maximum_hits, tuple(tags)))
        if any(not isinstance(record, SourceRecord) for record in records):
            raise AgentContractError(f"adapter {self.name} returned non-SourceRecord value")
        if any(record.source_name != self.name for record in records):
            raise AgentContractError(f"adapter {self.name} returned mismatched source_name")
        return tuple(sorted(records, key=lambda item: (-item.utility, item.record_id))[: self.maximum_hits])


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    card_limit: int = 12
    memory_limit: int = 10
    repository_limit: int = 12
    source_limit_per_tier: int = 16
    minimum_item_score: float = 0.18
    stop_coverage: float = 0.78
    stop_confidence: float = 0.74
    stop_trust: float = 0.62
    minimum_deep_gain: float = 0.025
    maximum_tier: ContextTier = ContextTier.ARCHIVE
    max_total_chars: int = 28_000

    def __post_init__(self) -> None:
        for name in ("card_limit", "memory_limit", "repository_limit", "source_limit_per_tier", "max_total_chars"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=2_000_000))
        for name in ("minimum_item_score", "stop_coverage", "stop_confidence", "stop_trust", "minimum_deep_gain"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not isinstance(self.maximum_tier, ContextTier):
            object.__setattr__(self, "maximum_tier", ContextTier(int(self.maximum_tier)))


@dataclass(frozen=True, slots=True)
class ResolutionStage:
    tier: ContextTier
    source: str
    queried: bool
    hit_count: int
    coverage_after: float
    confidence_after: float
    trust_after: float
    marginal_gain: float
    stop_after: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ResolvedItem:
    item_id: str
    tier: ContextTier
    source: str
    content: str
    score: float
    confidence: float
    trust: float
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("score", "confidence", "trust"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "content", bounded_text("resolved content", self.content, maximum=128_000))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ContextResolution:
    query: str
    items: tuple[ResolvedItem, ...]
    stages: tuple[ResolutionStage, ...]
    stopped_at: ContextTier
    fast_path: bool
    final_coverage: float
    final_confidence: float
    final_trust: float
    unresolved_terms: tuple[str, ...]
    fingerprint: str

    def sections(self, *, maximum_chars: int = 24_000) -> tuple[ContextSection, ...]:
        maximum_chars = positive_int("maximum_chars", maximum_chars, maximum=1_000_000)
        grouped: dict[ContextTier, list[ResolvedItem]] = {}
        for item in self.items:
            # Scoped memory is rendered by ContextCompiler's native MemoryManager
            # path, so do not duplicate it in extra sections.
            if item.tier is ContextTier.SCOPED_MEMORY:
                continue
            grouped.setdefault(item.tier, []).append(item)
        sections: list[ContextSection] = []
        remaining = maximum_chars
        for tier in sorted(grouped):
            rows: list[str] = []
            source_ids: list[str] = []
            for item in sorted(grouped[tier], key=lambda x: (-x.score, x.item_id)):
                row = f"[{item.item_id}] source={item.source} score={item.score:.4f} trust={item.trust:.4f} confidence={item.confidence:.4f}\n{item.content}"
                if len(row) + 2 > remaining:
                    continue
                rows.append(row)
                source_ids.append(item.item_id)
                remaining -= len(row) + 2
            if rows:
                sections.append(
                    ContextSection(
                        name=f"context_{tier.name.casefold()}",
                        content="\n\n".join(rows),
                        priority=max(35, 98 - int(tier) * 5),
                        required=False,
                        source_ids=tuple(source_ids),
                    )
                )
            if remaining <= 0:
                break
        return tuple(sections)


class LayeredContextResolver:
    """Resolve context depth-first by cost with an evidence-preserving audit."""

    def __init__(
        self,
        *,
        cards: MemoryGameIndex,
        memory: MemoryManager,
        relations: RelationalMemoryIndex | None = None,
        repository: ContextRepository | None = None,
        adapters: Sequence[ContextSourceAdapter] = (),
        policy: ResolutionPolicy | None = None,
    ) -> None:
        self.cards = cards
        self.memory = memory
        if relations is not None and relations.cards is not cards:
            raise AgentContractError("relational memory must use the same MemoryGameIndex as resolver")
        self.relations = relations
        self.repository = repository
        self.adapters = tuple(sorted(adapters, key=lambda item: (item.tier, item.priority, item.name)))
        self.policy = policy or ResolutionPolicy()

    @staticmethod
    def _terms(text: str) -> set[str]:
        token = ""
        result: set[str] = set()
        for char in (text or "").casefold():
            if char.isalnum() or char in "_-'":
                token += char
            elif token:
                result.add(token)
                token = ""
        if token:
            result.add(token)
        return result

    @classmethod
    def _coverage(cls, query: str, items: Sequence[ResolvedItem]) -> tuple[float, tuple[str, ...]]:
        query_terms = cls._terms(query)
        if not query_terms:
            return 0.0, ()
        covered: set[str] = set()
        for item in items:
            if item.score < 0.1:
                continue
            covered |= query_terms & cls._terms(item.content)
        missing = tuple(sorted(query_terms - covered))
        return len(covered) / len(query_terms), missing

    @staticmethod
    def _aggregate(items: Sequence[ResolvedItem]) -> tuple[float, float]:
        if not items:
            return 0.0, 0.0
        weights = [max(1e-9, item.score) for item in items]
        total = sum(weights)
        confidence = sum(w * item.confidence for w, item in zip(weights, items)) / total
        trust = sum(w * item.trust for w, item in zip(weights, items)) / total
        return confidence, trust

    def _ready(self, coverage: float, confidence: float, trust: float) -> bool:
        return coverage >= self.policy.stop_coverage and confidence >= self.policy.stop_confidence and trust >= self.policy.stop_trust

    @staticmethod
    def _card_item(hit: CardHit) -> ResolvedItem:
        return ResolvedItem(
            item_id=hit.card.card_id,
            tier=ContextTier.INDEX_CARD,
            source=hit.card.source,
            content=hit.card.content,
            score=hit.score,
            confidence=hit.retrieval_probability,
            trust=hit.card.trust,
            evidence_ids=hit.card.provenance,
            metadata={"activation": hit.activation, "lexical": hit.lexical, "context_match": hit.context_match},
        )

    @staticmethod
    def _relation_item(hit: RelationalHit) -> ResolvedItem:
        return ResolvedItem(
            item_id=hit.trace.relation_id,
            tier=ContextTier.INDEX_CARD,
            source="relational_memory",
            content=hit.content,
            score=hit.score,
            confidence=hit.retrieval_confidence,
            trust=hit.trace.trust,
            evidence_ids=hit.evidence_ids,
            metadata={
                "kind": hit.trace.kind.value,
                "card_ids": hit.trace.card_ids,
                "occurrences": hit.trace.occurrence_count,
                "cue_match": hit.cue_match,
                "lexical": hit.lexical,
                "support": hit.support,
                "transition_probability": hit.transition_probability,
                "context_match": hit.context_match,
            },
        )

    @staticmethod
    def _memory_item(hit: MemoryHit) -> ResolvedItem:
        return ResolvedItem(
            item_id=hit.record.memory_id,
            tier=ContextTier.SCOPED_MEMORY,
            source=hit.record.source,
            content=hit.record.content,
            score=hit.score,
            confidence=max(hit.record.trust, hit.record.salience) * 0.5 + min(hit.lexical_score, 1.0) * 0.5,
            trust=hit.record.trust,
            evidence_ids=tuple(ref.evidence_id for ref in hit.record.evidence),
            metadata={"kind": hit.record.kind.value, "salience": hit.record.salience, "promoted": hit.record.promoted},
        )

    @staticmethod
    def _repository_item(hit: RetrievalHit) -> ResolvedItem:
        entry = hit.entry
        return ResolvedItem(
            item_id=entry.entry_id,
            tier=ContextTier.CONTEXT_REPOSITORY,
            source=entry.source,
            content=entry.content,
            score=hit.score,
            confidence=entry.confidence,
            trust=entry.trust,
            evidence_ids=tuple(ref.evidence_id for ref in entry.evidence),
            metadata={"kind": entry.kind.value, "key": entry.key, "promoted": entry.promoted},
        )

    @staticmethod
    def _source_item(record: SourceRecord) -> ResolvedItem:
        return ResolvedItem(
            item_id=record.record_id,
            tier=_KIND_TIER[record.source_kind],
            source=record.source_name,
            content=record.content,
            score=record.utility,
            confidence=record.confidence,
            trust=record.trust,
            evidence_ids=record.evidence_ids,
            metadata={"kind": record.source_kind.value, **dict(record.metadata)},
        )

    def resolve(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        force_max_tier: ContextTier | None = None,
    ) -> ContextResolution:
        text = bounded_text("context query", query, maximum=32_000)
        max_tier = self.policy.maximum_tier if force_max_tier is None else force_max_tier
        if not isinstance(max_tier, ContextTier):
            max_tier = ContextTier(int(max_tier))
        items: list[ResolvedItem] = []
        stages: list[ResolutionStage] = []
        previous_quality = 0.0

        def measure(tier: ContextTier, source: str, hit_count: int, reason: str) -> bool:
            nonlocal previous_quality
            coverage, missing = self._coverage(text, items)
            confidence, trust = self._aggregate(items)
            quality = 0.45 * coverage + 0.30 * confidence + 0.25 * trust
            gain = max(0.0, quality - previous_quality)
            previous_quality = quality
            stop = self._ready(coverage, confidence, trust)
            stages.append(ResolutionStage(tier, source, True, hit_count, coverage, confidence, trust, gain, stop, reason))
            return stop

        # L0: cue-card/memory-game layer. This always runs first.
        card_hits = self.cards.search(namespace, text, context_tags=context_tags, limit=self.policy.card_limit)
        items.extend(self._card_item(hit) for hit in card_hits if hit.score >= self.policy.minimum_item_score)
        card_native_ready = self.cards.fast_path_ready(text, card_hits)
        stop = measure(ContextTier.INDEX_CARD, "memory_game", len(card_hits), "fast cue-card lookup")

        # L0b: expand strong cue hits through learned pair/triad structure before
        # touching durable memory. This keeps juxtaposition, motifs, transitions,
        # and prediction-error boundaries on the same cheap retrieval path.
        relation_hits: tuple[RelationalHit, ...] = ()
        if self.relations is not None and card_hits:
            relation_hits = self.relations.search(
                namespace,
                text,
                card_hits,
                context_tags=context_tags,
                limit=self.policy.card_limit,
                include_parent=True,
            )
            items.extend(
                self._relation_item(hit)
                for hit in relation_hits
                if hit.score >= self.policy.minimum_item_score
            )
            stop = measure(
                ContextTier.INDEX_CARD,
                "relational_memory",
                len(relation_hits),
                "cue-card relational expansion",
            )

        if card_native_ready and stop:
            coverage, missing = self._coverage(text, items)
            confidence, trust = self._aggregate(items)
            fingerprint = stable_fingerprint({"query": text, "items": [(x.item_id, x.score) for x in items], "stages": [(s.tier, s.stop_after) for s in stages]})
            return ContextResolution(text, tuple(items), tuple(stages), ContextTier.INDEX_CARD, True, coverage, confidence, trust, missing, fingerprint)

        if max_tier >= ContextTier.SCOPED_MEMORY:
            # Search the retriever without touching access counters. The native
            # ContextCompiler later performs the single authoritative recall/touch.
            memory_hits = self.memory.retriever.search(namespace, text, limit=self.policy.memory_limit, include_parent=True)
            items.extend(self._memory_item(hit) for hit in memory_hits if hit.score >= self.policy.minimum_item_score)
            if measure(ContextTier.SCOPED_MEMORY, "memory_manager", len(memory_hits), "scoped durable memory"):
                return self._finish(text, items, stages, ContextTier.SCOPED_MEMORY, False)

        if self.repository is not None and max_tier >= ContextTier.CONTEXT_REPOSITORY:
            repo_hits = self.repository.retrieve(text, max_entries=self.policy.repository_limit, touch=False)
            items.extend(self._repository_item(hit) for hit in repo_hits if hit.score >= self.policy.minimum_item_score)
            if measure(ContextTier.CONTEXT_REPOSITORY, "context_repository", len(repo_hits), "versioned durable context"):
                return self._finish(text, items, stages, ContextTier.CONTEXT_REPOSITORY, False)

        adapters_by_tier: dict[ContextTier, list[ContextSourceAdapter]] = {}
        for adapter in self.adapters:
            if adapter.enabled and adapter.tier <= max_tier:
                adapters_by_tier.setdefault(adapter.tier, []).append(adapter)

        for tier in sorted(adapters_by_tier):
            before = len(items)
            for adapter in adapters_by_tier[tier]:
                records = adapter.search(text, tags=context_tags)
                for record in records[: self.policy.source_limit_per_tier]:
                    item = self._source_item(record)
                    if item.score >= self.policy.minimum_item_score:
                        items.append(item)
                if len(items) - before >= self.policy.source_limit_per_tier:
                    break
            stop = measure(tier, "+".join(adapter.name for adapter in adapters_by_tier[tier]), len(items) - before, "deeper context tier")
            if stop:
                return self._finish(text, items, stages, tier, False)
            if stages[-1].marginal_gain < self.policy.minimum_deep_gain and tier >= ContextTier.JOURNAL:
                # Past the structured tiers, low marginal gain is a rational stop.
                break

        stopped = stages[-1].tier if stages else ContextTier.INDEX_CARD
        return self._finish(text, items, stages, stopped, False)

    def _finish(
        self,
        query: str,
        items: Sequence[ResolvedItem],
        stages: Sequence[ResolutionStage],
        stopped_at: ContextTier,
        fast_path: bool,
    ) -> ContextResolution:
        # Deduplicate exact item ids and enforce a total character ceiling.
        best: dict[str, ResolvedItem] = {}
        for item in items:
            prior = best.get(item.item_id)
            if prior is None or (item.score, item.trust, item.confidence) > (prior.score, prior.trust, prior.confidence):
                best[item.item_id] = item
        ordered = sorted(best.values(), key=lambda item: (item.tier, -item.score, item.item_id))
        retained: list[ResolvedItem] = []
        used = 0
        for item in ordered:
            if used + len(item.content) > self.policy.max_total_chars:
                continue
            retained.append(item)
            used += len(item.content)
        coverage, missing = self._coverage(query, retained)
        confidence, trust = self._aggregate(retained)
        fingerprint = stable_fingerprint(
            {
                "query": query,
                "items": [(item.item_id, int(item.tier), round(item.score, 10), stable_fingerprint(item.content)) for item in retained],
                "stages": [(int(stage.tier), stage.source, stage.hit_count, round(stage.marginal_gain, 10), stage.stop_after) for stage in stages],
            }
        )
        return ContextResolution(query, tuple(retained), tuple(stages), stopped_at, fast_path, coverage, confidence, trust, missing, fingerprint)


class LayeredContextCompiler:
    """Drop-in orchestration layer around the existing deterministic compiler."""

    def __init__(self, resolver: LayeredContextResolver, compiler: ContextCompiler | None = None) -> None:
        self.resolver = resolver
        self.compiler = compiler or ContextCompiler()

    def capture_user_interaction(
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
        return self.resolver.cards.capture_interaction(
            namespace,
            content,
            context_tags=context_tags,
            source=source,
            trust=trust,
            salience=salience,
            surprise=surprise,
            provenance=provenance,
            metadata=metadata,
        )

    def compile(
        self,
        *,
        system_instruction: str,
        task_instruction: str,
        goal: Goal,
        namespace: MemoryNamespace,
        memory: MemoryManager,
        evidence: EvidenceLedger,
        plan: Plan | None = None,
        current_step: PlanStep | None = None,
        observations: Sequence[ToolObservation] = (),
        scratchpad: RunScratchpad | None = None,
        extra_sections: Sequence[ContextSection] = (),
        context_tags: Sequence[str] = (),
        force_max_tier: ContextTier | None = None,
    ) -> tuple[ContextPacket, ContextResolution]:
        query_parts = [goal.objective, task_instruction]
        if current_step is not None:
            query_parts.extend((current_step.title, current_step.description, current_step.expected_outcome))
        query = " ".join(part for part in query_parts if part)
        resolution = self.resolver.resolve(namespace, query, context_tags=context_tags, force_max_tier=force_max_tier)
        layered_sections = resolution.sections(maximum_chars=self.resolver.policy.max_total_chars)
        audit = ContextSection(
            name="context_resolution_audit",
            content=str(
                {
                    "fingerprint": resolution.fingerprint,
                    "fast_path": resolution.fast_path,
                    "stopped_at": resolution.stopped_at.name,
                    "coverage": round(resolution.final_coverage, 6),
                    "confidence": round(resolution.final_confidence, 6),
                    "trust": round(resolution.final_trust, 6),
                    "unresolved_terms": list(resolution.unresolved_terms[:64]),
                    "stages": [
                        {
                            "tier": stage.tier.name,
                            "source": stage.source,
                            "hits": stage.hit_count,
                            "gain": round(stage.marginal_gain, 6),
                            "stop": stage.stop_after,
                        }
                        for stage in resolution.stages
                    ],
                }
            ),
            priority=52,
            required=False,
            source_ids=(resolution.fingerprint,),
        )
        packet = self.compiler.compile(
            system_instruction=system_instruction,
            task_instruction=task_instruction,
            goal=goal,
            namespace=namespace,
            memory=memory,
            evidence=evidence,
            plan=plan,
            current_step=current_step,
            observations=observations,
            scratchpad=scratchpad,
            extra_sections=tuple(layered_sections) + (audit,) + tuple(extra_sections),
        )
        return packet, resolution
