"""Service identity registry for the s2s plane.

Each calling service is registered with:

* ``scope_ceiling`` - the most a token from this service may ever carry.
  Scopes outside the ceiling are *stripped* before route authz runs, so an
  over-scoped token can never widen access (the route then answers 403
  ``missing_scope`` through the existing :mod:`authz` table).
* ``audiences`` - which target services it may address (empty = any).
* ``cert_fingerprints`` - optional mTLS-style binding: SHA-256 fingerprints
  of client certificates allowed to present this service's tokens
  (see :mod:`skeleton.gate_plane.s2s.binding`).
* ``enabled`` - a disabled service is rejected at verification (401).

The registry is a pure in-process table loadable from plain dicts so it can
be fed from config without pulling secrets into the repo: identities never
hold key material.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional

from skeleton.gate_plane.s2s.tokens import scope_granted, validate_scope, validate_service_name

_FP_RE = re.compile(r"^[0-9a-f]{64}$")


class RegistryError(ValueError):
    """Invalid registry operation or identity definition."""


def normalize_fingerprint(fp: str) -> str:
    """Lower-case hex SHA-256, accepting ``AA:BB:..`` colon form."""
    if not isinstance(fp, str):
        raise RegistryError("fingerprint must be a string")
    norm = fp.replace(":", "").strip().lower()
    if not _FP_RE.match(norm):
        raise RegistryError(f"fingerprint must be 64 hex chars, got {fp!r}")
    return norm


def cert_fingerprint(der: bytes) -> str:
    """SHA-256 fingerprint of a DER-encoded certificate."""
    return hashlib.sha256(der).hexdigest()


@dataclass(frozen=True)
class ServiceIdentity:
    service: str
    scope_ceiling: FrozenSet[str] = frozenset()
    audiences: FrozenSet[str] = frozenset()
    cert_fingerprints: FrozenSet[str] = frozenset()
    enabled: bool = True
    owner: str = ""
    description: str = ""

    @classmethod
    def build(
        cls,
        service: str,
        *,
        scopes: Iterable[str] = (),
        audiences: Iterable[str] = (),
        cert_fingerprints: Iterable[str] = (),
        enabled: bool = True,
        owner: str = "",
        description: str = "",
    ) -> "ServiceIdentity":
        try:
            name = validate_service_name(service)
            ceiling = frozenset(validate_scope(s) for s in scopes)
            auds = frozenset(validate_service_name(a) for a in audiences)
        except ValueError as exc:
            raise RegistryError(str(exc)) from exc
        fps = frozenset(normalize_fingerprint(f) for f in cert_fingerprints)
        if type(enabled) is not bool:
            raise RegistryError("enabled must be a boolean")
        return cls(name, ceiling, auds, fps, enabled, str(owner), str(description))

    @property
    def requires_binding(self) -> bool:
        return bool(self.cert_fingerprints)

    def may_address(self, audience: str) -> bool:
        return not self.audiences or audience in self.audiences

    def permits_scope(self, scope: str) -> bool:
        return scope_granted(self.scope_ceiling, scope)

    def clamp_scopes(self, requested: Iterable[str]) -> FrozenSet[str]:
        """Scopes from ``requested`` that the ceiling allows."""
        # A requested wildcard ``a:*`` survives only if the ceiling itself grants
        # ``a:*`` (or a broader wildcard); exact scopes never widen into wildcards.
        return frozenset(s for s in requested if self.permits_scope(s))

    def excess_scopes(self, requested: Iterable[str]) -> FrozenSet[str]:
        req = frozenset(requested)
        return req - self.clamp_scopes(req)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "scopes": sorted(self.scope_ceiling),
            "audiences": sorted(self.audiences),
            "cert_fingerprints": sorted(self.cert_fingerprints),
            "enabled": self.enabled,
            "owner": self.owner,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ServiceIdentity":
        if "service" not in data:
            raise RegistryError("identity requires 'service'")
        unknown = set(data) - {"service", "scopes", "audiences", "cert_fingerprints", "enabled", "owner", "description"}
        if unknown:
            raise RegistryError(f"unknown identity fields: {sorted(unknown)}")
        return cls.build(
            data["service"],
            scopes=data.get("scopes", ()),
            audiences=data.get("audiences", ()),
            cert_fingerprints=data.get("cert_fingerprints", ()),
            enabled=data.get("enabled", True),
            owner=data.get("owner", ""),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class RegistryEvent:
    action: str
    service: str
    detail: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {"action": self.action, "service": self.service, "detail": self.detail}


class ServiceRegistry:
    """Thread-safe service name -> :class:`ServiceIdentity` table."""

    def __init__(self, identities: Iterable[ServiceIdentity] = (), *, strict: bool = True) -> None:
        if type(strict) is not bool:
            raise RegistryError("strict must be a boolean")
        self.strict = strict  # unknown callers rejected when True
        self._ids: Dict[str, ServiceIdentity] = {}
        self._events: List[RegistryEvent] = []
        self._listeners: List[Any] = []
        self._lock = threading.RLock()
        for ident in identities:
            self.register(ident)

    def add_listener(self, fn: Any) -> None:
        self._listeners.append(fn)

    def _log(self, action: str, service: str, detail: str = "") -> None:
        ev = RegistryEvent(action, service, detail)
        self._events.append(ev)
        if len(self._events) > 1024:
            del self._events[: len(self._events) - 1024]
        for fn in list(self._listeners):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001 - listeners never break the registry
                pass

    def register(self, identity: ServiceIdentity, *, replace_existing: bool = False) -> ServiceIdentity:
        if not isinstance(identity, ServiceIdentity):
            raise RegistryError("identity must be a ServiceIdentity")
        with self._lock:
            if identity.service in self._ids and not replace_existing:
                raise RegistryError(f"service {identity.service!r} already registered")
            self._ids[identity.service] = identity
            self._log("register" if not replace_existing else "replace", identity.service)
            return identity

    def unregister(self, service: str) -> None:
        with self._lock:
            if self._ids.pop(service, None) is None:
                raise RegistryError(f"unknown service {service!r}")
            self._log("unregister", service)

    def _update(self, service: str, action: str, **changes: Any) -> ServiceIdentity:
        with self._lock:
            cur = self._ids.get(service)
            if cur is None:
                raise RegistryError(f"unknown service {service!r}")
            new = replace(cur, **changes)
            self._ids[service] = new
            self._log(action, service, json.dumps({k: sorted(v) if isinstance(v, frozenset) else v for k, v in changes.items()}, sort_keys=True))
            return new

    def disable(self, service: str, *, reason: str = "") -> ServiceIdentity:
        ident = self._update(service, "disable", enabled=False)
        if reason:
            self._log("disable_reason", service, reason)
        return ident

    def enable(self, service: str) -> ServiceIdentity:
        return self._update(service, "enable", enabled=True)

    def set_scopes(self, service: str, scopes: Iterable[str]) -> ServiceIdentity:
        try:
            ceiling = frozenset(validate_scope(s) for s in scopes)
        except ValueError as exc:
            raise RegistryError(str(exc)) from exc
        return self._update(service, "set_scopes", scope_ceiling=ceiling)

    def bind_certs(self, service: str, fingerprints: Iterable[str]) -> ServiceIdentity:
        fps = frozenset(normalize_fingerprint(f) for f in fingerprints)
        return self._update(service, "bind_certs", cert_fingerprints=fps)

    def get(self, service: str) -> Optional[ServiceIdentity]:
        with self._lock:
            return self._ids.get(service)

    def require(self, service: str) -> ServiceIdentity:
        ident = self.get(service)
        if ident is None:
            raise RegistryError(f"unknown service {service!r}")
        return ident

    def services(self) -> List[str]:
        with self._lock:
            return sorted(self._ids)

    def events(self) -> List[RegistryEvent]:
        with self._lock:
            return list(self._events)

    def __contains__(self, service: object) -> bool:
        with self._lock:
            return service in self._ids

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)

    def to_dicts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._ids[s].to_dict() for s in sorted(self._ids)]

    @classmethod
    def from_dicts(cls, rows: Iterable[Mapping[str, Any]], *, strict: bool = True) -> "ServiceRegistry":
        return cls((ServiceIdentity.from_dict(r) for r in rows), strict=strict)

    def digest(self) -> str:
        """Stable digest of the registry contents (for evidence / drift checks)."""
        blob = json.dumps(self.to_dicts(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


__all__ = [
    "RegistryError",
    "RegistryEvent",
    "ServiceIdentity",
    "ServiceRegistry",
    "cert_fingerprint",
    "normalize_fingerprint",
]
