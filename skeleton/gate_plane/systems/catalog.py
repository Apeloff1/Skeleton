"""Catalog of recovered systems fronted by the gate plane.

Each :class:`SystemProfile` describes one recovered system (Jeeves,
GameForge, local AI, Hive) as the edge sees it: which route patterns belong
to it, which service scopes read / write / administer it, which callers are
allowed at all, and the request limits the edge enforces before a request
reaches the system's own handlers.

Route patterns use the Pack F authZ grammar
(:class:`skeleton.gate_plane.s2s.authz.RoutePattern`), so the same strings
drive authZ policies, pipeline routes and system resolution. The default
catalog mirrors the prefixes actually mounted on main:

* Jeeves      ``backend/routes/jeeves_*.py`` (``/api/jeeves``, ``/api/jeeves-core`` ...)
* GameForge   ``backend/routes/gameforge_*.py`` (``/api/gameforge/**``)
* local AI    ``/api/llm-router`` plus the gate-plane loopback proxy ``/api/v1/local-ai``
* Hive        gate-plane mount ``/api/v1/hive`` over ``skeleton.automation.hive``

Pure data + validation; no I/O and no edits to ``skeleton/api/server.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from skeleton.gate_plane.s2s.authz import ALL_METHODS, MUTATING_METHODS, PolicyError, RoutePattern
from skeleton.gate_plane.s2s.tokens import validate_scope, validate_service_name

_SYSTEM_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
SAFE_METHODS: FrozenSet[str] = frozenset({"GET", "HEAD", "OPTIONS"})

MAX_BODY_CEILING = 64 * 1024 * 1024
MAX_DEADLINE_CEILING_S = 600.0
MAX_CONCURRENCY_CEILING = 4096


class CatalogError(ValueError):
    """Invalid system profile or conflicting catalog."""


@dataclass(frozen=True)
class SystemLimits:
    """Edge-enforced request limits for one system."""

    max_body_bytes: int = 1 * 1024 * 1024
    max_concurrency: int = 64
    deadline_s: float = 10.0
    write_deadline_s: Optional[float] = None
    retry_attempts: int = 2
    breaker_failures: int = 5
    breaker_cooldown_s: float = 30.0

    def __post_init__(self) -> None:
        if not (0 < int(self.max_body_bytes) <= MAX_BODY_CEILING):
            raise CatalogError(f"max_body_bytes must be in (0, {MAX_BODY_CEILING}]")
        if not (0 < int(self.max_concurrency) <= MAX_CONCURRENCY_CEILING):
            raise CatalogError(f"max_concurrency must be in (0, {MAX_CONCURRENCY_CEILING}]")
        if not (0 < float(self.deadline_s) <= MAX_DEADLINE_CEILING_S):
            raise CatalogError(f"deadline_s must be in (0, {MAX_DEADLINE_CEILING_S}]")
        if self.write_deadline_s is not None and not (0 < float(self.write_deadline_s) <= MAX_DEADLINE_CEILING_S):
            raise CatalogError(f"write_deadline_s must be in (0, {MAX_DEADLINE_CEILING_S}]")
        if not (1 <= int(self.retry_attempts) <= 5):
            raise CatalogError("retry_attempts must be within 1..5")
        if not (1 <= int(self.breaker_failures) <= 100):
            raise CatalogError("breaker_failures must be within 1..100")
        if not (0 < float(self.breaker_cooldown_s) <= 3600):
            raise CatalogError("breaker_cooldown_s must be in (0, 3600]")

    def deadline_for(self, method: str) -> float:
        if (method or "GET").upper() in MUTATING_METHODS and self.write_deadline_s is not None:
            return float(self.write_deadline_s)
        return float(self.deadline_s)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "max_body_bytes": int(self.max_body_bytes),
            "max_concurrency": int(self.max_concurrency),
            "deadline_s": float(self.deadline_s),
            "write_deadline_s": None if self.write_deadline_s is None else float(self.write_deadline_s),
            "retry_attempts": int(self.retry_attempts),
            "breaker_failures": int(self.breaker_failures),
            "breaker_cooldown_s": float(self.breaker_cooldown_s),
        }


@dataclass(frozen=True)
class SystemProfile:
    """How the edge treats one recovered system."""

    name: str
    title: str
    patterns: Tuple[str, ...]
    methods: FrozenSet[str] = ALL_METHODS
    read_scopes: FrozenSet[str] = frozenset()
    write_scopes: FrozenSet[str] = frozenset()
    admin_patterns: Tuple[str, ...] = ()
    admin_scopes: FrozenSet[str] = frozenset()
    allow_services: Optional[FrozenSet[str]] = None
    deny_services: FrozenSet[str] = frozenset()
    anonymous_read_patterns: Tuple[str, ...] = ()
    requires_ready: bool = True
    loopback_only: bool = False
    priority: int = 1
    limits: SystemLimits = field(default_factory=SystemLimits)
    upstream: str = ""

    @classmethod
    def build(
        cls,
        name: str,
        title: str,
        patterns: Iterable[str],
        *,
        methods: Optional[Iterable[str]] = None,
        read_scopes: Optional[Iterable[str]] = None,
        write_scopes: Optional[Iterable[str]] = None,
        admin_patterns: Iterable[str] = (),
        admin_scopes: Optional[Iterable[str]] = None,
        allow_services: Optional[Iterable[str]] = None,
        deny_services: Iterable[str] = (),
        anonymous_read_patterns: Iterable[str] = (),
        requires_ready: bool = True,
        loopback_only: bool = False,
        priority: int = 1,
        limits: Optional[SystemLimits] = None,
        upstream: Optional[str] = None,
    ) -> "SystemProfile":
        if not isinstance(name, str) or not _SYSTEM_RE.match(name):
            raise CatalogError(f"invalid system name {name!r}")
        pats = tuple(patterns)
        if not pats:
            raise CatalogError(f"{name}: at least one route pattern required")
        for raw in (*pats, *admin_patterns, *anonymous_read_patterns):
            try:
                RoutePattern.parse(raw)
            except PolicyError as exc:
                raise CatalogError(f"{name}: {exc}") from exc
        for raw in (*admin_patterns, *anonymous_read_patterns):
            if not any(_covers(owner, raw) for owner in pats):
                raise CatalogError(f"{name}: {raw!r} is not inside any system pattern")
        meths = ALL_METHODS if methods is None else frozenset(m.upper() for m in methods)
        if not meths or not meths <= ALL_METHODS:
            raise CatalogError(f"{name}: unsupported methods {sorted(meths - ALL_METHODS)}")
        try:
            rs = frozenset(validate_scope(s) for s in (read_scopes if read_scopes is not None else [f"{name}:read"]))
            ws = frozenset(validate_scope(s) for s in (write_scopes if write_scopes is not None else [f"{name}:write"]))
            ads = frozenset(validate_scope(s) for s in (admin_scopes if admin_scopes is not None else [f"{name}:admin"]))
            allow = None if allow_services is None else frozenset(validate_service_name(s) for s in allow_services)
            deny = frozenset(validate_service_name(s) for s in deny_services)
        except ValueError as exc:
            raise CatalogError(f"{name}: {exc}") from exc
        if not rs or not ws:
            raise CatalogError(f"{name}: read and write scopes must not be empty")
        if admin_patterns and not ads:
            raise CatalogError(f"{name}: admin patterns need admin scopes")
        if allow is not None and allow & deny:
            raise CatalogError(f"{name}: services both allowed and denied: {sorted(allow & deny)}")
        if not (0 <= int(priority) <= 9):
            raise CatalogError(f"{name}: priority must be within 0..9")
        return cls(
            name=name,
            title=str(title or name),
            patterns=pats,
            methods=meths,
            read_scopes=rs,
            write_scopes=ws,
            admin_patterns=tuple(admin_patterns),
            admin_scopes=ads,
            allow_services=allow,
            deny_services=deny,
            anonymous_read_patterns=tuple(anonymous_read_patterns),
            requires_ready=bool(requires_ready),
            loopback_only=bool(loopback_only),
            priority=int(priority),
            limits=limits if limits is not None else SystemLimits(),
            upstream=upstream or f"system-{name.replace('_', '-')}",
        )

    def compiled(self) -> Tuple[RoutePattern, ...]:
        return tuple(RoutePattern.parse(p) for p in self.patterns)

    def match(self, path: str) -> Optional[RoutePattern]:
        """Most specific own pattern matching ``path`` (None when outside the system)."""
        best: Optional[RoutePattern] = None
        for pat in self.compiled():
            if pat.match(path) is None:
                continue
            if best is None or pat.specificity() > best.specificity():
                best = pat
        return best

    def is_admin_path(self, path: str) -> bool:
        return any(RoutePattern.parse(p).match(path) is not None for p in self.admin_patterns)

    def is_anonymous_read(self, method: str, path: str) -> bool:
        if (method or "GET").upper() not in SAFE_METHODS:
            return False
        return any(RoutePattern.parse(p).match(path) is not None for p in self.anonymous_read_patterns)

    def required_scopes(self, method: str, path: str) -> Tuple[str, FrozenSet[str]]:
        """``("admin"|"write"|"read", scopes_any)`` for a request inside this system."""
        verb = (method or "GET").upper()
        if self.is_admin_path(path):
            return "admin", self.admin_scopes
        if verb in MUTATING_METHODS:
            return "write", self.write_scopes
        return "read", self.read_scopes | self.write_scopes

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "patterns": list(self.patterns),
            "methods": sorted(self.methods),
            "read_scopes": sorted(self.read_scopes),
            "write_scopes": sorted(self.write_scopes),
            "admin_patterns": list(self.admin_patterns),
            "admin_scopes": sorted(self.admin_scopes),
            "allow_services": None if self.allow_services is None else sorted(self.allow_services),
            "deny_services": sorted(self.deny_services),
            "anonymous_read_patterns": list(self.anonymous_read_patterns),
            "requires_ready": self.requires_ready,
            "loopback_only": self.loopback_only,
            "priority": self.priority,
            "limits": self.limits.as_dict(),
            "upstream": self.upstream,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SystemProfile":
        known = {
            "name", "title", "patterns", "methods", "read_scopes", "write_scopes", "admin_patterns",
            "admin_scopes", "allow_services", "deny_services", "anonymous_read_patterns",
            "requires_ready", "loopback_only", "priority", "limits", "upstream",
        }
        unknown = set(data) - known
        if unknown:
            raise CatalogError(f"unknown profile keys: {sorted(unknown)}")
        for key in ("name", "patterns"):
            if key not in data:
                raise CatalogError(f"profile requires {key!r}")
        limits_raw = data.get("limits")
        limits = None
        if limits_raw is not None:
            if not isinstance(limits_raw, Mapping):
                raise CatalogError("limits must be a mapping")
            try:
                limits = SystemLimits(**dict(limits_raw))
            except TypeError as exc:
                raise CatalogError(f"bad limits: {exc}") from exc
        return cls.build(
            data["name"],
            data.get("title", data["name"]),
            data["patterns"],
            methods=data.get("methods"),
            read_scopes=data.get("read_scopes"),
            write_scopes=data.get("write_scopes"),
            admin_patterns=data.get("admin_patterns", ()),
            admin_scopes=data.get("admin_scopes"),
            allow_services=data.get("allow_services"),
            deny_services=data.get("deny_services", ()),
            anonymous_read_patterns=data.get("anonymous_read_patterns", ()),
            requires_ready=bool(data.get("requires_ready", True)),
            loopback_only=bool(data.get("loopback_only", False)),
            priority=int(data.get("priority", 1)),
            limits=limits,
            upstream=data.get("upstream"),
        )


def _covers(owner: str, inner: str) -> bool:
    """True when every path matched by ``inner`` is also matched by ``owner``.

    Conservative structural check: ``owner`` must be a segment-wise prefix of
    ``inner`` ending in ``**``, or have the same shape.
    """
    o = RoutePattern.parse(owner)
    i = RoutePattern.parse(inner)
    if o.shape() == i.shape():
        return True
    if not o.has_globstar:
        return False
    head = o.segments[:-1]
    if len(i.segments) < len(head):
        return False
    for os_, is_ in zip(head, i.segments):
        if os_.kind == "literal":
            if is_.kind != "literal" or is_.value != os_.value:
                return False
        elif is_.kind == "globstar":
            return False
    return True


class SystemCatalog:
    """Set of system profiles with non-overlapping route ownership."""

    def __init__(self, profiles: Sequence[SystemProfile] = ()) -> None:
        self._profiles: Dict[str, SystemProfile] = {}
        for p in profiles:
            self.add(p)

    def add(self, profile: SystemProfile) -> None:
        if profile.name in self._profiles:
            raise CatalogError(f"duplicate system {profile.name!r}")
        for other in self._profiles.values():
            if other.upstream == profile.upstream:
                raise CatalogError(f"systems {other.name!r} and {profile.name!r} share upstream {profile.upstream!r}")
            for a in profile.patterns:
                for b in other.patterns:
                    if _covers(a, b) or _covers(b, a):
                        raise CatalogError(
                            f"system {profile.name!r} pattern {a!r} overlaps {other.name!r} pattern {b!r}"
                        )
        self._profiles[profile.name] = profile

    def __len__(self) -> int:
        return len(self._profiles)

    def __contains__(self, name: object) -> bool:
        return name in self._profiles

    def names(self) -> List[str]:
        return sorted(self._profiles)

    def get(self, name: str) -> SystemProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise CatalogError(f"unknown system {name!r}") from exc

    def profiles(self) -> List[SystemProfile]:
        return [self._profiles[n] for n in self.names()]

    def resolve(self, path: str) -> Optional[SystemProfile]:
        """System owning ``path`` (most specific pattern wins; None if unowned)."""
        best: Optional[Tuple[Tuple[int, int, int, int], SystemProfile]] = None
        for prof in self._profiles.values():
            pat = prof.match(path)
            if pat is None:
                continue
            spec = pat.specificity()
            if best is None or spec > best[0]:
                best = (spec, prof)
        return None if best is None else best[1]

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [p.as_dict() for p in self.profiles()]

    @classmethod
    def from_dicts(cls, rows: Iterable[Mapping[str, Any]]) -> "SystemCatalog":
        return cls([SystemProfile.from_dict(r) for r in rows])

    def digest(self) -> str:
        blob = json.dumps(self.to_dicts(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


JEEVES_LEGACY_FAMILIES: Tuple[str, ...] = (
    "jeeves-build",
    "jeeves-core",
    "jeeves-eq",
    "jeeves-hyperion",
    "jeeves-languages",
    "jeeves-master",
    "jeeves-synergy",
    "jeeves-voice",
)


def default_catalog() -> SystemCatalog:
    """Catalog for the recovered systems mounted on main (see module docstring)."""
    jeeves = SystemProfile.build(
        "jeeves",
        "Jeeves studio / director",
        ("/api/jeeves/**", "/jeeves/**", *(f"/api/{fam}/**" for fam in JEEVES_LEGACY_FAMILIES)),
        admin_patterns=("/api/jeeves-master/**",),
        anonymous_read_patterns=("/api/jeeves/health", "/jeeves/health"),
        limits=SystemLimits(
            max_body_bytes=4 * 1024 * 1024, max_concurrency=64, deadline_s=30.0, write_deadline_s=60.0,
        ),
        priority=2,
    )
    gameforge = SystemProfile.build(
        "gameforge",
        "GameForge build / runtime",
        ("/api/gameforge/**",),
        read_scopes=["gameforge:read"],
        write_scopes=["gameforge:write"],
        admin_patterns=("/api/gameforge/build/**", "/api/gameforge/workflow/**"),
        admin_scopes=["gameforge:build"],
        limits=SystemLimits(
            max_body_bytes=8 * 1024 * 1024, max_concurrency=32, deadline_s=30.0, write_deadline_s=120.0,
            retry_attempts=2,
        ),
        priority=1,
    )
    local_ai = SystemProfile.build(
        "local_ai",
        "Local AI inference (loopback llama.cpp runtime)",
        ("/api/llm-router/**", "/api/v1/local-ai/**"),
        read_scopes=["local_ai:read"],
        write_scopes=["local_ai:infer"],
        admin_patterns=("/api/v1/local-ai/admin/**",),
        admin_scopes=["local_ai:admin"],
        anonymous_read_patterns=("/api/v1/local-ai/health",),
        loopback_only=True,
        limits=SystemLimits(
            max_body_bytes=512 * 1024, max_concurrency=4, deadline_s=60.0, write_deadline_s=120.0,
            retry_attempts=1, breaker_failures=3, breaker_cooldown_s=15.0,
        ),
        priority=3,
    )
    hive = SystemProfile.build(
        "hive",
        "Hive 1.0 (GB-25) automation kernel",
        ("/api/v1/hive/**",),
        anonymous_read_patterns=("/api/v1/hive/capabilities",),
        limits=SystemLimits(max_body_bytes=64 * 1024, max_concurrency=16, deadline_s=5.0, retry_attempts=1),
        priority=2,
    )
    return SystemCatalog([jeeves, gameforge, local_ai, hive])


__all__ = [
    "CatalogError",
    "JEEVES_LEGACY_FAMILIES",
    "MAX_BODY_CEILING",
    "MAX_CONCURRENCY_CEILING",
    "MAX_DEADLINE_CEILING_S",
    "SAFE_METHODS",
    "SystemCatalog",
    "SystemLimits",
    "SystemProfile",
    "default_catalog",
]
