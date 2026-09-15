"""Webhook system — outbound event delivery with signing and retries.

Subscribers register URLs for event topics. Events are signed with
HMAC, delivered with exponential backoff retries, and every attempt
is recorded. Includes dead-letter capture for permanently failing
endpoints and a replay mechanism for missed events.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Subscription:
    sub_id: str
    topic: str
    url: str
    secret: str
    active: bool = True
    delivered: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub_id": self.sub_id,
            "topic": self.topic,
            "url": self.url,
            "active": self.active,
            "delivered": self.delivered,
            "failed": self.failed,
        }


@dataclass
class Delivery:
    delivery_id: str
    sub_id: str
    topic: str
    payload: Dict[str, Any]
    attempts: int = 0
    max_attempts: int = 5
    status: str = "pending"
    next_attempt_ns: int = 0

    def signature(self, secret: str) -> str:
        body = json.dumps(self.payload, sort_keys=True)
        return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "sub_id": self.sub_id,
            "topic": self.topic,
            "attempts": self.attempts,
            "status": self.status,
        }


class WebhookSystem:
    """Topic-based webhook delivery with HMAC signing and backoff."""

    def __init__(self, sender: Optional[Callable[[str, Dict[str, Any], str], bool]] = None):
        self._subs: Dict[str, Subscription] = {}
        self._deliveries: Dict[str, Delivery] = {}
        self._sender = sender or (lambda url, payload, sig: True)
        self._replay_log: List[Dict[str, Any]] = []

    def subscribe(self, topic: str, url: str, secret: str = "") -> Subscription:
        sub = Subscription(sub_id=uuid.uuid4().hex[:10], topic=topic, url=url, secret=secret or "whsec_default")
        self._subs[sub.sub_id] = sub
        return sub

    def unsubscribe(self, sub_id: str) -> bool:
        return self._subs.pop(sub_id, None) is not None

    def publish(self, topic: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        self._replay_log.append({"topic": topic, "payload": payload, "timestamp_ns": time.time_ns()})
        out = []
        for sub in self._subs.values():
            if sub.topic != topic or not sub.active:
                continue
            d = Delivery(
                delivery_id=uuid.uuid4().hex[:10],
                sub_id=sub.sub_id,
                topic=topic,
                payload=payload,
                next_attempt_ns=time.time_ns(),
            )
            self._deliveries[d.delivery_id] = d
            out.append(d.to_dict())
        return out

    def process_pending(self) -> int:
        now = time.time_ns()
        sent = 0
        for d in self._deliveries.values():
            if d.status != "pending" or d.next_attempt_ns > now:
                continue
            sub = self._subs.get(d.sub_id)
            if not sub:
                d.status = "dead"
                continue
            d.attempts += 1
            sig = d.signature(sub.secret)
            try:
                ok = self._sender(sub.url, d.payload, sig)
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                d.status = "delivered"
                sub.delivered += 1
                sent += 1
            else:
                sub.failed += 1
                if d.attempts >= d.max_attempts:
                    d.status = "dead"
                else:
                    backoff_s = min(2 ** d.attempts, 300)
                    d.next_attempt_ns = now + int(backoff_s * 1e9)
        return sent

    def replay(self, topic: str, since_ns: int = 0) -> int:
        events = [e for e in self._replay_log if e["topic"] == topic and e["timestamp_ns"] >= since_ns]
        for e in events:
            self.publish(topic, e["payload"])
        return len(events)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "webhook-card",
            "subscriptions": [s.to_dict() for s in self._subs.values()],
            "pending": len([d for d in self._deliveries.values() if d.status == "pending"]),
            "dead": len([d for d in self._deliveries.values() if d.status == "dead"]),
            "delivered": sum(s.delivered for s in self._subs.values()),
        }
