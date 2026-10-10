"""Memory API client (unified query + Δ-Memory-facing surfaces)."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.client.gateway import GatewayClient


class MemoryClient:
    """Typed client for memory HTTP routes under ``/api/v1``."""

    def __init__(self, gateway: GatewayClient) -> None:
        self._gw = gateway

    def query(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """POST /api/v1/memory/query — unified Memory Trinity query."""
        return self._gw._json("POST", "/api/v1/memory/query", json=dict(body))

    def query_unified(self, query: str, *, limit: int = 10) -> dict[str, Any]:
        """Convenience wrapper around ``query``."""
        return self.query({"query": query, "limit": limit})
