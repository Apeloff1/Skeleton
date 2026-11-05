"""Ports (driven side). Adapters: ``sqlite_store``, ``memory_store``, ``transport``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .models import Attempt, Delivery, Event, WebhookSubscription
from .retry import RetryPolicy


class SubscriptionRepository(Protocol):
    def insert(self, sub: WebhookSubscription) -> None: ...
    def get(self, tenant_id: str, webhook_id: str) -> WebhookSubscription | None: ...
    def update(self, sub: WebhookSubscription, expected_version: int) -> bool: ...
    def count_active(self, tenant_id: str) -> int: ...
    def list_page(self, tenant_id: str, limit: int,
                  after: tuple[float, str] | None) -> list[WebhookSubscription]: ...
    def matching(self, tenant_id: str, event_type: str) -> list[WebhookSubscription]: ...


class SecretRepository(Protocol):
    def put(self, secret_id: str, tenant_id: str, secret: bytes, created_at: float) -> None: ...
    def get(self, tenant_id: str, secret_id: str) -> bytes | None: ...


class EventRepository(Protocol):
    def insert_if_new(self, event: Event) -> Event:
        """Insert, or return the existing event with the same (tenant, dedupe_key)."""
    def get(self, tenant_id: str, event_id: str) -> Event | None: ...


class DeliveryRepository(Protocol):
    def insert_many(self, deliveries: Sequence[Delivery]) -> None: ...
    def get(self, tenant_id: str, delivery_id: str) -> Delivery | None: ...
    def claim_due(self, now: float, lease_seconds: float, limit: int) -> list[Delivery]: ...
    def complete(self, delivery: Delivery, attempt: Attempt) -> bool: ...
    def list_page(self, tenant_id: str, webhook_id: str, limit: int,
                  after: tuple[float, str] | None, status: str | None) -> list[Delivery]: ...
    def attempts(self, delivery_id: str) -> list[Attempt]: ...
    def exists_for(self, webhook_id: str, event_id: str) -> bool: ...


@dataclass(frozen=True)
class TransportResult:
    status_code: int | None
    error: str = ""
    duration_ms: float = 0.0


class Transport(Protocol):
    def post(self, url: str, body: bytes, headers: Mapping[str, str],
             timeout: float) -> TransportResult: ...


class UrlPolicy(Protocol):
    def check(self, url: str) -> str:
        """Return a normalised URL or raise ValueError."""


class RetryPolicyRepository(Protocol):
    def get(self, tenant_id: str, webhook_id: str) -> RetryPolicy | None: ...
    def put(self, tenant_id: str, webhook_id: str, policy: RetryPolicy, updated_at: float) -> None: ...
    def delete(self, tenant_id: str, webhook_id: str) -> bool: ...


@dataclass(frozen=True)
class DeliveryQuery:
    """Tenant-scoped delivery-log filter. Time bounds are half-open [since, until)."""
    tenant_id: str
    webhook_id: str | None = None
    event_id: str | None = None
    statuses: tuple[str, ...] = ()
    since: float | None = None
    until: float | None = None
    time_field: str = "created_at"  # or "updated_at" (DLQ: when it died)

    def __post_init__(self) -> None:
        if self.time_field not in ("created_at", "updated_at"):
            raise ValueError("time_field must be created_at or updated_at")


@dataclass(frozen=True)
class AttemptQuery:
    tenant_id: str
    webhook_id: str | None = None
    event_id: str | None = None
    delivery_id: str | None = None
    outcomes: tuple[str, ...] = ()
    since: float | None = None
    until: float | None = None


@dataclass(frozen=True)
class AttemptRecord:
    attempt: Attempt
    webhook_id: str
    event_id: str

    def key(self) -> tuple[float, str]:
        return self.attempt.started_at, f"{self.attempt.delivery_id}:{self.attempt.attempt:04d}"


class DeliveryLogRepository(Protocol):
    def query(self, q: DeliveryQuery, limit: int, after: tuple[float, str] | None) -> list[Delivery]:
        """Ordered by (q.time_field, delivery_id); up to ``limit + 1`` rows."""
    def query_attempts(self, q: AttemptQuery, limit: int,
                       after: tuple[float, str] | None) -> list[AttemptRecord]:
        """Ordered by (started_at, 'dlv_id:NNNN'); up to ``limit + 1`` rows."""
    def open_replay_exists(self, tenant_id: str, delivery_id: str) -> bool: ...
    def purge_dead(self, tenant_id: str, before: float, webhook_id: str | None, limit: int) -> list[str]:
        """Delete dead deliveries (and their attempts) last updated before ``before``."""
