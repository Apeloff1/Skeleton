"""In-memory adapters with the same semantics as ``sqlite_store`` (for unit tests)."""
from __future__ import annotations

import threading
from dataclasses import replace
from typing import Sequence

from .idempotency import IdempotencyRecord, StoredResponse
from .models import Attempt, Delivery, DeliveryStatus, Event, WebhookSubscription


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._d: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    def get(self, scope_key: str) -> IdempotencyRecord | None:
        return self._d.get(scope_key)

    def try_lock(self, record: IdempotencyRecord, now: float) -> bool:
        with self._lock:
            cur = self._d.get(record.scope_key)
            if cur is not None and cur.expires_at > now and (cur.response is not None or cur.locked_until > now):
                return False
            self._d[record.scope_key] = record
            return True

    def save_response(self, scope_key: str, response: StoredResponse) -> None:
        with self._lock:
            self._d[scope_key] = replace(self._d[scope_key], response=response, locked_until=0)

    def release(self, scope_key: str) -> None:
        with self._lock:
            cur = self._d.get(scope_key)
            if cur is not None and cur.response is None:
                del self._d[scope_key]


class MemorySubscriptionRepository:
    def __init__(self) -> None:
        self._d: dict[str, WebhookSubscription] = {}

    def insert(self, s: WebhookSubscription) -> None:
        if s.webhook_id in self._d:
            raise KeyError(s.webhook_id)
        self._d[s.webhook_id] = s

    def get(self, tenant_id: str, webhook_id: str) -> WebhookSubscription | None:
        s = self._d.get(webhook_id)
        return s if s and s.tenant_id == tenant_id else None

    def update(self, s: WebhookSubscription, expected_version: int) -> bool:
        cur = self.get(s.tenant_id, s.webhook_id)
        if cur is None or cur.version != expected_version:
            return False
        self._d[s.webhook_id] = s
        return True

    def count_active(self, tenant_id: str) -> int:
        return sum(1 for s in self._d.values() if s.tenant_id == tenant_id and s.active)

    def _sorted(self, tenant_id: str) -> list[WebhookSubscription]:
        return sorted((s for s in self._d.values() if s.tenant_id == tenant_id),
                      key=lambda s: (s.created_at, s.webhook_id))

    def list_page(self, tenant_id, limit, after):
        rows = [s for s in self._sorted(tenant_id) if after is None or (s.created_at, s.webhook_id) > after]
        return rows[: limit + 1]

    def matching(self, tenant_id: str, event_type: str) -> list[WebhookSubscription]:
        return [s for s in self._sorted(tenant_id) if s.active and s.matches(event_type)]


class MemorySecretRepository:
    def __init__(self) -> None:
        self._d: dict[str, tuple[str, bytes]] = {}

    def put(self, secret_id, tenant_id, secret, created_at) -> None:
        self._d[secret_id] = (tenant_id, secret)

    def get(self, tenant_id, secret_id):
        v = self._d.get(secret_id)
        return v[1] if v and v[0] == tenant_id else None


class MemoryEventRepository:
    def __init__(self) -> None:
        self._d: dict[str, Event] = {}
        self._dedupe: dict[tuple[str, str], str] = {}

    def insert_if_new(self, e: Event) -> Event:
        k = (e.tenant_id, e.dedupe_key)
        if k in self._dedupe:
            return self._d[self._dedupe[k]]
        self._d[e.event_id] = e
        self._dedupe[k] = e.event_id
        return e

    def get(self, tenant_id, event_id):
        e = self._d.get(event_id)
        return e if e and e.tenant_id == tenant_id else None


class MemoryDeliveryRepository:
    def __init__(self) -> None:
        self._d: dict[str, Delivery] = {}
        self._attempts: dict[str, list[Attempt]] = {}
        self._lock = threading.Lock()

    def insert_many(self, ds: Sequence[Delivery]) -> None:
        with self._lock:
            for d in ds:
                if not d.replay_of and self.exists_for(d.webhook_id, d.event_id):
                    continue
                self._d.setdefault(d.delivery_id, d)

    def exists_for(self, webhook_id, event_id) -> bool:
        return any(d.webhook_id == webhook_id and d.event_id == event_id and not d.replay_of
                   for d in self._d.values())

    def get(self, tenant_id, delivery_id):
        d = self._d.get(delivery_id)
        return d if d and d.tenant_id == tenant_id else None

    def claim_due(self, now, lease_seconds, limit):
        with self._lock:
            due = [d for d in self._d.values()
                   if (d.status in (DeliveryStatus.PENDING, DeliveryStatus.FAILED) and d.next_attempt_at <= now)
                   or (d.status is DeliveryStatus.IN_FLIGHT and d.lease_until <= now)]
            due.sort(key=lambda d: (d.next_attempt_at, d.delivery_id))
            out = []
            for d in due[:limit]:
                n = replace(d, status=DeliveryStatus.IN_FLIGHT, lease_until=now + lease_seconds, updated_at=now)
                self._d[d.delivery_id] = n
                out.append(n)
            return out

    def complete(self, d: Delivery, a: Attempt) -> bool:
        with self._lock:
            cur = self._d.get(d.delivery_id)
            if cur is None or cur.status is not DeliveryStatus.IN_FLIGHT or cur.attempts != d.attempts - 1:
                return False
            self._d[d.delivery_id] = replace(d, lease_until=0)
            self._attempts.setdefault(d.delivery_id, []).append(a)
            return True

    def list_page(self, tenant_id, webhook_id, limit, after, status):
        rows = sorted((d for d in self._d.values() if d.tenant_id == tenant_id and d.webhook_id == webhook_id
                       and (status is None or d.status.value == status)),
                      key=lambda d: (d.created_at, d.delivery_id))
        rows = [d for d in rows if after is None or (d.created_at, d.delivery_id) > after]
        return rows[: limit + 1]

    def attempts(self, delivery_id):
        return list(self._attempts.get(delivery_id, []))
