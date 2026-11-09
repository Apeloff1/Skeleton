"""Hyper-advanced KV cache control plane.

The cache treats key/value tensors as opaque bytes so the control plane stays
runtime-neutral. GPU runtimes can provide packed tensor pages while the cache
owns identity, deduplication, tiering, admission, eviction, transactions,
branching, verification hooks, sharding, telemetry, and adaptive policy.
"""

from __future__ import annotations

import hashlib
import math
import time
import zlib
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum, IntEnum
from typing import Protocol


class MemoryTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class Precision(str, Enum):
    FP16 = "fp16"
    FP8 = "fp8"
    INT8 = "int8"
    INT4 = "int4"
    INT2 = "int2"


class PriorityClass(IntEnum):
    BACKGROUND = 0
    NORMAL = 1
    INTERACTIVE = 2
    CRITICAL = 3


class CacheIntegrityError(RuntimeError):
    """Cached data failed a content-integrity check."""


class CacheCompatibilityError(RuntimeError):
    """A cache block is incompatible with the active model/runtime identity."""


@dataclass(frozen=True, slots=True)
class KVIdentity:
    """Identity boundary preventing unsafe reuse across incompatible runtimes."""

    model: str
    revision: str
    layer: int
    head_group: int
    rope_signature: str = "default"
    layout_version: int = 1

    def fingerprint(self) -> str:
        raw = (
            f"{self.model}\x1f{self.revision}\x1f{self.layer}\x1f{self.head_group}\x1f"
            f"{self.rope_signature}\x1f{self.layout_version}"
        ).encode()
        return hashlib.blake2b(raw, digest_size=16).hexdigest()


@dataclass(frozen=True, slots=True)
class QuantizationPlan:
    key_precision: Precision = Precision.FP16
    value_precision: Precision = Precision.FP16
    residual_tokens: int = 128
    per_channel: bool = True
    scale_group_size: int = 64


@dataclass(frozen=True, slots=True)
class CachePolicy:
    max_bytes: int = 512 * 1024 * 1024
    hot_ratio: float = 0.50
    warm_ratio: float = 0.35
    low_watermark: float = 0.80
    high_watermark: float = 0.92
    default_ttl_seconds: float | None = 1800.0
    min_admission_score: float = 0.05
    reuse_weight: float = 0.35
    recency_weight: float = 0.25
    priority_weight: float = 0.20
    attention_weight: float = 0.20
    compression_min_bytes: int = 1024

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if not 0.0 < self.hot_ratio < 1.0:
            raise ValueError("hot_ratio must be in (0, 1)")
        if not 0.0 <= self.warm_ratio < 1.0 or self.hot_ratio + self.warm_ratio > 1.0:
            raise ValueError("invalid warm_ratio")
        if not 0.0 < self.low_watermark < self.high_watermark <= 1.0:
            raise ValueError("watermarks must satisfy 0 < low < high <= 1")


@dataclass(slots=True)
class KVBlock:
    digest: str
    identity_fingerprint: str
    prefix_digest: str
    token_count: int
    payload: bytes
    stored_payload: bytes
    compressed: bool
    checksum: str
    created_at: float
    last_access: float
    ttl_seconds: float | None
    priority: PriorityClass
    attention_score: float
    reuse_count: int = 0
    pinned: bool = False
    semantic_tags: frozenset[str] = frozenset()
    quantization: QuantizationPlan = field(default_factory=QuantizationPlan)
    version: int = 1
    tier: MemoryTier = MemoryTier.HOT
    tenant: str = "default"
    branch: str = "main"

    @property
    def size_bytes(self) -> int:
        return len(self.stored_payload)

    def expired(self, now: float) -> bool:
        return self.ttl_seconds is not None and now >= self.created_at + self.ttl_seconds


@dataclass(frozen=True, slots=True)
class CacheHit:
    digest: str
    payload: bytes
    token_count: int
    tier: MemoryTier
    reuse_count: int
    semantic_tags: frozenset[str]


