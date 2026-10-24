"""SSE framing, parsing and the server stream loop (ADR §1, §4).

Frame format::

    retry: 2000                       (first write only; client backoff floor)

    id: 1792252800123001              (== envelope.id)
    event: build.progress             (== envelope.type)
    data: {"v":1,"id":"1792252800123001",...}

    event: stream.lagged              (control events carry no id line, so
    data: {"v":1,"type":"stream.lagged","payload":{"dropped":3},...}
                                       they never move Last-Event-ID)
    : hb                              (heartbeat comment every 15 s)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, List, Optional, Union

from .envelope import CONTROL_TYPES, ControlEvent, EnvelopeError, RealtimeEvent, ts_to_ms

DEFAULT_RETRY_MS = 2000
HEARTBEAT_COMMENT = ": hb\n\n"
SSE_MEDIA_TYPE = "text/event-stream"

Frame = Union[RealtimeEvent, ControlEvent]


def _data_lines(text: str) -> str:
    return "".join(f"data: {line}\n" for line in text.split("\n"))


def format_sse_event(event: RealtimeEvent, epoch: Optional[str] = None) -> str:
    """``id:`` is ``<envelope.id>-<hub epoch>`` when the hub epoch is known (S2-6)."""
    sse_id = f"{event.id}-{epoch}" if epoch else event.id
    return f"id: {sse_id}\nevent: {event.type}\n{_data_lines(event.to_json())}\n"


def format_sse_control(frame: ControlEvent) -> str:
    return f"event: {frame.type}\n{_data_lines(frame.to_json())}\n"


def format_sse(frame: Frame, epoch: Optional[str] = None) -> str:
    if isinstance(frame, RealtimeEvent):
        return format_sse_event(frame, epoch)
    return format_sse_control(frame)


def format_retry(retry_ms: int = DEFAULT_RETRY_MS) -> str:
    return f"retry: {int(retry_ms)}\n\n"


@dataclass
class SSEMessage:
    event: str = "message"
    data: str = ""
    id: Optional[str] = None
    data_lines: List[str] = field(default_factory=list)


class SSEParser:
    """Incremental ``text/event-stream`` parser (WHATWG semantics).

    ``retry`` and ``comments`` are tracked so clients can honour the retry
    floor and treat ``: hb`` comments as liveness.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._cur = SSEMessage()
        self.last_event_id: Optional[str] = None
        self.retry_ms: Optional[int] = None
        self.comments = 0

    def feed(self, chunk: str) -> Iterator[SSEMessage]:
        self._buf += chunk.replace("\r\n", "\n").replace("\r", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            msg = self._line(line)
            if msg is not None:
                yield msg

    def _line(self, line: str) -> Optional[SSEMessage]:
        if line == "":
            cur = self._cur
            self._cur = SSEMessage()
            if cur.id is not None:
                self.last_event_id = cur.id
            if not cur.data_lines:
                return None
            cur.data = "\n".join(cur.data_lines)
            return cur
        if line.startswith(":"):
            self.comments += 1
            return None
        name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "data":
            self._cur.data_lines.append(value)
        elif name == "event":
            self._cur.event = value or "message"
        elif name == "id" and "\x00" not in value:
            self._cur.id = value
        elif name == "retry" and value.isdigit():
            self.retry_ms = int(value)
        return None


def sse_message_to_frame(msg: SSEMessage) -> Optional[Frame]:
    """Decode one SSE message into an envelope or control event.

    Returns ``None`` for messages that are not v1 frames so clients ignore
    unknown event names, as the ADR requires.
    """
    if not msg.data:
        return None
    if msg.event in CONTROL_TYPES:
        return ControlEvent.from_dict(json.loads(msg.data))
    event = RealtimeEvent.from_json(msg.data)
    if msg.id is not None and msg.id.split("-", 1)[0] != event.id:
        raise EnvelopeError("SSE id line does not match envelope id")
    return event


async def iter_frames(
    hub: Any,
    sub: Any,
    *,
    max_events: Optional[int] = None,
    heartbeat_interval_s: Optional[float] = None,
    is_disconnected: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncIterator[Optional[Frame]]:
    """Yield frames; ``None`` means "write a heartbeat comment now".

    Records delivery latency for live events, heartbeats sent / late
    heartbeats (event-loop stalls) and the disconnect reason, and always
    unsubscribes on exit. When the subscription's max lifetime elapses
    (Jenkins S2-4) a ``stream.reauth`` control frame is yielded and the
    stream ends so the client reconnects with a fresh seal.
    """
    interval = hub.heartbeat_interval_s if heartbeat_interval_s is None else float(heartbeat_interval_s)
    delivered = 0
    reason = "closed"
    last_write = time.monotonic()
    try:
        while True:
            if is_disconnected is not None and await is_disconnected():
                reason = "client_gone"
                return
            remaining = sub.remaining_lifetime() if hasattr(sub, "remaining_lifetime") else None
            if remaining is not None and remaining <= 0:
                reason = "max_lifetime"
                yield hub.reauth_event(sub)
                return
            wait = interval if remaining is None else max(0.0, min(interval, remaining))
            try:
                frame = await sub.next(timeout=wait)
            except EOFError:
                reason = "server_closed"
                return
            now = time.monotonic()
            if now - last_write > 2 * interval:
                hub.slo.record_heartbeat_miss()
            last_write = now
            if frame is None:
                if remaining is not None and sub.remaining_lifetime() <= 0:
                    continue
                hub.slo.record_heartbeat_sent()
                yield None
                continue
            if isinstance(frame, RealtimeEvent) and frame.type != "presence.snapshot":
                if frame.seq > sub.head_at_connect:
                    hub.slo.record_delivered(frame.channel, time.time() * 1000.0 - ts_to_ms(frame.ts))
                delivered += 1
                sub.last_delivered_id = frame.id
            yield frame
            if max_events is not None and delivered >= max_events:
                reason = "max_events"
                return
    finally:
        hub.unsubscribe(sub, reason=reason)


async def sse_body(hub: Any, sub: Any, *, retry_ms: int = DEFAULT_RETRY_MS, **kwargs: Any) -> AsyncIterator[str]:
    """Async iterator of SSE text chunks for a ``StreamingResponse``."""
    yield format_retry(retry_ms)
    epoch = getattr(hub, "epoch", None)
    async for frame in iter_frames(hub, sub, **kwargs):
        yield HEARTBEAT_COMMENT if frame is None else format_sse(frame, epoch)


def sse_headers() -> dict:
    return {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }


__all__ = [
    "DEFAULT_RETRY_MS",
    "HEARTBEAT_COMMENT",
    "SSEMessage",
    "SSEParser",
    "SSE_MEDIA_TYPE",
    "format_retry",
    "format_sse",
    "format_sse_control",
    "format_sse_event",
    "iter_frames",
    "sse_body",
    "sse_headers",
    "sse_message_to_frame",
]
