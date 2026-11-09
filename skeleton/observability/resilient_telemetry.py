"""Bounded telemetry isolation and reconstruction primitives.

Core correctness must not depend on the primary telemetry sink. This module
redacts before emission, collapses unbounded cardinality, isolates sink
exceptions, and retains a compact digest ledger that can reconstruct critical
event history when full telemetry is unavailable.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Any

from skeleton.observability.redaction import redact_payload


class ResilientTelemetryError(ValueError):
    """Telemetry input or configuration violates the bounded contract."""


@dataclass(frozen=True, slots=True)
class ReconstructionReceipt:
    sequence: int
    kind: str
    series_id: str
    correlation_digest: str
    event_digest: str
    overflowed: bool

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ResilientTelemetryError("sequence must be positive")
        if not self.kind:
            raise ResilientTelemetryError("kind must be non-empty")
        for name in ("correlation_digest", "event_digest"):
            value = getattr(self, name)
            if len(value) != 64:
                raise ResilientTelemetryError(f"{name} must be SHA-256 hex")
            try:
                bytes.fromhex(value)
            except ValueError as exc:
                raise ResilientTelemetryError(
                    f"{name} must be hexadecimal"
                ) from exc


@dataclass(frozen=True, slots=True)
class TelemetryEmitResult:
    receipt: ReconstructionReceipt
    delivered: bool
    sink_failed: bool


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResilientTelemetryError(
            "telemetry payload must be finite canonical JSON"
        ) from exc


def _token(value: str, field: str, *, max_length: int = 128) -> str:
    if not isinstance(value, str):
        raise ResilientTelemetryError(f"{field} must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > max_length
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ResilientTelemetryError(f"invalid {field}")
    return normalized


class ResilientTelemetry:
    """Fail-open telemetry with bounded cardinality and reconstruction evidence."""

    def __init__(
        self,
        *,
        sink: Callable[[Mapping[str, Any]], None] | None = None,
        max_series: int = 128,
        max_receipts: int = 2048,
        max_labels: int = 16,
        clock: Callable[[], float] | None = None,
    ) -> None:
        for name, value, minimum in (
            ("max_series", max_series, 1),
            ("max_receipts", max_receipts, 1),
            ("max_labels", max_labels, 0),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < minimum
            ):
                raise ResilientTelemetryError(
                    f"{name} must be an integer >= {minimum}"
                )
        self._sink = sink
        self._max_series = max_series
        self._max_labels = max_labels
        self._receipts: deque[ReconstructionReceipt] = deque(
            maxlen=max_receipts
        )
        self._series: set[str] = set()
        self._sequence = 0
        self._sink_failures = 0
        self._overflow_events = 0
        self._delivered = 0
        self._clock = clock or time.time

    @property
    def sink_failures(self) -> int:
        return self._sink_failures

    @property
    def overflow_events(self) -> int:
        return self._overflow_events

    @property
    def series_count(self) -> int:
        return len(self._series)

    def _safe_labels(
        self,
        labels: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if labels is None:
            return {}
        if not isinstance(labels, Mapping):
            raise ResilientTelemetryError("labels must be a mapping")
        if len(labels) > self._max_labels:
            raise ResilientTelemetryError("label count exceeds bound")
        safe = redact_payload(labels)
        if not isinstance(safe, dict):
            raise ResilientTelemetryError("redacted labels must be an object")
        for key in safe:
            _token(key, "label key", max_length=96)
        _canonical_json(safe)
        return safe

    @staticmethod
    def _series_digest(kind: str, labels: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            _canonical_json({"kind": kind, "labels": labels})
        ).hexdigest()

    def emit(
        self,
        kind: str,
        *,
        payload: Mapping[str, Any] | None = None,
        labels: Mapping[str, Any] | None = None,
        correlation_id: str = "",
    ) -> TelemetryEmitResult:
        kind = _token(kind, "kind")
        safe_labels = self._safe_labels(labels)
        safe_payload = redact_payload(payload or {})
        if not isinstance(safe_payload, dict):
            raise ResilientTelemetryError("payload must be an object")
        _canonical_json(safe_payload)

        raw_series = self._series_digest(kind, safe_labels)
        overflowed = False
        if raw_series in self._series:
            series_id = raw_series
        elif len(self._series) < self._max_series:
            self._series.add(raw_series)
            series_id = raw_series
        else:
            overflowed = True
            self._overflow_events += 1
            series_id = hashlib.sha256(
                f"overflow:{kind}".encode("utf-8")
            ).hexdigest()

        correlation = (
            _token(correlation_id, "correlation_id", max_length=256)
            if correlation_id
            else ""
        )
        correlation_digest = hashlib.sha256(
            correlation.encode("utf-8")
        ).hexdigest()

        emitted_at = float(self._clock())
        if not math.isfinite(emitted_at):
            raise ResilientTelemetryError("clock returned non-finite time")

        safe_event = {
            "kind": kind,
            "labels": safe_labels if not overflowed else {"overflow": True},
            "payload": safe_payload,
            "correlation_digest": correlation_digest,
            "emitted_at": emitted_at,
            "series_id": series_id,
            "overflowed": overflowed,
        }
        event_digest = hashlib.sha256(
            _canonical_json(safe_event)
        ).hexdigest()

        self._sequence += 1
        receipt = ReconstructionReceipt(
            sequence=self._sequence,
            kind=kind,
            series_id=series_id,
            correlation_digest=correlation_digest,
            event_digest=event_digest,
            overflowed=overflowed,
        )
        self._receipts.append(receipt)

        delivered = False
        sink_failed = False
        if self._sink is not None:
            try:
                self._sink(safe_event)
            except Exception:
                self._sink_failures += 1
                sink_failed = True
            else:
                self._delivered += 1
                delivered = True

        return TelemetryEmitResult(
            receipt=receipt,
            delivered=delivered,
            sink_failed=sink_failed,
        )

    def reconstruct(self) -> dict[str, Any]:
        """Reconstruct bounded critical history without full telemetry payloads."""

        rows = tuple(self._receipts)
        by_kind = Counter(item.kind for item in rows)
        by_series = Counter(item.series_id for item in rows)
        return {
            "receipt_count": len(rows),
            "first_sequence": rows[0].sequence if rows else None,
            "last_sequence": rows[-1].sequence if rows else None,
            "by_kind": dict(sorted(by_kind.items())),
            "series_event_counts": dict(sorted(by_series.items())),
            "overflow_events_in_window": sum(item.overflowed for item in rows),
            "sink_failures_total": self._sink_failures,
            "delivered_total": self._delivered,
            "series_count": len(self._series),
            "receipt_digests": [item.event_digest for item in rows],
        }

    def receipts(self) -> tuple[ReconstructionReceipt, ...]:
        return tuple(self._receipts)


__all__ = [
    "ReconstructionReceipt",
    "ResilientTelemetry",
    "ResilientTelemetryError",
    "TelemetryEmitResult",
]