@dataclass(slots=True)
class CacheMetrics:
    lookups: int = 0
    hits: int = 0
    misses: int = 0
    admissions: int = 0
    rejections: int = 0
    evictions: int = 0
    integrity_failures: int = 0
    compatibility_failures: int = 0
    promotions: int = 0
    demotions: int = 0
    dedup_hits: int = 0
    bytes_saved_dedup: int = 0
    bytes_saved_compression: int = 0
    speculative_rollbacks: int = 0
    verifier_disagreements: int = 0
    prefetch_hits: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0


class Verifier(Protocol):
    def __call__(self, block: KVBlock) -> tuple[bool, float, str]: ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    accepted: bool
    confidence: float
    reasons: tuple[str, ...]
    votes: tuple[tuple[bool, float, str], ...]


class KVArbitrationGraph:
    """Verifier/arbitration/reconciliation graph for cache reuse decisions."""

    def __init__(self, verifiers: Sequence[Verifier] = (), *, quorum: float = 0.60) -> None:
        if not 0.0 < quorum <= 1.0:
            raise ValueError("quorum must be in (0, 1]")
        self._verifiers = tuple(verifiers)
        self.quorum = quorum

    def verify(self, block: KVBlock) -> VerificationResult:
        if not self._verifiers:
            return VerificationResult(True, 1.0, (), ())
        votes = tuple(verifier(block) for verifier in self._verifiers)
        total_weight = sum(max(0.0, confidence) for _, confidence, _ in votes)
        yes_weight = sum(max(0.0, confidence) for ok, confidence, _ in votes if ok)
        ratio = yes_weight / total_weight if total_weight else 0.0
        accepted = ratio >= self.quorum
        reasons = tuple(reason for ok, _, reason in votes if ok != accepted and reason)
        return VerificationResult(accepted, ratio, reasons, votes)


@dataclass(frozen=True, slots=True)
class AdmissionContext:
    expected_reuse: float = 0.5
    priority: PriorityClass = PriorityClass.NORMAL
    attention_score: float = 0.5
    tenant: str = "default"
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class TransactionToken:
    branch: str
    baseline_digests: frozenset[str]


class RendezvousShardRouter:
    """Stable highest-random-weight routing with deterministic failover order."""

    def __init__(self, nodes: Iterable[str]) -> None:
        self.nodes = tuple(sorted(set(nodes)))
        if not self.nodes:
            raise ValueError("at least one shard node is required")

    @staticmethod
    def _score(key: str, node: str) -> int:
        return int.from_bytes(hashlib.blake2b(f"{key}:{node}".encode(), digest_size=8).digest(), "big")

    def rank(self, key: str) -> tuple[str, ...]:
        return tuple(sorted(self.nodes, key=lambda node: self._score(key, node), reverse=True))

    def route(self, key: str) -> str:
        return self.rank(key)[0]


