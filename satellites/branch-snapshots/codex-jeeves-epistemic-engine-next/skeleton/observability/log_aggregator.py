"""Log aggregator — structured log collection with levels and search.

Central structured log sink for all subsystems. Supports levels,
key-value fields, ring-buffer retention per subsystem, tail queries,
full-text search, and severity rollups for the dashboard.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}


@dataclass
class LogRecord:
    timestamp_ns: int
    subsystem: str
    level: str
    message: str
    fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "subsystem": self.subsystem,
            "level": self.level,
            "message": self.message,
            "fields": self.fields,
        }


class LogAggregator:
    """Structured log sink with per-subsystem ring buffers."""

    def __init__(self, capacity_per_subsystem: int = 1000):
        self.capacity = capacity_per_subsystem
        self._buffers: Dict[str, List[LogRecord]] = {}

    def log(self, subsystem: str, level: str, message: str, **fields: Any) -> LogRecord:
        if level not in LEVELS:
            level = "info"
        rec = LogRecord(time.time_ns(), subsystem, level, message, fields)
        buf = self._buffers.setdefault(subsystem, [])
        buf.append(rec)
        if len(buf) > self.capacity:
            buf.pop(0)
        return rec

    def debug(self, subsystem: str, message: str, **fields: Any) -> LogRecord:
        return self.log(subsystem, "debug", message, **fields)

    def info(self, subsystem: str, message: str, **fields: Any) -> LogRecord:
        return self.log(subsystem, "info", message, **fields)

    def warning(self, subsystem: str, message: str, **fields: Any) -> LogRecord:
        return self.log(subsystem, "warning", message, **fields)

    def error(self, subsystem: str, message: str, **fields: Any) -> LogRecord:
        return self.log(subsystem, "error", message, **fields)

    def tail(self, subsystem: Optional[str] = None, n: int = 20,
             min_level: str = "debug") -> List[Dict[str, Any]]:
        threshold = LEVELS.get(min_level, 10)
        subs = [subsystem] if subsystem else list(self._buffers.keys())
        records: List[LogRecord] = []
        for s in subs:
            records.extend(r for r in self._buffers.get(s, []) if LEVELS[r.level] >= threshold)
        records.sort(key=lambda r: r.timestamp_ns)
        return [r.to_dict() for r in records[-n:]]

    def search(self, query: str, subsystem: Optional[str] = None,
               limit: int = 50) -> List[Dict[str, Any]]:
        q = query.lower()
        subs = [subsystem] if subsystem else list(self._buffers.keys())
        hits: List[LogRecord] = []
        for s in subs:
            for r in self._buffers.get(s, []):
                if q in r.message.lower() or any(q in str(v).lower() for v in r.fields.values()):
                    hits.append(r)
        hits.sort(key=lambda r: r.timestamp_ns, reverse=True)
        return [r.to_dict() for r in hits[:limit]]

    def rollup(self) -> Dict[str, Dict[str, int]]:
        out: Dict[str, Dict[str, int]] = {}
        for sub, buf in self._buffers.items():
            counts: Dict[str, int] = {lvl: 0 for lvl in LEVELS}
            for r in buf:
                counts[r.level] += 1
            out[sub] = counts
        return out

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "log-aggregator-card",
            "subsystems": len(self._buffers),
            "total_records": sum(len(b) for b in self._buffers.values()),
            "rollup": self.rollup(),
        }
