"""Notification center — multi-channel operator notifications.

Routes alerts and system events to channels (in-app, webhook,
email-stub, log). Supports severity-based routing rules, rate
limiting per channel, deduplication windows, and delivery tracking
with retry for failed sends.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Channel:
    name: str
    sender: Callable[[Dict[str, Any]], bool]
    min_severity: str = "info"
    rate_limit_s: float = 0.0
    last_sent_ns: int = 0
    delivered: int = 0
    failed: int = 0


@dataclass
class Notification:
    title: str
    body: str
    severity: str
    source: str
    timestamp_ns: int = 0

    def dedupe_key(self) -> str:
        return hashlib.sha256(f"{self.title}:{self.source}".encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "source": self.source,
            "timestamp_ns": self.timestamp_ns,
        }


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class NotificationCenter:
    """Multi-channel notification router with dedupe and rate limits."""

    def __init__(self, dedupe_window_s: float = 300.0):
        self._channels: Dict[str, Channel] = {}
        self._history: List[Dict[str, Any]] = []
        self._dedupe: Dict[str, int] = {}
        self.dedupe_window_s = dedupe_window_s
        self._retry_queue: List[Notification] = []

    def add_channel(self, name: str, sender: Callable[[Dict[str, Any]], bool],
                    min_severity: str = "info", rate_limit_s: float = 0.0) -> Channel:
        ch = Channel(name=name, sender=sender, min_severity=min_severity, rate_limit_s=rate_limit_s)
        self._channels[name] = ch
        return ch

    def remove_channel(self, name: str) -> bool:
        return self._channels.pop(name, None) is not None

    def _is_duplicate(self, n: Notification) -> bool:
        key = n.dedupe_key()
        last = self._dedupe.get(key)
        now = time.time_ns()
        if last and (now - last) / 1e9 < self.dedupe_window_s:
            return True
        self._dedupe[key] = now
        return False

    def notify(self, title: str, body: str, severity: str = "info", source: str = "system") -> Dict[str, Any]:
        n = Notification(title=title, body=body, severity=severity, source=source, timestamp_ns=time.time_ns())
        if self._is_duplicate(n):
            return {"status": "deduplicated", "title": title}
        deliveries: Dict[str, str] = {}
        now = time.time_ns()
        for ch in self._channels.values():
            if SEVERITY_ORDER.get(severity, 0) < SEVERITY_ORDER.get(ch.min_severity, 0):
                continue
            if ch.rate_limit_s and (now - ch.last_sent_ns) / 1e9 < ch.rate_limit_s:
                deliveries[ch.name] = "rate_limited"
                continue
            try:
                ok = ch.sender(n.to_dict())
                if ok:
                    ch.delivered += 1
                    ch.last_sent_ns = now
                    deliveries[ch.name] = "delivered"
                else:
                    ch.failed += 1
                    self._retry_queue.append(n)
                    deliveries[ch.name] = "failed"
            except Exception:  # noqa: BLE001
                ch.failed += 1
                self._retry_queue.append(n)
                deliveries[ch.name] = "error"
        record = {**n.to_dict(), "deliveries": deliveries}
        self._history.append(record)
        if len(self._history) > 500:
            self._history.pop(0)
        return record

    def flush_retries(self) -> int:
        count = 0
        remaining: List[Notification] = []
        for n in self._retry_queue:
            delivered_any = False
            for ch in self._channels.values():
                try:
                    if ch.sender(n.to_dict()):
                        ch.delivered += 1
                        delivered_any = True
                except Exception:  # noqa: BLE001
                    pass
            if delivered_any:
                count += 1
            else:
                remaining.append(n)
        self._retry_queue = remaining
        return count

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "notification-card",
            "channels": {n: {"delivered": c.delivered, "failed": c.failed, "min_severity": c.min_severity} for n, c in self._channels.items()},
            "history": len(self._history),
            "retry_queue": len(self._retry_queue),
        }
