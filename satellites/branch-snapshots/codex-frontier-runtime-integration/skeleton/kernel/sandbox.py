"""Kernel capability sandbox — deny-by-default execution permits.

Every subsystem that touches the outside world (filesystem, network,
subprocess, secrets, the event bus itself) must hold a capability. The
sandbox is the single authority that grants, checks, and revokes them,
so the answer to "can module X do Y?" is always one lookup — never a
code-reading exercise.

Design:

- **Deny by default** — anything not explicitly granted is refused,
  with a typed :class:`CapabilityDenied` riding the error lattice.
- **Scoped grants** — a grant binds (holder, capability, scope); a
  network grant scoped to one host does not leak to others.
- **Auditable** — every grant, check, and revocation lands in an
  in-memory audit trail the observability plane can drain.

Zero dependencies, thread-safe enough for a single-process kernel
(dict ops under the GIL), trivially serialisable for persistence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .errors import KernelError, Severity


class Capability(str, Enum):
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    NET_EGRESS = "net.egress"
    NET_INGRESS = "net.ingress"
    SUBPROCESS = "subprocess"
    SECRET_READ = "secret.read"
    BUS_PUBLISH = "bus.publish"
    BUS_ADMIN = "bus.admin"
    REGISTRY_WRITE = "registry.write"
    CLOCK_SKIP = "clock.skip"


class CapabilityDenied(KernelError):
    code = "KRN.CAPABILITY"
    severity = Severity.WARNING
    http_status = 403


@dataclass(frozen=True)
class Grant:
    holder: str
    capability: Capability
    scope: str  # "*" or a concrete resource pattern, e.g. "host:api.example.com"
    granted_at: float
    expires_at: Optional[float] = None

    def expired(self, now: Optional[float] = None) -> bool:
        return self.expires_at is not None and (now or time.time()) >= self.expires_at

    def covers(self, scope: str) -> bool:
        if self.scope == "*":
            return True
        if self.scope.endswith("*"):
            return scope.startswith(self.scope[:-1])
        return self.scope == scope


@dataclass(frozen=True)
class AuditRecord:
    action: str  # "grant" | "revoke" | "check.ok" | "check.denied"
    holder: str
    capability: Capability
    scope: str
    timestamp: float
    detail: str = ""


@dataclass
class Sandbox:
    """The kernel's capability authority."""

    _grants: Dict[Tuple[str, Capability], List[Grant]] = field(default_factory=dict)
    _audit: List[AuditRecord] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Grant lifecycle
    # ------------------------------------------------------------------

    def grant(self, holder: str, capability: Capability,
              scope: str = "*", ttl_seconds: Optional[float] = None) -> Grant:
        now = time.time()
        grant = Grant(
            holder=holder,
            capability=capability,
            scope=scope,
            granted_at=now,
            expires_at=now + ttl_seconds if ttl_seconds else None,
        )
        key = (holder, capability)
        self._grants.setdefault(key, []).append(grant)
        self._log("grant", holder, capability, scope,
                  detail=f"ttl={ttl_seconds}s" if ttl_seconds else "permanent")
        return grant

    def revoke(self, holder: str, capability: Capability, scope: Optional[str] = None) -> int:
        """Revoke matching grants; returns how many were removed."""
        key = (holder, capability)
        existing = self._grants.get(key, [])
        kept = [g for g in existing if scope is not None and not g.covers(scope)]
        removed = len(existing) - len(kept)
        if kept:
            self._grants[key] = kept
        else:
            self._grants.pop(key, None)
        if removed:
            self._log("revoke", holder, capability, scope or "*",
                      detail=f"removed={removed}")
        return removed

    def revoke_all(self, holder: str) -> int:
        keys = [k for k in self._grants if k[0] == holder]
        count = sum(len(self._grants[k]) for k in keys)
        for k in keys:
            self._grants.pop(k, None)
        if count:
            self._log("revoke", holder, Capability.BUS_ADMIN, "*",
                      detail=f"revoke-all removed={count}")
        return count

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def can(self, holder: str, capability: Capability, scope: str = "*") -> bool:
        now = time.time()
        grants = self._grants.get((holder, capability), [])
        # Prune expired grants lazily.
        live = [g for g in grants if not g.expired(now)]
        if len(live) != len(grants):
            if live:
                self._grants[(holder, capability)] = live
            else:
                self._grants.pop((holder, capability), None)
        return any(g.covers(scope) for g in live)

    def require(self, holder: str, capability: Capability, scope: str = "*") -> None:
        if not self.can(holder, capability, scope):
            self._log("check.denied", holder, capability, scope)
            raise CapabilityDenied(
                f"{holder} lacks capability {capability.value} for scope {scope!r}",
                context={"holder": holder, "capability": capability.value, "scope": scope},
            )
        self._log("check.ok", holder, capability, scope)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def grants_for(self, holder: str) -> Tuple[Grant, ...]:
        out: List[Grant] = []
        for (h, _), grants in self._grants.items():
            if h == holder:
                out.extend(g for g in grants if not g.expired())
        return tuple(out)

    def holders(self) -> Set[str]:
        return {h for (h, _) in self._grants}

    def audit_trail(self, limit: Optional[int] = None) -> Tuple[AuditRecord, ...]:
        return tuple(self._audit[-limit:] if limit else self._audit)

    def _log(self, action: str, holder: str,
             capability: Capability, scope: str, detail: str = "") -> None:
        self._audit.append(AuditRecord(
            action=action, holder=holder, capability=capability,
            scope=scope, timestamp=time.time(), detail=detail,
        ))
