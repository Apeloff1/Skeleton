"""Pluggable job/agent event sink (envelope v1) for the realtime hub.

The realtime transport (SSE/WebSocket hub) registers itself on a
``FanOutPublisher`` via ``subscribe``; it never imports queue internals.

Envelope v1::

    {v: 1, id: <monotonic per channel stream>, ts, channel: build|agent|presence,
     type, payload, correlation_id?, job_id?}

Payloads are passed through ``skeleton.observability.redaction.redact_payload``
so secret/token-shaped keys and inline credentials never leave the process.
The existing observability emit layer (kernel ``EventBus`` ->
``EventMetricsBridge``) is reached through ``EventBusBridge`` instead of a
parallel bus.
"""
from __future__ import annotations

import itertools
import logging
import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from skeleton.observability.redaction import redact_payload, redact_text

ENVELOPE_VERSION = 1
CHANNELS = frozenset({"build", "agent", "presence"})
EVENT_TYPES = frozenset({
    "build.started", "build.progress", "build.log", "build.completed", "build.failed",
    "agent.started", "agent.step", "agent.completed",
    "presence.update",
})

_log = logging.getLogger(__name__)


@runtime_checkable
class JobEventPublisher(Protocol):
    def publish(self, event: dict) -> None: ...


class NullJobEventPublisher:
    """Default sink: drops everything."""

    def publish(self, event: dict) -> None:  # noqa: D401 - protocol method
        return None


class _StreamIds:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, itertools.count] = {}

    def next(self, channel: str) -> int:
        with self._lock:
            counter = self._counters.setdefault(channel, itertools.count(1))
            return next(counter)


_DEFAULT_IDS = _StreamIds()


def make_envelope(
    channel: str,
    type: str,
    payload: Optional[Mapping[str, Any]] = None,
    *,
    correlation_id: str = "",
    job_id: str = "",
    ids: Optional[_StreamIds] = None,
    clock: Callable[[], float] = time.time,
) -> dict:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel!r}")
    if type not in EVENT_TYPES or not type.startswith(channel + "."):
        raise ValueError(f"unknown or mismatched event type: {type!r}")
    safe = redact_payload(dict(payload or {}))
    if not isinstance(safe, dict):
        safe = {"value": safe}
    env: dict[str, Any] = {
        "v": ENVELOPE_VERSION,
        "id": (ids or _DEFAULT_IDS).next(channel),
        "ts": clock(),
        "channel": channel,
        "type": type,
        "payload": safe,
    }
    if correlation_id:
        env["correlation_id"] = redact_text(str(correlation_id))
    if job_id:
        env["job_id"] = str(job_id)
    return env


class FanOutPublisher:
    """In-process fan-out.  Subscriber failures are isolated and logged."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: list[JobEventPublisher] = []

    def subscribe(self, sink: JobEventPublisher) -> Callable[[], None]:
        if not callable(getattr(sink, "publish", None)):
            raise TypeError("sink must implement publish(event: dict)")
        with self._lock:
            self._subs.append(sink)

        def unsubscribe() -> None:
            with self._lock:
                if sink in self._subs:
                    self._subs.remove(sink)

        return unsubscribe

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for sink in subs:
            try:
                sink.publish(dict(event))
            except Exception:  # pragma: no cover - logged, never propagated
                _log.exception("job event sink failed")


class EventBusBridge:
    """Forward envelopes onto the kernel EventBus (observability emit layer)."""

    def __init__(self, bus: Any, topic_prefix: str = "app") -> None:
        self._bus = bus
        self._prefix = topic_prefix

    def publish(self, event: dict) -> None:
        from skeleton.kernel.events import DomainEvent

        self._bus.publish(DomainEvent(
            topic=f"{self._prefix}.{event['type']}",
            payload=dict(event),
            correlation_id=str(event.get("correlation_id", "")),
            timestamp=float(event.get("ts", time.time())),
        ))
