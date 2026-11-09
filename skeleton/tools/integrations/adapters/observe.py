"""Observation hooks and an in-memory metrics recorder for the adapter layer.

Observers receive structured events; they must never raise into the call
path (the dispatcher swallows observer failures).  Events never include
message content or credentials, only names, codes, counts and timings.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

__all__ = ["AdapterEvent", "Observer", "ObserverHub", "MetricsRecorder", "EventLog"]


@dataclass(frozen=True)
class AdapterEvent:
    kind: str
    provider: str = ""
    tool: str = ""
    attempt: int = 0
    code: str = ""
    latency_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        for key in ("provider", "tool", "code"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        if self.attempt:
            payload["attempt"] = self.attempt
        if self.latency_ms:
            payload["latency_ms"] = round(self.latency_ms, 3)
        if self.attributes:
            payload["attributes"] = dict(self.attributes)
        return payload


class Observer(Protocol):
    def on_event(self, event: AdapterEvent) -> None: ...


class ObserverHub:
    """Fan-out dispatcher that isolates observer failures."""

    def __init__(self, observers: Iterable[Observer] = ()) -> None:
        self._observers: list[Observer] = list(observers)
        self._lock = threading.Lock()
        self.dropped = 0

    def add(self, observer: Observer) -> None:
        with self._lock:
            self._observers.append(observer)

    def remove(self, observer: Observer) -> None:
        with self._lock:
            self._observers = [o for o in self._observers if o is not observer]

    def emit(self, kind: str, **fields: Any) -> AdapterEvent:
        event = AdapterEvent(kind=kind, **fields)
        with self._lock:
            observers = list(self._observers)
        for observer in observers:
            try:
                observer.on_event(event)
            except Exception:  # noqa: BLE001 - observers must not break calls
                self.dropped += 1
        return event


class EventLog:
    """Bounded in-memory event list, handy for tests and debugging."""

    def __init__(self, limit: int = 1000) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self.limit = limit
        self.events: list[AdapterEvent] = []
        self._lock = threading.Lock()

    def on_event(self, event: AdapterEvent) -> None:
        with self._lock:
            self.events.append(event)
            if len(self.events) > self.limit:
                del self.events[: len(self.events) - self.limit]

    def kinds(self) -> list[str]:
        with self._lock:
            return [e.kind for e in self.events]

    def of_kind(self, kind: str) -> list[AdapterEvent]:
        with self._lock:
            return [e for e in self.events if e.kind == kind]


class MetricsRecorder:
    """Counters and latency summaries keyed by (kind, provider/tool, code)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, str, str], int] = defaultdict(int)
        self._latency: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._max_samples = 2048

    def on_event(self, event: AdapterEvent) -> None:
        subject = event.provider or event.tool
        with self._lock:
            self._counters[(event.kind, subject, event.code)] += 1
            if event.latency_ms:
                samples = self._latency[(event.kind, subject)]
                samples.append(event.latency_ms)
                if len(samples) > self._max_samples:
                    del samples[: len(samples) - self._max_samples]

    def count(self, kind: str, subject: str | None = None, code: str | None = None) -> int:
        with self._lock:
            return sum(
                n
                for (k, s, c), n in self._counters.items()
                if k == kind and (subject is None or s == subject) and (code is None or c == code)
            )

    def latency(self, kind: str, subject: str) -> dict[str, float]:
        with self._lock:
            samples = sorted(self._latency.get((kind, subject), ()))
        if not samples:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "max": 0.0}

        def pct(p: float) -> float:
            idx = min(len(samples) - 1, max(0, int(round(p * (len(samples) - 1)))))
            return samples[idx]

        return {"count": float(len(samples)), "p50": pct(0.5), "p95": pct(0.95), "max": samples[-1]}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = {"|".join(k): v for k, v in sorted(self._counters.items())}
            subjects = sorted(self._latency)
        return {
            "counters": counters,
            "latency": {f"{k}|{s}": self.latency(k, s) for k, s in subjects},
        }
