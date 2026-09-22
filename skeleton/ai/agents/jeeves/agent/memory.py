"""Scoped memory for the Jeeves agent runtime.

Memory is deliberately not a transcript dump.  Records carry namespace,
kind, trust, salience, provenance fingerprints, expiry, and promotion state.
Retrieval combines lexical relevance with salience, trust, recency, and access
frequency while preserving tenant/session boundaries.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    EvidenceRef,
    MemoryKind,
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


class MemoryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MemoryNamespace:
    tenant_id: str
    user_id: str
    workspace_id: str = "default"
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", require_id("tenant_id", self.tenant_id))
        object.__setattr__(self, "user_id", require_id("user_id", self.user_id))
        object.__setattr__(self, "workspace_id", require_id("workspace_id", self.workspace_id))
        if self.session_id is not None:
            object.__setattr__(self, "session_id", require_id("session_id", self.session_id))

    @property
    def key(self) -> str:
        parts = [self.tenant_id, self.user_id, self.workspace_id]
        if self.session_id:
            parts.append(self.session_id)
        return "/".join(parts)

    def parent(self) -> "MemoryNamespace":
        return replace(self, session_id=None)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    namespace: MemoryNamespace
    kind: MemoryKind
    content: str
    created_at: float
    updated_at: float
    salience: float = 0.5
    trust: float = 0.5
    source: str = "runtime"
    evidence: tuple[EvidenceRef, ...] = ()
    tags: tuple[str, ...] = ()
    expires_at: float | None = None
    access_count: int = 0
    last_accessed_at: float | None = None
    promoted: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "memory_id", require_id("memory_id", self.memory_id))
        if not isinstance(self.namespace, MemoryNamespace):
            raise AgentContractError("namespace must be MemoryNamespace")
        if not isinstance(self.kind, MemoryKind):
            object.__setattr__(self, "kind", MemoryKind(str(self.kind)))
        object.__setattr__(self, "content", bounded_text("memory content", self.content, maximum=64_000))
        created = finite_number("created_at", self.created_at)
        updated = finite_number("updated_at", self.updated_at)
        if created < 0 or updated < created:
            raise AgentContractError("invalid memory timestamps")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "salience", probability("salience", self.salience))
        object.__setattr__(self, "trust", probability("trust", self.trust))
        object.__setattr__(self, "source", bounded_text("memory source", self.source, maximum=1024))
        refs = tuple(self.evidence)
        if any(not isinstance(ref, EvidenceRef) for ref in refs):
            raise AgentContractError("memory evidence must contain EvidenceRef values")
        object.__setattr__(self, "evidence", refs)
        tags = tuple(sorted({str(tag).strip().lower() for tag in self.tags if str(tag).strip()}))
        if len(tags) > 64 or any(len(tag) > 128 for tag in tags):
            raise AgentContractError("invalid memory tags")
        object.__setattr__(self, "tags", tags)
        if self.expires_at is not None:
            expiry = finite_number("expires_at", self.expires_at)
            if expiry <= created:
                raise AgentContractError("memory expiry must be after creation")
            object.__setattr__(self, "expires_at", expiry)
        if isinstance(self.access_count, bool) or not isinstance(self.access_count, int) or self.access_count < 0:
            raise AgentContractError("access_count must be a non-negative integer")
        if self.last_accessed_at is not None:
            accessed = finite_number("last_accessed_at", self.last_accessed_at)
            if accessed < created:
                raise AgentContractError("last_accessed_at predates creation")
            object.__setattr__(self, "last_accessed_at", accessed)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "namespace": self.namespace.key,
                "kind": self.kind.value,
                "content": self.content,
                "source": self.source,
                "evidence": [(ref.evidence_id, ref.fingerprint) for ref in self.evidence],
                "tags": self.tags,
            }
        )

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


@dataclass(frozen=True, slots=True)
class MemoryHit:
    record: MemoryRecord
    score: float
    lexical_score: float
    recency_score: float
    salience_score: float
    trust_score: float
    frequency_score: float


@dataclass(frozen=True, slots=True)
class RetrievalWeights:
    lexical: float = 0.45
    recency: float = 0.15
    salience: float = 0.15
    trust: float = 0.20
    frequency: float = 0.05

    def __post_init__(self) -> None:
        values = [finite_number(name, getattr(self, name)) for name in ("lexical", "recency", "salience", "trust", "frequency")]
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise AgentContractError("retrieval weights must be non-negative and non-zero")
        total = sum(values)
        for name, value in zip(("lexical", "recency", "salience", "trust", "frequency"), values):
            object.__setattr__(self, name, value / total)


@dataclass(frozen=True, slots=True)
class MemoryPromotionPolicy:
    minimum_trust: float = 0.75
    minimum_salience: float = 0.45
    minimum_accesses: int = 1
    require_evidence_for_semantic: bool = True
    allow_kinds: tuple[MemoryKind, ...] = (
        MemoryKind.EPISODIC,
        MemoryKind.SEMANTIC,
        MemoryKind.PROCEDURAL,
        MemoryKind.PREFERENCE,
        MemoryKind.PROFILE,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum_trust", probability("minimum_trust", self.minimum_trust))
        object.__setattr__(self, "minimum_salience", probability("minimum_salience", self.minimum_salience))
        object.__setattr__(self, "minimum_accesses", positive_int("minimum_accesses", self.minimum_accesses, maximum=1_000_000))
        kinds = tuple(kind if isinstance(kind, MemoryKind) else MemoryKind(str(kind)) for kind in self.allow_kinds)
        object.__setattr__(self, "allow_kinds", kinds)

    def permits(self, record: MemoryRecord) -> bool:
        if record.kind not in self.allow_kinds:
            return False
        if record.trust < self.minimum_trust or record.salience < self.minimum_salience:
            return False
        if record.access_count < self.minimum_accesses:
            return False
        if self.require_evidence_for_semantic and record.kind is MemoryKind.SEMANTIC and not record.evidence:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ConsolidationCandidate:
    candidate_id: str
    namespace: MemoryNamespace
    kind: MemoryKind
    content: str
    source_memory_ids: tuple[str, ...]
    trust: float
    salience: float
    evidence: tuple[EvidenceRef, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", require_id("candidate_id", self.candidate_id))
        if not isinstance(self.namespace, MemoryNamespace):
            raise AgentContractError("namespace must be MemoryNamespace")
        if not isinstance(self.kind, MemoryKind):
            object.__setattr__(self, "kind", MemoryKind(str(self.kind)))
        object.__setattr__(self, "content", bounded_text("candidate content", self.content, maximum=64_000))
        source_ids = tuple(require_id("source_memory_id", item) for item in self.source_memory_ids)
        if not source_ids:
            raise AgentContractError("consolidation candidate needs source memories")
        object.__setattr__(self, "source_memory_ids", source_ids)
        object.__setattr__(self, "trust", probability("candidate trust", self.trust))
        object.__setattr__(self, "salience", probability("candidate salience", self.salience))
        object.__setattr__(self, "rationale", bounded_text("candidate rationale", self.rationale, maximum=4096))


class InMemoryStore:
    """Thread-safe reference store used by tests and the default runtime."""

    def __init__(self, *, max_records: int = 50_000, clock: Callable[[], float] = time.time) -> None:
        self.max_records = positive_int("max_records", max_records, maximum=10_000_000)
        self._clock = clock
        self._records: dict[str, MemoryRecord] = {}
        self._fingerprints: dict[tuple[str, str], str] = {}
        self._lock = threading.RLock()

    def put(self, record: MemoryRecord) -> MemoryRecord:
        if not isinstance(record, MemoryRecord):
            raise TypeError("record must be MemoryRecord")
        key = (record.namespace.key, record.fingerprint)
        with self._lock:
            duplicate_id = self._fingerprints.get(key)
            if duplicate_id is not None and duplicate_id != record.memory_id:
                return self._records[duplicate_id]
            if record.memory_id not in self._records and len(self._records) >= self.max_records:
                self._evict_one()
            old = self._records.get(record.memory_id)
            if old is not None:
                self._fingerprints.pop((old.namespace.key, old.fingerprint), None)
            self._records[record.memory_id] = record
            self._fingerprints[key] = record.memory_id
            return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            return self._records.get(require_id("memory_id", memory_id))

    def delete(self, memory_id: str) -> bool:
        memory_id = require_id("memory_id", memory_id)
        with self._lock:
            record = self._records.pop(memory_id, None)
            if record is None:
                return False
            self._fingerprints.pop((record.namespace.key, record.fingerprint), None)
            return True

    def list_namespace(
        self,
        namespace: MemoryNamespace,
        *,
        include_parent: bool = True,
        include_expired: bool = False,
    ) -> tuple[MemoryRecord, ...]:
        now = self._clock()
        keys = {namespace.key}
        if include_parent and namespace.session_id is not None:
            keys.add(namespace.parent().key)
        with self._lock:
            records = [
                record
                for record in self._records.values()
                if record.namespace.key in keys and (include_expired or not record.expired(now))
            ]
        return tuple(sorted(records, key=lambda item: (item.updated_at, item.memory_id), reverse=True))

    def prune_expired(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [memory_id for memory_id, record in self._records.items() if record.expired(now)]
            for memory_id in expired:
                self.delete(memory_id)
            return len(expired)

    def _evict_one(self) -> None:
        candidates = list(self._records.values())
        if not candidates:
            return
        victim = min(
            candidates,
            key=lambda record: (
                record.promoted,
                record.trust * 0.4 + record.salience * 0.4 + min(1.0, record.access_count / 10) * 0.2,
                record.updated_at,
            ),
        )
        self.delete(victim.memory_id)

    def count(self) -> int:
        with self._lock:
            return len(self._records)


class MemoryRetriever:
    def __init__(
        self,
        store: InMemoryStore,
        *,
        weights: RetrievalWeights | None = None,
        half_life_seconds: float = 7 * 24 * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.weights = weights or RetrievalWeights()
        half_life = finite_number("half_life_seconds", half_life_seconds)
        if half_life <= 0:
            raise ValueError("half_life_seconds must be positive")
        self.half_life_seconds = half_life
        self._clock = clock

    def search(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        limit: int = 8,
        kinds: Sequence[MemoryKind] | None = None,
        minimum_trust: float = 0.0,
        tags: Sequence[str] = (),
        include_parent: bool = True,
    ) -> tuple[MemoryHit, ...]:
        limit = positive_int("limit", limit, maximum=1000)
        minimum_trust = probability("minimum_trust", minimum_trust)
        query_tokens = self._tokens(query)
        kind_set = None if kinds is None else {kind if isinstance(kind, MemoryKind) else MemoryKind(str(kind)) for kind in kinds}
        required_tags = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
        now = self._clock()
        hits: list[MemoryHit] = []
        for record in self.store.list_namespace(namespace, include_parent=include_parent):
            if kind_set is not None and record.kind not in kind_set:
                continue
            if record.trust < minimum_trust:
                continue
            if required_tags and not required_tags.issubset(set(record.tags)):
                continue
            lexical = self._lexical(query_tokens, self._tokens(record.content + " " + " ".join(record.tags)))
            age = max(0.0, now - record.updated_at)
            recency = math.exp(-math.log(2) * age / self.half_life_seconds)
            frequency = 1.0 - math.exp(-record.access_count / 5.0)
            score = (
                self.weights.lexical * lexical
                + self.weights.recency * recency
                + self.weights.salience * record.salience
                + self.weights.trust * record.trust
                + self.weights.frequency * frequency
            )
            hits.append(MemoryHit(record, score, lexical, recency, record.salience, record.trust, frequency))
        hits.sort(key=lambda hit: (hit.score, hit.record.updated_at, hit.record.memory_id), reverse=True)
        return tuple(hits[:limit])

    @staticmethod
    def _tokens(text: str) -> Counter[str]:
        return Counter(token.casefold() for token in _TOKEN_RE.findall(text or ""))

    @staticmethod
    def _lexical(query: Counter[str], document: Counter[str]) -> float:
        if not query:
            return 0.0
        overlap = sum(min(count, document.get(token, 0)) for token, count in query.items())
        query_norm = math.sqrt(sum(count * count for count in query.values()))
        document_norm = math.sqrt(sum(count * count for count in document.values()))
        if not query_norm or not document_norm:
            return 0.0
        dot = sum(count * document.get(token, 0) for token, count in query.items())
        return max(0.0, min(1.0, dot / (query_norm * document_norm)))


class MemoryConsolidator:
    """Host-side candidate generator; promotion remains an explicit action."""

    def __init__(self, *, minimum_group: int = 2, maximum_group: int = 8) -> None:
        self.minimum_group = positive_int("minimum_group", minimum_group, maximum=100)
        self.maximum_group = positive_int("maximum_group", maximum_group, maximum=100)
        if self.minimum_group > self.maximum_group:
            raise ValueError("minimum_group cannot exceed maximum_group")

    def propose(self, records: Sequence[MemoryRecord]) -> tuple[ConsolidationCandidate, ...]:
        buckets: dict[tuple[str, MemoryKind, tuple[str, ...]], list[MemoryRecord]] = {}
        for record in records:
            key = (record.namespace.key, record.kind, record.tags)
            buckets.setdefault(key, []).append(record)
        candidates: list[ConsolidationCandidate] = []
        for (_, kind, _), bucket in sorted(buckets.items(), key=lambda item: str(item[0])):
            bucket.sort(key=lambda record: (record.updated_at, record.memory_id), reverse=True)
            group = bucket[: self.maximum_group]
            if len(group) < self.minimum_group:
                continue
            normalized = {self._normalize(record.content) for record in group}
            if len(normalized) != 1:
                continue
            source_ids = tuple(record.memory_id for record in group)
            evidence: dict[str, EvidenceRef] = {}
            for record in group:
                for ref in record.evidence:
                    evidence.setdefault(ref.evidence_id, ref)
            trust = min(1.0, sum(record.trust for record in group) / len(group) + 0.05 * min(3, len(group) - 1))
            salience = min(1.0, max(record.salience for record in group) + 0.05)
            content = group[0].content
            candidates.append(
                ConsolidationCandidate(
                    candidate_id=stable_id("consolidation", {"sources": source_ids, "content": content}),
                    namespace=group[0].namespace.parent(),
                    kind=kind,
                    content=content,
                    source_memory_ids=source_ids,
                    trust=trust,
                    salience=salience,
                    evidence=tuple(sorted(evidence.values(), key=lambda ref: ref.evidence_id)),
                    rationale=f"{len(group)} repeated memories agree on the same normalized content",
                )
            )
        return tuple(candidates)

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(_TOKEN_RE.findall(text.casefold()))


class MemoryManager:
    def __init__(
        self,
        store: InMemoryStore | None = None,
        *,
        retriever: MemoryRetriever | None = None,
        promotion_policy: MemoryPromotionPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        self.store = store or InMemoryStore(clock=clock)
        self.retriever = retriever or MemoryRetriever(self.store, clock=clock)
        self.promotion_policy = promotion_policy or MemoryPromotionPolicy()
        self.consolidator = MemoryConsolidator()

    def remember(
        self,
        namespace: MemoryNamespace,
        content: str,
        *,
        kind: MemoryKind = MemoryKind.WORKING,
        salience: float = 0.5,
        trust: float = 0.5,
        source: str = "runtime",
        evidence: Sequence[EvidenceRef] = (),
        tags: Sequence[str] = (),
        ttl_seconds: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryRecord:
        now = self._clock()
        expiry = None
        if ttl_seconds is not None:
            ttl = finite_number("ttl_seconds", ttl_seconds)
            if ttl <= 0:
                raise ValueError("ttl_seconds must be positive")
            expiry = now + ttl
        payload = {
            "namespace": namespace.key,
            "kind": kind.value if isinstance(kind, MemoryKind) else str(kind),
            "content": content,
            "source": source,
            "evidence": [(ref.evidence_id, ref.fingerprint) for ref in evidence],
            "tags": sorted(str(tag).strip().lower() for tag in tags if str(tag).strip()),
        }
        record = MemoryRecord(
            memory_id=stable_id("mem", payload),
            namespace=namespace,
            kind=kind,
            content=content,
            created_at=now,
            updated_at=now,
            salience=salience,
            trust=trust,
            source=source,
            evidence=tuple(evidence),
            tags=tuple(tags),
            expires_at=expiry,
            metadata=metadata or {},
        )
        return self.store.put(record)

    def recall(self, namespace: MemoryNamespace, query: str, **kwargs: Any) -> tuple[MemoryHit, ...]:
        hits = self.retriever.search(namespace, query, **kwargs)
        now = self._clock()
        for hit in hits:
            record = hit.record
            touched = replace(record, access_count=record.access_count + 1, last_accessed_at=now, updated_at=max(record.updated_at, now))
            self.store.put(touched)
        return hits

    def promote(self, memory_id: str) -> MemoryRecord:
        record = self.store.get(memory_id)
        if record is None:
            raise MemoryError("unknown memory")
        if not self.promotion_policy.permits(record):
            raise MemoryError("memory does not satisfy promotion policy")
        promoted = replace(record, promoted=True, namespace=record.namespace.parent(), updated_at=self._clock())
        return self.store.put(promoted)

    def promote_candidate(self, candidate: ConsolidationCandidate) -> MemoryRecord:
        if any(self.store.get(source_id) is None for source_id in candidate.source_memory_ids):
            raise MemoryError("consolidation candidate references missing memories")
        return self.remember(
            candidate.namespace,
            candidate.content,
            kind=candidate.kind,
            salience=candidate.salience,
            trust=candidate.trust,
            source=f"consolidation:{candidate.candidate_id}",
            evidence=candidate.evidence,
            tags=("consolidated",),
            metadata={"source_memory_ids": list(candidate.source_memory_ids), "rationale": candidate.rationale},
        )

    def consolidation_candidates(self, namespace: MemoryNamespace) -> tuple[ConsolidationCandidate, ...]:
        return self.consolidator.propose(self.store.list_namespace(namespace, include_parent=False))
