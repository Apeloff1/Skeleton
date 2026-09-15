"""logbuffer.py — per-job ring buffers for streamed stdout/stderr."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock


@dataclass
class LogLine:
    ts: float
    stream: str      # "stdout" | "stderr" | "system"
    text: str


class LogBuffer:
    """Fixed-size ring buffer; oldest lines drop when full (backpressure-safe)."""

    def __init__(self, capacity: int = 2000) -> None:
        self._lines: deque[LogLine] = deque(maxlen=capacity)
        self._lock = Lock()
        self.dropped = 0

    def append(self, stream: str, text: str) -> None:
        with self._lock:
            if len(self._lines) == self._lines.maxlen:
                self.dropped += 1
            self._lines.append(LogLine(time.time(), stream, text))

    def tail(self, stream: str | None = None, limit: int = 200) -> list[dict]:
        with self._lock:
            lines = list(self._lines)
        if stream:
            lines = [l for l in lines if l.stream == stream]
        return [
            {"ts": l.ts, "stream": l.stream, "text": l.text}
            for l in lines[-limit:]
        ]

    def drain_since(self, index: int) -> tuple[int, list[dict]]:
        """Incremental read for streaming clients: returns (next_index, lines)."""
        with self._lock:
            lines = list(self._lines)
        if index >= len(lines):
            return index, []
        out = [
            {"ts": l.ts, "stream": l.stream, "text": l.text}
            for l in lines[index:]
        ]
        return len(lines), out

    def __len__(self) -> int:
        return len(self._lines)


class LogBufferPool:
    """Owns one LogBuffer per job id; bounded total memory."""

    def __init__(self, max_buffers: int = 64, capacity: int = 2000) -> None:
        self._buffers: dict[str, LogBuffer] = {}
        self._max = max_buffers
        self._capacity = capacity
        self._lock = Lock()

    def get(self, job_id: str) -> LogBuffer:
        with self._lock:
            buf = self._buffers.get(job_id)
            if buf is None:
                if len(self._buffers) >= self._max:
                    oldest = next(iter(self._buffers))
                    self._buffers.pop(oldest, None)
                buf = LogBuffer(self._capacity)
                self._buffers[job_id] = buf
            return buf

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._buffers.pop(job_id, None)

    def stats(self) -> dict:
        with self._lock:
            return {
                "buffers": len(self._buffers),
                "lines": sum(len(b) for b in self._buffers.values()),
                "dropped": sum(b.dropped for b in self._buffers.values()),
            }


log_pool = LogBufferPool()
