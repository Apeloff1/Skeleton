"""Domain records for the webhooks resource. Pure data + validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from .errors import validation

EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$")
EVENT_FILTER_RE = re.compile(r"^[a-z][a-z0-9_]*(\.([a-z][a-z0-9_]*|\*)){1,4}$")
MAX_FILTERS = 32
MAX_DESCRIPTION = 280
MAX_PAYLOAD_BYTES = 64 * 1024


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"        # retry scheduled
    DEAD = "dead"            # retries exhausted or permanent failure


TERMINAL = frozenset({DeliveryStatus.SUCCEEDED, DeliveryStatus.DEAD})


@dataclass(frozen=True)
class Scope:
    """Server-derived tenant/actor scope. Never parsed from request bodies."""
    tenant_id: str
    actor_id: str
    role: str = "viewer"

    def key(self) -> str:
        return self.tenant_id


@dataclass(frozen=True)
class WebhookSubscription:
    webhook_id: str
    tenant_id: str
    url: str
    event_filters: tuple[str, ...]
    description: str
    active: bool
    secret_ids: tuple[str, ...]          # newest first; at most two during rotation
    max_attempts: int
    version: int
    created_by: str
    created_at: float
    updated_at: float
    disabled_reason: str = ""

    def matches(self, event_type: str) -> bool:
        if not self.event_filters:
            return True
        return any(filter_matches(f, event_type) for f in self.event_filters)

    def bump(self, now: float, **changes: Any) -> "WebhookSubscription":
        return replace(self, version=self.version + 1, updated_at=now, **changes)


@dataclass(frozen=True)
class Event:
    event_id: str
    tenant_id: str
    event_type: str
    payload: Mapping[str, Any]
    dedupe_key: str
    created_at: float


@dataclass(frozen=True)
class Delivery:
    delivery_id: str
    tenant_id: str
    webhook_id: str
    event_id: str
    status: DeliveryStatus
    attempts: int
    next_attempt_at: float
    lease_until: float
    last_status_code: int | None
    last_error: str
    created_at: float
    updated_at: float
    replay_of: str = ""


@dataclass(frozen=True)
class Attempt:
    delivery_id: str
    attempt: int
    started_at: float
    duration_ms: float
    status_code: int | None
    error: str
    outcome: str  # "success" | "retry" | "dead"


@dataclass(frozen=True)
class SubscriptionDraft:
    url: str
    event_filters: tuple[str, ...] = ()
    description: str = ""
    max_attempts: int = 8
    extra: Mapping[str, Any] = field(default_factory=dict)


def filter_matches(pattern: str, event_type: str) -> bool:
    """``project.*`` matches ``project.created`` but not ``project.build.done``."""
    p, e = pattern.split("."), event_type.split(".")
    if len(p) != len(e):
        return False
    return all(a == "*" or a == b for a, b in zip(p, e))


def validate_filters(filters: Any) -> tuple[str, ...]:
    if filters is None:
        return ()
    if not isinstance(filters, (list, tuple)):
        raise validation("CORE.WEBHOOK.INVALID", "event_filters must be a list", field="event_filters")
    if len(filters) > MAX_FILTERS:
        raise validation("CORE.WEBHOOK.INVALID", "too many event filters",
                         field="event_filters", max=MAX_FILTERS)
    out = []
    for f in filters:
        if not isinstance(f, str) or not EVENT_FILTER_RE.match(f):
            raise validation("CORE.WEBHOOK.INVALID", "invalid event filter", field="event_filters")
        out.append(f)
    return tuple(sorted(set(out)))


def validate_draft(d: SubscriptionDraft) -> SubscriptionDraft:
    if not isinstance(d.description, str) or len(d.description) > MAX_DESCRIPTION:
        raise validation("CORE.WEBHOOK.INVALID", "description too long",
                         field="description", max=MAX_DESCRIPTION)
    if not isinstance(d.max_attempts, int) or not 1 <= d.max_attempts <= 20:
        raise validation("CORE.WEBHOOK.INVALID", "max_attempts must be 1..20", field="max_attempts")
    if d.extra:
        raise validation("CORE.WEBHOOK.INVALID", "unknown fields", fields=sorted(d.extra))
    return replace(d, event_filters=validate_filters(list(d.event_filters)))


def validate_event_type(event_type: Any) -> str:
    if not isinstance(event_type, str) or not EVENT_TYPE_RE.match(event_type):
        raise validation("CORE.EVENT.INVALID", "invalid event type", field="type")
    return event_type
