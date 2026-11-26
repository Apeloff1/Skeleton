"""Delivery-log queries, DLQ operations, per-subscription retry policy and
secrets-at-rest administration.

Extends :class:`WebhookService` rather than duplicating it: replay/redrive go
through ``WebhookService.replay`` so the "terminal only, webhook active, new
linked delivery" invariants live in one place.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .errors import CoreError, conflict, forbidden, not_found, validation
from .ids import is_id
from .models import Delivery, DeliveryStatus, Scope
from .pagination import CursorCodec, Page, build_page
from .ports import (AttemptQuery, AttemptRecord, DeliveryLogRepository, DeliveryQuery,
                    RetryPolicyRepository)
from .retry import RetryPolicy, policy_from_dict, policy_to_dict
from .service import WebhookService

ADMIN_ROLES = frozenset({"owner", "admin"})
STATUSES = frozenset(s.value for s in DeliveryStatus)
OUTCOMES = frozenset({"success", "retry", "dead"})
MAX_REDRIVE = 100
MAX_PURGE = 1000
MAX_FILTER_VALUES = 5


def _bad(message: str, **ctx: Any) -> CoreError:
    return validation("CORE.DELIVERY_LOG.INVALID_FILTER", message, **ctx)


def parse_time(raw: Any, field: str) -> float | None:
    """ISO-8601 (``Z`` or offset required) or unix seconds; ``None``/'' -> unbounded."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        raise _bad("invalid timestamp", field=field)
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        try:
            value = float(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
            except ValueError:
                raise _bad("timestamp must be ISO-8601 or unix seconds", field=field) from None
            if dt.tzinfo is None:
                raise _bad("timestamp must carry a timezone", field=field)
            value = dt.timestamp()
    else:
        raise _bad("invalid timestamp", field=field)
    if not math.isfinite(value) or not 0 <= value < 1e11:
        raise _bad("timestamp out of range", field=field)
    return value


def parse_set(raw: Any, allowed: frozenset[str], field: str) -> tuple[str, ...]:
    """Comma-separated or list -> sorted unique tuple of allowed values."""
    if raw is None or raw == "" or raw == []:
        return ()
    parts = raw.split(",") if isinstance(raw, str) else raw
    if not isinstance(parts, (list, tuple)):
        raise _bad(f"{field} must be a list", field=field)
    vals = {p.strip() if isinstance(p, str) else p for p in parts}
    vals.discard("")
    if len(vals) > MAX_FILTER_VALUES or not all(isinstance(v, str) and v in allowed for v in vals):
        raise _bad(f"unknown {field} value", field=field, allowed=sorted(allowed))
    return tuple(sorted(vals))


def _window(since: Any, until: Any) -> tuple[float | None, float | None]:
    s, u = parse_time(since, "since"), parse_time(until, "until")
    if s is not None and u is not None and s >= u:
        raise _bad("since must be before until", field="since")
    return s, u


def _digest(obj: Mapping[str, Any]) -> str:
    """Filter fingerprint bound into the cursor so a cursor can't be replayed
    under a different filter (which would skip or repeat rows)."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class RedriveReport:
    requested: int
    redriven: tuple[tuple[str, str], ...]     # (dead delivery id, new delivery id)
    skipped: tuple[tuple[str, str], ...]      # (delivery id, reason)

    def as_dict(self) -> dict:
        return {"requested": self.requested,
                "redriven": [{"delivery_id": a, "replay_id": b} for a, b in self.redriven],
                "skipped": [{"delivery_id": a, "reason": r} for a, r in self.skipped]}


class DeliveryOps:
    def __init__(self, *, webhooks: WebhookService, log: DeliveryLogRepository,
                 policies: RetryPolicyRepository, cursor_codec: CursorCodec,
                 secrets_admin: "SecretsAdmin | None" = None) -> None:
        self.webhooks, self.log, self.policies = webhooks, log, policies
        self.codec = cursor_codec
        self.secrets_admin = secrets_admin

    @property
    def clock(self):
        return self.webhooks.clock

    # ---------------------------------------------------------------- authz
    @staticmethod
    def _require_admin(scope: Scope) -> None:
        if scope.role not in ADMIN_ROLES:
            raise forbidden(required=sorted(ADMIN_ROLES))

    def _check_webhook(self, scope: Scope, webhook_id: str | None) -> None:
        if webhook_id is not None:
            self.webhooks._load(scope, webhook_id)  # tenant-scoped 404

    def _check_event(self, scope: Scope, event_id: str | None) -> None:
        if event_id is None:
            return
        ev = self.webhooks.events.get(scope.tenant_id, event_id) if is_id(event_id, "event") else None
        if ev is None:
            raise not_found("event", event_id)

    # ------------------------------------------------------------ delivery log
    def deliveries(self, scope: Scope, *, limit: int, cursor: str | None = None,
                   webhook_id: str | None = None, event_id: str | None = None,
                   status: Any = None, since: Any = None, until: Any = None,
                   time_field: str = "created_at") -> Page[Delivery]:
        if time_field not in ("created_at", "updated_at"):
            raise _bad("time_field must be created_at or updated_at", field="time_field")
        self._check_webhook(scope, webhook_id)
        self._check_event(scope, event_id)
        statuses = parse_set(status, STATUSES, "status")
        s, u = _window(since, until)
        q = DeliveryQuery(scope.tenant_id, webhook_id, event_id, statuses, s, u, time_field)
        page_scope = "dlog:" + scope.tenant_id + ":" + _digest(
            {"w": webhook_id, "e": event_id, "st": statuses, "s": s, "u": u, "f": time_field})
        after = self.codec.decode(page_scope, cursor) if cursor else None
        rows = self.log.query(q, limit, after)
        return build_page(rows, limit, lambda d: (getattr(d, time_field), d.delivery_id),
                          self.codec, page_scope)

    def attempts(self, scope: Scope, *, limit: int, cursor: str | None = None,
                 webhook_id: str | None = None, event_id: str | None = None,
                 delivery_id: str | None = None, outcome: Any = None,
                 since: Any = None, until: Any = None) -> Page[AttemptRecord]:
        self._check_webhook(scope, webhook_id)
        self._check_event(scope, event_id)
        if delivery_id is not None:
            self.webhooks.get_delivery(scope, delivery_id)
        outcomes = parse_set(outcome, OUTCOMES, "outcome")
        s, u = _window(since, until)
        q = AttemptQuery(scope.tenant_id, webhook_id, event_id, delivery_id, outcomes, s, u)
        page_scope = "alog:" + scope.tenant_id + ":" + _digest(
            {"w": webhook_id, "e": event_id, "d": delivery_id, "o": outcomes, "s": s, "u": u})
        after = self.codec.decode(page_scope, cursor) if cursor else None
        rows = self.log.query_attempts(q, limit, after)
        return build_page(rows, limit, AttemptRecord.key, self.codec, page_scope)

    # -------------------------------------------------------------------- DLQ
    def dlq(self, scope: Scope, *, limit: int, cursor: str | None = None,
            webhook_id: str | None = None, since: Any = None, until: Any = None) -> Page[Delivery]:
        """Dead deliveries ordered by when they died (``updated_at``)."""
        return self.deliveries(scope, limit=limit, cursor=cursor, webhook_id=webhook_id,
                               status="dead", since=since, until=until, time_field="updated_at")

    def redrive(self, scope: Scope, body: Any) -> RedriveReport:
        """Replay dead deliveries, by explicit ids or by filter (webhook/window).

        Idempotent per dead delivery: one that already has an open (non-terminal)
        replay is skipped, so a retried redrive request does not fan out."""
        self.webhooks._require_write(scope)
        if not isinstance(body, dict):
            raise validation("CORE.DLQ.INVALID", "body must be an object")
        unknown = set(body) - {"delivery_ids", "webhook_id", "since", "until", "limit"}
        if unknown:
            raise validation("CORE.DLQ.INVALID", "unknown fields", fields=sorted(unknown))
        ids = body.get("delivery_ids")
        limit = body.get("limit", MAX_REDRIVE)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_REDRIVE:
            raise validation("CORE.DLQ.INVALID", "limit out of range", min=1, max=MAX_REDRIVE)
        if ids is not None:
            if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_REDRIVE
                    or not all(isinstance(i, str) for i in ids)):
                raise validation("CORE.DLQ.INVALID", "delivery_ids must be 1..100 ids", max=MAX_REDRIVE)
            if any(k in body for k in ("webhook_id", "since", "until")):
                raise validation("CORE.DLQ.INVALID", "use either delivery_ids or a filter, not both")
            targets = list(dict.fromkeys(ids))
        else:
            webhook_id = body.get("webhook_id")
            if webhook_id is not None and not isinstance(webhook_id, str):
                raise validation("CORE.DLQ.INVALID", "webhook_id must be a string")
            page = self.dlq(scope, limit=limit, webhook_id=webhook_id,
                            since=body.get("since"), until=body.get("until"))
            targets = [d.delivery_id for d in page.items]
        done, skipped = [], []
        for did in targets:
            d = self.webhooks.deliveries.get(scope.tenant_id, did) if is_id(did, "delivery") else None
            if d is None:
                skipped.append((did, "not_found"))
                continue
            if d.status is not DeliveryStatus.DEAD:
                skipped.append((did, "not_dead"))
                continue
            if self.log.open_replay_exists(scope.tenant_id, did):
                skipped.append((did, "replay_in_progress"))
                continue
            try:
                new = self.webhooks.replay(scope, did)
            except CoreError as exc:
                skipped.append((did, exc.code))
                continue
            done.append((did, new.delivery_id))
        return RedriveReport(len(targets), tuple(done), tuple(skipped))

    def purge(self, scope: Scope, body: Any) -> dict:
        """Hard-delete dead deliveries (and their attempts) that died before a cutoff."""
        self._require_admin(scope)
        if not isinstance(body, dict):
            raise validation("CORE.DLQ.INVALID", "body must be an object")
        unknown = set(body) - {"older_than_seconds", "webhook_id", "limit"}
        if unknown:
            raise validation("CORE.DLQ.INVALID", "unknown fields", fields=sorted(unknown))
        age = body.get("older_than_seconds")
        if isinstance(age, bool) or not isinstance(age, (int, float)) or not 3600 <= age <= 365 * 86400:
            raise validation("CORE.DLQ.INVALID", "older_than_seconds must be in [3600, 31536000]",
                             field="older_than_seconds")
        limit = body.get("limit", MAX_PURGE)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PURGE:
            raise validation("CORE.DLQ.INVALID", "limit out of range", min=1, max=MAX_PURGE)
        webhook_id = body.get("webhook_id")
        if webhook_id is not None:
            if not isinstance(webhook_id, str):
                raise validation("CORE.DLQ.INVALID", "webhook_id must be a string")
            self._check_webhook(scope, webhook_id)
        cutoff = self.clock.now() - float(age)
        purged = self.log.purge_dead(scope.tenant_id, cutoff, webhook_id, limit)
        return {"purged": len(purged), "delivery_ids": purged, "cutoff": cutoff,
                "has_more": len(purged) == limit}

    # ----------------------------------------------------------- retry policy
    def get_policy(self, scope: Scope, webhook_id: str) -> tuple[RetryPolicy, bool]:
        """(effective policy, is_override)."""
        self._check_webhook(scope, webhook_id)
        p = self.policies.get(scope.tenant_id, webhook_id)
        return (p, True) if p is not None else (self.webhooks.retry, False)

    def put_policy(self, scope: Scope, webhook_id: str, body: Any) -> RetryPolicy:
        self.webhooks._require_write(scope)
        self._check_webhook(scope, webhook_id)
        policy = policy_from_dict(body, self.webhooks.retry)
        self.policies.put(scope.tenant_id, webhook_id, policy, self.clock.now())
        return policy

    def delete_policy(self, scope: Scope, webhook_id: str) -> None:
        self.webhooks._require_write(scope)
        self._check_webhook(scope, webhook_id)
        if not self.policies.delete(scope.tenant_id, webhook_id):
            raise not_found("retry_policy", webhook_id)

    # ---------------------------------------------------------- secrets admin
    def _secrets(self, scope: Scope) -> "SecretsAdmin":
        self._require_admin(scope)
        if self.secrets_admin is None:
            raise conflict("CORE.SECRETS.NO_KEYRING", "secrets-at-rest encryption is not configured")
        return self.secrets_admin

    def secrets_status(self, scope: Scope) -> dict:
        return self._secrets(scope).status()

    def secrets_job(self, scope: Scope, job: str, body: Any) -> dict:
        admin = self._secrets(scope)
        body = {} if body is None else body
        if not isinstance(body, dict) or set(body) - {"batch_size", "max_batches", "force"}:
            raise validation("CORE.SECRETS.INVALID_JOB", "expected {batch_size?, max_batches?, force?}")
        bs, mb, force = body.get("batch_size", 200), body.get("max_batches", 10), body.get("force", False)
        for name, v, hi in (("batch_size", bs, 1000), ("max_batches", mb, 100)):
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= hi:
                raise validation("CORE.SECRETS.INVALID_JOB", f"{name} out of range", field=name, max=hi)
        if not isinstance(force, bool):
            raise validation("CORE.SECRETS.INVALID_JOB", "force must be a boolean", field="force")
        return admin.run(job, bs, mb, force)


class SecretsAdmin:
    """Thin adapter over ``SecretMigrator``; one instance per runtime."""

    def __init__(self, migrator) -> None:
        self.m = migrator

    def status(self) -> dict:
        return self.m.status()

    def run(self, job: str, batch_size: int, max_batches: int, force: bool) -> dict:
        if job == "encrypt":
            return self.m.encrypt_plaintext(batch_size, max_batches, force).as_dict()
        if job == "rewrap":
            return self.m.rewrap(batch_size, max_batches, force).as_dict()
        raise ValueError(job)


def render_attempt(r: AttemptRecord) -> dict:
    from . import render
    out = render.attempt(r.attempt)
    out.update({"object": "delivery_attempt", "delivery_id": r.attempt.delivery_id,
                "webhook_id": r.webhook_id, "event_id": r.event_id})
    return out


def render_policy(p: RetryPolicy, webhook_id: str, override: bool) -> dict:
    return {"object": "retry_policy", "webhook_id": webhook_id, "override": override, **policy_to_dict(p)}


__all__ = ["DeliveryOps", "SecretsAdmin", "RedriveReport", "parse_time", "parse_set",
           "render_attempt", "render_policy", "ADMIN_ROLES", "MAX_REDRIVE", "MAX_PURGE"]
