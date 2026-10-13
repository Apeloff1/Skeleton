"""Validation helpers for a remote MCP transport adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from skeleton.shells.ai.mcp import MCPRequestEnvelope


@dataclass(frozen=True)
class MCPTransportPolicy:
    max_headers: int = 64
    max_header_name_bytes: int = 128
    max_header_value_bytes: int = 4096
    require_routing_headers: bool = True

    def __post_init__(self) -> None:
        if self.max_headers <= 0:
            raise ValueError("max_headers must be positive")
        if self.max_header_name_bytes <= 0 or self.max_header_value_bytes <= 0:
            raise ValueError("MCP header byte limits must be positive")


@dataclass(frozen=True)
class MCPTransportDecision:
    allowed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reasons": list(self.reasons)}


class MCPTransportValidator:
    def __init__(self, policy: MCPTransportPolicy | None = None) -> None:
        self.policy = policy or MCPTransportPolicy()

    @staticmethod
    def _lower(headers: Mapping[str, str]) -> dict[str, str]:
        return {str(key).lower(): str(value) for key, value in headers.items()}

    def inspect(
        self,
        request: MCPRequestEnvelope,
        headers: Mapping[str, str],
    ) -> MCPTransportDecision:
        reasons = []
        if len(headers) > self.policy.max_headers:
            reasons.append("MCP request has too many headers")
        for name, value in headers.items():
            if len(str(name).encode()) > self.policy.max_header_name_bytes:
                reasons.append("MCP header name exceeds byte limit")
                break
            if len(str(value).encode()) > self.policy.max_header_value_bytes:
                reasons.append("MCP header value exceeds byte limit")
                break
        normalized = self._lower(headers)
        method = normalized.get("mcp-method")
        name = normalized.get("mcp-name")
        if self.policy.require_routing_headers:
            if method is None:
                reasons.append("Mcp-Method header is required")
            if request.name and name is None:
                reasons.append("Mcp-Name header is required")
        if method is not None and method != request.method:
            reasons.append("Mcp-Method header/body mismatch")
        if request.name and name is not None and name != request.name:
            reasons.append("Mcp-Name header/body mismatch")
        return MCPTransportDecision(not reasons, tuple(reasons))

    def require(
        self,
        request: MCPRequestEnvelope,
        headers: Mapping[str, str],
    ) -> MCPTransportDecision:
        decision = self.inspect(request, headers)
        if not decision.allowed:
            raise ValueError("; ".join(decision.reasons))
        return decision
