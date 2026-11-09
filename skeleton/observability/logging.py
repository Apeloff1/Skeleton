"""Structured logging — JSON-lines events with levels and bound context.

Writes one JSON object per line to a caller-controlled sink while retaining a
bounded in-memory event window for diagnostics and tests. Sink failures are
isolated so observability cannot break the instrumented runtime.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.kernel.errors import KernelError
from skeleton.observability.redaction import redact_payload, redact_text


class LogError(KernelError):
    code = "OBS.LOG"


_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@dataclass
class LogEvent:
    level: str
    message: str
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "level": self.level,
                "message": self.message,
                "timestamp": self.timestamp,
                "context": self.context,
            },
            separators=(",", ":"),
        )


class StructuredLogger:
    """Level-filtered JSON-lines logger with bounded, redacted retention."""

    def __init__(
        self,
        sink: Optional[Callable[[str], None]] = None,
        *,
        min_level: str = "INFO",
        clock: Optional[Callable[[], float]] = None,
        capacity: int = 8192,
    ) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("capacity must be an integer")
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._sink = sink or (lambda line: None)
        self._min_index = _LEVELS.index(min_level) if min_level in _LEVELS else 1
        self._now = clock or time.time
        self._capacity = capacity
        self._context: Dict[str, Any] = {}
        self.events: List[LogEvent] = []

    def bind(self, **context: Any) -> "StructuredLogger":
        """Return a child logger with additional redacted context merged."""
        child = StructuredLogger(
            sink=self._sink,
            min_level=_LEVELS[self._min_index],
            clock=self._now,
            capacity=self._capacity,
        )
        merged = redact_payload({**self._context, **context})
        child._context = dict(merged) if isinstance(merged, dict) else {}
        child.events = self.events
        return child

    def log(self, level: str, message: str, **context: Any) -> LogEvent:
        if level not in _LEVELS:
            raise LogError("unknown level", context={"level": level})
        safe_message = redact_text(message)
        if _LEVELS.index(level) < self._min_index:
            return LogEvent(level=level, message=safe_message, timestamp=self._now())
        merged = redact_payload({**self._context, **context})
        safe_context = dict(merged) if isinstance(merged, dict) else {}
        event = LogEvent(
            level=level,
            message=safe_message,
            timestamp=self._now(),
            context=safe_context,
        )
        self.events.append(event)
        if len(self.events) > self._capacity:
            del self.events[: len(self.events) - self._capacity]
        try:
            self._sink(event.to_json())
        except Exception:
            pass
        return event

    def debug(self, message: str, **context: Any) -> LogEvent:
        return self.log("DEBUG", message, **context)

    def info(self, message: str, **context: Any) -> LogEvent:
        return self.log("INFO", message, **context)

    def warning(self, message: str, **context: Any) -> LogEvent:
        return self.log("WARNING", message, **context)

    def error(self, message: str, **context: Any) -> LogEvent:
        return self.log("ERROR", message, **context)
