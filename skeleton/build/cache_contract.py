"""Deterministic local/CI cache identity and eviction contract for B003.

The contract intentionally excludes execution location (developer machine versus
CI runner) from cache identity. Identical declared materials under the same
repository policy produce the same key everywhere.

This module does not perform cache I/O. It defines the bounded, content-addressed
identity and deterministic eviction plan that cache adapters must obey.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from skeleton.kernel.errors import SkeletonError


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = REPO_ROOT / ".github" / "ci" / "cache-policy.json"

CACHE_POLICY_SCHEMA = 1
CACHE_ALGORITHM = "sha256"
REQUIRED_DOMAINS = ("assets", "generated", "node", "python")
MAX_POLICY_BYTES = 64 * 1024
MAX_MATERIALS = 64
MAX_MATERIAL_NAME = 128
MAX_MATERIAL_VALUE_BYTES = 4096
MAX_KEY_PREFIX = 48
MAX_ENTRIES = 10_000
MAX_ENTRY_BYTES = 1 << 50
MAX_EPOCH = (1 << 63) - 1
SECONDS_PER_DAY = 86_400
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")


class CacheContractError(SkeletonError):
    """Refuse cache identity/eviction when the contract is ambiguous."""

    code = "BUILD.CACHE_CONTRACT"
    http_status = 400


@dataclass(frozen=True, slots=True)
class CacheDomainPolicy:
    max_entries: int
    max_bytes: int

    def to_dict(self) -> dict[str, int]:
        return {
            "max_entries": self.max_entries,
            "max_bytes": self.max_bytes,
        }


@dataclass(frozen=True, slots=True)
class CachePolicy:
    schema_version: int
    algorithm: str
    key_prefix: str
    max_age_days: int
    domains: tuple[tuple[str, CacheDomainPolicy], ...]

    def domain_map(self) -> dict[str, CacheDomainPolicy]:
        return dict(self.domains)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "algorithm": self.algorithm,
            "key_prefix": self.key_prefix,
            "max_age_days": self.max_age_days,
            "domains": {
                name: policy.to_dict()
                for name, policy in self.domains
            },
        }

    @property
    def digest(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class CacheKey:
    domain: str
    digest: str
    policy_digest: str
    key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "domain": self.domain,
            "digest": self.digest,
            "policy_digest": self.policy_digest,
            "key": self.key,
        }


@dataclass(frozen=True, slots=True)
class CacheEntry:
    key: str
    domain: str
    size_bytes: int
    created_epoch: int
    last_used_epoch: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "domain": self.domain,
            "size_bytes": self.size_bytes,
            "created_epoch": self.created_epoch,
            "last_used_epoch": self.last_used_epoch,
        }


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


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CacheContractError(
                "duplicate JSON key",
                context={"key": key},
            )
        result[key] = value
    return result


def _load_json(path: Path, *, max_bytes: int) -> Any:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CacheContractError(
            "cannot stat JSON input",
            context={"path": path.name},
        ) from exc
    if size > max_bytes:
        raise CacheContractError(
            "JSON input exceeds byte limit",
            context={"path": path.name, "bytes": size, "max_bytes": max_bytes},
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CacheContractError(
            "cannot read JSON input",
            context={"path": path.name},
        ) from exc
    try:
        return json.loads(raw, object_pairs_hook=_pairs_no_duplicates)
    except CacheContractError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise CacheContractError(
            "invalid UTF-8 JSON input",
            context={"path": path.name},
        ) from exc


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    *,
    field: str,
) -> None:
    actual = frozenset(payload)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise CacheContractError(
            "object keys do not match contract",
            context={"field": field, "missing": missing, "extra": extra},
        )


def _positive_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CacheContractError(
            "value must be an integer",
            context={"field": field},
        )
    if value <= 0 or value > maximum:
        raise CacheContractError(
            "integer outside contract bounds",
            context={"field": field, "value": value, "maximum": maximum},
        )
    return value


def _nonnegative_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CacheContractError(
            "value must be an integer",
            context={"field": field},
        )
    if value < 0 or value > maximum:
        raise CacheContractError(
            "integer outside contract bounds",
            context={"field": field, "value": value, "maximum": maximum},
        )
    return value


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> CachePolicy:
    raw = _load_json(path, max_bytes=MAX_POLICY_BYTES)
    if not isinstance(raw, Mapping):
        raise CacheContractError("cache policy root must be an object")
    _require_exact_keys(
        raw,
        frozenset(
            {
                "schema_version",
                "algorithm",
                "key_prefix",
                "max_age_days",
                "domains",
            }
        ),
        field="policy",
    )
    if raw["schema_version"] != CACHE_POLICY_SCHEMA:
        raise CacheContractError(
            "unsupported cache policy schema",
            context={"schema_version": raw["schema_version"]},
        )
    if raw["algorithm"] != CACHE_ALGORITHM:
        raise CacheContractError(
            "unsupported cache key algorithm",
            context={"algorithm": raw["algorithm"]},
        )
    prefix = raw["key_prefix"]
    if not isinstance(prefix, str) or not PREFIX_RE.fullmatch(prefix):
        raise CacheContractError("invalid cache key prefix")
    max_age_days = _positive_int(
        raw["max_age_days"],
        "max_age_days",
        maximum=365,
    )

    domains_raw = raw["domains"]
    if not isinstance(domains_raw, Mapping):
        raise CacheContractError("domains must be an object")
    if tuple(sorted(domains_raw)) != REQUIRED_DOMAINS:
        raise CacheContractError(
            "cache domains must match the canonical domain set",
            context={
                "expected": list(REQUIRED_DOMAINS),
                "actual": sorted(domains_raw),
            },
        )

    domains: list[tuple[str, CacheDomainPolicy]] = []
    for name in REQUIRED_DOMAINS:
        value = domains_raw[name]
        if not isinstance(value, Mapping):
            raise CacheContractError(
                "domain policy must be an object",
                context={"domain": name},
            )
        _require_exact_keys(
            value,
            frozenset({"max_entries", "max_bytes"}),
            field=f"domains.{name}",
        )
        domains.append(
            (
                name,
                CacheDomainPolicy(
                    max_entries=_positive_int(
                        value["max_entries"],
                        f"domains.{name}.max_entries",
                        maximum=MAX_ENTRIES,
                    ),
                    max_bytes=_positive_int(
                        value["max_bytes"],
                        f"domains.{name}.max_bytes",
                        maximum=MAX_ENTRY_BYTES,
                    ),
                ),
            )
        )

    return CachePolicy(
        schema_version=CACHE_POLICY_SCHEMA,
        algorithm=CACHE_ALGORITHM,
        key_prefix=prefix,
        max_age_days=max_age_days,
        domains=tuple(domains),
    )


def _normalize_materials(materials: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    if not isinstance(materials, Mapping):
        raise CacheContractError("materials must be a mapping")
    if not materials:
        raise CacheContractError("cache key requires at least one material")
    if len(materials) > MAX_MATERIALS:
        raise CacheContractError(
            "material count exceeds contract bound",
            context={"count": len(materials), "maximum": MAX_MATERIALS},
        )

    normalized: list[tuple[str, str]] = []
    for raw_name, raw_value in materials.items():
        if not isinstance(raw_name, str) or not NAME_RE.fullmatch(raw_name):
            raise CacheContractError(
                "invalid material name",
                context={"name": str(raw_name)[:MAX_MATERIAL_NAME]},
            )
        if not isinstance(raw_value, str):
            raise CacheContractError(
                "material value must be a string",
                context={"name": raw_name},
            )
        if "\x00" in raw_value:
            raise CacheContractError(
                "material value contains NUL",
                context={"name": raw_name},
            )
        encoded = raw_value.encode("utf-8")
        if len(encoded) > MAX_MATERIAL_VALUE_BYTES:
            raise CacheContractError(
                "material value exceeds byte limit",
                context={
                    "name": raw_name,
                    "bytes": len(encoded),
                    "maximum": MAX_MATERIAL_VALUE_BYTES,
                },
            )
        normalized.append((raw_name, raw_value))
    return tuple(sorted(normalized))


def compile_cache_key(
    policy: CachePolicy,
    *,
    domain: str,
    materials: Mapping[str, str],
    build_graph_fingerprint: str | None = None,
) -> CacheKey:
    domain_map = policy.domain_map()
    if domain not in domain_map:
        raise CacheContractError(
            "unknown cache domain",
            context={"domain": domain},
        )
    normalized = _normalize_materials(materials)
    if build_graph_fingerprint is not None:
        if not isinstance(build_graph_fingerprint, str) or not SHA256_RE.fullmatch(
            build_graph_fingerprint
        ):
            raise CacheContractError("build_graph_fingerprint must be lowercase SHA-256")

    payload = {
        "schema_version": policy.schema_version,
        "algorithm": policy.algorithm,
        "policy_digest": policy.digest,
        "domain": domain,
        "materials": [[name, value] for name, value in normalized],
        "build_graph_fingerprint": build_graph_fingerprint,
    }
    digest = _sha256(payload)
    key = f"{policy.key_prefix}-v{policy.schema_version}-{domain}-{digest}"
    return CacheKey(
        domain=domain,
        digest=digest,
        policy_digest=policy.digest,
        key=key,
    )


def _coerce_entry(raw: CacheEntry | Mapping[str, Any], *, domain: str) -> CacheEntry:
    if isinstance(raw, CacheEntry):
        payload = raw.to_dict()
    elif isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        raise CacheContractError(
            "cache entry must be an object",
            context={"type": type(raw).__name__},
        )
    _require_exact_keys(
        payload,
        frozenset(
            {
                "key",
                "domain",
                "size_bytes",
                "created_epoch",
                "last_used_epoch",
            }
        ),
        field="cache_entry",
    )
    key = payload["key"]
    if not isinstance(key, str) or not key or len(key) > 256 or "\x00" in key:
        raise CacheContractError("cache entry key is invalid")
    if payload["domain"] != domain:
        raise CacheContractError(
            "cache entry domain mismatch",
            context={"expected": domain, "actual": payload["domain"]},
        )
    size_bytes = _nonnegative_int(
        payload["size_bytes"],
        "size_bytes",
        maximum=MAX_ENTRY_BYTES,
    )
    created = _nonnegative_int(
        payload["created_epoch"],
        "created_epoch",
        maximum=MAX_EPOCH,
    )
    last_used = _nonnegative_int(
        payload["last_used_epoch"],
        "last_used_epoch",
        maximum=MAX_EPOCH,
    )
    if last_used < created:
        raise CacheContractError("last_used_epoch cannot precede created_epoch")
    return CacheEntry(
        key=key,
        domain=domain,
        size_bytes=size_bytes,
        created_epoch=created,
        last_used_epoch=last_used,
    )


def plan_evictions(
    policy: CachePolicy,
    *,
    domain: str,
    entries: Iterable[CacheEntry | Mapping[str, Any]],
    now_epoch: int,
) -> tuple[str, ...]:
    domain_policy = policy.domain_map().get(domain)
    if domain_policy is None:
        raise CacheContractError(
            "unknown cache domain",
            context={"domain": domain},
        )
    now = _nonnegative_int(now_epoch, "now_epoch", maximum=MAX_EPOCH)

    normalized: list[CacheEntry] = []
    seen: set[str] = set()
    for raw in entries:
        if len(normalized) >= MAX_ENTRIES:
            raise CacheContractError(
                "cache entry count exceeds contract bound",
                context={"maximum": MAX_ENTRIES},
            )
        entry = _coerce_entry(raw, domain=domain)
        if entry.key in seen:
            raise CacheContractError(
                "duplicate cache entry key",
                context={"key": entry.key},
            )
        if entry.created_epoch > now or entry.last_used_epoch > now:
            raise CacheContractError(
                "cache entry timestamp is in the future",
                context={"key": entry.key},
            )
        seen.add(entry.key)
        normalized.append(entry)

    age_limit = policy.max_age_days * SECONDS_PER_DAY
    expired = {
        entry.key
        for entry in normalized
        if now - entry.last_used_epoch >= age_limit
    }
    survivors = [entry for entry in normalized if entry.key not in expired]
    total_bytes = sum(entry.size_bytes for entry in survivors)
    evicted = set(expired)

    ordered = sorted(
        survivors,
        key=lambda entry: (
            entry.last_used_epoch,
            entry.created_epoch,
            entry.key,
        ),
    )
    index = 0
    while (
        len(survivors) - (index) > domain_policy.max_entries
        or total_bytes > domain_policy.max_bytes
    ):
        if index >= len(ordered):
            raise CacheContractError("eviction planner could not satisfy cache budget")
        victim = ordered[index]
        index += 1
        if victim.key in evicted:
            continue
        evicted.add(victim.key)
        total_bytes -= victim.size_bytes

    return tuple(
        entry.key
        for entry in sorted(
            normalized,
            key=lambda item: (
                item.last_used_epoch,
                item.created_epoch,
                item.key,
            ),
        )
        if entry.key in evicted
    )


def _parse_material(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("material must be NAME=VALUE")
    name, material = value.split("=", 1)
    if not name:
        raise argparse.ArgumentTypeError("material name cannot be empty")
    return name, material


def cli_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    key_parser = subparsers.add_parser("key", help="emit a deterministic cache key")
    key_parser.add_argument("--domain", required=True)
    key_parser.add_argument("--material", action="append", type=_parse_material, default=[])
    key_parser.add_argument("--build-graph-fingerprint")

    evict_parser = subparsers.add_parser("evict", help="emit deterministic eviction keys")
    evict_parser.add_argument("--domain", required=True)
    evict_parser.add_argument("--entries", type=Path, required=True)
    evict_parser.add_argument("--now-epoch", type=int, required=True)

    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        if args.command == "key":
            materials: dict[str, str] = {}
            for name, value in args.material:
                if name in materials:
                    raise CacheContractError(
                        "duplicate CLI material name",
                        context={"name": name},
                    )
                materials[name] = value
            result = compile_cache_key(
                policy,
                domain=args.domain,
                materials=materials,
                build_graph_fingerprint=args.build_graph_fingerprint,
            )
            print(result.key)
            return 0

        entries_raw = _load_json(args.entries, max_bytes=MAX_POLICY_BYTES * 4)
        if not isinstance(entries_raw, list):
            raise CacheContractError("eviction entries JSON must be a list")
        for key in plan_evictions(
            policy,
            domain=args.domain,
            entries=entries_raw,
            now_epoch=args.now_epoch,
        ):
            print(key)
        return 0
    except CacheContractError as exc:
        print(f"Cache contract violation: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(cli_main())
