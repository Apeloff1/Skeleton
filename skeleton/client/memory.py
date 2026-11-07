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

    def query_unified(
        self, query: str, *, top_k: int | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """Convenience wrapper around ``query``.

        The server reads ``top_k`` (per-tier result count, default 3).
        ``limit`` is kept as a backwards-compatible alias for ``top_k``.
        """
        if top_k is not None and limit is not None and top_k != limit:
            raise ValueError("pass top_k or limit, not both")
        k = top_k if top_k is not None else limit
        body: dict[str, Any] = {"query": query}
        if k is not None:
            body["top_k"] = k
        return self.query(body)
