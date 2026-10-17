"""Services / command-plane client."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.client.gateway import GatewayClient


class ServicesClient:
    """Typed client for command contracts and execution."""

    def __init__(self, gateway: GatewayClient) -> None:
        self._gw = gateway

    def contracts(self) -> Any:
        return self._gw._json("GET", "/api/v1/commands/contracts", idempotent=True)

    def execute(self, command: str, body: Mapping[str, Any] | None = None) -> Any:
        return self._gw._json(
            "POST",
            f"/api/v1/commands/execute/{command}",
            json=dict(body or {}),
        )

    def invoke(self, body: Mapping[str, Any]) -> Any:
        return self._gw._json("POST", "/api/v1/commands/invoke", json=dict(body))
