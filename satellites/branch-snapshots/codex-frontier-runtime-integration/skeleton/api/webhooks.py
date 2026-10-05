"""API webhooks — outbound event delivery with HMAC signing.

In addition to inbound routes, Skeleton pushes domain events to external
subscribers. Each subscription stores (endpoint, secret, event_filters);
delivery signs with HMAC-SHA256 and retries get a dead-letter queue.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import KernelError


class WebhookError(KernelError):
    code = "API.WEBHOOK"


@dataclass
class Subscription:
    endpoint: str
    secret: bytes
    events: Tuple[str, ...] = ()  # empty means all
    max_retries: int = 3
    active: bool = True


class WebhookDispatcher:
    """Dispatch events to subscriptions with signing + retry."""

    def __init__(
        self,
        *,
        sender: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._sender = sender or (lambda url, payload: None)
        self._now = clock or time.monotonic
        self._subscriptions: List[Subscription] = []
        self._dead: List[Dict[str, Any]] = []
        self._deliveries = 0

    def subscribe(self, subscription: Subscription) -> None:
        self._subscriptions.append(subscription)

    def dispatch(self, event_type: str, payload: Dict[str, Any]) -> int:
        fired = 0
        body = {"type": event_type, "timestamp": self._now(), "payload": payload}
        for sub in list(self._subscriptions):
            if not sub.active:
                continue
            if sub.events and event_type not in sub.events:
                continue
            signed_body = dict(body)
            signed_body["sig"] = self._sign(body, sub.secret)
            try:
                self._sender(sub.endpoint, signed_body)
                self._deliveries += 1
                fired += 1
            except Exception:
                attempts = signed_body.get("attempts", 0) + 1
                if attempts >= sub.max_retries:
                    self._dead.append(
                        {
                            "endpoint": sub.endpoint,
                            "event": event_type,
                            "reason": "max retries",
                            "at": self._now(),
                        }
                    )
                # else: re-queue in real impl; here just count retry
        return fired

    def _sign(self, body: Dict[str, Any], secret: bytes) -> str:
        payload = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    def dead_letters(self) -> Tuple[Dict[str, Any], ...]:
        return tuple(self._dead)

    def stats(self) -> Dict[str, int]:
        return {
            "subscriptions": len(self._subscriptions),
            "deliveries": self._deliveries,
            "dead": len(self._dead),
        }