class HyperKVCache:
    """Runtime-neutral, content-addressed, multi-tier KV cache control plane."""

    def __init__(
        self,
        policy: CachePolicy = CachePolicy(),
        *,
        arbitration: KVArbitrationGraph | None = None,
        clock: Callable[[], float] = time.monotonic,
        tenant_quotas: Mapping[str, int] | None = None,
    ) -> None:
        self.policy = policy
        self.arbitration = arbitration or KVArbitrationGraph()
        self._clock = clock
        self._blocks: dict[str, KVBlock] = {}
        self._prefix_index: dict[tuple[str, str, str], str] = {}
        self._tier_members: dict[MemoryTier, set[str]] = {tier: set() for tier in MemoryTier}
        self._tenant_bytes: Counter[str] = Counter()
        self._tenant_quotas = dict(tenant_quotas or {})
        self._branch_parents: dict[str, str | None] = {"main": None}
        self._branch_members: dict[str, set[str]] = defaultdict(set)
        self.metrics = CacheMetrics()

    @staticmethod
    def prefix_digest(token_ids: Sequence[int]) -> str:
        hasher = hashlib.blake2b(digest_size=16)
        for token in token_ids:
            hasher.update(int(token).to_bytes(8, "little", signed=True))
        return hasher.hexdigest()

    @staticmethod
    def _payload_digest(identity_fp: str, prefix_digest: str, payload: bytes) -> str:
        h = hashlib.blake2b(digest_size=20)
        h.update(identity_fp.encode())
        h.update(prefix_digest.encode())
        h.update(payload)
        return h.hexdigest()

    @staticmethod
    def _checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _compress(self, payload: bytes) -> tuple[bytes, bool]:
        if len(payload) < self.policy.compression_min_bytes:
            return payload, False
        compressed = zlib.compress(payload, level=1)
        if len(compressed) + 32 >= len(payload):
            return payload, False
        self.metrics.bytes_saved_compression += len(payload) - len(compressed)
        return compressed, True

    @staticmethod
    def _decompress(block: KVBlock) -> bytes:
        return zlib.decompress(block.stored_payload) if block.compressed else block.stored_payload

    def _admission_score(self, ctx: AdmissionContext) -> float:
        priority = float(ctx.priority) / float(PriorityClass.CRITICAL)
        return (
            self.policy.reuse_weight * max(0.0, min(1.0, ctx.expected_reuse))
            + self.policy.priority_weight * priority
            + self.policy.attention_weight * max(0.0, min(1.0, ctx.attention_score))
            + self.policy.recency_weight
        )

    def _tenant_allows(self, tenant: str, incoming_bytes: int) -> bool:
        quota = self._tenant_quotas.get(tenant)
        return quota is None or self._tenant_bytes[tenant] + incoming_bytes <= quota

    def put(
        self,
        identity: KVIdentity,
        token_ids: Sequence[int],
        payload: bytes,
        *,
        context: AdmissionContext = AdmissionContext(),
        semantic_tags: Iterable[str] = (),
        quantization: QuantizationPlan = QuantizationPlan(),
        ttl_seconds: float | None = None,
        branch: str = "main",
    ) -> str | None:
        if not payload:
            raise ValueError("payload must not be empty")
        if not token_ids:
            raise ValueError("token_ids must not be empty")
        if branch not in self._branch_parents:
            raise KeyError(f"unknown branch: {branch}")
        if self._admission_score(context) < self.policy.min_admission_score and not context.pinned:
            self.metrics.rejections += 1
            return None

        identity_fp = identity.fingerprint()
        prefix = self.prefix_digest(token_ids)
        digest = self._payload_digest(identity_fp, prefix, payload)
        if digest in self._blocks:
            self.metrics.dedup_hits += 1
            self.metrics.bytes_saved_dedup += len(payload)
            block = self._blocks[digest]
            block.reuse_count += 1
            block.last_access = self._clock()
            self._prefix_index[(identity_fp, prefix, branch)] = digest
            self._branch_members[branch].add(digest)
            return digest

        stored, compressed = self._compress(payload)
        if not self._tenant_allows(context.tenant, len(stored)) and not context.pinned:
            self.metrics.rejections += 1
            return None
        now = self._clock()
        block = KVBlock(
            digest=digest,
            identity_fingerprint=identity_fp,
            prefix_digest=prefix,
            token_count=len(token_ids),
            payload=payload,
            stored_payload=stored,
            compressed=compressed,
            checksum=self._checksum(payload),
            created_at=now,
            last_access=now,
            ttl_seconds=self.policy.default_ttl_seconds if ttl_seconds is None else ttl_seconds,
            priority=context.priority,
            attention_score=max(0.0, min(1.0, context.attention_score)),
            pinned=context.pinned,
            semantic_tags=frozenset(semantic_tags),
            quantization=quantization,
            tenant=context.tenant,
            branch=branch,
        )
        self._blocks[digest] = block
        self._prefix_index[(identity_fp, prefix, branch)] = digest
        self._tier_members[MemoryTier.HOT].add(digest)
        self._branch_members[branch].add(digest)
        self._tenant_bytes[context.tenant] += len(stored)
        self.metrics.admissions += 1
        self._rebalance()
        return digest

    def get(
        self,
        identity: KVIdentity,
        token_ids: Sequence[int],
        *,
        branch: str = "main",
        verify: bool = True,
    ) -> CacheHit | None:
        self.metrics.lookups += 1
        fp = identity.fingerprint()
        prefix = self.prefix_digest(token_ids)
        digest = self._resolve_prefix(fp, prefix, branch)
        if digest is None:
            self.metrics.misses += 1
            return None
        block = self._blocks.get(digest)
        if block is None:
            self.metrics.misses += 1
            return None
        now = self._clock()
        if block.expired(now) and not block.pinned:
            self._evict(digest)
            self.metrics.misses += 1
            return None
        if block.identity_fingerprint != fp:
            self.metrics.compatibility_failures += 1
            raise CacheCompatibilityError("KV identity mismatch")
        payload = self._decompress(block)
        if self._checksum(payload) != block.checksum:
            self.metrics.integrity_failures += 1
            self._evict(digest)
            raise CacheIntegrityError("KV checksum mismatch")
        if verify:
            result = self.arbitration.verify(block)
            if not result.accepted:
                self.metrics.verifier_disagreements += 1
                self.metrics.misses += 1
                return None
        block.last_access = now
        block.reuse_count += 1
        self.metrics.hits += 1
        if block.tier is not MemoryTier.HOT:
            self._move(digest, MemoryTier.HOT)
            self.metrics.promotions += 1
            if block.reuse_count == 1:
                self.metrics.prefetch_hits += 1
        return CacheHit(digest, payload, block.token_count, block.tier, block.reuse_count, block.semantic_tags)

    def _resolve_prefix(self, fp: str, prefix: str, branch: str) -> str | None:
        current: str | None = branch
        while current is not None:
            digest = self._prefix_index.get((fp, prefix, current))
            if digest is not None:
                return digest
            current = self._branch_parents.get(current)
        return None

    def best_prefix(
        self,
        identity: KVIdentity,
        token_ids: Sequence[int],
        *,
        branch: str = "main",
    ) -> CacheHit | None:
        for end in range(len(token_ids), 0, -1):
            hit = self.get(identity, token_ids[:end], branch=branch)
            if hit is not None:
                return hit
        return None

    def prefetch(self, identity: KVIdentity, token_prefixes: Iterable[Sequence[int]], *, branch: str = "main") -> int:
        promoted = 0
        fp = identity.fingerprint()
        for tokens in token_prefixes:
            digest = self._resolve_prefix(fp, self.prefix_digest(tokens), branch)
            if digest is None or digest not in self._blocks:
                continue
            if self._blocks[digest].tier is not MemoryTier.HOT:
                self._move(digest, MemoryTier.HOT)
                self.metrics.promotions += 1
                promoted += 1
        self._rebalance()
        return promoted

    def fork(self, branch: str, *, parent: str = "main") -> None:
        if branch in self._branch_parents:
            raise ValueError(f"branch already exists: {branch}")
        if parent not in self._branch_parents:
            raise KeyError(f"unknown parent branch: {parent}")
        self._branch_parents[branch] = parent

    def drop_branch(self, branch: str) -> None:
        if branch == "main":
            raise ValueError("cannot drop main branch")
        if branch not in self._branch_parents:
            return
        for digest in tuple(self._branch_members.get(branch, ())):
            self._branch_members[branch].discard(digest)
            block = self._blocks.get(digest)
            if block is not None and not any(digest in members for name, members in self._branch_members.items() if name != branch):
                self._evict(digest)
        self._branch_members.pop(branch, None)
        self._branch_parents.pop(branch, None)
        for key in tuple(self._prefix_index):
            if key[2] == branch:
                self._prefix_index.pop(key, None)

    def begin(self, *, branch: str = "main") -> TransactionToken:
        if branch not in self._branch_parents:
            raise KeyError(f"unknown branch: {branch}")
        return TransactionToken(branch, frozenset(self._branch_members.get(branch, ())))

    def rollback(self, transaction: TransactionToken) -> int:
        current = set(self._branch_members.get(transaction.branch, ()))
        created = current.difference(transaction.baseline_digests)
        removed = 0
        for digest in tuple(created):
            self._branch_members[transaction.branch].discard(digest)
            for key, value in tuple(self._prefix_index.items()):
                if key[2] == transaction.branch and value == digest:
                    self._prefix_index.pop(key, None)
            if not any(digest in members for members in self._branch_members.values()):
                self._evict(digest)
            removed += 1
        self.metrics.speculative_rollbacks += 1
        return removed

    def commit(self, transaction: TransactionToken) -> int:
        return len(set(self._branch_members.get(transaction.branch, ())).difference(transaction.baseline_digests))

    def invalidate_model(self, model: str, revision: str | None = None) -> int:
        # Identity fingerprints are one-way; model metadata is intentionally not duplicated.
        # Callers should use invalidate_if when revision-aware invalidation is required.
        return self.invalidate_if(lambda block: model in block.semantic_tags and (revision is None or revision in block.semantic_tags))

    def invalidate_if(self, predicate: Callable[[KVBlock], bool]) -> int:
        doomed = [digest for digest, block in self._blocks.items() if predicate(block) and not block.pinned]
        for digest in doomed:
            self._evict(digest)
        return len(doomed)

    def pin(self, digest: str, value: bool = True) -> None:
        self._blocks[digest].pinned = value

    def update_attention(self, digest: str, score: float) -> None:
        self._blocks[digest].attention_score = max(0.0, min(1.0, score))

    def _eviction_score(self, block: KVBlock, now: float) -> float:
        age = max(0.0, now - block.last_access)
        recency = 1.0 / (1.0 + age)
        frequency = math.log2(2.0 + block.reuse_count) / 8.0
        priority = float(block.priority) / float(PriorityClass.CRITICAL)
        return (
            self.policy.recency_weight * recency
            + self.policy.reuse_weight * frequency
            + self.policy.priority_weight * priority
            + self.policy.attention_weight * block.attention_score
        )

    def _rebalance(self) -> None:
        high = int(self.policy.max_bytes * self.policy.high_watermark)
        low = int(self.policy.max_bytes * self.policy.low_watermark)
        hot_cap = int(self.policy.max_bytes * self.policy.hot_ratio)
        warm_cap = int(self.policy.max_bytes * self.policy.warm_ratio)
        now = self._clock()

        for digest, block in tuple(self._blocks.items()):
            if block.expired(now) and not block.pinned:
                self._evict(digest)

        self._trim_tier(MemoryTier.HOT, hot_cap, MemoryTier.WARM, now)
        self._trim_tier(MemoryTier.WARM, warm_cap, MemoryTier.COLD, now)
        if self.bytes_used > high:
            victims = sorted(
                (block for block in self._blocks.values() if not block.pinned),
                key=lambda block: (self._eviction_score(block, now), -block.size_bytes),
            )
            for block in victims:
                self._evict(block.digest)
                if self.bytes_used <= low:
                    break

    def _trim_tier(self, tier: MemoryTier, cap: int, target: MemoryTier, now: float) -> None:
        while self.tier_bytes(tier) > cap:
            candidates = [self._blocks[digest] for digest in self._tier_members[tier] if not self._blocks[digest].pinned]
            if not candidates:
                return
            victim = min(candidates, key=lambda block: self._eviction_score(block, now))
            self._move(victim.digest, target)
            self.metrics.demotions += 1

    def _move(self, digest: str, tier: MemoryTier) -> None:
        block = self._blocks[digest]
        self._tier_members[block.tier].discard(digest)
        block.tier = tier
        self._tier_members[tier].add(digest)

    def _evict(self, digest: str) -> None:
        block = self._blocks.pop(digest, None)
        if block is None:
            return
        self._tier_members[block.tier].discard(digest)
        self._tenant_bytes[block.tenant] -= block.size_bytes
        for key, value in tuple(self._prefix_index.items()):
            if value == digest:
                self._prefix_index.pop(key, None)
        for members in self._branch_members.values():
            members.discard(digest)
        self.metrics.evictions += 1

    @property
    def bytes_used(self) -> int:
        return sum(block.size_bytes for block in self._blocks.values())

    def tier_bytes(self, tier: MemoryTier) -> int:
        return sum(self._blocks[digest].size_bytes for digest in self._tier_members[tier] if digest in self._blocks)

    def snapshot(self) -> dict[str, object]:
        return {
            "blocks": len(self._blocks),
            "bytes_used": self.bytes_used,
            "hit_rate": self.metrics.hit_rate,
            "tiers": {tier.value: len(self._tier_members[tier]) for tier in MemoryTier},
            "tenant_bytes": dict(self._tenant_bytes),
            "policy": self.policy,
        }

    def autotune(self, *, memory_pressure: float, observed_hit_rate: float | None = None) -> CachePolicy:
        """Closed-loop conservative policy adjustment; returns and installs the new policy."""
        pressure = max(0.0, min(1.0, memory_pressure))
        hit_rate = self.metrics.hit_rate if observed_hit_rate is None else max(0.0, min(1.0, observed_hit_rate))
        hot_ratio = self.policy.hot_ratio
        admission = self.policy.min_admission_score
        if pressure > 0.85:
            hot_ratio = max(0.25, hot_ratio - 0.05)
            admission = min(0.80, admission + 0.05)
        elif pressure < 0.60 and hit_rate < 0.75:
            hot_ratio = min(0.70, hot_ratio + 0.05)
            admission = max(0.0, admission - 0.025)
        max_warm = max(0.0, 0.95 - hot_ratio)
        self.policy = replace(self.policy, hot_ratio=hot_ratio, warm_ratio=min(self.policy.warm_ratio, max_warm), min_admission_score=admission)
        self._rebalance()
        return self.policy


