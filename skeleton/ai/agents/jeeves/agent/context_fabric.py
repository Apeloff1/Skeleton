"""Multi-stage context fabric for Jeeves.

Retrieval order:
    1. memory-game cue/index cards (cheap, associative, user-local)
    2. targeted canonical rehydration of the indexed sources
    3. semantic-lens routing over query + recalled adjacency
    4. broad deep-store search only when required
    5. provenance-aware deduplication and bounded packing

The fabric can front journals, logs, diaries, annals, chronicles, databases,
caches, files, the ContextRepository, and MemoryManager through adapters.

Fast cards never override canonical source content.  A stale card fingerprint is
reported and the canonical record wins.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from .context_repository import ContextKind, ContextRepository
from .lens_governance import LensGovernanceDecision, LensScienceRegistry
from .lens_system import LensBundle, SemanticLensRouter
from .memory import MemoryManager, MemoryNamespace
from .memory_game_index import CardKind, MemoryGameIndex, RecallPacket, SourceTier
from .types import AgentContractError, json_safe, positive_int, probability, stable_fingerprint


@dataclass(frozen=True, slots=True)
class DeepContextRecord:
    source_tier: SourceTier
    source_ref: str
    source_fingerprint: str
    content: str
    canonical: bool
    trust: float
    confidence: float
    salience: float
    token_estimate: int
    source_provider: str = ""
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source_tier, SourceTier):
            object.__setattr__(self, "source_tier", SourceTier(str(self.source_tier)))
        source_ref = str(self.source_ref).strip()
        if not source_ref:
            raise AgentContractError("source_ref cannot be empty")
        object.__setattr__(self, "source_ref", source_ref[:2048])
        source_fingerprint = str(self.source_fingerprint).strip().lower()
        if not source_fingerprint:
            raise AgentContractError("source_fingerprint cannot be empty")
        object.__setattr__(self, "source_fingerprint", source_fingerprint[:2048])
        content = str(self.content)
        object.__setattr__(self, "content", content)
        if not isinstance(self.canonical, bool):
            raise AgentContractError("canonical must be boolean")
        object.__setattr__(
            self,
            "source_provider",
            str(self.source_provider).strip()[:512],
        )
        for name in ("trust", "confidence", "salience"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        token_estimate = positive_int(
            "token_estimate",
            self.token_estimate,
            maximum=10_000_000,
        )
        minimum_token_estimate = max(1, (len(content) + 3) // 4)
        if token_estimate < minimum_token_estimate:
            raise AgentContractError(
                "token_estimate understates context content size"
            )
        object.__setattr__(self, "token_estimate", token_estimate)
        tags = tuple(
            sorted(
                {
                    str(value).casefold().strip()
                    for value in self.tags
                    if str(value).strip()
                }
            )
        )
        if len(tags) > 64 or any(len(tag) > 128 for tag in tags):
            raise AgentContractError("invalid context tags")
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


class ContextStoreAdapter(Protocol):
    source_tier: SourceTier

    def fetch_refs(
        self,
        namespace_key: str,
        source_refs: Sequence[str],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        ...

    def search(
        self,
        namespace_key: str,
        query: str,
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        ...


@dataclass(frozen=True, slots=True)
class ContextFabricPolicy:
    fast_limit: int = 8
    associative_limit: int = 8
    deep_limit: int = 16
    maximum_tokens: int = 6000
    minimum_fast_hits_before_skip_deep: int = 2
    minimum_deep_trust: float = 0.0
    always_rehydrate_index_hits: bool = True
    broad_search_on_conflict: bool = True
    broad_search_on_fast_fallback: bool = True
    lens_limit: int = 16
    index_deep_results: bool = True

    def __post_init__(self) -> None:
        for name in ("fast_limit", "associative_limit", "deep_limit", "maximum_tokens", "minimum_fast_hits_before_skip_deep", "lens_limit"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))
        object.__setattr__(
            self,
            "minimum_deep_trust",
            probability("minimum_deep_trust", self.minimum_deep_trust),
        )
        for name in (
            "always_rehydrate_index_hits",
            "broad_search_on_conflict",
            "broad_search_on_fast_fallback",
            "index_deep_results",
        ):
            if not isinstance(getattr(self, name), bool):
                raise AgentContractError(f"{name} must be boolean")


@dataclass(frozen=True, slots=True)
class ContextFabricResult:
    namespace_key: str
    query: str
    fast_recall: RecallPacket
    lenses: LensBundle
    lens_governance: tuple[LensGovernanceDecision, ...]
    records: tuple[DeepContextRecord, ...]
    stale_card_ids: tuple[str, ...]
    unresolved_source_refs: tuple[str, ...]
    broad_search_used: bool
    token_estimate: int
    fingerprint: str

    def __post_init__(self) -> None:
        namespace_key = str(self.namespace_key).strip()
        if not namespace_key or len(namespace_key) > 2048:
            raise AgentContractError("namespace_key is invalid")
        object.__setattr__(self, "namespace_key", namespace_key)

        query = str(self.query)
        if len(query) > 256_000:
            raise AgentContractError("context fabric query is too large")
        object.__setattr__(self, "query", query)

        if not isinstance(self.fast_recall, RecallPacket):
            raise AgentContractError("fast_recall must be RecallPacket")
        if not isinstance(self.lenses, LensBundle):
            raise AgentContractError("lenses must be LensBundle")

        governance = tuple(self.lens_governance)
        if any(not isinstance(item, LensGovernanceDecision) for item in governance):
            raise AgentContractError(
                "lens_governance must contain LensGovernanceDecision values"
            )
        object.__setattr__(self, "lens_governance", governance)

        records = tuple(self.records)
        if any(not isinstance(item, DeepContextRecord) for item in records):
            raise AgentContractError(
                "records must contain DeepContextRecord values"
            )
        object.__setattr__(self, "records", records)

        stale = tuple(
            sorted({str(value).strip() for value in self.stale_card_ids if str(value).strip()})
        )
        unresolved = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in self.unresolved_source_refs
                    if str(value).strip()
                }
            )
        )
        object.__setattr__(self, "stale_card_ids", stale)
        object.__setattr__(self, "unresolved_source_refs", unresolved)

        if not isinstance(self.broad_search_used, bool):
            raise AgentContractError("broad_search_used must be boolean")
        if (
            isinstance(self.token_estimate, bool)
            or not isinstance(self.token_estimate, int)
            or self.token_estimate < 0
        ):
            raise AgentContractError("token_estimate must be a non-negative integer")
        expected_tokens = sum(record.token_estimate for record in records)
        if self.token_estimate != expected_tokens:
            raise AgentContractError(
                "token_estimate does not match packed context records"
            )

        fingerprint = str(self.fingerprint).strip().lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise AgentContractError("fabric fingerprint must be sha256 hex")
        object.__setattr__(self, "fingerprint", fingerprint)

    def render_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "source_tier": record.source_tier.value,
                "source_ref": record.source_ref,
                "source_provider": record.source_provider,
                "source_fingerprint": record.source_fingerprint,
                "content": record.content,
                "canonical": record.canonical,
                "trust": record.trust,
                "confidence": record.confidence,
                "salience": record.salience,
                "tags": list(record.tags),
                "metadata": dict(record.metadata),
            }
            for record in self.records
        ]


class RepositoryContextAdapter:
    source_tier = SourceTier.CONTEXT_REPOSITORY

    def __init__(self, repository: ContextRepository, *, branch: str = "main") -> None:
        self.repository = repository
        self.branch = str(branch)
        self.source_provider = f"context-repository:{repository.namespace.key}"

    def fetch_refs(
        self,
        namespace_key: str,
        source_refs: Sequence[str],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        if namespace_key != self.repository.namespace.key:
            return ()
        refs = {str(value) for value in source_refs}
        if not refs:
            return ()
        records: list[DeepContextRecord] = []
        used = 0
        snapshot = self.repository.checkout(self.branch, include_tombstones=False)
        for entry in snapshot.entries:
            if entry.key not in refs and entry.entry_id not in refs:
                continue
            record = self._record(entry)
            if used + record.token_estimate > max_tokens:
                continue
            records.append(record)
            used += record.token_estimate
            if len(records) >= max_records:
                break
        return tuple(records)

    def search(
        self,
        namespace_key: str,
        query: str,
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        if namespace_key != self.repository.namespace.key:
            return ()
        hits = self.repository.retrieve(
            query,
            branch=self.branch,
            max_entries=max_records,
            max_tokens=max_tokens,
            minimum_trust=0.0,
            include_unpromoted=True,
            touch=False,
        )
        return tuple(self._record(hit.entry) for hit in hits)

    @staticmethod
    def _record(entry) -> DeepContextRecord:
        return DeepContextRecord(
            source_tier=SourceTier.CONTEXT_REPOSITORY,
            source_ref=entry.key,
            source_fingerprint=entry.content_fingerprint,
            content=entry.content,
            canonical=True,
            trust=entry.trust,
            confidence=entry.confidence,
            salience=entry.salience,
            token_estimate=max(1, (len(entry.content) + 3) // 4),
            source_provider=f"context-repository:{entry.namespace.key}",
            tags=entry.tags,
            metadata={
                "entry_id": entry.entry_id,
                "kind": entry.kind.value,
                "promoted": entry.promoted,
                "protected": entry.protected,
                "source": entry.source,
                "evidence_ids": [ref.evidence_id for ref in entry.evidence],
            },
        )


class MemoryManagerAdapter:
    source_tier = SourceTier.MEMORY_STORE

    def __init__(self, manager: MemoryManager, namespace: MemoryNamespace) -> None:
        self.manager = manager
        self.namespace = namespace
        self.source_provider = f"memory-store:{namespace.key}"

    def supports_source_provider(self, source_provider: str) -> bool:
        provider = str(source_provider).strip()
        if not provider:
            return True
        return provider in {
            f"memory-store:{self.namespace.key}",
            f"memory-store:{self.namespace.parent().key}",
        }

    def fetch_refs(
        self,
        namespace_key: str,
        source_refs: Sequence[str],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        parent = self.namespace.parent()
        if namespace_key == self.namespace.key:
            allowed_namespaces = {self.namespace.key, parent.key}
        elif namespace_key == parent.key:
            allowed_namespaces = {parent.key}
        else:
            return ()
        refs = tuple(dict.fromkeys(str(value) for value in source_refs))
        records: list[DeepContextRecord] = []
        used = 0
        for source_ref in refs:
            record = self.manager.store.get(source_ref)
            if record is None or record.namespace.key not in allowed_namespaces:
                continue
            item = self._record(record)
            if used + item.token_estimate > max_tokens:
                continue
            records.append(item)
            used += item.token_estimate
            if len(records) >= max_records:
                break
        return tuple(records)

    def search(
        self,
        namespace_key: str,
        query: str,
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        parent = self.namespace.parent()
        if namespace_key == self.namespace.key:
            search_namespace = self.namespace
            include_parent = True
        elif namespace_key == parent.key:
            search_namespace = parent
            include_parent = False
        else:
            return ()
        hits = self.manager.retriever.search(
            search_namespace,
            query,
            limit=max_records,
            minimum_trust=0.0,
            include_parent=include_parent,
        )
        records: list[DeepContextRecord] = []
        used = 0
        for hit in hits:
            item = self._record(hit.record)
            if used + item.token_estimate > max_tokens:
                continue
            records.append(item)
            used += item.token_estimate
        return tuple(records)

    @staticmethod
    def _record(record) -> DeepContextRecord:
        return DeepContextRecord(
            source_tier=SourceTier.MEMORY_STORE,
            source_ref=record.memory_id,
            source_fingerprint=record.fingerprint,
            content=record.content,
            canonical=True,
            trust=record.trust,
            confidence=record.trust,
            salience=record.salience,
            token_estimate=max(1, (len(record.content) + 3) // 4),
            source_provider=f"memory-store:{record.namespace.key}",
            tags=record.tags,
            metadata={
                "kind": record.kind.value,
                "promoted": record.promoted,
                "source": record.source,
                "evidence_ids": [ref.evidence_id for ref in record.evidence],
            },
        )


class CallableContextAdapter:
    """Adapter for journal/log/DB/cache/file implementations supplied by host code."""

    def __init__(
        self,
        source_tier: SourceTier,
        *,
        fetcher: Callable[[str, Sequence[str], int, int], Sequence[DeepContextRecord]],
        searcher: Callable[[str, str, int, int], Sequence[DeepContextRecord]],
        source_provider: str = "",
    ) -> None:
        self.source_tier = source_tier if isinstance(source_tier, SourceTier) else SourceTier(str(source_tier))
        self.source_provider = str(source_provider).strip()[:512]
        if not callable(fetcher) or not callable(searcher):
            raise TypeError("context adapter fetcher/searcher must be callable")
        self._fetcher = fetcher
        self._searcher = searcher

    def fetch_refs(
        self,
        namespace_key: str,
        source_refs: Sequence[str],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        values = tuple(self._fetcher(namespace_key, source_refs, max_records, max_tokens))
        self._validate(values)
        return self._bounded(values, max_records=max_records, max_tokens=max_tokens)

    def search(
        self,
        namespace_key: str,
        query: str,
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        values = tuple(self._searcher(namespace_key, query, max_records, max_tokens))
        self._validate(values)
        return self._bounded(values, max_records=max_records, max_tokens=max_tokens)

    @staticmethod
    def _bounded(
        values: Sequence[DeepContextRecord],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        records: list[DeepContextRecord] = []
        used = 0
        for value in values:
            if len(records) >= max_records:
                break
            if used + value.token_estimate > max_tokens:
                continue
            records.append(value)
            used += value.token_estimate
        return tuple(records)

    def _validate(self, values: Sequence[DeepContextRecord]) -> None:
        if any(not isinstance(value, DeepContextRecord) for value in values):
            raise TypeError("context adapter must return DeepContextRecord values")
        if any(value.source_tier is not self.source_tier for value in values):
            raise AgentContractError("context adapter returned wrong source tier")


class CognitiveContextFabric:
    def __init__(
        self,
        *,
        index: MemoryGameIndex | None = None,
        lens_router: SemanticLensRouter | None = None,
        lens_science: LensScienceRegistry | None = None,
        policy: ContextFabricPolicy | None = None,
    ) -> None:
        self.index = index or MemoryGameIndex()
        self.lens_router = lens_router or SemanticLensRouter()
        self.lens_science = lens_science or LensScienceRegistry()
        self.policy = policy or ContextFabricPolicy()
        self._adapters: dict[SourceTier, list[ContextStoreAdapter]] = {}
        self._lock = threading.RLock()

    def register(self, adapter: ContextStoreAdapter) -> None:
        """Register an adapter without evicting other providers for the tier."""
        tier = adapter.source_tier
        if not isinstance(tier, SourceTier):
            tier = SourceTier(str(tier))
        with self._lock:
            bucket = self._adapters.setdefault(tier, [])
            if all(existing is not adapter for existing in bucket):
                bucket.append(adapter)

    @staticmethod
    def _adapter_supports_provider(
        adapter: ContextStoreAdapter,
        source_provider: str,
    ) -> bool:
        provider = str(source_provider).strip()
        if not provider:
            return True
        checker = getattr(adapter, "supports_source_provider", None)
        if callable(checker):
            return bool(checker(provider))
        adapter_provider = str(getattr(adapter, "source_provider", "")).strip()
        return bool(adapter_provider) and adapter_provider == provider

    def unregister(
        self,
        source_tier: SourceTier,
        adapter: ContextStoreAdapter | None = None,
    ) -> bool:
        tier = source_tier if isinstance(source_tier, SourceTier) else SourceTier(str(source_tier))
        with self._lock:
            if adapter is None:
                return self._adapters.pop(tier, None) is not None
            bucket = self._adapters.get(tier)
            if not bucket:
                return False
            remaining = [value for value in bucket if value is not adapter]
            changed = len(remaining) != len(bucket)
            if remaining:
                self._adapters[tier] = remaining
            else:
                self._adapters.pop(tier, None)
            return changed

    def retrieve(
        self,
        namespace_key: str,
        query: str,
        *,
        requested_tiers: Sequence[SourceTier] = (),
        tags: Sequence[str] = (),
        prior_lens_ids: Sequence[str] = (),
        call_adapters: Sequence[ContextStoreAdapter] = (),
    ) -> ContextFabricResult:
        fast = self.index.query(
            namespace_key,
            query,
            limit=self.policy.fast_limit,
            associative_limit=self.policy.associative_limit,
            tags=tags,
            touch=True,
        )
        adjacent = tuple(hit.card.preview for hit in fast.all_hits[:12])
        lens_bundle = self.lens_router.route(
            query,
            adjacent_text=adjacent,
            prior_lens_ids=tuple(prior_lens_ids) + fast.lens_hints,
            limit=self.policy.lens_limit,
        )

        lens_governance = self.lens_science.assess_bundle(lens_bundle)

        with self._lock:
            adapters = {tier: list(values) for tier, values in self._adapters.items()}
        # Per-call adapters are additive.  A namespace-scoped memory adapter,
        # historical chronicle, durable user chronicle, cache and DB may all
        # legitimately share a tier without replacing one another.
        for adapter in tuple(call_adapters):
            tier = adapter.source_tier
            if not isinstance(tier, SourceTier):
                tier = SourceTier(str(tier))
            adapters.setdefault(tier, []).append(adapter)
        requested = {
            tier if isinstance(tier, SourceTier) else SourceTier(str(tier))
            for tier in requested_tiers
        }
        if requested:
            adapters = {tier: values for tier, values in adapters.items() if tier in requested}

        records: list[DeepContextRecord] = []
        stale: set[str] = set()
        resolved_sources: set[tuple[SourceTier, str, str]] = set()
        canonical_fingerprints: dict[tuple[SourceTier, str, str], set[str]] = {}
        budget_remaining = self.policy.maximum_tokens

        # Targeted canonical rehydration comes before any broad retrieval.
        refs_by_tier: dict[SourceTier, list[str]] = {}
        card_by_source: dict[tuple[SourceTier, str, str], list[Any]] = {}
        for hit in fast.all_hits:
            provider = hit.card.source_provider
            key = (hit.card.source_tier, provider, hit.card.source_ref)
            refs_by_tier.setdefault(hit.card.source_tier, []).append(hit.card.source_ref)
            card_by_source.setdefault(key, []).append(hit.card)

        if self.policy.always_rehydrate_index_hits:
            for tier, refs in refs_by_tier.items():
                tier_adapters = adapters.get(tier, ())
                if not tier_adapters:
                    continue
                for adapter in tier_adapters:
                    if budget_remaining <= 0:
                        break
                    adapter_provider = str(getattr(adapter, "source_provider", "")).strip()
                    eligible_refs = tuple(
                        dict.fromkeys(
                            card.source_ref
                            for hit in fast.all_hits
                            for card in (hit.card,)
                            if card.source_tier is tier
                            and self._adapter_supports_provider(
                                adapter,
                                card.source_provider,
                            )
                        )
                    )
                    if not eligible_refs:
                        continue
                    fetched = adapter.fetch_refs(
                        namespace_key,
                        eligible_refs,
                        max_records=self.policy.deep_limit,
                        max_tokens=max(1, budget_remaining),
                    )
                    for record in fetched:
                        if record.trust < self.policy.minimum_deep_trust:
                            continue
                        if record.token_estimate > budget_remaining:
                            continue
                        records.append(record)
                        budget_remaining = max(0, budget_remaining - record.token_estimate)
                        source_key = (
                            record.source_tier,
                            record.source_provider,
                            record.source_ref,
                        )
                        resolved_sources.add(source_key)
                        resolved_sources.add(
                            (record.source_tier, "", record.source_ref)
                        )
                        canonical_fingerprints.setdefault(source_key, set()).add(record.source_fingerprint)
                        # Legacy cards without a provider are wildcards and may
                        # match any provider in the same tier.
                        canonical_fingerprints.setdefault(
                            (record.source_tier, "", record.source_ref),
                            set(),
                        ).add(record.source_fingerprint)

            # A card is stale only when canonical providers resolved its source
            # and none of them agree with the indexed fingerprint.  With
            # multiple providers per tier, eagerly marking on the first
            # disagreement would create false staleness.
            for source_key, cards in card_by_source.items():
                fingerprints = canonical_fingerprints.get(source_key)
                if not fingerprints:
                    continue
                for card in cards:
                    if card.source_fingerprint not in fingerprints:
                        stale.add(card.card_id)

        fast_is_weak = (
            fast.fallback_to_deep_context
            or len(fast.direct_hits) < self.policy.minimum_fast_hits_before_skip_deep
        )
        broad = (
            (fast_is_weak and self.policy.broad_search_on_fast_fallback)
            or (fast.conflict_detected and self.policy.broad_search_on_conflict)
        )
        if broad and budget_remaining > 0:
            adapter_count = sum(len(values) for values in adapters.values())
            per_adapter_records = max(1, self.policy.deep_limit // max(1, adapter_count))
            ordered_adapters = [
                (tier, adapter)
                for tier, values in adapters.items()
                for adapter in values
            ]
            ordered_adapters.sort(
                key=lambda item: (
                    item[0].value,
                    str(getattr(item[1], "source_provider", "")),
                    type(item[1]).__name__,
                )
            )
            for tier, adapter in ordered_adapters:
                if budget_remaining <= 0:
                    break
                found = adapter.search(
                    namespace_key,
                    query,
                    max_records=per_adapter_records,
                    max_tokens=max(1, budget_remaining),
                )
                for record in found:
                    if record.trust < self.policy.minimum_deep_trust:
                        continue
                    if record.token_estimate > budget_remaining:
                        continue
                    records.append(record)
                    budget_remaining = max(0, budget_remaining - record.token_estimate)
                    resolved_sources.add(
                        (
                            record.source_tier,
                            record.source_provider,
                            record.source_ref,
                        )
                    )
                    resolved_sources.add(
                        (record.source_tier, "", record.source_ref)
                    )

        packed = self._dedupe(records)[: self.policy.deep_limit]
        if self.policy.index_deep_results:
            self._index_records(namespace_key, packed, lens_bundle)

        unresolved = tuple(
            sorted(
                {
                    hit.card.source_ref
                    for hit in fast.all_hits
                    if (
                        (
                            hit.card.source_tier,
                            hit.card.source_provider,
                            hit.card.source_ref,
                        )
                        not in resolved_sources
                        and bool(adapters.get(hit.card.source_tier))
                    )
                }
            )
        )
        token_estimate = sum(record.token_estimate for record in packed)
        fingerprint = stable_fingerprint(
            {
                "namespace": namespace_key,
                "query": query,
                "fast": fast.fingerprint,
                "lenses": lens_bundle.fingerprint,
                "lens_governance": [decision.fingerprint for decision in lens_governance],
                "records": [
                    (
                        record.source_tier.value,
                        record.source_provider,
                        record.source_ref,
                        record.source_fingerprint,
                    )
                    for record in packed
                ],
                "stale": sorted(stale),
                "unresolved": unresolved,
                "broad": broad,
            }
        )
        return ContextFabricResult(
            namespace_key=namespace_key,
            query=query,
            fast_recall=fast,
            lenses=lens_bundle,
            lens_governance=lens_governance,
            records=tuple(packed),
            stale_card_ids=tuple(sorted(stale)),
            unresolved_source_refs=unresolved,
            broad_search_used=broad,
            token_estimate=token_estimate,
            fingerprint=fingerprint,
        )

    def index_record(
        self,
        namespace_key: str,
        record: DeepContextRecord,
        *,
        cue: str | None = None,
        kind: CardKind = CardKind.SOURCE_CUE,
        lens_ids: Sequence[str] = (),
        continuation_ids: Sequence[str] = (),
    ):
        return self.index.index_source(
            namespace_key=namespace_key,
            source_tier=record.source_tier,
            source_ref=record.source_ref,
            source_fingerprint=record.source_fingerprint,
            cue=cue or record.content[:2048],
            source_provider=record.source_provider,
            preview=record.content[:8192],
            kind=kind,
            salience=record.salience,
            trust=record.trust,
            confidence=record.confidence,
            tags=record.tags,
            lens_ids=lens_ids,
            continuation_ids=continuation_ids,
            metadata={
                "canonical_source_required": True,
                "indexed_by": "context-fabric",
                "source_metadata": dict(record.metadata),
            },
        )

    def _index_records(self, namespace_key: str, records: Sequence[DeepContextRecord], lenses: LensBundle) -> None:
        lens_ids = lenses.ids()
        for record in records:
            self.index_record(namespace_key, record, lens_ids=lens_ids[:8])

    @staticmethod
    def _dedupe(records: Sequence[DeepContextRecord]) -> list[DeepContextRecord]:
        by_key: dict[tuple[SourceTier, str, str], DeepContextRecord] = {}
        by_fingerprint: dict[tuple[SourceTier, str, str], DeepContextRecord] = {}

        def rank(record: DeepContextRecord) -> tuple[Any, ...]:
            return (
                record.canonical,
                record.trust,
                record.confidence,
                record.salience,
                -record.token_estimate,
                record.source_fingerprint,
            )

        for record in records:
            key = (record.source_tier, record.source_provider, record.source_ref)
            prior = by_key.get(key)
            if prior is None or rank(record) > rank(prior):
                by_key[key] = record

        # Identical canonical content may be duplicated under multiple refs from
        # one provider, but independent providers remain distinct provenance.
        for record in by_key.values():
            fingerprint_key = (
                record.source_tier,
                record.source_provider,
                record.source_fingerprint,
            )
            prior = by_fingerprint.get(fingerprint_key)
            if prior is None or (
                rank(record),
                record.source_ref,
            ) > (
                rank(prior),
                prior.source_ref,
            ):
                by_fingerprint[fingerprint_key] = record

        values = list(by_fingerprint.values())
        values.sort(
            key=lambda record: (
                rank(record),
                record.source_tier.value,
                record.source_provider,
                record.source_ref,
            ),
            reverse=True,
        )
        return values


__all__ = [
    "CallableContextAdapter",
    "CognitiveContextFabric",
    "ContextFabricPolicy",
    "ContextFabricResult",
    "ContextStoreAdapter",
    "DeepContextRecord",
    "MemoryManagerAdapter",
    "RepositoryContextAdapter",
]
