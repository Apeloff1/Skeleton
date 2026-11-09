"""Notification center — multi-channel operator notifications.

A notification is a duplicate only after a channel has accepted it.
A failed channel stays on the retry queue. A later flush retries that
channel only, and does not send the alert again to a channel that already
accepted it.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


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
        # Severity is part of the identity. An info alert must not swallow
        # a later critical alert with the same title.
        return hashlib.sha256(
            f"{self.severity}:{self.title}:{self.source}".encode()
        ).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "source": self.source,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass
class _Pending:
    notification: Notification
    channels: set[str] = field(default_factory=set)


SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class NotificationCenter:
    """Multi-channel notification router with dedupe and rate limits."""

    def __init__(self, dedupe_window_s: float = 300.0):
        if isinstance(dedupe_window_s, bool) or not isinstance(dedupe_window_s, (int, float)) or dedupe_window_s < 0:
            raise ValueError("dedupe_window_s must be non-negative")
        self._channels: Dict[str, Channel] = {}
        self._history: List[Dict[str, Any]] = []
        self._dedupe: Dict[str, int] = {}
        self.dedupe_window_s = dedupe_window_s
        self._retry_queue: List[_Pending] = []

    def add_channel(self, name: str, sender: Callable[[Dict[str, Any]], bool],
                    min_severity: str = "info", rate_limit_s: float = 0.0) -> Channel:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("channel name is required")
        if not callable(sender):
            raise TypeError("sender must be callable")
        if min_severity not in SEVERITY_ORDER:
            raise ValueError(f"unknown severity {min_severity!r}")
        if isinstance(rate_limit_s, bool) or not isinstance(rate_limit_s, (int, float)) or rate_limit_s < 0:
            raise ValueError("rate_limit_s must be non-negative")
        ch = Channel(name=name, sender=sender, min_severity=min_severity, rate_limit_s=rate_limit_s)
        self._channels[name] = ch
        return ch

    def remove_channel(self, name: str) -> bool:
        return self._channels.pop(name, None) is not None

    def _is_duplicate(self, notification: Notification) -> bool:
        last = self._dedupe.get(notification.dedupe_key())
        if last is None:
            return False
        return (time.time_ns() - last) / 1e9 < self.dedupe_window_s

    def _remember(self, notification: Notification) -> None:
        self._dedupe[notification.dedupe_key()] = time.time_ns()

    def notify(self, title: str, body: str, severity: str = "info", source: str = "system") -> Dict[str, Any]:
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title is required")
        if not isinstance(body, str):
            raise ValueError("body must be a string")
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"unknown severity {severity!r}")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source is required")
        notification = Notification(
            title=title,
            body=body,
            severity=severity,
            source=source,
            timestamp_ns=time.time_ns(),
        )
        if self._is_duplicate(notification):
            return {"status": "deduplicated", "title": title}
        deliveries: Dict[str, str] = {}
        pending: set[str] = set()
        delivered_any = False
        now = time.time_ns()
        for channel in self._channels.values():
            if SEVERITY_ORDER[severity] < SEVERITY_ORDER[channel.min_severity]:
                continue
            if channel.rate_limit_s and (now - channel.last_sent_ns) / 1e9 < channel.rate_limit_s:
                deliveries[channel.name] = "rate_limited"
                pending.add(channel.name)
                continue
            if self._send(channel, notification, now):
                deliveries[channel.name] = "delivered"
                delivered_any = True
            else:
                deliveries[channel.name] = "failed"
                pending.add(channel.name)
        if delivered_any:
            self._remember(notification)
        if pending:
            self._retry_queue.append(_Pending(notification, pending))
        record = {**notification.to_dict(), "deliveries": deliveries}
        self._history.append(record)
        if len(self._history) > 500:
            self._history.pop(0)
        return record

    def flush_retries(self) -> int:
        finished = 0
        remaining: List[_Pending] = []
        now = time.time_ns()
        for pending in self._retry_queue:
            still: set[str] = set()
            delivered_any = False
            for name in sorted(pending.channels):
                channel = self._channels.get(name)
                if channel is None:
                    continue
                if SEVERITY_ORDER[pending.notification.severity] < SEVERITY_ORDER[channel.min_severity]:
                    continue
                if channel.rate_limit_s and (now - channel.last_sent_ns) / 1e9 < channel.rate_limit_s:
                    still.add(name)
                    continue
                if self._send(channel, pending.notification, now):
                    delivered_any = True
                else:
                    still.add(name)
            if delivered_any:
                self._remember(pending.notification)
            if still:
                remaining.append(_Pending(pending.notification, still))
            else:
                finished += 1
        self._retry_queue = remaining
        return finished

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "notification-card",
            "channels": {
                name: {"delivered": channel.delivered, "failed": channel.failed, "min_severity": channel.min_severity}
                for name, channel in self._channels.items()
            },
            "history": len(self._history),
            "retry_queue": len(self._retry_queue),
        }

    def _send(self, channel: Channel, notification: Notification, now: int) -> bool:
        try:
            accepted = channel.sender(notification.to_dict()) is True
        except Exception:
            accepted = False
        if accepted:
            channel.delivered += 1
            channel.last_sent_ns = now
            return True
        channel.failed += 1
        return False


__all__ = ["Channel", "Notification", "NotificationCenter", "SEVERITY_ORDER"]
