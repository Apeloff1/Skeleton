"""Presence join / heartbeat / leave over ``POST /api/v1/presence`` (ADR §1).

Heartbeat every 15 s; the server expires members after 45 s of silence and
broadcasts ``presence.left {reason: heartbeat_timeout}``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from .errors import RealtimeAuthError, RealtimeConnectError

PRESENCE_HEARTBEAT_SECONDS = 15.0
Poster = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class HttpPresencePoster:
    """POSTs presence bodies with fresh auth headers per call."""

    def __init__(self, base_url: str, *, client: Any = None, headers: Optional[Callable[[], Dict[str, str]]] = None, path: str = "/api/v1/presence") -> None:
        self.url = base_url.rstrip("/") + path
        self._client = client
        self._headers = headers or (lambda: {})

    async def __call__(self, body: Dict[str, Any]) -> Dict[str, Any]:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=10.0)
        try:
            response = await self._client.post(self.url, json=body, headers=self._headers())
        except Exception as exc:
            raise RealtimeConnectError(f"presence post failed: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise RealtimeAuthError("presence refused", status_code=response.status_code)
        if response.status_code >= 400:
            raise RealtimeConnectError("presence post failed", status_code=response.status_code)
        return response.json()


class PresenceClient:
    def __init__(
        self,
        poster: Poster,
        *,
        client_id: str,
        scope: str = "app",
        interval_s: float = PRESENCE_HEARTBEAT_SECONDS,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._post = poster
        self.client_id = client_id
        self.scope = scope
        self.interval_s = float(interval_s)
        self.meta = dict(meta or {})
        self.heartbeat_failures = 0
        self._task: Optional[asyncio.Task] = None
        self.last_snapshot: Optional[Dict[str, Any]] = None

    def _body(self, action: str) -> Dict[str, Any]:
        body: Dict[str, Any] = {"action": action, "client_id": self.client_id, "scope": self.scope}
        if action == "join" and self.meta:
            body["meta"] = self.meta
        return body

    async def join(self, *, heartbeat: bool = True) -> Dict[str, Any]:
        self.last_snapshot = await self._post(self._body("join"))
        if heartbeat and self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._beat())
        return self.last_snapshot

    async def heartbeat(self) -> Dict[str, Any]:
        self.last_snapshot = await self._post(self._body("heartbeat"))
        return self.last_snapshot

    async def _beat(self) -> None:
        while True:
            await asyncio.sleep(self.interval_s)
            try:
                await self.heartbeat()
            except RealtimeAuthError:
                return
            except Exception:
                self.heartbeat_failures += 1

    async def leave(self) -> Dict[str, Any]:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self.last_snapshot = await self._post(self._body("leave"))
        return self.last_snapshot


__all__ = ["HttpPresencePoster", "PRESENCE_HEARTBEAT_SECONDS", "PresenceClient"]