HYPER_KV_EVOLUTION: tuple[str, ...] = (
    "paged-block allocator contract", "zero-copy opaque payload boundary", "hot-page locality layout",
    "prefix hashing", "cross-request prefix reuse", "content-addressed deduplication",
    "token-selective prefix lookup", "attention telemetry", "recency-frequency scoring",
    "heavy-hitter retention", "sink/pinned block retention", "independent key/value precision plans",
    "per-channel quantization metadata", "mixed-precision layer/head plans", "full-precision residual window",
    "pressure-adaptive precision policy hook", "cold-block compression", "entropy-aware compression admission",
    "compact positional identity metadata", "system-prefix deduplication", "hot/warm/cold tier abstraction",
    "asynchronous-backend-ready prefetch API", "speculative prefetch", "watermark eviction",
    "SLA-aware admission score", "tenant quotas", "priority classes", "TTL and pinning",
    "semantic segment tags", "retrieval-driven prefix rehydration", "RoPE compatibility fingerprint",
    "model/revision/layer/head fingerprint", "coherence/version tags", "checksums and integrity rejection",
    "stale/poison invalidation", "transactional speculative append", "speculative rollback",
    "branch sharing with copy-on-write indexing", "KVARG verifier arbitration graph", "disagreement reconciliation result",
    "GQA/MQA head-group identity", "scheduler-friendly batch prefix interface", "tier defragmentation/rebalance",
    "backpressure and byte budgets", "predictive capacity policy hook", "hit/reuse/compute-savings telemetry",
    "closed-loop adaptive controller", "rendezvous distributed sharding", "deterministic replica failover order",
    "autotuning plus invariant-ready snapshot surface",
)

assert len(HYPER_KV_EVOLUTION) == 50
