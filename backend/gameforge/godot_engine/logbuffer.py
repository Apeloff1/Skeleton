"""logbuffer.py — bounded ring buffer for job output with cursor streaming.

Subscribers read from a monotonically increasing offset, so SSE clients can
poll/tail without re-receiving old lines. Memory is capped per buffer.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class LogLine:
    seq: int
    ts: float
    stream: str  # "stdout" | "stderr" | "system"
    text: str


class LogBuffer:
    def __init__(self, maxlen: int = 2000) -> None:
        self._lines: deque[LogLine] = deque(maxlen=maxlen)
        self._seq = 0

    def append(self, text: str, stream: str = "stdout") -> LogLine:
        self._seq += 1
        line = LogLine(seq=self._seq, ts=time.time(), stream=stream, text=text)
        self._lines.append(line)
        return line

    def since(self, offset: int = 0, limit: int = 500) -> tuple[list[dict], int]:
        """Return (lines with seq > offset, next_offset)."""
        out = [
            {"seq": l.seq, "ts": l.ts, "stream": l.stream, "text": l.text}
            for l in self._lines if l.seq > offset
        ][-limit:]
        return out, self._seq

    def tail(self, n: int = 50) -> list[dict]:
        return [
            {"seq": l.seq, "ts": l.ts, "stream": l.stream, "text": l.text}
            for l in list(self._lines)[-n:]
        ]

    def __len__(self) -> int:
        return len(self._lines)
