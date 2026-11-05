"""Webhooks application service (driving side of the hexagon).

Use cases: subscription CRUD with optimistic concurrency, secret rotation,
idempotent event publication with fan-out, leased dispatch with retry and
dead-lettering, and manual replay. All reads/writes are tenant-scoped by
the server-derived ``Scope``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from . import signing
from .clock import Clock, iso
from .concurrency import check_if_match
from .errors import CoreError, conflict, forbidden, not_found, precondition_failed, validation
from .ids import is_id, new_id
from .models import (MAX_PAYLOAD_BYTES, TERMINAL, Attempt, Delivery, DeliveryStatus, Event, Scope,
                     SubscriptionDraft, WebhookSubscription, validate_draft, validate_event_type,
                     validate_filters)
from .pagination import CursorCodec, Page, build_page
from .ports import (DeliveryRepository, EventRepository, SecretRepository, SubscriptionRepository,
                    Transport, UrlPolicy)
from .retry import RetryPolicy, classify

WRITE_ROLES = frozenset({"owner", "admin", "editor"})
MAX_ACTIVE_PER_TENANT = 25
ROTATION_GRACE_SECONDS = 24 * 3600.0
UPDATABLE = frozenset({"url", "event_filters", "description", "active", "max_attempts"})


@dataclass(frozen=True)
class CreatedSubscription:
    subscription: WebhookSubscription
    secret: str  # shown exactly once


@dataclass(frozen=True)
class DispatchReport:
    claimed: int
    succeeded: int
    retried: int
    dead: int
    stale: int


class WebhookService:
    def __init__(self, *, subs: SubscriptionRepository, secrets: SecretRepository,
                 events: EventRepository, deliveries: DeliveryRepository, transport: Transport,
                 url_policy: UrlPolicy, clock: Clock, cursor_codec: CursorCodec,
                 retry: RetryPolicy | None = None, lease_seconds: float = 60.0,
                 timeout_seconds: float = 10.0) -> None:
        self.subs, self.secrets, self.events, self.deliveries = subs, secrets, events, deliveries
        self.transport, self.url_policy, self.clock = transport, url_policy, clock
        self.codec, self.retry = cursor_codec, retry or RetryPolicy()
        self.lease_seconds, self.timeout_seconds = lease_seconds, timeout_seconds

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _require_write(scope: Scope) -> None:
        if scope.role not in WRITE_ROLES:
            raise forbidden(required=sorted(WRITE_ROLES))

    def _check_url(self, url: Any) -> str:
        if not isinstance(url, str):
            raise validation("CORE.WEBHOOK.INVALID_URL", "url must be a string", field="url")
        try:
            return self.url_policy.check(url)
        except ValueError as exc:
            raise validation("CORE.WEBHOOK.INVALID_URL", str(exc), field="url") from None

    def _load(self, scope: Scope, webhook_id: str) -> WebhookSubscription:
        if not is_id(webhook_id, "webhook"):
            raise not_found("webhook", webhook_id)
        sub = self.subs.get(scope.tenant_id, webhook_id)
        if sub is None:
            raise not_found("webhook", webhook_id)
        return sub

    def _new_secret(self, tenant_id: str) -> tuple[str, str]:
        raw = signing.new_secret()
        sid = new_id("secret")
        self.secrets.put(sid, tenant_id, signing.secret_bytes(raw), self.clock.now())
        return sid, raw

    def _save(self, old: WebhookSubscription, new: WebhookSubscription) -> WebhookSubscription:
        if not self.subs.update(new, old.version):
            cur = self.subs.get(old.tenant_id, old.webhook_id)
            raise precondition_failed(f'"{old.webhook_id}.{cur.version if cur else 0}"')
        return new

    # -------------------------------------------------------- subscriptions
    def create(self, scope: Scope, draft: SubscriptionDraft) -> CreatedSubscription:
        self._require_write(scope)
        draft = validate_draft(draft)
        url = self._check_url(draft.url)
        if self.subs.count_active(scope.tenant_id) >= MAX_ACTIVE_PER_TENANT:
            raise conflict("CORE.WEBHOOK.LIMIT_REACHED", "too many active webhooks",
                           max=MAX_ACTIVE_PER_TENANT)
        now = self.clock.now()
        sid, raw = self._new_secret(scope.tenant_id)
        sub = WebhookSubscription(
            webhook_id=new_id("webhook"), tenant_id=scope.tenant_id, url=url,
            event_filters=draft.event_filters, description=draft.description, active=True,
            secret_ids=(sid,), max_attempts=draft.max_attempts, version=1,
            created_by=scope.actor_id, created_at=now, updated_at=now)
        self.subs.insert(sub)
        return CreatedSubscription(sub, raw)

    def get(self, scope: Scope, webhook_id: str) -> WebhookSubscription:
        return self._load(scope, webhook_id)

    def list(self, scope: Scope, limit: int, cursor: str | None) -> Page[WebhookSubscription]:
        page_scope = f"webhooks:{scope.tenant_id}"
        after = self.codec.decode(page_scope, cursor) if cursor else None
        rows = self.subs.list_page(scope.tenant_id, limit, after)
        return build_page(rows, limit, lambda s: (s.created_at, s.webhook_id), self.codec, page_scope)

    def update(self, scope: Scope, webhook_id: str, patch: Mapping[str, Any],
               if_match: str | None) -> WebhookSubscription:
        self._require_write(scope)
        sub = self._load(scope, webhook_id)
        check_if_match(if_match, sub.webhook_id, sub.version)
        unknown = set(patch) - UPDATABLE
        if unknown:
            raise validation("CORE.WEBHOOK.INVALID", "unknown fields", fields=sorted(unknown))
        changes: dict[str, Any] = {}
        if "url" in patch:
            changes["url"] = self._check_url(patch["url"])
        if "event_filters" in patch:
            changes["event_filters"] = validate_filters(patch["event_filters"])
        if "description" in patch or "max_attempts" in patch:
            d = validate_draft(SubscriptionDraft(
                url=sub.url, description=patch.get("description", sub.description),
                max_attempts=patch.get("max_attempts", sub.max_attempts)))
            changes["description"], changes["max_attempts"] = d.description, d.max_attempts
        if "active" in patch:
            if not isinstance(patch["active"], bool):
                raise validation("CORE.WEBHOOK.INVALID", "active must be boolean", field="active")
            if patch["active"] and not sub.active and \
                    self.subs.count_active(scope.tenant_id) >= MAX_ACTIVE_PER_TENANT:
                raise conflict("CORE.WEBHOOK.LIMIT_REACHED", "too many active webhooks",
                               max=MAX_ACTIVE_PER_TENANT)
            changes["active"] = patch["active"]
            changes["disabled_reason"] = "" if patch["active"] else "disabled_by_user"
        return self._save(sub, sub.bump(self.clock.now(), **changes))

    def delete(self, scope: Scope, webhook_id: str, if_match: str | None) -> WebhookSubscription:
        """Soft delete: deactivates and records the reason (history stays auditable)."""
        self._require_write(scope)
        sub = self._load(scope, webhook_id)
        check_if_match(if_match, sub.webhook_id, sub.version)
        return self._save(sub, sub.bump(self.clock.now(), active=False, disabled_reason="deleted"))

    def rotate_secret(self, scope: Scope, webhook_id: str,
                      if_match: str | None) -> CreatedSubscription:
        """New secret signs first; previous one keeps co-signing until next rotation."""
        self._require_write(scope)
        sub = self._load(scope, webhook_id)
        check_if_match(if_match, sub.webhook_id, sub.version)
        sid, raw = self._new_secret(scope.tenant_id)
        new = self._save(sub, sub.bump(self.clock.now(), secret_ids=(sid, sub.secret_ids[0])))
        return CreatedSubscription(new, raw)

    # --------------------------------------------------------------- events
    def publish(self, scope: Scope, event_type: str, payload: Any,
                dedupe_key: str | None = None) -> tuple[Event, int, bool]:
        """Record an event once and fan out. Returns (event, deliveries_created, duplicate)."""
        self._require_write(scope)
        validate_event_type(event_type)
        if not isinstance(payload, dict):
            raise validation("CORE.EVENT.INVALID", "payload must be an object", field="data")
        try:
            size = len(json.dumps(payload, separators=(",", ":"), allow_nan=False).encode())
        except (TypeError, ValueError):
            raise validation("CORE.EVENT.INVALID", "payload is not JSON-serialisable", field="data") from None
        if size > MAX_PAYLOAD_BYTES:
            raise validation("CORE.EVENT.INVALID", "payload too large", max_bytes=MAX_PAYLOAD_BYTES)
        if dedupe_key is not None and (not isinstance(dedupe_key, str) or not 1 <= len(dedupe_key) <= 128):
            raise validation("CORE.EVENT.INVALID", "dedupe_key must be 1..128 chars", field="dedupe_key")
        now = self.clock.now()
        eid = new_id("event")
        stored = self.events.insert_if_new(Event(eid, scope.tenant_id, event_type, payload,
                                                 dedupe_key or eid, now))
        if stored.event_id != eid:
            return stored, 0, True
        ds = [Delivery(new_id("delivery"), scope.tenant_id, s.webhook_id, stored.event_id,
                       DeliveryStatus.PENDING, 0, now, 0.0, None, "", now, now)
              for s in self.subs.matching(scope.tenant_id, event_type)]
        self.deliveries.insert_many(ds)
        return stored, len(ds), False

    # ------------------------------------------------------------- dispatch
    def body_for(self, event: Event, delivery: Delivery) -> bytes:
        return json.dumps({"id": event.event_id, "type": event.event_type,
                           "created_at": iso(event.created_at), "delivery_id": delivery.delivery_id,
                           "data": event.payload}, sort_keys=True, separators=(",", ":")).encode()

    def _signing_secrets(self, sub: WebhookSubscription) -> list[bytes]:
        out = []
        for sid in sub.secret_ids:
            s = self.secrets.get(sub.tenant_id, sid)
            if s is not None:
                out.append(s)
        return out

    def dispatch_due(self, limit: int = 50) -> DispatchReport:
        now = self.clock.now()
        claimed = self.deliveries.claim_due(now, self.lease_seconds, limit)
        ok = retried = dead = stale = 0
        for d in claimed:
            outcome = self._attempt(d)
            if outcome == "success":
                ok += 1
            elif outcome == "retry":
                retried += 1
            elif outcome == "dead":
                dead += 1
            else:
                stale += 1
        return DispatchReport(len(claimed), ok, retried, dead, stale)

    def _attempt(self, d: Delivery) -> str:
        start = self.clock.now()
        sub = self.subs.get(d.tenant_id, d.webhook_id)
        event = self.events.get(d.tenant_id, d.event_id)
        n = d.attempts + 1
        if sub is None or event is None or not sub.active:
            reason = "subscription_inactive" if sub is not None and event is not None else "missing_reference"
            return self._finish(d, n, start, None, f"policy:{reason}", "dead", 0.0)
        secrets = self._signing_secrets(sub)
        if not secrets:
            return self._finish(d, n, start, None, "policy:no_secret", "dead", 0.0)
        body = self.body_for(event, d)
        headers = {"Content-Type": "application/json",
                   signing.HEADER: signing.sign(body, secrets, int(start)),
                   "Skeleton-Event-Id": event.event_id, "Skeleton-Event-Type": event.event_type,
                   "Skeleton-Delivery-Id": d.delivery_id, "Skeleton-Delivery-Attempt": str(n)}
        result = self.transport.post(sub.url, body, headers, self.timeout_seconds)
        kind = classify(result.status_code, result.error)
        if kind == "success":
            outcome = "success"
        elif kind == "retry" and n < sub.max_attempts:
            outcome = "retry"
        else:
            outcome = "dead"
        return self._finish(d, n, start, result.status_code, result.error, outcome, result.duration_ms)

    def _finish(self, d: Delivery, n: int, start: float, code: int | None, error: str,
                outcome: str, duration_ms: float) -> str:
        now = self.clock.now()
        status = {"success": DeliveryStatus.SUCCEEDED, "retry": DeliveryStatus.FAILED,
                  "dead": DeliveryStatus.DEAD}[outcome]
        nxt = now + self.retry.delay(d.delivery_id, n) if outcome == "retry" else now
        new = replace(d, status=status, attempts=n, next_attempt_at=nxt, last_status_code=code,
                      last_error=error[:500], updated_at=now)
        if not self.deliveries.complete(new, Attempt(d.delivery_id, n, start, duration_ms, code,
                                                     error[:500], outcome)):
            return "stale"
        return outcome

    # ------------------------------------------------------ delivery queries
    def list_deliveries(self, scope: Scope, webhook_id: str, limit: int, cursor: str | None,
                        status: str | None) -> Page[Delivery]:
        self._load(scope, webhook_id)
        if status is not None and status not in {s.value for s in DeliveryStatus}:
            raise validation("CORE.WEBHOOK.INVALID", "unknown status filter", field="status")
        page_scope = f"deliveries:{scope.tenant_id}:{webhook_id}:{status or ''}"
        after = self.codec.decode(page_scope, cursor) if cursor else None
        rows = self.deliveries.list_page(scope.tenant_id, webhook_id, limit, after, status)
        return build_page(rows, limit, lambda d: (d.created_at, d.delivery_id), self.codec, page_scope)

    def get_delivery(self, scope: Scope, delivery_id: str) -> tuple[Delivery, list[Attempt]]:
        d = self.deliveries.get(scope.tenant_id, delivery_id) if is_id(delivery_id, "delivery") else None
        if d is None:
            raise not_found("delivery", delivery_id)
        return d, self.deliveries.attempts(delivery_id)

    def replay(self, scope: Scope, delivery_id: str) -> Delivery:
        """Re-send a terminal delivery as a new delivery linked by ``replay_of``."""
        self._require_write(scope)
        d, _ = self.get_delivery(scope, delivery_id)
        if d.status not in TERMINAL:
            raise conflict("CORE.DELIVERY.NOT_REPLAYABLE", "delivery is still in progress",
                           status=d.status.value)
        sub = self._load(scope, d.webhook_id)
        if not sub.active:
            raise conflict("CORE.WEBHOOK.DISABLED", "webhook is disabled", webhook_id=sub.webhook_id)
        now = self.clock.now()
        new = Delivery(new_id("delivery"), scope.tenant_id, d.webhook_id, d.event_id,
                       DeliveryStatus.PENDING, 0, now, 0.0, None, "", now, now, replay_of=d.delivery_id)
        self.deliveries.insert_many([new])
        return new


__all__ = ["WebhookService", "CreatedSubscription", "DispatchReport", "CoreError",
           "MAX_ACTIVE_PER_TENANT", "WRITE_ROLES"]
