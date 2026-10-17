"""Canonical realtime stream (``GET /api/v1/events``) wired through #4128's SDK client.

``skeleton.client.realtime`` (owned by Walt, #4128) is the only SSE
implementation used here: :class:`~skeleton.client.realtime.RealtimeClient`
over :class:`~skeleton.client.realtime.SSETransport` supplies Last-Event-ID
resume, de-duplication, ``stream.lagged`` reconnect, ``stream.reset`` cursor
moves, 45 s dead-stream detection and full-jitter reconnect backoff. This
module only bridges that async client into the synchronous SDK style:

* frames become :class:`~skeleton.client.streaming.StreamEvent` (control
  events included, so callers still see ``stream.reset`` / ``stream.lagged``);
* a :class:`~skeleton.client.cancel.CancelToken` is checked between events and
  while waiting, and stops the background stream promptly;
* seal: the realtime routes are the ``realtime`` gate domain, verified by the
  same ``RequestSealMiddleware`` / ``verify_seal`` as every other written route,
  so the gateway's ``x-gf-seal`` (plus one ``x-request-id``) is minted per
  (re)connect. A 401 re-mints once and resumes from the last delivered id; a
  second 401, or any 403, raises :class:`~skeleton.client.realtime.RealtimeAuthError`.

Server-side filtering: ``?job_id=`` restricts build/agent envelopes to that
job (``Subscription.wants`` in ``skeleton/realtime/hub.py``); presence events
are never job-filtered, so they are only present when ``presence`` is asked for.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from skeleton.client.cancel import CancelToken
from skeleton.client.gateway import GatewayClient
from skeleton.client.realtime import RealtimeAuthError, RealtimeClient, SSETransport
from skeleton.client.streaming import StreamEvent

EVENTS_PATH = "/api/v1/events"
EVENTS_SLO_PATH = "/api/v1/events/slo"
PRESENCE_PATH = "/api/v1/presence"

# Routes the SDK hits on the realtime surface (#4128 ``realtime_routes.router``,
# mounted at /api/v1). POST /presence is called by ``realtime.PresenceClient``.
SDK_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", EVENTS_PATH),
    ("GET", EVENTS_SLO_PATH),
    ("POST", PRESENCE_PATH),
)

BUILD_CHANNELS: tuple[str, ...] = ("build", "agent")

_POLL_SECONDS = 0.1
_FRAME, _ERROR, _END = "frame", "error", "end"


def frame_to_event(frame: Any) -> StreamEvent:
    """``RealtimeEvent`` / ``ControlEvent`` -> :class:`StreamEvent` (raw = v1 dict)."""
    raw = frame.to_dict() if hasattr(frame, "to_dict") else frame
    return StreamEvent.from_obj(
        raw, sse_event=getattr(frame, "type", None), sse_id=getattr(frame, "id", None)
    )


def _resume_point(last_event_id: str | None, cursor: str | None) -> str | None:
    if last_event_id is not None and cursor is not None and str(last_event_id) != str(cursor):
        raise ValueError("pass last_event_id or cursor, not two different resume points")
    point = last_event_id if last_event_id is not None else cursor
    return None if point is None else str(point)


class _Pump:
    """Runs one ``RealtimeClient.frames()`` on a private event loop thread."""

    def __init__(self, client: RealtimeClient, transport: Any, *, owns_transport: bool) -> None:
        self.client = client
        self.transport = transport
        self.owns_transport = owns_transport
        self.queue: queue.Queue = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="skeleton-realtime", daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            self._task = loop.create_task(self._pump())
            self._ready.set()
            loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        finally:
            self._ready.set()
            if self.owns_transport and hasattr(self.transport, "aclose"):
                try:
                    loop.run_until_complete(self.transport.aclose())
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass
            loop.close()

    async def _pump(self) -> None:
        try:
            async for frame in self.client.frames():
                self.queue.put((_FRAME, frame))
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - handed to the consumer thread
            self.queue.put((_ERROR, exc))
            return
        self.queue.put((_END, None))

    def stop(self) -> None:
        self.client.close()
        loop, task = self._loop, self._task
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass
        self._thread.join(timeout=5.0)


def stream_realtime(
    gateway: GatewayClient,
    *,
    channels: Sequence[str] = BUILD_CHANNELS,
    job_id: str | None = None,
    last_event_id: str | None = None,
    cursor: str | None = None,
    cancel: CancelToken | None = None,
    transport: Any = None,
    http_client: Any = None,
    on_reset: Callable[[Any], Any] | None = None,
    realtime_options: Mapping[str, Any] | None = None,
) -> Iterator[StreamEvent]:
    """Yield events from ``GET /api/v1/events`` until cancelled or closed.

    ``transport`` overrides the default ``SSETransport`` (e.g. #4128's
    ``InProcessTransport``); ``http_client`` is an ``httpx.AsyncClient`` for the
    default transport. ``realtime_options`` go to ``RealtimeClient`` (``backoff``,
    ``dead_stream_s``, ``sleep``, ``clock``). The stream reconnects forever, so
    stop it with ``cancel`` or by closing the generator.
    """
    resume = _resume_point(last_event_id, cursor)
    sealer = getattr(gateway, "_seal", None)
    injected = transport
    static = dict(getattr(gateway, "_headers", {}) or {})

    def _headers() -> dict[str, str]:
        return {**static, **gateway._call_headers()}

    opts = dict(realtime_options or {})

    def _start(point: str | None) -> _Pump:
        # A default SSETransport (and its AsyncClient) is per event loop, so each
        # pump gets a fresh one and closes it; an injected transport is reused.
        tx = injected or SSETransport(
            gateway._base, client=http_client, headers=_headers, path=EVENTS_PATH
        )
        client = RealtimeClient(
            tx, channels=tuple(channels), job_id=job_id, cursor=point,
            on_reset=on_reset, **opts,
        )
        return _Pump(client, tx, owns_transport=injected is None)

    pump = _start(resume)
    resealed = False
    try:
        while True:
            if cancel is not None:
                cancel.raise_if_cancelled()
            try:
                kind, item = pump.queue.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                continue
            if kind == _FRAME:
                if cancel is not None:
                    cancel.raise_if_cancelled()
                yield frame_to_event(item)
            elif kind == _END:
                return
            else:
                if (
                    isinstance(item, RealtimeAuthError)
                    and getattr(item, "status_code", None) == 401
                    and sealer is not None
                    and not resealed
                ):
                    resealed = True
                    point = pump.client.last_event_id
                    pump.stop()
                    sealer.invalidate()
                    pump = _start(point)
                    continue
                raise item
    finally:
        pump.stop()


class EventsClient:
    """Thin sync wrappers for the realtime surface not covered by ``skeleton.client.realtime``.

    Presence lives in ``skeleton.client.realtime.PresenceClient`` (async), so it
    is intentionally not duplicated here.
    """

    def __init__(self, gateway: GatewayClient) -> None:
        self._gw = gateway

    def slo(self, *, cancel: CancelToken | None = None) -> dict[str, Any]:
        """GET /api/v1/events/slo -> ``{"slo": {...}, "hub": {...}}``."""
        return self._gw._json("GET", EVENTS_SLO_PATH, idempotent=True, cancel=cancel)

    def stream(self, **kwargs: Any) -> Iterator[StreamEvent]:
        """Canonical stream; see :func:`stream_realtime`."""
        return stream_realtime(self._gw, **kwargs)


__all__ = [
    "BUILD_CHANNELS",
    "EVENTS_PATH",
    "EVENTS_SLO_PATH",
    "PRESENCE_PATH",
    "SDK_ROUTES",
    "EventsClient",
    "frame_to_event",
    "stream_realtime",
]
