"""Auth client: GitHub OAuth handshake + token/authz audit surfaces.

Backend: ``skeleton/api/routes.py`` (mounted at ``/api/v1``).
"""

from __future__ import annotations

from typing import Any, TypedDict
from urllib.parse import quote

from skeleton.client.gateway import GatewayClient

SDK_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/auth/github"),
    ("GET", "/api/v1/auth/github/start"),
    ("GET", "/api/v1/auth/github/callback"),
    ("GET", "/api/v1/application/tokens/audit"),
    ("GET", "/api/v1/application/tokens/audit/{token_id}"),
    ("GET", "/api/v1/application/authz/audit"),
    ("GET", "/api/v1/application/authz/audit/{command_id}"),
)


class GitHubCallbackResult(TypedDict, total=False):
    """Callback payload; ``access_token`` is stripped server-side."""

    state: str


class AuthClient:
    """Typed client for auth routes under ``/api/v1``."""

    def __init__(self, gateway: GatewayClient) -> None:
        self._gw = gateway

    def github_oauth_card(self) -> dict[str, Any]:
        """GET /api/v1/auth/github — strings for the GitHub OAuth App form."""
        return self._gw._json("GET", "/api/v1/auth/github", idempotent=True)

    def github_start(self) -> dict[str, Any]:
        """GET /api/v1/auth/github/start — authorize URL (503 if unconfigured)."""
        return self._gw._json("GET", "/api/v1/auth/github/start", idempotent=True)

    def github_callback(self, code: str, state: str = "") -> GitHubCallbackResult:
        """GET /api/v1/auth/github/callback — exchange code (not retried)."""
        if not code:
            raise ValueError("code is required")
        return self._gw._json(
            "GET",
            "/api/v1/auth/github/callback",
            params={"code": code, "state": state},
            idempotent=False,  # OAuth codes are single-use
        )

    def tokens_audit(self) -> dict[str, Any]:
        return self._gw._json("GET", "/api/v1/application/tokens/audit", idempotent=True)

    def token_audit(self, token_id: str) -> dict[str, Any]:
        return self._gw._json(
            "GET",
            f"/api/v1/application/tokens/audit/{quote(token_id, safe='')}",
            idempotent=True,
        )

    def authz_audit(self) -> dict[str, Any]:
        return self._gw._json("GET", "/api/v1/application/authz/audit", idempotent=True)

    def authz_audit_row(self, command_id: str) -> dict[str, Any]:
        return self._gw._json(
            "GET",
            f"/api/v1/application/authz/audit/{quote(command_id, safe='')}",
            idempotent=True,
        )
