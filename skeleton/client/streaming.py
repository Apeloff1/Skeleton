"""Progress-event stream parsing: SSE first, plus JSON snapshot fallback.

PROVISIONAL: the transport is pending Walt's realtime work and will delegate to
``skeleton.client.realtime``. Aligned with ADR-realtime-transport
(docs/architecture/ADR-realtime-transport.md, PR #4101):

- SSE is the only canonical stream format, and NDJSON is not supported. Frames
  are ``id: <envelope.id>``, ``event: <type>``, ``data: <envelope JSON>``.
- The ``: hb`` heartbeat comment is skipped. ``stream.reset`` and
  ``stream.lagged`` control events are yielded so callers can react.
- Resume uses ``Last-Event-ID`` (``last_event_id=``) or ``?cursor=``.
- Reconnect, dead-stream detection and jittered backoff are deliberately NOT
  implemented here; they belong to ``skeleton.client.realtime``.
- Today's ``/events`` endpoints return a JSON snapshot (``{"events": [...]}``),
  which is still handled.

Event shape tolerates the realtime envelope v1::

    {v, id, ts, channel (build|agent|presence), type, payload,
     correlation_id?, job_id?}

Fields are exposed when present; ``raw`` always carries the original dict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping

import httpx

from skeleton.client.cancel import CancelToken
from skeleton.client.errors import (
    SkeletonHTTPError,
    SkeletonTimeoutError,
    SkeletonTransportError,
)

HEARTBEAT_TYPES = frozenset({"heartbeat"})
CONTROL_TYPES = frozenset({"stream.reset", "stream.lagged"})


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One parsed progress event."""

    raw: dict[str, Any]
    type: str | None = None
    id: str | None = None
    v: int | None = None
    ts: Any = None
    channel: str | None = None
    payload: Any = None
    correlation_id: str | None = None
    job_id: str | None = None
    sequence: int | None = None
    sse_event: str | None = None
    sse_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_envelope_v1(self) -> bool:
        return self.v is not None and self.channel is not None

    @property
    def is_control(self) -> bool:
        """``stream.reset`` / ``stream.lagged`` (ADR section 4)."""
        return self.type in CONTROL_TYPES

    @property
    def is_heartbeat(self) -> bool:
        return (self.type or self.sse_event) in HEARTBEAT_TYPES

    @classmethod
    def from_obj(
        cls,
        obj: Any,
        *,
        sse_event: str | None = None,
        sse_id: str | None = None,
    ) -> "StreamEvent":
        raw = dict(obj) if isinstance(obj, Mapping) else {"data": obj}
        ev_id = raw.get("id", raw.get("event_id"))
        seq = raw.get("sequence")
        version = raw.get("v")
        return cls(
            raw=raw,
            type=_opt_str(raw.get("type")) or sse_event,
            id=_opt_str(ev_id) if ev_id is not None else sse_id,
            v=version if isinstance(version, int) else None,
            ts=raw.get("ts", raw.get("timestamp")),
            channel=_opt_str(raw.get("channel")),
            payload=raw.get("payload"),
            correlation_id=_opt_str(raw.get("correlation_id")),
            job_id=_opt_str(raw.get("job_id")),
            sequence=seq if isinstance(seq, int) else None,
            sse_event=sse_event,
            sse_id=sse_id,
        )


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _decode(data: str) -> Any:
    try:
        return json.loads(data)
    except ValueError:
        return data


def parse_sse_lines(
    lines: Iterable[str], cancel: CancelToken | None = None
) -> Iterator[StreamEvent]:
    """Parse ``text/event-stream`` lines; skips comments and heartbeats."""
    data: list[str] = []
    event_name: str | None = None
    event_id: str | None = None
    for line in lines:
        if cancel is not None:
            cancel.raise_if_cancelled()
        line = line.rstrip("\r\n")
        if line == "":
            if data:
                ev = StreamEvent.from_obj(
                    _decode("\n".join(data)), sse_event=event_name, sse_id=event_id
                )
                if not ev.is_heartbeat:
                    yield ev
            data, event_name = [], None
            continue
        if line.startswith(":"):
            continue  # comment / keep-alive
        name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "data":
            data.append(value)
        elif name == "event":
            event_name = value or None
        elif name == "id":
            event_id = value or None  # persists across events per SSE spec
    if data:
        ev = StreamEvent.from_obj(
            _decode("\n".join(data)), sse_event=event_name, sse_id=event_id
        )
        if not ev.is_heartbeat:
            yield ev


def parse_json_events(
    body: Any, cancel: CancelToken | None = None
) -> Iterator[StreamEvent]:
    """Plain JSON list, or ``{"events": [...]}`` (engine/swarm snapshot shape)."""
    items = body.get("events", []) if isinstance(body, Mapping) else body
    for item in items or []:
        if cancel is not None:
            cancel.raise_if_cancelled()
        ev = StreamEvent.from_obj(item)
        if not ev.is_heartbeat:
            yield ev


def iter_response_events(
    response: httpx.Response, cancel: CancelToken | None = None
) -> Iterator[StreamEvent]:
    """Dispatch on content-type of an open (streaming) response."""
    ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype == "text/event-stream":
        yield from parse_sse_lines(response.iter_lines(), cancel)
    else:
        response.read()
        yield from parse_json_events(response.json(), cancel)


def stream_events(
    gateway: Any,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    last_event_id: str | None = None,
    cursor: str | None = None,
    cancel: CancelToken | None = None,
    idempotent: bool = False,
) -> Iterator[StreamEvent]:
    """PROVISIONAL: GET ``path`` with httpx streaming and yield parsed events.

    Retries retryable statuses (with backoff) only when ``idempotent=True``
    and only before the body is consumed, never mid-stream. A 503 ``seal_unavailable`` is never retried.
    Does not reconnect.
    """
    from skeleton.client.errors import SkeletonSealConfigError
    from skeleton.client.gateway import _invalid_seal, _seal_unavailable

    query = dict(params or {})
    if cursor:
        query["cursor"] = cursor
    policy = gateway._retry
    max_attempts = policy.max_attempts if idempotent else 1
    resealed = False
    attempt = 0
    while attempt < max_attempts:
        if cancel is not None:
            cancel.raise_if_cancelled()
        headers = {"accept": "text/event-stream, application/json"}
        if last_event_id:
            headers["last-event-id"] = last_event_id
        headers.update(gateway._call_headers())
        try:
            with gateway._client.stream(
                "GET", path, params=query, headers=headers
            ) as response:
                gateway._note_response(response, headers["x-request-id"])
                if response.status_code >= 400:
                    response.read()
                    if _seal_unavailable(response):
                        raise SkeletonSealConfigError(
                            "server has no seal secret configured (503 seal_unavailable)"
                        )
                    if gateway._seal is not None and not resealed and _invalid_seal(response):
                        resealed = True
                        gateway._seal.invalidate()
                        continue
                    if (
                        response.status_code in policy.retry_status_codes
                        and attempt + 1 < max_attempts
                    ):
                        gateway._backoff(attempt, response, cancel)
                        attempt += 1
                        continue
                    from skeleton.client.gateway import _safe_body

                    raise SkeletonHTTPError(
                        response.status_code,
                        response.reason_phrase,
                        url=str(response.url),
                        body=_safe_body(response),
                    )
                yield from iter_response_events(response, cancel)
                return
        except httpx.TimeoutException as exc:
            raise SkeletonTimeoutError(str(exc)) from exc
        except httpx.TransportError as exc:
            raise SkeletonTransportError(str(exc)) from exc
