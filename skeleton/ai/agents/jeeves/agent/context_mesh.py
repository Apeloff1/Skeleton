"""Namespace-safe durable-context routing for Jeeves.

The memory-game index stores cheap source pointers.  This module maps those
pointers back to the correct canonical ContextRepository storage class without
installing one mutable global adapter per user.

A single MultiplexedRepositoryAdapter is registered per SourceTier and routes
by namespace key internally.  That preserves tenant/workspace isolation while
allowing journals, logs, diaries, annals, chronicles, databases, caches and
files to participate in the same fast-index -> canonical-rehydrate -> broad
search pipeline.
"""

from __future__ import annotations

import threading
from typing import Mapping, Sequence

from .context_fabric import CognitiveContextFabric, ContextStoreAdapter, DeepContextRecord
from .context_repository import ContextKind, ContextRepository
from .memory_game_index import SourceTier
from .types import AgentContractError, positive_int


_STORAGE_KIND_BY_TIER: Mapping[SourceTier, tuple[ContextKind, ...]] = {
    SourceTier.JOURNAL: (ContextKind.JOURNAL,),
    SourceTier.LOG: (ContextKind.LOG,),
    SourceTier.DIARY: (ContextKind.DIARY,),
    SourceTier.ANNAL: (ContextKind.ANNAL,),
    SourceTier.CHRONICLE: (ContextKind.CHRONICLE,),
    SourceTier.DATABASE: (ContextKind.DATABASE,),
    SourceTier.CACHE: (ContextKind.CACHE,),
    SourceTier.FILE: (ContextKind.FILE,),
}

_SPECIAL_KINDS = frozenset(kind for kinds in _STORAGE_KIND_BY_TIER.values() for kind in kinds)
_GENERIC_KINDS = tuple(kind for kind in ContextKind if kind not in _SPECIAL_KINDS)


