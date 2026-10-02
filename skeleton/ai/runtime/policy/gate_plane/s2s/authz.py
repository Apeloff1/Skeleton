"""Per-route service authorization policy for the s2s plane.

A :class:`PolicyTable` maps ``(method, path)`` to the most specific
:class:`RoutePolicy` and evaluates a :class:`Principal` (the verified
calling service) against it. The table is **default-deny**: a request that
matches no policy is refused with ``no_matching_policy``.

Pattern grammar (``/``-separated segments)::

    literal     exact segment match            /api/v1/forge
    {name}      one segment, captured          /api/v1/forge/{job_id}
    *           one segment, not captured      /api/v1/*/status
    **          zero or more trailing segments /api/v1/admin/**  (last only)

Specificity (highest wins): more literal segments, then more single-segment
wildcards/params, then no ``**``, then an explicit method list over ``*``.
Two policies with identical pattern shape and overlapping methods are a
configuration error, so ordering never silently decides access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from skeleton.gate_plane.s2s.tokens import scope_granted, validate_scope, validate_service_name

ALL_METHODS: FrozenSet[str] = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"})
MUTATING_METHODS: FrozenSet[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PARAM_RE = re.compile(r"^\{([a-z_][a-z0-9_]{0,31})\}$")
_LITERAL_RE = re.compile(r"^[A-Za-z0-9._~:@!$&'()+,;=-]+$")


class PolicyError(ValueError):
    """Invalid policy definition or conflicting table."""


class AuthzReason(str, Enum):
    ALLOWED = "allowed"
    NO_MATCHING_POLICY = "no_matching_policy"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    EXPLICIT_DENY = "explicit_deny"
    ANONYMOUS_FORBIDDEN = "anonymous_forbidden"
    SERVICE_NOT_ALLOWED = "service_not_allowed"
    SERVICE_DENIED = "service_denied"
    MISSING_SCOPE = "missing_scope"
    OVERLAP_KEY_FORBIDDEN = "overlap_key_forbidden"


class Effect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class Principal:
    """Authenticated caller as seen by authz."""

    service: Optional[str]
    scopes: FrozenSet[str] = frozenset()
    kid: Optional[str] = None
    in_overlap: bool = False

    @property
    def anonymous(self) -> bool:
        return self.service is None

    @classmethod
    def anonymous_principal(cls) -> "Principal":
        return cls(service=None)

    @classmethod
    def from_verified(cls, verified: Any) -> "Principal":
        """Build from :class:`~skeleton.gate_plane.s2s.tokens.VerifiedToken`."""
        return cls(
            service=verified.claims.iss,
            scopes=frozenset(verified.claims.scopes),
            kid=verified.kid,
            in_overlap=bool(verified.in_overlap),
        )

    def attester(self) -> Optional[str]:
        return None if self.service is None else f"svc:{self.service}"


@dataclass(frozen=True)
class Segment:
    kind: str  # literal | param | star | globstar
    value: str = ""


@dataclass(frozen=True)
class RoutePattern:
    raw: str
    segments: Tuple[Segment, ...]

    @classmethod
    def parse(cls, raw: str) -> "RoutePattern":
        if not isinstance(raw, str) or not raw.startswith("/"):
            raise PolicyError(f"pattern must start with '/': {raw!r}")
        parts = [p for p in raw.split("/")[1:]]
        if parts == [""]:
            parts = []
        segs: List[Segment] = []
        names: set[str] = set()
        for i, part in enumerate(parts):
            if part == "":
                raise PolicyError(f"empty segment in {raw!r}")
            if part == "**":
                if i != len(parts) - 1:
                    raise PolicyError(f"'**' must be the last segment in {raw!r}")
                segs.append(Segment("globstar"))
            elif part == "*":
                segs.append(Segment("star"))
            elif _PARAM_RE.match(part):
                name = _PARAM_RE.match(part).group(1)  # type: ignore[union-attr]
                if name in names:
                    raise PolicyError(f"duplicate param {name!r} in {raw!r}")
                names.add(name)
                segs.append(Segment("param", name))
            elif _LITERAL_RE.match(part) and "{" not in part and "*" not in part:
                segs.append(Segment("literal", part))
            else:
                raise PolicyError(f"invalid segment {part!r} in {raw!r}")
        return cls(raw=raw, segments=tuple(segs))

    @property
    def has_globstar(self) -> bool:
        return bool(self.segments) and self.segments[-1].kind == "globstar"

    def shape(self) -> Tuple[str, ...]:
        """Pattern with param names erased — equal shapes match the same paths."""
        return tuple(s.value if s.kind == "literal" else ("*" if s.kind != "globstar" else "**") for s in self.segments)

    def specificity(self) -> Tuple[int, int, int, int]:
        literals = sum(1 for s in self.segments if s.kind == "literal")
        singles = sum(1 for s in self.segments if s.kind in ("param", "star"))
        return (literals, singles, 0 if self.has_globstar else 1, len(self.segments))

    def match(self, path: str) -> Optional[Dict[str, str]]:
        parts = split_path(path)
        params: Dict[str, str] = {}
        for i, seg in enumerate(self.segments):
            if seg.kind == "globstar":
                return params
            if i >= len(parts):
                return None
            part = parts[i]
            if seg.kind == "literal":
                if part != seg.value:
                    return None
            elif seg.kind == "param":
                params[seg.value] = part
        if len(parts) != len(self.segments):
            return None
        return params


def split_path(path: str) -> List[str]:
    """Normalise a request path into segments (query dropped, empty segments collapsed)."""
    p = (path or "/").split("?", 1)[0].split("#", 1)[0]
    return [s for s in p.split("/") if s not in ("", ".")]


@dataclass(frozen=True)
class RoutePolicy:
    name: str
    pattern: RoutePattern
    methods: FrozenSet[str] = ALL_METHODS
    effect: Effect = Effect.ALLOW
    scopes_all: FrozenSet[str] = frozenset()
    scopes_any: FrozenSet[str] = frozenset()
    allow_services: Optional[FrozenSet[str]] = None
    deny_services: FrozenSet[str] = frozenset()
    allow_anonymous: bool = False
    allow_overlap_keys: bool = True
    priority: int = 1
    explicit_methods: bool = False

    @classmethod
    def build(
        cls,
        name: str,
        pattern: str,
        *,
        methods: Optional[Iterable[str]] = None,
        effect: str | Effect = Effect.ALLOW,
        scopes_all: Iterable[str] = (),
        scopes_any: Iterable[str] = (),
        allow_services: Optional[Iterable[str]] = None,
        deny_services: Iterable[str] = (),
        allow_anonymous: bool = False,
        allow_overlap_keys: bool = True,
        priority: int = 1,
    ) -> "RoutePolicy":
        if not name or not isinstance(name, str):
            raise PolicyError("policy name required")
        meths = ALL_METHODS if methods is None else frozenset(m.upper() for m in methods)
        if not meths or not meths <= ALL_METHODS:
            raise PolicyError(f"{name}: unsupported methods {sorted(meths - ALL_METHODS)}")
        try:
            sa = frozenset(validate_scope(s) for s in scopes_all)
            sy = frozenset(validate_scope(s) for s in scopes_any)
            allow = None if allow_services is None else frozenset(validate_service_name(s) for s in allow_services)
            deny = frozenset(validate_service_name(s) for s in deny_services)
        except ValueError as exc:
            raise PolicyError(f"{name}: {exc}") from exc
        if allow is not None and allow & deny:
            raise PolicyError(f"{name}: services both allowed and denied: {sorted(allow & deny)}")
        if not (0 <= int(priority) <= 9):
            raise PolicyError(f"{name}: priority must be within 0..9")
        eff = Effect(effect)
        if allow_anonymous and (sa or sy or allow):
            raise PolicyError(f"{name}: anonymous access cannot also require scopes/services")
        return cls(
            name=name,
            pattern=RoutePattern.parse(pattern),
            methods=meths,
            effect=eff,
            scopes_all=sa,
            scopes_any=sy,
            allow_services=allow,
            deny_services=deny,
            allow_anonymous=bool(allow_anonymous),
            allow_overlap_keys=bool(allow_overlap_keys),
            priority=int(priority),
            explicit_methods=methods is not None,
        )

    def rank(self) -> Tuple[int, int, int, int, int]:
        return (*self.pattern.specificity(), 1 if self.explicit_methods else 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pattern": self.pattern.raw,
            "methods": sorted(self.methods) if self.explicit_methods else None,
            "effect": self.effect.value,
            "scopes_all": sorted(self.scopes_all),
            "scopes_any": sorted(self.scopes_any),
            "allow_services": None if self.allow_services is None else sorted(self.allow_services),
            "deny_services": sorted(self.deny_services),
            "allow_anonymous": self.allow_anonymous,
            "allow_overlap_keys": self.allow_overlap_keys,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RoutePolicy":
        known = {
            "name", "pattern", "methods", "effect", "scopes_all", "scopes_any", "allow_services",
            "deny_services", "allow_anonymous", "allow_overlap_keys", "priority",
        }
        unknown = set(data) - known
        if unknown:
            raise PolicyError(f"unknown policy keys: {sorted(unknown)}")
        if "name" not in data or "pattern" not in data:
            raise PolicyError("policy requires name and pattern")
        return cls.build(
            data["name"],
            data["pattern"],
            methods=data.get("methods"),
            effect=data.get("effect", "allow"),
            scopes_all=data.get("scopes_all", ()),
            scopes_any=data.get("scopes_any", ()),
            allow_services=data.get("allow_services"),
            deny_services=data.get("deny_services", ()),
            allow_anonymous=bool(data.get("allow_anonymous", False)),
            allow_overlap_keys=bool(data.get("allow_overlap_keys", True)),
            priority=int(data.get("priority", 1)),
        )


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: AuthzReason
    policy: Optional[str] = None
    missing_scopes: Tuple[str, ...] = ()
    params: Mapping[str, str] = field(default_factory=dict)
    priority: int = 1

    @property
    def http_status(self) -> int:
        if self.allowed:
            return 200
        if self.reason is AuthzReason.ANONYMOUS_FORBIDDEN:
            return 401
        if self.reason is AuthzReason.METHOD_NOT_ALLOWED:
            return 405
        return 403

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason.value,
            "policy": self.policy,
            "missing_scopes": list(self.missing_scopes),
            "params": dict(self.params),
            "priority": self.priority,
            "http_status": self.http_status,
        }


class PolicyTable:
    """Default-deny route policy table with specificity-ordered matching."""

    def __init__(self, policies: Sequence[RoutePolicy] = ()) -> None:
        self._policies: List[RoutePolicy] = []
        for p in policies:
            self.add(p)

    def add(self, policy: RoutePolicy) -> None:
        for existing in self._policies:
            if existing.name == policy.name:
                raise PolicyError(f"duplicate policy name {policy.name!r}")
            if existing.pattern.shape() == policy.pattern.shape() and existing.methods & policy.methods:
                if existing.explicit_methods == policy.explicit_methods:
                    raise PolicyError(
                        f"policies {existing.name!r} and {policy.name!r} overlap on "
                        f"{policy.pattern.raw} {sorted(existing.methods & policy.methods)}"
                    )
        self._policies.append(policy)
        self._policies.sort(key=lambda p: (p.rank(), p.name), reverse=True)

    def __len__(self) -> int:
        return len(self._policies)

    def policies(self) -> List[RoutePolicy]:
        return list(self._policies)

    def match(self, method: str, path: str) -> Tuple[Optional[RoutePolicy], Dict[str, str], bool]:
        """Return (policy, params, path_matched_any).

        ``path_matched_any`` distinguishes 405 (path known, verb not) from
        default-deny on an unknown path.
        """
        m = (method or "GET").upper()
        path_hit = False
        for policy in self._policies:
            params = policy.pattern.match(path)
            if params is None:
                continue
            path_hit = True
            if m in policy.methods:
                return policy, params, True
        return None, {}, path_hit

    def evaluate(self, method: str, path: str, principal: Principal) -> PolicyDecision:
        policy, params, path_hit = self.match(method, path)
        if policy is None:
            reason = AuthzReason.METHOD_NOT_ALLOWED if path_hit else AuthzReason.NO_MATCHING_POLICY
            return PolicyDecision(False, reason)
        return evaluate_policy(policy, principal, params)

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in sorted(self._policies, key=lambda p: p.name)]

    @classmethod
    def from_dicts(cls, rows: Iterable[Mapping[str, Any]]) -> "PolicyTable":
        return cls([RoutePolicy.from_dict(r) for r in rows])

    def digest(self) -> str:
        blob = json.dumps(self.to_dicts(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def explain(self, method: str, path: str) -> List[Dict[str, Any]]:
        """Every policy whose pattern matches ``path``, in evaluation order (debug aid)."""
        m = (method or "GET").upper()
        out: List[Dict[str, Any]] = []
        for p in self._policies:
            params = p.pattern.match(path)
            if params is not None:
                out.append({"policy": p.name, "method_ok": m in p.methods, "rank": list(p.rank()), "params": params})
        return out


def evaluate_policy(policy: RoutePolicy, principal: Principal, params: Optional[Mapping[str, str]] = None) -> PolicyDecision:
    params = dict(params or {})

    def deny(reason: AuthzReason, missing: Tuple[str, ...] = ()) -> PolicyDecision:
        return PolicyDecision(False, reason, policy.name, missing, params, policy.priority)

    if policy.effect is Effect.DENY:
        return deny(AuthzReason.EXPLICIT_DENY)
    if principal.anonymous:
        if policy.allow_anonymous:
            return PolicyDecision(True, AuthzReason.ALLOWED, policy.name, (), params, policy.priority)
        return deny(AuthzReason.ANONYMOUS_FORBIDDEN)
    assert principal.service is not None
    if principal.service in policy.deny_services:
        return deny(AuthzReason.SERVICE_DENIED)
    if policy.allow_services is not None and principal.service not in policy.allow_services:
        return deny(AuthzReason.SERVICE_NOT_ALLOWED)
    if principal.in_overlap and not policy.allow_overlap_keys:
        return deny(AuthzReason.OVERLAP_KEY_FORBIDDEN)
    missing = tuple(sorted(s for s in policy.scopes_all if not scope_granted(principal.scopes, s)))
    if missing:
        return deny(AuthzReason.MISSING_SCOPE, missing)
    if policy.scopes_any and not any(scope_granted(principal.scopes, s) for s in policy.scopes_any):
        return deny(AuthzReason.MISSING_SCOPE, tuple(sorted(policy.scopes_any)))
    return PolicyDecision(True, AuthzReason.ALLOWED, policy.name, (), params, policy.priority)


def default_gate_plane_policies() -> PolicyTable:
    """Baseline table aligned with the Pack B gate plane route families.

    Open probes stay anonymous; every other route requires a service token
    with the family's scope, mutations need ``<family>:write``, and admin
    control routes are restricted to the control-plane service.
    """
    rows: List[RoutePolicy] = [
        RoutePolicy.build("health", "/health/**", methods=["GET", "HEAD"], allow_anonymous=True, priority=0),
        RoutePolicy.build("ready", "/ready", methods=["GET", "HEAD"], allow_anonymous=True, priority=0),
        RoutePolicy.build("api-health", "/api/v1/health/**", methods=["GET", "HEAD"], allow_anonymous=True, priority=0),
        RoutePolicy.build(
            "admin-control",
            "/api/v1/admin/**",
            scopes_all=["admin:control"],
            allow_services=["control-plane"],
            allow_overlap_keys=False,
            priority=0,
        ),
    ]
    for family, prio in (("forge", 1), ("gameforge", 1), ("swarm", 2), ("telemetry", 3)):
        rows.append(
            RoutePolicy.build(
                f"{family}-read", f"/api/v1/{family}/**", methods=["GET", "HEAD", "OPTIONS"],
                scopes_any=[f"{family}:read", f"{family}:write"], priority=prio,
            )
        )
        rows.append(
            RoutePolicy.build(
                f"{family}-write", f"/api/v1/{family}/**", methods=sorted(MUTATING_METHODS),
                scopes_all=[f"{family}:write"], priority=prio,
            )
        )
    return PolicyTable(rows)


__all__ = [
    "ALL_METHODS",
    "AuthzReason",
    "Effect",
    "MUTATING_METHODS",
    "PolicyDecision",
    "PolicyError",
    "PolicyTable",
    "Principal",
    "RoutePattern",
    "RoutePolicy",
    "default_gate_plane_policies",
    "evaluate_policy",
    "split_path",
]
