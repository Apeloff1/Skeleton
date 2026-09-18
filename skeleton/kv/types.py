from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class CacheTier(str, Enum):
    GPU = "gpu"
    CPU = "cpu"
    NVME = "nvme"
    REMOTE = "remote"


@dataclass(frozen=True, slots=True)
class KVNamespace:
    """All semantics that must match before KV state can be reused."""

    model_id: str
    model_revision: str = "default"
    tokenizer_id: str = "default"
    adapter_id: str = ""
    rope_signature: str = "default"
    attention_signature: str = "default"
    kv_dtype: str = "auto"
    tensor_layout: str = "auto"
    trust_domain: str = "default"
    cache_salt: str = ""

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for value in (
            self.model_id,
            self.model_revision,
            self.tokenizer_id,
            self.adapter_id,
            self.rope_signature,
            self.attention_signature,
            self.kv_dtype,
            self.tensor_layout,
            self.trust_domain,
            self.cache_salt,
        ):
            encoded = value.encode("utf-8")
            digest.update(struct.pack(">I", len(encoded)))
            digest.update(encoded)
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class KVPageInput:
    handle: Any
    size_bytes: int
    tier: CacheTier = CacheTier.GPU
    recompute_cost: float = 1.0
    retention_bias: float = 1.0
    quantization: str = "native"
    extra_fingerprint: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes <= 0:
            raise ValueError("size_bytes must be a positive integer")
        for name, value in (
            ("recompute_cost", self.recompute_cost),
            ("retention_bias", self.retention_bias),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0")


@dataclass(frozen=True, slots=True)
class KVCacheConfig:
    block_size_tokens: int = 16
    max_bytes: int = 1 << 30
    max_entries: int = 65_536
    min_prefix_tokens: int = 1
    strict_verification: bool = True
    frequency_decay_interval: int = 16_384
    recency_half_life_seconds: float = 60.0
    trust_domain_max_bytes: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("block_size_tokens", self.block_size_tokens),
            ("max_bytes", self.max_bytes),
            ("max_entries", self.max_entries),
            ("min_prefix_tokens", self.min_prefix_tokens),
            ("frequency_decay_interval", self.frequency_decay_interval),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not math.isfinite(self.recency_half_life_seconds) or self.recency_half_life_seconds <= 0:
            raise ValueError("recency_half_life_seconds must be finite and > 0")
        limit = self.trust_domain_max_bytes
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
            raise ValueError("trust_domain_max_bytes must be a positive integer when set")


class KVStorageAdapter(Protocol):
    """Backend hook for moving/releasing opaque KV pages."""

    def move(self, handle: Any, source: CacheTier, target: CacheTier) -> Any: ...

    def release(self, handle: Any, tier: CacheTier) -> None: ...


@dataclass(frozen=True, slots=True)
class KVCacheMatch:
    namespace: KVNamespace
    matched_tokens: int
    requested_tokens: int
    handles: tuple[Any, ...]
    page_keys: tuple[str, ...]
    tiers: tuple[CacheTier, ...]

    @property
    def hit_ratio(self) -> float:
        return self.matched_tokens / self.requested_tokens if self.requested_tokens else 0.0

    @property
    def full_hit(self) -> bool:
        return self.requested_tokens > 0 and self.matched_tokens == self.requested_tokens


@dataclass(frozen=True, slots=True)
class KVReuseEstimate:
    matched_tokens: int
    requested_tokens: int
    hit_ratio: float
    hottest_tier: CacheTier | None
    route_score: float


@dataclass(frozen=True, slots=True)
class KVCacheStats:
    lookups: int
    hits: int
    full_hits: int
    token_hits: int
    token_lookups: int
    stores: int
    deduplicated_pages: int
    evictions: int
    evicted_bytes: int
    verification_failures: int
    migrations: int
    invalidations: int
    storage_errors: int
    resident_pages: int
    resident_bytes: int

    @property
    def request_hit_ratio(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0

    @property
    def token_hit_ratio(self) -> float:
        return self.token_hits / self.token_lookups if self.token_lookups else 0.0


@dataclass(frozen=True, slots=True)
class KVIntegrityReport:
    valid: bool
    resident_pages: int
    resident_bytes: int
    orphan_pages: tuple[str, ...]
    index_mismatches: tuple[str, ...]
    byte_accounting_ok: bool
