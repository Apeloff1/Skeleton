"""Scope and role based auth on top of the Bearer middleware.

`BearerAuth` verifies that a token is genuine; this module decides
typher bearer may do. Scopes and roles ride inside the token payload
(`scopes: ["read", "write"]`, `roles: ["admin"]`), and dependencies
raise before the route handler ever runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, Optional, Tuple

from skeleton.api.middleware import AuthError, BearerAuth


@dataclass
class AuthContext:
    subject: str
    scopes: FrozenSet[str] = field(default_factory=frozenset)
    roles: FrozenSet[str] = field(default_factory=frozenset)
    claims: Dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def has_role(self, role: str) -> bool:
        return role in self.roles


def scope_dependency(bearer: BearerAuth, *required: str):
    """Factory: dependency that requires every scope to be present."""

    def check(authorization: Optional[str] = None) -> AuthContext:
        claims = bearer(authorization)
        ctx = AuthContext(
            subject=str(claims.get("sub", "")),
            scopes=frozenset(claims.get("scopes", []) or []),
            roles=frozenset(claims.get("roles", []) or []),
            claims=claims,
        )
        missing = [s for s in required if s not in ctx.scopes]
        if missing:
            raise AuthError("missing scopes", context={"missing": missing})
        return ctx

    return check


def role_dependency(bearer: BearerAuth, *required: str):
    """Factory: dependency that requires at least one listed role."""

    def check(authorization: Optional[str] = None) -> AuthContext:
        claims = bearer(authorization)
        ctx = AuthContext(
            subject=str(claims.get("sub", "")),
            scopes=frozenset(claims.get("scopes", []) or []),
            roles=frozenset(claims.get("roles", []) or []),
            claims=claims,
        )
        if not any(r in ctx.roles for r in required):
            raise AuthError("insufficient role", context={"required": list(required)})
        return ctx

    return check
