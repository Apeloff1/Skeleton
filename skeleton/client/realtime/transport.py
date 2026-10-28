"""Realtime transports for the SDK. SSE is the only canonical wire (ADR §1).

* :class:`SSETransport` - ``GET /api/v1/events`` over ``httpx`` streaming,
  ``Last-Event-ID`` + ``?cursor=`` resume, ``: hb`` liveness, ``retry:``
  floor, typed errors carrying the server's JSON ``error`` code.
* :class:`InProcessTransport` - same frames straight from a local
  :class:`~skeleton.realtime.RealtimeHub` (embedded app, tests).

Streams yield envelope/control frames, or :data:`HEARTBEAT` whenever bytes
arrived without a complete frame (``: hb`` comments, partial chunks): any
byte counts as liveness for the 45 s dead-stream rule.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Callable, Dict, Optional, Protocol, Sequence, Union

from skeleton.realtime.envelope import ControlEvent, EnvelopeError, RealtimeEvent
from skeleton.realtime.sse import SSE_MEDIA_TYPE, SSEParser, iter_frames, sse_message_to_frame

from .errors import (
    SEAL_UNAVAILABLE,
    RealtimeAuthError,
    RealtimeConnectError,
    RealtimeError,
    RealtimeProtocolError,
    RealtimeSealUnavailable,
)

#: Upper bound on bytes read from an error response body.
ERROR_BODY_LIMIT = 4096
# Server error codes are short snake_case identifiers; anything else (free
# text, echoed values, token-shaped strings) is dropped so it can never reach
# an exception message.
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class _Heartbeat:
    __slots__ = ()

    def __repr__(self) -> str:
        return "HEARTBEAT"


HEARTBEAT = _Heartbeat()
StreamItem = Union[RealtimeEvent, ControlEvent, _Heartbeat]
HeaderProvider = Callable[[], Dict[str, str]]


class RealtimeStream(Protocol):
    retry_ms: Optional[int]

    def __aiter__(self) -> AsyncIterator[StreamItem]: ...

    async def aclose(self) -> None: ...


class RealtimeTransport(Protocol):
    name: str

    async def open(self, *, channels: Sequence[str], job_id: Optional[str], cursor: Optional[str]) -> RealtimeStream: ...


class _SSEStream:
    def __init__(self, ctx: Any, response: Any) -> None:
        self._ctx = ctx
        self._response = response
        self._parser = SSEParser()
        self._chunks: Any = None
        self._closed = False
        self.retry_ms: Optional[int] = None

    async def __aiter__(self) -> AsyncIterator[StreamItem]:
        if self._chunks is None:
            self._chunks = self._response.aiter_text()
        try:
            async for chunk in self._chunks:
                produced = False
                for msg in self._parser.feed(chunk):
                    try:
                        frame = sse_message_to_frame(msg)
                    except (EnvelopeError, ValueError) as exc:
                        raise RealtimeProtocolError(str(exc)) from exc
                    if frame is not None:
                        produced = True
                        yield frame
                if self._parser.retry_ms is not None:
                    self.retry_ms = self._parser.retry_ms
                if not produced:
                    yield HEARTBEAT
        finally:
            await self._close_chunks()

    async def _close_chunks(self) -> None:
        chunks, self._chunks = self._chunks, None
        closer = getattr(chunks, "aclose", None)
        if closer is None:
            return
        try:
            await closer()
        except Exception:
            pass

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._close_chunks()
        try:
            await self._ctx.__aexit__(None, None, None)
        except Exception:
            pass


def _error_code_from_body(raw: bytes) -> Optional[str]:
    """Extract the gate/route error code from a JSON error body.

    Accepts the middleware shape ``{"error": code}`` and the FastAPI
    ``HTTPException`` shape ``{"detail": {"error": code, ...}}`` (or a bare
    ``{"detail": code}``). Returns only a validated identifier, never free text.
    """
    try:
        body = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    code = body.get("error")
    if code is None:
        detail = body.get("detail")
        code = detail.get("error") if isinstance(detail, dict) else detail
    if isinstance(code, str) and _ERROR_CODE_RE.match(code):
        return code
    return None


async def _read_error_body(response: Any, limit: int = ERROR_BODY_LIMIT) -> bytes:
    buf = bytearray()
    parts = response.aiter_bytes()
    try:
        async for part in parts:
            buf.extend(part)
            if len(buf) >= limit:
                break
    except Exception:
        pass
    finally:
        closer = getattr(parts, "aclose", None)
        if closer is not None:
            try:
                await closer()
            except Exception:
                pass
    return bytes(buf[:limit])


def error_for_status(status: int, error_code: Optional[str]) -> RealtimeError:
    """Map an HTTP error status + parsed code to the typed realtime error."""
    label = f"{status} ({error_code})" if error_code else str(status)
    if error_code == SEAL_UNAVAILABLE:
        return RealtimeSealUnavailable(f"stream refused with {label}", status_code=status)
    if status in (401, 403):
        return RealtimeAuthError(f"stream refused with {label}", status_code=status, error_code=error_code)
    return RealtimeConnectError(f"stream open failed with {label}", status_code=status, error_code=error_code)


class SSETransport:
    """``httpx``-based SSE transport.

    ``headers`` is called on every (re)connect so short-lived ``x-gf-seal``
    values can be minted per attempt; it is never logged.

    On reconnect the cursor is sent both as ``Last-Event-ID`` and as
    ``?cursor=`` (the server prefers the header; both carry the same value).
    Error statuses raise :class:`RealtimeAuthError` (401/403),
    :class:`RealtimeSealUnavailable` (``seal_unavailable``, never retried) or
    :class:`RealtimeConnectError`, each with ``status_code``/``error_code``
    parsed from at most :data:`ERROR_BODY_LIMIT` bytes of the JSON body.
    """

    name = "sse"

    def __init__(
        self,
        base_url: str,
        *,
        client: Any = None,
        headers: Optional[HeaderProvider] = None,
        path: str = "/api/v1/events",
        timeout_s: float = 10.0,
        actor_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.path = path
        self._client = client
        self._owns_client = client is None
        self._headers = headers or (lambda: {})
        self._timeout_s = timeout_s
        # Job-scoped subscriptions need engine actor+tenant authorization.
        # Query parameters are composed by httpx (not embedded in ``path``:
        # passing ``params=`` would discard a pre-existing path query string).
        if (actor_id is None) != (tenant_id is None):
            raise ValueError("actor_id and tenant_id must be supplied together")
        for value in (actor_id, tenant_id):
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 512):
                raise ValueError("invalid actor/tenant scope")
        self._actor_id = actor_id
        self._tenant_id = tenant_id

    def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_s, read=None))
        return self._client

    async def open(self, *, channels: Sequence[str], job_id: Optional[str], cursor: Optional[str]) -> RealtimeStream:
        params: Dict[str, str] = {"channels": ",".join(channels)}
        if job_id:
            params["job_id"] = job_id
            if self._actor_id is not None and self._tenant_id is not None:
                params["actor_id"] = self._actor_id
                params["tenant_id"] = self._tenant_id
        if cursor:
            params["cursor"] = cursor
        headers = {"accept": SSE_MEDIA_TYPE, "cache-control": "no-cache"}
        headers.update(self._headers())
        if cursor:
            headers["last-event-id"] = cursor
        ctx = self._http().stream("GET", self.base_url + self.path, params=params, headers=headers)
        try:
            response = await ctx.__aenter__()
        except Exception as exc:
            raise RealtimeConnectError(f"connect failed: {type(exc).__name__}") from exc
        status = response.status_code
        if status >= 400:
            try:
                error_code = _error_code_from_body(await _read_error_body(response))
                if error_code and any(error_code in str(value) for value in headers.values()):
                    error_code = None  # never echo anything we sent (seals, tokens)
            finally:
                await ctx.__aexit__(None, None, None)
            raise error_for_status(status, error_code)
        content_type = response.headers.get("content-type", "")
        if SSE_MEDIA_TYPE not in content_type:
            await ctx.__aexit__(None, None, None)
            raise RealtimeConnectError(f"stream open failed with {status} (not {SSE_MEDIA_TYPE})", status_code=status)
        return _SSEStream(ctx, response)

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None


class _HubStream:
    def __init__(self, hub: Any, sub: Any) -> None:
        self._hub = hub
        self._sub = sub
        self.retry_ms: Optional[int] = None
        self._gen = iter_frames(hub, sub)

    async def __aiter__(self) -> AsyncIterator[StreamItem]:
        async for frame in self._gen:
            yield HEARTBEAT if frame is None else frame

    async def aclose(self) -> None:
        await self._gen.aclose()
        self._hub.unsubscribe(self._sub)


class InProcessTransport:
    """Consume a local hub with the exact semantics of the SSE endpoint."""

    name = "inprocess"

    def __init__(self, hub: Any, *, principal: str) -> None:
        self.hub = hub
        self.principal = principal

    async def open(self, *, channels: Sequence[str], job_id: Optional[str], cursor: Optional[str]) -> RealtimeStream:
        from skeleton.realtime.envelope import parse_cursor
        from skeleton.realtime.hub import RealtimeAuthError as HubAuthError

        try:
            sub = self.hub.subscribe(channels, principal=self.principal, cursor=parse_cursor(cursor), job_id=job_id)
        except HubAuthError as exc:
            raise RealtimeAuthError(str(exc)) from exc
        except RuntimeError as exc:
            raise RealtimeConnectError(str(exc)) from exc
        return _HubStream(self.hub, sub)


__all__ = [
    "ERROR_BODY_LIMIT",
    "HEARTBEAT",
    "InProcessTransport",
    "RealtimeStream",
    "RealtimeTransport",
    "SSETransport",
    "StreamItem",
    "error_for_status",
]
