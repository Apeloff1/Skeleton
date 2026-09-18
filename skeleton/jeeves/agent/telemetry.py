"""Deterministic tracing and metrics for Jeeves agent runs."""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping

from .types import AgentContractError, json_safe, require_id, stable_fingerprint


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    trace_id: str
    run_id: str
    event_type: str
    at: float
    payload: Mapping[str, Any] = field(default_factory=dict)
    parent_span_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AgentContractError("trace sequence must be a positive integer")
        object.__setattr__(self, "trace_id", require_id("trace_id", self.trace_id))
        object.__setattr__(self, "run_id", require_id("run_id", self.run_id))
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise AgentContractError("event_type must be non-empty")
        object.__setattr__(self, "event_type", self.event_type.strip()[:128])
        if not isinstance(self.at, (int, float)) or self.at < 0:
            raise AgentContractError("event time must be non-negative")
        object.__setattr__(self, "at", float(self.at))
        object.__setattr__(self, "payload", json_safe(dict(self.payload)))
        if self.parent_span_id is not None:
            object.__setattr__(self, "parent_span_id", require_id("parent_span_id", self.parent_span_id))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "sequence": self.sequence,
                "trace_id": self.trace_id,
                "run_id": self.run_id,
                "event_type": self.event_type,
                "at": self.at,
                "payload": self.payload,
                "parent_span_id": self.parent_span_id,
            }
        )


@dataclass(frozen=True, slots=True)
class SpanRecord:
    span_id: str
    name: str
    started_at: float
    ended_at: float
    ok: bool
    attributes: Mapping[str, Any]
    error_type: str | None = None

    @property
    def duration_ms(self) -> float:
        return max(0.0, (self.ended_at - self.started_at) * 1000.0)


class TraceLedger:
    """Append-only hash-chained event ledger suitable for deterministic replay."""

    def __init__(self, trace_id: str, run_id: str, *, clock: Callable[[], float] = time.time, max_events: int = 10_000) -> None:
        self.trace_id = require_id("trace_id", trace_id)
        self.run_id = require_id("run_id", run_id)
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._max_events = max_events
        self._clock = clock
        self._events: list[TraceEvent] = []
        self._hash_chain: list[str] = []
        self._lock = threading.RLock()

    def emit(self, event_type: str, payload: Mapping[str, Any] | None = None, *, parent_span_id: str | None = None) -> TraceEvent:
        with self._lock:
            if len(self._events) >= self._max_events:
                raise RuntimeError("trace event budget exhausted")
            event = TraceEvent(
                sequence=len(self._events) + 1,
                trace_id=self.trace_id,
                run_id=self.run_id,
                event_type=event_type,
                at=self._clock(),
                payload=dict(payload or {}),
                parent_span_id=parent_span_id,
            )
            previous = self._hash_chain[-1] if self._hash_chain else "GENESIS"
            chained = stable_fingerprint({"previous": previous, "event": event.fingerprint})
            self._events.append(event)
            self._hash_chain.append(chained)
            return event

    def events(self) -> tuple[TraceEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return self._hash_chain[-1] if self._hash_chain else stable_fingerprint("GENESIS")

    def verify(self) -> bool:
        previous = "GENESIS"
        with self._lock:
            if len(self._events) != len(self._hash_chain):
                return False
            for event, expected in zip(self._events, self._hash_chain):
                actual = stable_fingerprint({"previous": previous, "event": event.fingerprint})
                if actual != expected:
                    return False
                previous = actual
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trace_id": self.trace_id,
                "run_id": self.run_id,
                "event_count": len(self._events),
                "fingerprint": self.fingerprint,
                "events": [
                    {
                        "sequence": event.sequence,
                        "type": event.event_type,
                        "at": event.at,
                        "payload": dict(event.payload),
                        "parent_span_id": event.parent_span_id,
                    }
                    for event in self._events
                ],
            }


class Tracer:
    def __init__(self, ledger: TraceLedger, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._ledger = ledger
        self._monotonic = monotonic
        self._spans: list[SpanRecord] = []
        self._lock = threading.RLock()
        self._counter = 0

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[str]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("span name must be non-empty")
        with self._lock:
            self._counter += 1
            span_id = f"span:{self._counter}"
        started = self._monotonic()
        self._ledger.emit("span.started", {"span_id": span_id, "name": name, **json_safe(attributes)}, parent_span_id=span_id)
        error_type: str | None = None
        ok = False
        try:
            yield span_id
            ok = True
        except BaseException as exc:
            error_type = type(exc).__name__
            self._ledger.emit(
                "span.failed",
                {"span_id": span_id, "name": name, "error_type": error_type},
                parent_span_id=span_id,
            )
            raise
        finally:
            ended = self._monotonic()
            record = SpanRecord(
                span_id=span_id,
                name=name,
                started_at=started,
                ended_at=ended,
                ok=ok,
                attributes=json_safe(attributes),
                error_type=error_type,
            )
            with self._lock:
                self._spans.append(record)
            self._ledger.emit(
                "span.ended",
                {"span_id": span_id, "name": name, "ok": ok, "duration_ms": record.duration_ms},
                parent_span_id=span_id,
            )

    def spans(self) -> tuple[SpanRecord, ...]:
        with self._lock:
            return tuple(self._spans)


class MetricsRegistry:
    """Minimal dependency-free counters, gauges, and latency histograms."""

    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.RLock()

    def increment(self, name: str, amount: int = 1) -> None:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError("counter increment must be non-negative integer")
        with self._lock:
            self._counters[self._name(name)] += amount

    def gauge(self, name: str, value: float) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("gauge value must be numeric")
        with self._lock:
            self._gauges[self._name(name)] = float(value)

    def observe(self, name: str, value: float) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError("histogram observation must be non-negative numeric")
        with self._lock:
            bucket = self._histograms[self._name(name)]
            bucket.append(float(value))
            if len(bucket) > 10_000:
                del bucket[: len(bucket) - 10_000]

    @staticmethod
    def _name(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("metric name must be non-empty")
        return value.strip()[:128]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            histograms: dict[str, Any] = {}
            for name, values in sorted(self._histograms.items()):
                ordered = sorted(values)
                if not ordered:
                    continue
                histograms[name] = {
                    "count": len(ordered),
                    "min": ordered[0],
                    "max": ordered[-1],
                    "mean": sum(ordered) / len(ordered),
                    "p50": self._percentile(ordered, 0.50),
                    "p95": self._percentile(ordered, 0.95),
                    "p99": self._percentile(ordered, 0.99),
                }
            return {
                "counters": dict(sorted(self._counters.items())),
                "gauges": dict(sorted(self._gauges.items())),
                "histograms": histograms,
            }

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
        return values[index]
