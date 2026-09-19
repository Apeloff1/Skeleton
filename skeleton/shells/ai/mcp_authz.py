"""Authorization policy for stateless MCP-style shell tool requests."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class MCPPrincipalPolicy:
    principal: str
    allowed_tools: frozenset[str] = frozenset()
    denied_tools: frozenset[str] = frozenset()
    max_timeout_seconds: float = 60.0
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.principal or len(self.principal) > 256:
            raise ValueError("invalid MCP principal")
        allowed = frozenset(self.allowed_tools)
        denied = frozenset(self.denied_tools)
        if allowed & denied:
            raise ValueError("MCP tool cannot be both allowed and denied")
        if self.max_timeout_seconds <= 0:
            raise ValueError("MCP max timeout must be positive")
        metadata = dict(self.metadata)
        object.__setattr__(self, "allowed_tools", allowed)
        object.__setattr__(self, "denied_tools", denied)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def allows(self, tool: str) -> bool:
        if tool in self.denied_tools:
            return False
        return not self.allowed_tools or tool in self.allowed_tools


@dataclass(frozen=True)
class MCPAuthorizationDecision:
    allowed: bool
    reason: str
    principal: str
    tool: str

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "principal": self.principal,
            "tool": self.tool,
        }


class MCPAuthorization:
    def __init__(self, *, max_principals: int = 10000) -> None:
        if max_principals <= 0:
            raise ValueError("max_principals must be positive")
        self.max_principals = max_principals
        self._items: dict[str, MCPPrincipalPolicy] = {}
        self._lock = threading.RLock()

    def set(self, policy: MCPPrincipalPolicy) -> None:
        with self._lock:
            if policy.principal not in self._items and len(self._items) >= self.max_principals:
                raise RuntimeError("MCP authorization capacity exhausted")
            self._items[policy.principal] = policy

    def remove(self, principal: str) -> bool:
        with self._lock:
            return self._items.pop(principal, None) is not None

    def inspect(
        self,
        principal: str,
        tool: str,
        *,
        timeout_seconds: float | None = None,
    ) -> MCPAuthorizationDecision:
        with self._lock:
            policy = self._items.get(principal)
        if policy is None:
            return MCPAuthorizationDecision(
                False,
                "principal has no MCP shell authorization policy",
                principal,
                tool,
            )
        if not policy.allows(tool):
            return MCPAuthorizationDecision(
                False,
                "tool is not authorized for principal",
                principal,
                tool,
            )
        if timeout_seconds is not None and timeout_seconds > policy.max_timeout_seconds:
            return MCPAuthorizationDecision(
                False,
                "requested timeout exceeds principal MCP policy",
                principal,
                tool,
            )
        return MCPAuthorizationDecision(True, "", principal, tool)

    def require(
        self,
        principal: str,
        tool: str,
        *,
        timeout_seconds: float | None = None,
    ) -> MCPAuthorizationDecision:
        decision = self.inspect(
            principal,
            tool,
            timeout_seconds=timeout_seconds,
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return decision
