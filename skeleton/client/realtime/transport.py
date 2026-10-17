"""Realtime transports for the SDK. SSE is the only canonical wire (ADR §1).

* :class:`SSETransport` - ``GET /api/v1/events`` over ``httpx`` streaming,
  ``Last-Event-ID`` resume, ``: hb`` liveness, ``retry:`` floor.
* :class:`InProcessTransport` - same frames straight from a local
  :class:`~skeleton.realtime.RealtimeHub` (embedded app, tests).

Streams yield envelope/control frames, or :data:`HEARTBEAT` whenever bytes
arrived without a complete frame (``: hb`` comments, partial chunks): any
byte counts as liveness for the 45 s dead-stream rule.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict, Optional, Protocol, Sequence, Union

from skeleton.realtime.envelope import ControlEvent, EnvelopeError, RealtimeEvent
from skeleton.realtime.sse import SSE_MEDIA_TYPE, SSEParser, iter_frames, sse_message_to_frame

from .errors import RealtimeAuthError, RealtimeConnectError, RealtimeProtocolError


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
        self.retry_ms: Optional[int] = None

    async def __aiter__(self) -> AsyncIterator[StreamItem]:
        async for chunk in self._response.aiter_text():
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

    async def aclose(self) -> None:
        try:
            await self._ctx.__aexit__(None, None, None)
        except Exception:
            pass


class SSETransport:
    """``httpx``-based SSE transport.

    ``headers`` is called on every (re)connect so short-lived ``x-gf-seal``
    values can be minted per attempt; it is never logged.
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.path = path
        self._client = client
        self._owns_client = client is None
        self._headers = headers or (lambda: {})
        self._timeout_s = timeout_s

    def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_s, read=None))
        return self._client

    async def open(self, *, channels: Sequence[str], job_id: Optional[str], cursor: Optional[str]) -> RealtimeStream:
        params: Dict[str, str] = {"channels": ",".join(channels)}
        if job_id:
            params["job_id"] = job_id
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
        if status in (401, 403):
            await ctx.__aexit__(None, None, None)
            raise RealtimeAuthError(f"stream refused with {status}", status_code=status)
        content_type = response.headers.get("content-type", "")
        if status >= 400 or SSE_MEDIA_TYPE not in content_type:
            await ctx.__aexit__(None, None, None)
            raise RealtimeConnectError(f"stream open failed with {status}", status_code=status)
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
    "HEARTBEAT",
    "InProcessTransport",
    "RealtimeStream",
    "RealtimeTransport",
    "SSETransport",
    "StreamItem",
]
