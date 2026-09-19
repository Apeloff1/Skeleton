"""Structured audit events and sinks for shell execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol
import uuid

from skeleton.shells.redaction import SecretRedactor


@dataclass(frozen=True)
class AuditEvent:
    kind: str
    correlation_id: str
    timestamp: str
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    command: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        kind: str,
        correlation_id: str,
        *,
        command: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> "AuditEvent":
        return cls(
            kind=kind,
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            command=command,
            data=MappingProxyType(dict(data or {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "command": self.command,
            "data": dict(self.data),
        }


class AuditSink(Protocol):
    def emit(self, event: AuditEvent) -> None: ...


class NullAuditSink:
    def emit(self, event: AuditEvent) -> None:
        del event


class MemoryAuditSink:
    """Thread-safe bounded in-memory audit ring."""

    def __init__(self, *, max_events: int = 10_000) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self.max_events = max_events
        self._events: list[AuditEvent] = []
        self._lock = threading.RLock()
        self._dropped = 0

    def emit(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)
            overflow = len(self._events) - self.max_events
            if overflow > 0:
                del self._events[:overflow]
                self._dropped += overflow

    def snapshot(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def by_correlation(self, correlation_id: str) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.correlation_id == correlation_id)

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped


class CompositeAuditSink:
    def __init__(self, sinks: Iterable[AuditSink]) -> None:
        self._sinks = tuple(sinks)

    def emit(self, event: AuditEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)


class RedactingAuditSink:
    """Apply recursive redaction before forwarding an event."""

    def __init__(self, sink: AuditSink, redactor: SecretRedactor | None = None) -> None:
        self._sink = sink
        self._redactor = redactor or SecretRedactor()

    def emit(self, event: AuditEvent) -> None:
        cleaned = self._redactor.redact(event.data)
        assert isinstance(cleaned, dict)
        self._sink.emit(
            AuditEvent(
                kind=event.kind,
                correlation_id=event.correlation_id,
                timestamp=event.timestamp,
                event_id=event.event_id,
                command=event.command,
                data=MappingProxyType(cleaned),
            )
        )


class JsonlAuditSink:
    """Append-only JSONL sink with bounded event serialization.

    The caller owns filesystem permissions and retention.  This sink does not
    create parent directories and refuses symlink targets to reduce accidental
    log redirection.
    """

    def __init__(self, path: Path | str, *, max_event_bytes: int = 64 * 1024) -> None:
        self.path = Path(path)
        self.max_event_bytes = max_event_bytes
        if max_event_bytes <= 0:
            raise ValueError("max_event_bytes must be positive")
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("audit path may not be a symlink")
        if not self.path.parent.exists():
            raise ValueError("audit parent directory must exist")
        self._lock = threading.Lock()

    def emit(self, event: AuditEvent) -> None:
        encoded = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > self.max_event_bytes:
            raise ValueError("audit event exceeds byte limit")
        with self._lock:
            if self.path.exists() and self.path.is_symlink():
                raise ValueError("audit path became a symlink")
            with self.path.open("ab") as handle:
                handle.write(encoded + b"\n")
