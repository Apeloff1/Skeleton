"""Outbound webhook / callback egress gateway.

Delivery of one callback to one subscription runs through the **same Pack F
pipeline** as inbound s2s traffic, keyed by destination host::

    [backpressure] -> deadline -> retry (shared per-host RetryBudget)
                   -> breaker (per-host, ``egress:<host>``) -> [attempt_timeout]
                   -> sign + transport

* **Allowlist / SSRF guard first** — a URL that fails
  :class:`~skeleton.gate_plane.egress.allowlist.EgressAllowlist` is never
  contacted; the callback is dead-lettered with ``egress_denied:<reason>``.
* **Signed** — Standard Webhooks headers, re-signed per attempt (fresh
  timestamp); ``webhook-id`` doubles as ``Idempotency-Key`` so POST retries
  are allowed by :class:`RetrySpec` and receivers can dedupe.
* **Correlated** — ``x-request-id`` / ``traceparent`` from the bound
  request context (or a fresh root) via :func:`propagate`.
* **Two retry tiers** — fast in-call retries (pipeline, bounded by deadline
  and the per-host retry budget), then slow *redelivery rounds* from the
  outbox on ``redelivery_schedule_s`` (with jitter) up to ``max_age_s``.
  Anything still failing is dead-lettered; DLQ entries can be replayed.
* **Receiver signals** — ``410 Gone`` disables the subscription; ``429`` /
  ``503`` ``Retry-After`` pushes the next round out; 3xx redirects are
  refused (they could bounce the request to an internal address); other
  4xx are permanent and dead-letter immediately.

Pure library code: injectable clock, transport, resolver and RNG; no
background threads (call :meth:`EgressGateway.drain` from a scheduler) and
no edits to ``skeleton/api/server.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import secrets
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple, Union
from urllib.parse import urlsplit

from skeleton.gate_plane.egress.allowlist import EgressAllowlist
from skeleton.gate_plane.egress.dlq import DeadLetter, DeadLetterQueue
from skeleton.gate_plane.egress.signing import SecretSet, WebhookSigner, validate_message_id
from skeleton.gate_plane.egress.transport import Transport, TransportRequest, TransportResponse
from skeleton.gate_plane.hardening.request_id import propagate
from skeleton.gate_plane.pipeline.breaker import BreakerConfig, BreakerRegistry
from skeleton.gate_plane.pipeline.budget import RetryBudgetRegistry
from skeleton.gate_plane.pipeline.core import CallContext, Pipeline, PipelineRequest, PipelineResponse, Stage
from skeleton.gate_plane.pipeline.errors import BreakerOpenError, PipelineError
from skeleton.gate_plane.pipeline.retry import RetrySpec
from skeleton.gate_plane.pipeline.stages import AttemptTimeoutStage, BreakerStage, DeadlineStage, RetryStage
from skeleton.gate_plane.s2s.clock import Clock, system_clock

DEFAULT_REDELIVERY_SCHEDULE_S: Tuple[float, ...] = (5.0, 30.0, 120.0, 600.0, 1800.0, 3600.0)
DEFAULT_MAX_AGE_S = 24 * 3600.0
DEFAULT_MAX_BODY_BYTES = 256 * 1024
MAX_RETRY_AFTER_S = 3600.0
_SUB_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class DeliveryOutcome(str, Enum):
    DELIVERED = "delivered"
    SCHEDULED = "scheduled"
    DEAD_LETTERED = "dead_lettered"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class RedirectRefused(PipelineError):
    status = 502
    reason = "redirect_refused"


class TransportFailure(PipelineError):
    """Wraps a terminal transport error so the pipeline reports it uniformly."""

    status = 502
    reason = "transport_error"


@dataclass
class Subscription:
    id: str
    url: str
    secrets: SecretSet
    event_types: FrozenSet[str] = frozenset({"*"})
    enabled: bool = True
    disabled_reason: str = ""
    tenant_id: Optional[str] = None
    max_age_s: Optional[float] = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _SUB_ID_RE.match(self.id or ""):
            raise ValueError(f"invalid subscription id {self.id!r}")
        for et in self.event_types:
            if et != "*" and not _EVENT_RE.match(et.rstrip("*").rstrip(".") or "x"):
                raise ValueError(f"invalid event type filter {et!r}")
        bad = [k for k in self.headers if k.lower().startswith("webhook-") or k.lower() in ("authorization", "host")]
        if bad:
            raise ValueError(f"subscription headers may not override {bad}")

    def accepts(self, event_type: str) -> bool:
        for et in self.event_types:
            if et == "*" or et == event_type:
                return True
            if et.endswith(".*") and event_type.startswith(et[:-1]):
                return True
        return False

    @property
    def host(self) -> str:
        try:
            return (urlsplit(self.url).hostname or "").lower()
        except ValueError:
            return ""

    def public_view(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "event_types": sorted(self.event_types),
            "enabled": self.enabled,
            "disabled_reason": self.disabled_reason,
            "tenant_id": self.tenant_id,
            "secret_fingerprint": self.secrets.fingerprint(),
        }


@dataclass(frozen=True)
class Callback:
    event_type: str
    body: bytes
    message_id: str
    tenant_id: Optional[str] = None
    priority: int = 1
    created_at: float = 0.0

    @classmethod
    def build(
        cls,
        event_type: str,
        payload: Union[bytes, Mapping[str, Any], List[Any]],
        *,
        message_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        priority: int = 1,
        created_at: float = 0.0,
    ) -> "Callback":
        if not _EVENT_RE.match(event_type or ""):
            raise ValueError(f"invalid event type {event_type!r}")
        if isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(
                {"type": event_type, "data": payload}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        mid = validate_message_id(message_id) if message_id else "msg_" + secrets.token_hex(12)
        return cls(event_type, body, mid, tenant_id, int(priority), float(created_at))

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class DeliveryResult:
    message_id: str
    subscription: str
    outcome: DeliveryOutcome
    reason: str
    status: Optional[int] = None
    attempts: int = 0
    round: int = 1
    next_attempt_at: Optional[float] = None

    @property
    def delivered(self) -> bool:
        return self.outcome is DeliveryOutcome.DELIVERED

    def as_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "subscription": self.subscription,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "status": self.status,
            "attempts": self.attempts,
            "round": self.round,
            "next_attempt_at": self.next_attempt_at,
        }


@dataclass
class OutboxEntry:
    subscription_id: str
    callback: Callback
    first_attempt_at: Optional[float] = None
    rounds: int = 0
    next_attempt_at: float = 0.0
    last_status: Optional[int] = None
    last_reason: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)


DeliveryListener = Callable[[DeliveryResult], None]


class EgressGateway:
    def __init__(
        self,
        allowlist: EgressAllowlist,
        transport: Transport,
        *,
        clock: Optional[Clock] = None,
        signer: Optional[WebhookSigner] = None,
        dlq: Optional[DeadLetterQueue] = None,
        breakers: Optional[BreakerRegistry] = None,
        budgets: Optional[RetryBudgetRegistry] = None,
        retry: Optional[RetrySpec] = None,
        timeout_s: float = 10.0,
        attempt_timeout_s: Optional[float] = 5.0,
        breaker_config: Optional[BreakerConfig] = None,
        backpressure_stage: Optional[Stage] = None,
        redelivery_schedule_s: Iterable[float] = DEFAULT_REDELIVERY_SCHEDULE_S,
        redelivery_jitter: float = 0.1,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        store_bodies_in_dlq: bool = True,
        disable_on_gone: bool = True,
        service: str = "egress",
        rng: Optional[random.Random] = None,
    ) -> None:
        self.allowlist = allowlist
        self.transport = transport
        self.clock: Clock = clock or system_clock()
        self.signer = signer or WebhookSigner(clock=self.clock)
        self.dlq = dlq or DeadLetterQueue(clock=self.clock)
        self.breakers = breakers or BreakerRegistry(clock=self.clock)
        self.budgets = budgets or RetryBudgetRegistry(clock=self.clock, retry_ratio=0.2, min_retries_per_s=1.0)
        self.retry = retry or RetrySpec(max_attempts=3, base_backoff_s=0.2, max_backoff_s=2.0, retry_on_429=False)
        if timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if attempt_timeout_s is not None and attempt_timeout_s > timeout_s:
            raise ValueError("attempt_timeout_s cannot exceed timeout_s")
        self.timeout_s = float(timeout_s)
        self.attempt_timeout_s = attempt_timeout_s
        self.breaker_config = breaker_config or BreakerConfig(
            consecutive_failures=5, failure_rate=0.5, window_size=20, min_calls=10, cooldown_s=30.0,
            cooldown_multiplier=2.0, max_cooldown_s=600.0,
        )
        self.backpressure_stage = backpressure_stage
        schedule = tuple(float(s) for s in redelivery_schedule_s)
        if any(s <= 0 for s in schedule):
            raise ValueError("redelivery delays must be > 0")
        self.redelivery_schedule_s = schedule
        if not 0.0 <= redelivery_jitter <= 0.5:
            raise ValueError("redelivery_jitter must be within [0, 0.5]")
        self.redelivery_jitter = float(redelivery_jitter)
        self.max_age_s = float(max_age_s)
        self.max_body_bytes = int(max_body_bytes)
        self.store_bodies_in_dlq = bool(store_bodies_in_dlq)
        self.disable_on_gone = bool(disable_on_gone)
        self.service = service
        self.rng = rng or random.Random()
        self._subs: Dict[str, Subscription] = {}
        self._outbox: Dict[str, OutboxEntry] = {}
        self._pipelines: Dict[str, Pipeline] = {}
        self._lock = threading.RLock()
        self._counts: Dict[str, int] = {}
        self._listeners: List[DeliveryListener] = []

    # -- registry --------------------------------------------------------

    def register(self, sub: Subscription, *, validate_url: bool = True) -> Subscription:
        if validate_url:
            verdict = self.allowlist.check(sub.url)
            if not verdict.allowed:
                raise ValueError(f"subscription url rejected: {verdict.reason.value}")
        with self._lock:
            self._subs[sub.id] = sub
        return sub

    def subscription(self, sub_id: str) -> Optional[Subscription]:
        with self._lock:
            return self._subs.get(sub_id)

    def subscriptions(self) -> List[Subscription]:
        with self._lock:
            return list(self._subs.values())

    def disable(self, sub_id: str, reason: str) -> None:
        with self._lock:
            sub = self._subs.get(sub_id)
            if sub is not None:
                sub.enabled = False
                sub.disabled_reason = reason

    def enable(self, sub_id: str) -> None:
        with self._lock:
            sub = self._subs.get(sub_id)
            if sub is not None:
                sub.enabled = True
                sub.disabled_reason = ""

    def rotate_secret(self, sub_id: str, new_secret: Any, *, keep: int = 1) -> None:
        with self._lock:
            sub = self._subs[sub_id]
            sub.secrets = sub.secrets.rotate(new_secret, keep=keep)

    def add_listener(self, fn: DeliveryListener) -> None:
        self._listeners.append(fn)

    # -- pipeline ------------------------------------------------------

    def _count(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def pipeline_for(self, host: str) -> Pipeline:
        with self._lock:
            pipe = self._pipelines.get(host)
            if pipe is not None:
                return pipe
            stages: List[Stage] = []
            if self.backpressure_stage is not None:
                stages.append(self.backpressure_stage)
            stages.append(DeadlineStage(self.timeout_s))
            stages.append(RetryStage(self.retry, budget=self.budgets.get(f"egress:{host}"), rng=self.rng))
            stages.append(BreakerStage(self.breakers.get(f"egress:{host}", self.breaker_config), spec=self.retry))
            if self.attempt_timeout_s is not None:
                stages.append(AttemptTimeoutStage(self.attempt_timeout_s))
            pipe = Pipeline(stages, route=f"egress:{host}", upstream=host, clock=self.clock)
            self._pipelines[host] = pipe
            return pipe

    def _handler(self, sub: Subscription, cb: Callback, pinned: Tuple[str, ...]) -> Callable[..., PipelineResponse]:
        def handler(request: PipelineRequest, ctx: CallContext) -> PipelineResponse:
            signed = self.signer.headers(sub.secrets, cb.message_id, cb.body)
            headers = {**dict(request.headers), **signed}
            remaining = ctx.attrs.get("attempt_deadline", ctx.deadline)
            timeout = remaining.remaining() if remaining.bounded else self.timeout_s
            try:
                resp: TransportResponse = self.transport(
                    TransportRequest("POST", sub.url, headers, cb.body, timeout, pinned_addresses=pinned)
                )
            except (ConnectionError, TimeoutError, OSError):
                raise
            except Exception as exc:  # noqa: BLE001 - unknown transport bug: terminal
                raise TransportFailure(type(exc).__name__) from None
            ctx.event("egress_attempt", status=resp.status, subscription=sub.id)
            if 300 <= resp.status < 400:
                raise RedirectRefused(f"receiver answered {resp.status}")
            return PipelineResponse(resp.status, None, resp.headers)

        return handler

    # -- delivery ------------------------------------------------------

    def _emit(self, result: DeliveryResult) -> DeliveryResult:
        self._count(f"outcome:{result.outcome.value}")
        for fn in list(self._listeners):
            try:
                fn(result)
            except Exception:  # noqa: BLE001
                pass
        return result

    def _dead_letter(self, entry: OutboxEntry, sub: Optional[Subscription], reason: str, status: Optional[int]) -> None:
        cb = entry.callback
        now = self.clock.now()
        self.dlq.put(
            DeadLetter(
                message_id=cb.message_id,
                subscription=entry.subscription_id,
                event_type=cb.event_type,
                url=sub.url if sub is not None else "",
                reason=reason,
                attempts=sum(int(h.get("attempts", 0)) for h in entry.history),
                first_attempt_at=entry.first_attempt_at if entry.first_attempt_at is not None else now,
                dead_at=now,
                last_status=status,
                body_sha256=cb.body_sha256,
                body_size=len(cb.body),
                body_b64=base64.b64encode(cb.body).decode("ascii") if self.store_bodies_in_dlq else None,
                history=tuple(entry.history),
            )
        )
        with self._lock:
            self._outbox.pop(cb.message_id, None)

    def _next_delay(self, rounds: int, retry_after: Optional[float]) -> Optional[float]:
        if rounds > len(self.redelivery_schedule_s):
            return None
        base = self.redelivery_schedule_s[rounds - 1]
        if self.redelivery_jitter:
            base *= 1.0 - self.redelivery_jitter + 2 * self.redelivery_jitter * self.rng.random()
        if retry_after is not None:
            base = max(base, min(MAX_RETRY_AFTER_S, retry_after))
        return round(base, 3)

    def enqueue(self, sub_id: str, callback: Callback, *, delay_s: float = 0.0) -> OutboxEntry:
        with self._lock:
            if sub_id not in self._subs:
                raise KeyError(f"unknown subscription {sub_id!r}")
            existing = self._outbox.get(callback.message_id)
            if existing is not None:
                return existing
            entry = OutboxEntry(sub_id, callback, next_attempt_at=self.clock.now() + max(0.0, delay_s))
            self._outbox[callback.message_id] = entry
        self._count("enqueued")
        return entry

    def publish(
        self,
        event_type: str,
        payload: Union[bytes, Mapping[str, Any], List[Any]],
        *,
        tenant_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> List[str]:
        """Fan an event out to every enabled matching subscription (enqueue only)."""
        eid = event_id or "evt_" + secrets.token_hex(10)
        ids: List[str] = []
        for sub in self.subscriptions():
            if not sub.enabled or not sub.accepts(event_type):
                continue
            if sub.tenant_id is not None and tenant_id is not None and sub.tenant_id != tenant_id:
                continue
            mid = f"{eid}:{sub.id}"[:128]
            cb = Callback.build(event_type, payload, message_id=mid, tenant_id=tenant_id, created_at=self.clock.now())
            self.enqueue(sub.id, cb)
            ids.append(mid)
        return ids

    def deliver(self, sub_id: str, callback: Callback) -> DeliveryResult:
        """Enqueue (idempotently) and attempt immediately."""
        entry = self.enqueue(sub_id, callback)
        return self._attempt(entry)

    def due(self) -> List[OutboxEntry]:
        now = self.clock.now()
        with self._lock:
            entries = [e for e in self._outbox.values() if e.next_attempt_at <= now]
        entries.sort(key=lambda e: (e.next_attempt_at, e.callback.priority))
        return entries

    def drain(self, *, max_items: Optional[int] = None) -> List[DeliveryResult]:
        results: List[DeliveryResult] = []
        for entry in self.due():
            if max_items is not None and len(results) >= max_items:
                break
            results.append(self._attempt(entry))
        return results

    def pending(self) -> int:
        with self._lock:
            return len(self._outbox)

    def outbox_entry(self, message_id: str) -> Optional[OutboxEntry]:
        with self._lock:
            return self._outbox.get(message_id)

    def replay(self, message_id: str, *, sub_id: Optional[str] = None) -> OutboxEntry:
        """Move a dead letter back to the outbox (fresh redelivery rounds)."""
        letter = self.dlq.get(message_id)
        if letter is None:
            raise KeyError(f"no dead letter {message_id!r}")
        body = letter.body()
        if body is None:
            raise ValueError("dead letter has no stored body; cannot replay")
        target = sub_id or letter.subscription
        cb = Callback(letter.event_type or "replay", body, letter.message_id, created_at=self.clock.now())
        self.dlq.remove(message_id)
        self._count("replayed")
        return self.enqueue(target, cb)

    def _attempt(self, entry: OutboxEntry) -> DeliveryResult:
        cb = entry.callback
        now = self.clock.now()
        sub = self.subscription(entry.subscription_id)
        if entry.first_attempt_at is None:
            entry.first_attempt_at = now
        entry.rounds += 1
        rnd = entry.rounds

        if sub is None:
            self._dead_letter(entry, None, "subscription_missing", None)
            return self._emit(DeliveryResult(cb.message_id, entry.subscription_id, DeliveryOutcome.DEAD_LETTERED,
                                             "subscription_missing", round=rnd))
        if not sub.enabled:
            self._dead_letter(entry, sub, f"subscription_disabled:{sub.disabled_reason or 'manual'}", None)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.DEAD_LETTERED,
                                             "subscription_disabled", round=rnd))
        if len(cb.body) > self.max_body_bytes:
            self._dead_letter(entry, sub, "body_too_large", None)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.REJECTED, "body_too_large",
                                             round=rnd))
        verdict = self.allowlist.check(sub.url)
        if not verdict.allowed:
            reason = f"egress_denied:{verdict.reason.value}"
            entry.history.append({"round": rnd, "at": now, "attempts": 0, "reason": reason})
            self._dead_letter(entry, sub, reason, None)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.REJECTED, reason, round=rnd))

        host = verdict.host or sub.host
        base_headers = {
            "content-type": "application/json",
            "idempotency-key": cb.message_id,
            **dict(sub.headers),
        }
        headers = propagate(base_headers, service=self.service)
        request = PipelineRequest(
            method="POST", path=urlsplit(sub.url).path or "/", headers=headers, body=cb.body,
            tenant_id=cb.tenant_id or sub.tenant_id, priority=cb.priority, service=self.service,
        )
        pipe = self.pipeline_for(host)
        ctx = pipe.new_context()
        status: Optional[int] = None
        retry_after: Optional[float] = None
        reason = ""
        try:
            resp = pipe.run(request, self._handler(sub, cb, verdict.addresses), ctx=ctx)
            status = resp.status
            ra = resp.header("retry-after")
            if ra is not None:
                try:
                    retry_after = max(0.0, float(ra))
                except ValueError:
                    retry_after = None
            reason = f"status_{status}"
        except BreakerOpenError as exc:
            reason = "circuit_open"
            retry_after = exc.retry_after_s
        except PipelineError as exc:
            reason = exc.reason
        except (ConnectionError, TimeoutError, OSError) as exc:
            reason = f"transport:{type(exc).__name__}"
        attempts = int(ctx.attrs.get("attempts", 1 if status is not None else 0))
        entry.last_status = status
        entry.last_reason = reason
        entry.history.append({"round": rnd, "at": now, "attempts": attempts, "status": status, "reason": reason})

        if status is not None and 200 <= status < 300:
            with self._lock:
                self._outbox.pop(cb.message_id, None)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.DELIVERED, reason, status,
                                             attempts, rnd))
        if status == 410 and self.disable_on_gone:
            self.disable(sub.id, "gone")
            self._dead_letter(entry, sub, "gone", status)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.DEAD_LETTERED, "gone", status,
                                             attempts, rnd))
        permanent = reason in ("redirect_refused", "transport_error") or (
            status is not None and 400 <= status < 500 and status not in (408, 425, 429)
        )
        if permanent:
            self._dead_letter(entry, sub, f"permanent:{reason}", status)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.DEAD_LETTERED,
                                             f"permanent:{reason}", status, attempts, rnd))
        max_age = sub.max_age_s if sub.max_age_s is not None else self.max_age_s
        delay = self._next_delay(rnd, retry_after)
        age_at_next = None if delay is None else (now + delay) - entry.first_attempt_at
        if delay is None or age_at_next is None or age_at_next > max_age:
            self._dead_letter(entry, sub, f"exhausted:{reason}", status)
            return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.DEAD_LETTERED,
                                             f"exhausted:{reason}", status, attempts, rnd))
        entry.next_attempt_at = now + delay
        return self._emit(DeliveryResult(cb.message_id, sub.id, DeliveryOutcome.SCHEDULED, reason, status, attempts,
                                         rnd, next_attempt_at=entry.next_attempt_at))

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counts = dict(self._counts)
            pending = len(self._outbox)
            subs = {s.id: s.public_view() for s in self._subs.values()}
        return {
            "pending": pending,
            "subscriptions": subs,
            "dlq": self.dlq.stats(),
            "breakers": self.breakers.states(),
            "budgets": self.budgets.stats(),
            **counts,
        }


__all__ = [
    "Callback",
    "DEFAULT_REDELIVERY_SCHEDULE_S",
    "DeliveryOutcome",
    "DeliveryResult",
    "EgressGateway",
    "OutboxEntry",
    "RedirectRefused",
    "Subscription",
    "TransportFailure",
]
