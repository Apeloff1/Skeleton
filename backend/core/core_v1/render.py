"""Wire representations (JSON-safe dicts). Secrets are never rendered."""
from __future__ import annotations

from .clock import iso
from .concurrency import etag
from .models import Attempt, Delivery, Event, WebhookSubscription


def subscription(s: WebhookSubscription) -> dict:
    return {"id": s.webhook_id, "object": "webhook", "url": s.url,
            "event_filters": list(s.event_filters), "description": s.description,
            "active": s.active, "disabled_reason": s.disabled_reason or None,
            "max_attempts": s.max_attempts, "version": s.version, "etag": etag(s.webhook_id, s.version),
            "secret_count": len(s.secret_ids), "created_by": s.created_by,
            "created_at": iso(s.created_at), "updated_at": iso(s.updated_at)}


def event(e: Event) -> dict:
    return {"id": e.event_id, "object": "event", "type": e.event_type, "data": dict(e.payload),
            "dedupe_key": e.dedupe_key, "created_at": iso(e.created_at)}


def delivery(d: Delivery) -> dict:
    return {"id": d.delivery_id, "object": "delivery", "webhook_id": d.webhook_id,
            "event_id": d.event_id, "status": d.status.value, "attempts": d.attempts,
            "next_attempt_at": iso(d.next_attempt_at) if d.status.value in ("pending", "failed") else None,
            "last_status_code": d.last_status_code, "last_error": d.last_error or None,
            "replay_of": d.replay_of or None, "created_at": iso(d.created_at), "updated_at": iso(d.updated_at)}


def attempt(a: Attempt) -> dict:
    return {"attempt": a.attempt, "started_at": iso(a.started_at), "duration_ms": round(a.duration_ms, 2),
            "status_code": a.status_code, "error": a.error or None, "outcome": a.outcome}
