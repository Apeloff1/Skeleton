"""Least-authority tool grants, signed by the caller's explicit choices.

A grant is a server-side object. Model output cannot create or modify grants.
Expiry is expressed in a caller-supplied monotonic domain for deterministic
acceptance testing, not in unverified wall-clock strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from .canonical import ContractViolation, require_digest
from .identity import require_id


@dataclass(frozen=True, slots=True)
class ToolGrant:
    tenant: str
    user: str
    session: str
    allowed_tools: frozenset[str]
    expires_monotonic_ns: int
    permit_write: bool = False

    def __post_init__(self) -> None:
        for key in ("tenant", "user", "session"):
            require_id(getattr(self, key), field=key)
        if not isinstance(self.allowed_tools, frozenset) or not self.allowed_tools:
            raise ContractViolation("empty or mutable tool grant")
        for name in self.allowed_tools:
            require_id(name, field="tool name")
        if type(self.expires_monotonic_ns) is not int or self.expires_monotonic_ns <= 0:
            raise ContractViolation("invalid grant expiry")
        if type(self.permit_write) is not bool:
            raise ContractViolation("invalid write authority")

    def check(self, *, tenant: str, user: str, session: str, tool: str,
              now_monotonic_ns: int, write: bool) -> None:
        if any((tenant != self.tenant, user != self.user, session != self.session)):
            raise ContractViolation("cross-principal or cross-session tool access")
        require_id(tool, field="tool")
        if type(now_monotonic_ns) is not int or now_monotonic_ns >= self.expires_monotonic_ns:
            raise ContractViolation("tool grant expired")
        if tool not in self.allowed_tools or (write and not self.permit_write):
            raise ContractViolation("tool authority not granted")

    def attenuate(self, names: Iterable[str], *, expiry_ns: int | None = None,
                  allow_write: bool = False) -> "ToolGrant":
        chosen = frozenset(names)
        if (not chosen or not chosen.issubset(self.allowed_tools)
                or (expiry_ns is not None and (type(expiry_ns) is not int
                    or expiry_ns > self.expires_monotonic_ns))):
            raise ContractViolation("grant attenuation attempted escalation")
        if allow_write and not self.permit_write:
            raise ContractViolation("grant cannot escalate write authority")
        return ToolGrant(self.tenant, self.user, self.session, chosen,
                         self.expires_monotonic_ns if expiry_ns is None else expiry_ns,
                         allow_write)