class MultiplexedRepositoryAdapter(ContextStoreAdapter):
    """Route one source tier across many namespace-owned repositories."""

    def __init__(
        self,
        source_tier: SourceTier,
        *,
        kinds: Sequence[ContextKind],
        branch: str = "main",
    ) -> None:
        self.source_tier = (
            source_tier if isinstance(source_tier, SourceTier) else SourceTier(str(source_tier))
        )
        self.kinds = tuple(
            kind if isinstance(kind, ContextKind) else ContextKind(str(kind))
            for kind in kinds
        )
        if not self.kinds:
            raise AgentContractError("multiplexed repository adapter requires context kinds")
        self.branch = str(branch)
        self.source_provider = f"context-mesh:{self.source_tier.value}"
        self._repositories: dict[str, ContextRepository] = {}
        self._lock = threading.RLock()

    def attach(self, repository: ContextRepository, *, replace: bool = False) -> None:
        if not isinstance(repository, ContextRepository):
            raise TypeError("repository must be ContextRepository")
        namespace_key = repository.namespace.key
        with self._lock:
            prior = self._repositories.get(namespace_key)
            if prior is not None and prior is not repository and not replace:
                raise AgentContractError(
                    f"context repository already attached for namespace {namespace_key!r}"
                )
            self._repositories[namespace_key] = repository

    def detach(self, namespace_key: str) -> bool:
        with self._lock:
            return self._repositories.pop(str(namespace_key), None) is not None

    def repository(self, namespace_key: str) -> ContextRepository | None:
        key = str(namespace_key)
        with self._lock:
            exact = self._repositories.get(key)
            if exact is not None:
                return exact
            # Runtime MemoryNamespace may add a fourth session component while
            # ContextRepository deliberately persists at workspace scope.
            # Sessions inherit their own workspace's durable repository; no
            # parent may ever resolve into a child/session repository.
            parts = key.split("/")
            if len(parts) == 4:
                return self._repositories.get("/".join(parts[:3]))
            return None

    def namespaces(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._repositories))

    def fetch_refs(
        self,
        namespace_key: str,
        source_refs: Sequence[str],
        *,
        max_records: int,
        max_tokens: int,
    ) -> tuple[DeepContextRecord, ...]:
        max_records = positive_int("max_records", max_records, maximum=1_000_000)
        max_tokens = positive_int("max_tokens", max_tokens, maximum=10_000_000)
        repository = self.repository(namespace_key)
        if repository is None:
            return ()
        refs = {str(value) for value in source_refs if str(value)}
        if not refs:
            return ()

        records: list[DeepContextRecord] = []
        used = 0
        snapshot = repository.checkout(self.branch, include_tombstones=False)
        for entry in snapshot.entries:
            if entry.kind not in self.kinds:
                continue
            if entry.key not in refs and entry.entry_id not in refs:
                continue
            record = self._record(entry)
            if records and used + record.token_estimate > max_tokens:
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
        max_records = positive_int("max_records", max_records, maximum=1_000_000)
        max_tokens = positive_int("max_tokens", max_tokens, maximum=10_000_000)
        repository = self.repository(namespace_key)
        if repository is None:
            return ()
        hits = repository.retrieve(
            query,
            branch=self.branch,
            kinds=self.kinds,
            max_entries=max_records,
            max_tokens=max_tokens,
            minimum_trust=0.0,
            include_unpromoted=True,
            touch=False,
        )
        return tuple(self._record(hit.entry) for hit in hits)

    def _record(self, entry) -> DeepContextRecord:
        return DeepContextRecord(
            source_tier=self.source_tier,
            source_ref=entry.key,
            source_fingerprint=entry.content_fingerprint,
            content=entry.content,
            canonical=True,
            trust=entry.trust,
            confidence=entry.confidence,
            salience=entry.salience,
            token_estimate=max(1, len(entry.content) // 4),
            source_provider=self.source_provider,
            tags=entry.tags,
            metadata={
                "entry_id": entry.entry_id,
                "kind": entry.kind.value,
                "promoted": entry.promoted,
                "protected": entry.protected,
                "source": entry.source,
                "evidence_ids": [ref.evidence_id for ref in entry.evidence],
                "context_repository_namespace": entry.namespace.key,
            },
        )


class ContextRepositoryMesh:
    """Install namespace-safe canonical repository routing into a context fabric."""

    def __init__(self, fabric: CognitiveContextFabric, *, branch: str = "main") -> None:
        if not isinstance(fabric, CognitiveContextFabric):
            raise TypeError("fabric must be CognitiveContextFabric")
        self.fabric = fabric
        self.branch = str(branch)
        adapters: dict[SourceTier, MultiplexedRepositoryAdapter] = {
            SourceTier.CONTEXT_REPOSITORY: MultiplexedRepositoryAdapter(
                SourceTier.CONTEXT_REPOSITORY,
                kinds=_GENERIC_KINDS,
                branch=self.branch,
            )
        }
        for tier, kinds in _STORAGE_KIND_BY_TIER.items():
            adapters[tier] = MultiplexedRepositoryAdapter(
                tier,
                kinds=kinds,
                branch=self.branch,
            )
        self._adapters = adapters
        for adapter in self._adapters.values():
            self.fabric.register(adapter)

    def attach(self, repository: ContextRepository, *, replace: bool = False) -> None:
        for adapter in self._adapters.values():
            adapter.attach(repository, replace=replace)

    def detach(self, namespace_key: str) -> bool:
        removed = False
        for adapter in self._adapters.values():
            removed = adapter.detach(namespace_key) or removed
        return removed

    def adapter(self, source_tier: SourceTier) -> MultiplexedRepositoryAdapter:
        tier = source_tier if isinstance(source_tier, SourceTier) else SourceTier(str(source_tier))
        return self._adapters[tier]

    def attached_namespaces(self) -> tuple[str, ...]:
        return self._adapters[SourceTier.CONTEXT_REPOSITORY].namespaces()

    @property
    def source_tiers(self) -> tuple[SourceTier, ...]:
        return tuple(sorted(self._adapters, key=lambda item: item.value))


__all__ = [
    "ContextRepositoryMesh",
    "MultiplexedRepositoryAdapter",
]
