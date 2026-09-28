"""Deterministic cache identity and eviction policy for local/CI parity.

Issue #807 batch B003 requires Python, Node, asset, and generated caches to use
the same explicit identity rules regardless of where a build runs. This module
is planning-only: it performs no filesystem, package-manager, network, or
wall-clock operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from skeleton.kernel.errors import SkeletonError


CACHE_SCHEMA = 1
CACHE_ALGORITHM = "sha256"
CACHE_KEY_PREFIX = "skeleton-cache-v1"
CACHE_KINDS = frozenset({"python", "node", "assets", "generated"})
MAX_NAMESPACE_LENGTH = 128
MAX_MATERIALS = 256
MAX_MATERIAL_NAME_LENGTH = 256
MAX_MATERIAL_VALUE_BYTES = 1_048_576
MAX_ENTRIES = 100_000
MAX_CACHE_BYTES = 1 << 50
MAX_GENERATION = (1 << 63) - 1


class CacheContractError(SkeletonError):
    """Reject cache plans whose identity or retention cannot be trusted."""

    code = "BUILD.CACHE_CONTRACT"
    http_status = 400


@dataclass(frozen=True, slots=True)
class CacheKey:
    schema: int
    algorithm: str
    kind: str
    namespace: str
    key: str
    material_digest: str
    toolchain_digest: str
    config_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "algorithm": self.algorithm,
            "kind": self.kind,
            "namespace": self.namespace,
            "key": self.key,
            "material_digest": self.material_digest,
            "toolchain_digest": self.toolchain_digest,
            "config_digest": self.config_digest,
        }

    def serialize(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class CacheEntry:
    key: str
    size_bytes: int
    last_access_generation: int
    created_generation: int
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class EvictionPolicy:
    max_entries: int
    max_bytes: int
    ttl_generations: int | None = None


@dataclass(frozen=True, slots=True)
class EvictionPlan:
    retained: tuple[str, ...]
    victims: tuple[str, ...]
    expired: tuple[str, ...]
    bytes_before: int
    bytes_after: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "retained": list(self.retained),
            "victims": list(self.victims),
            "expired": list(self.expired),
            "bytes_before": self.bytes_before,
            "bytes_after": self.bytes_after,
        }


def build_cache_key(
    *,
    kind: str,
    namespace: str,
    materials: Mapping[str, str],
    toolchain: Mapping[str, str],
    config: Mapping[str, str] | None = None,
) -> CacheKey:
    """Build the same cache identity for identical local and CI inputs."""

    normalized_kind = _require_kind(kind)
    normalized_namespace = _require_namespace(namespace)
    material_pairs = _normalize_mapping(materials, field="materials", allow_empty=False)
    toolchain_pairs = _normalize_mapping(toolchain, field="toolchain", allow_empty=False)
    config_pairs = _normalize_mapping(
        {} if config is None else config,
        field="config",
        allow_empty=True,
    )

    material_digest = _sha256_pairs(material_pairs)
    toolchain_digest = _sha256_pairs(toolchain_pairs)
    config_digest = _sha256_pairs(config_pairs)
    aggregate = _sha256(
        {
            "schema": CACHE_SCHEMA,
            "algorithm": CACHE_ALGORITHM,
            "kind": normalized_kind,
            "namespace": normalized_namespace,
            "material_digest": material_digest,
            "toolchain_digest": toolchain_digest,
            "config_digest": config_digest,
        }
    )
    key = f"{CACHE_KEY_PREFIX}:{normalized_kind}:{normalized_namespace}:{aggregate}"
    return CacheKey(
        schema=CACHE_SCHEMA,
        algorithm=CACHE_ALGORITHM,
        kind=normalized_kind,
        namespace=normalized_namespace,
        key=key,
        material_digest=material_digest,
        toolchain_digest=toolchain_digest,
        config_digest=config_digest,
    )


def plan_eviction(
    entries: Sequence[CacheEntry | Mapping[str, Any]],
    *,
    policy: EvictionPolicy,
    current_generation: int,
) -> EvictionPlan:
    """Apply deterministic generation-based TTL then stable LRU eviction."""

    checked_policy = _require_policy(policy)
    generation = _require_generation(current_generation, field="current_generation")
    if len(entries) > MAX_ENTRIES:
        raise CacheContractError(
            "entry count exceeds hard safety bound",
            context={"entries": len(entries), "max_entries": MAX_ENTRIES},
        )

    normalized: list[CacheEntry] = []
    seen: set[str] = set()
    for raw in entries:
        entry = _coerce_entry(raw)
        if entry.key in seen:
            raise CacheContractError("duplicate cache entry key", context={"key": entry.key})
        seen.add(entry.key)
        if entry.created_generation > generation:
            raise CacheContractError("cache entry was created in the future", context={"key": entry.key})
        if entry.last_access_generation > generation:
            raise CacheContractError("cache entry was accessed in the future", context={"key": entry.key})
        if entry.last_access_generation < entry.created_generation:
            raise CacheContractError("cache entry access predates creation", context={"key": entry.key})
        normalized.append(entry)

    bytes_before = sum(entry.size_bytes for entry in normalized)
    if bytes_before > MAX_CACHE_BYTES:
        raise CacheContractError("cache bytes exceed hard safety bound")

    pinned = [entry for entry in normalized if entry.pinned]
    pinned_bytes = sum(entry.size_bytes for entry in pinned)
    if len(pinned) > checked_policy.max_entries or pinned_bytes > checked_policy.max_bytes:
        raise CacheContractError("pinned entries exceed eviction policy")

    expired_keys: set[str] = set()
    ttl = checked_policy.ttl_generations
    if ttl is not None:
        for entry in normalized:
            if not entry.pinned and generation - entry.last_access_generation > ttl:
                expired_keys.add(entry.key)

    retained = {entry.key: entry for entry in normalized if entry.key not in expired_keys}
    victims = list(sorted(expired_keys))
    retained_bytes = bytes_before - sum(
        entry.size_bytes for entry in normalized if entry.key in expired_keys
    )

    candidates = sorted(
        (entry for entry in retained.values() if not entry.pinned),
        key=lambda entry: (
            entry.last_access_generation,
            entry.created_generation,
            entry.key,
        ),
    )
    index = 0
    while (
        len(retained) > checked_policy.max_entries
        or retained_bytes > checked_policy.max_bytes
    ):
        if index >= len(candidates):
            raise CacheContractError("eviction policy cannot be satisfied")
        victim = candidates[index]
        index += 1
        if victim.key in retained:
            del retained[victim.key]
            retained_bytes -= victim.size_bytes
            victims.append(victim.key)

    return EvictionPlan(
        retained=tuple(sorted(retained)),
        victims=tuple(victims),
        expired=tuple(sorted(expired_keys)),
        bytes_before=bytes_before,
        bytes_after=retained_bytes,
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CacheContractError("value is not canonically serializable") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_pairs(pairs: tuple[tuple[str, str], ...]) -> str:
    return _sha256([[name, value] for name, value in pairs])


def _require_kind(value: Any) -> str:
    if not isinstance(value, str) or value not in CACHE_KINDS:
        raise CacheContractError(
            "unsupported cache kind",
            context={"kind": value, "supported": sorted(CACHE_KINDS)},
        )
    return value


def _require_namespace(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CacheContractError("namespace must be a non-empty trimmed string")
    if len(value) > MAX_NAMESPACE_LENGTH:
        raise CacheContractError("namespace exceeds max length")
    if any(ch in value for ch in ("\x00", "\n", "\r", "\\", ":")):
        raise CacheContractError("namespace contains unsafe characters")
    return value


def _normalize_mapping(
    value: Any,
    *,
    field: str,
    allow_empty: bool,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        raise CacheContractError(f"{field} must be a mapping")
    if not allow_empty and not value:
        raise CacheContractError(f"{field} must not be empty")
    if len(value) > MAX_MATERIALS:
        raise CacheContractError(f"{field} count exceeds configured limit")

    normalized: list[tuple[str, str]] = []
    for name, raw_value in value.items():
        if not isinstance(name, str) or not name or name != name.strip():
            raise CacheContractError(f"{field} keys must be non-empty trimmed strings")
        if len(name) > MAX_MATERIAL_NAME_LENGTH:
            raise CacheContractError(f"{field} key exceeds max length")
        if any(ch in name for ch in ("\x00", "\n", "\r")):
            raise CacheContractError(f"{field} key contains unsafe characters")
        if not isinstance(raw_value, str):
            raise CacheContractError(f"{field} values must be strings")
        encoded = raw_value.encode("utf-8")
        if len(encoded) > MAX_MATERIAL_VALUE_BYTES:
            raise CacheContractError(f"{field} value exceeds max bytes")
        if "\x00" in raw_value:
            raise CacheContractError(f"{field} value contains NUL")
        normalized.append((name, raw_value))
    return tuple(sorted(normalized))


def _require_generation(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CacheContractError(f"{field} must be an integer")
    if value < 0 or value > MAX_GENERATION:
        raise CacheContractError(f"{field} is out of range")
    return value


def _require_size(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CacheContractError("size_bytes must be a non-negative integer")
    if value > MAX_CACHE_BYTES:
        raise CacheContractError("cache entry exceeds hard byte bound")
    return value


def _require_entry_key(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CacheContractError("cache entry key must be a non-empty trimmed string")
    if len(value) > 512:
        raise CacheContractError("cache entry key exceeds max length")
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        raise CacheContractError("cache entry key contains unsafe characters")
    return value


def _coerce_entry(raw: CacheEntry | Mapping[str, Any]) -> CacheEntry:
    if isinstance(raw, CacheEntry):
        entry = raw
    elif isinstance(raw, Mapping):
        allowed = {
            "key",
            "size_bytes",
            "last_access_generation",
            "created_generation",
            "pinned",
        }
        extra = sorted(str(key) for key in raw if key not in allowed)
        if extra:
            raise CacheContractError("cache entry contains unknown keys", context={"keys": extra})
        try:
            entry = CacheEntry(
                key=raw["key"],
                size_bytes=raw["size_bytes"],
                last_access_generation=raw["last_access_generation"],
                created_generation=raw["created_generation"],
                pinned=raw.get("pinned", False),
            )
        except KeyError as exc:
            raise CacheContractError("cache entry is missing a required field") from exc
    else:
        raise CacheContractError("cache entry must be a CacheEntry or mapping")

    if not isinstance(entry.pinned, bool):
        raise CacheContractError("pinned must be boolean")
    return CacheEntry(
        key=_require_entry_key(entry.key),
        size_bytes=_require_size(entry.size_bytes),
        last_access_generation=_require_generation(
            entry.last_access_generation, field="last_access_generation"
        ),
        created_generation=_require_generation(
            entry.created_generation, field="created_generation"
        ),
        pinned=entry.pinned,
    )


def _require_policy(policy: Any) -> EvictionPolicy:
    if not isinstance(policy, EvictionPolicy):
        raise CacheContractError("policy must be an EvictionPolicy")
    if (
        isinstance(policy.max_entries, bool)
        or not isinstance(policy.max_entries, int)
        or policy.max_entries < 1
        or policy.max_entries > MAX_ENTRIES
    ):
        raise CacheContractError("max_entries is out of range")
    if (
        isinstance(policy.max_bytes, bool)
        or not isinstance(policy.max_bytes, int)
        or policy.max_bytes < 1
        or policy.max_bytes > MAX_CACHE_BYTES
    ):
        raise CacheContractError("max_bytes is out of range")
    ttl = policy.ttl_generations
    if ttl is not None and (
        isinstance(ttl, bool)
        or not isinstance(ttl, int)
        or ttl < 0
        or ttl > MAX_GENERATION
    ):
        raise CacheContractError("ttl_generations is out of range")
    return policy
