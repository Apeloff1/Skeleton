from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Deque, Iterable, Mapping

from .provider_types import (
    BudgetSnapshot,
    ensure_utc,
    nonnegative,
    positive,
    utcnow,
)


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Static per-route local admission limits.

    These limits are deliberately local and conservative. Provider-reported
    limits may tighten them at runtime, but cannot widen them without an
    explicit policy update.
    """

    request_limit: int = 60
    token_limit: int = 120_000
    concurrency_limit: int = 8
    window_seconds: float = 60.0
    reservation_ttl_seconds: float = 120.0
    max_single_request_tokens: int = 64_000

    def __post_init__(self) -> None:
        for field_name in (
            "request_limit",
            "token_limit",
            "concurrency_limit",
            "max_single_request_tokens",
        ):
            try:
                value = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)
        object.__setattr__(
            self,
            "window_seconds",
            positive(self.window_seconds, name="window_seconds"),
        )
        object.__setattr__(
            self,
            "reservation_ttl_seconds",
            positive(
                self.reservation_ttl_seconds,
                name="reservation_ttl_seconds",
            ),
        )
        if self.max_single_request_tokens > self.token_limit:
            raise ValueError(
                "max_single_request_tokens cannot exceed token_limit"
            )


@dataclass(frozen=True, slots=True)
class UsageEvent:
    occurred_at: datetime
    requests: int = 0
    tokens: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))
        for field_name in ("requests", "tokens"):
            try:
                value = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True, slots=True)
class Reservation:
    reservation_id: str
    route_id: str
    created_at: datetime
    expires_at: datetime
    estimated_tokens: int
    committed: bool = False

    def __post_init__(self) -> None:
        reservation_id = str(self.reservation_id or "").strip()
        route_id = str(self.route_id or "").strip()
        if not reservation_id:
            raise ValueError("reservation_id must not be empty")
        if not route_id:
            raise ValueError("route_id must not be empty")
        object.__setattr__(self, "reservation_id", reservation_id[:200])
        object.__setattr__(self, "route_id", route_id[:160])
        object.__setattr__(self, "created_at", ensure_utc(self.created_at))
        object.__setattr__(self, "expires_at", ensure_utc(self.expires_at))
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        try:
            estimated = int(self.estimated_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("estimated_tokens must be an integer") from exc
        if estimated < 0:
            raise ValueError("estimated_tokens must be non-negative")
        object.__setattr__(self, "estimated_tokens", estimated)


@dataclass(frozen=True, slots=True)
class ReserveResult:
    allowed: bool
    reservation: Reservation | None
    reason: str
    snapshot: BudgetSnapshot
    retry_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed", bool(self.allowed))
        object.__setattr__(self, "reason", str(self.reason or "")[:240])
        if self.retry_at is not None:
            object.__setattr__(self, "retry_at", ensure_utc(self.retry_at))
        if self.allowed and self.reservation is None:
            raise ValueError("allowed reserve result requires a reservation")
        if not self.allowed and self.reservation is not None:
            raise ValueError("rejected reserve result cannot carry reservation")


@dataclass(slots=True)
class _RouteBudgetState:
    policy: BudgetPolicy
    events: Deque[UsageEvent] = field(default_factory=deque)
    reservations: dict[str, Reservation] = field(default_factory=dict)
    active_concurrency: int = 0
    provider_request_limit: int | None = None
    provider_token_limit: int | None = None
    provider_remaining_requests: int | None = None
    provider_remaining_tokens: int | None = None
    provider_reset_at: datetime | None = None

    def effective_request_limit(self) -> int:
        values = [self.policy.request_limit]
        if self.provider_request_limit is not None:
            values.append(max(1, self.provider_request_limit))
        return min(values)

    def effective_token_limit(self) -> int:
        values = [self.policy.token_limit]
        if self.provider_token_limit is not None:
            values.append(max(1, self.provider_token_limit))
        return min(values)


class BudgetLedger:
    """Thread-safe rolling request/token/concurrency admission ledger."""

    def __init__(
        self,
        *,
        default_policy: BudgetPolicy | None = None,
        route_policies: Mapping[str, BudgetPolicy] | None = None,
    ) -> None:
        self.default_policy = default_policy or BudgetPolicy()
        self._states: dict[str, _RouteBudgetState] = {}
        self._route_policies = dict(route_policies or {})
        self._lock = threading.RLock()

    def _state(self, route_id: str) -> _RouteBudgetState:
        key = str(route_id or "").strip()
        if not key:
            raise ValueError("route_id must not be empty")
        state = self._states.get(key)
        if state is None:
            state = _RouteBudgetState(
                policy=self._route_policies.get(key, self.default_policy)
            )
            self._states[key] = state
        return state

    @staticmethod
    def _cutoff(policy: BudgetPolicy, now: datetime) -> datetime:
        return now - timedelta(seconds=policy.window_seconds)

    def _prune_locked(
        self,
        state: _RouteBudgetState,
        now: datetime,
    ) -> None:
        cutoff = self._cutoff(state.policy, now)
        while state.events and state.events[0].occurred_at <= cutoff:
            state.events.popleft()

        expired = [
            reservation_id
            for reservation_id, reservation in state.reservations.items()
            if reservation.expires_at <= now and not reservation.committed
        ]
        for reservation_id in expired:
            state.reservations.pop(reservation_id, None)
            if state.active_concurrency > 0:
                state.active_concurrency -= 1

        if (
            state.provider_reset_at is not None
            and state.provider_reset_at <= now
        ):
            state.provider_remaining_requests = None
            state.provider_remaining_tokens = None
            state.provider_reset_at = None

    @staticmethod
    def _usage_locked(state: _RouteBudgetState) -> tuple[int, int]:
        requests = sum(event.requests for event in state.events)
        tokens = sum(event.tokens for event in state.events)
        reserved_tokens = sum(
            reservation.estimated_tokens
            for reservation in state.reservations.values()
            if not reservation.committed
        )
        return requests, tokens + reserved_tokens

    def _snapshot_locked(
        self,
        route_id: str,
        state: _RouteBudgetState,
        now: datetime,
    ) -> BudgetSnapshot:
        requests, tokens = self._usage_locked(state)
        return BudgetSnapshot(
            route_id=route_id,
            captured_at=now,
            request_limit=state.effective_request_limit(),
            requests_used=requests,
            token_limit=state.effective_token_limit(),
            tokens_used=tokens,
            concurrency_limit=state.policy.concurrency_limit,
            concurrency_used=state.active_concurrency,
            window_seconds=state.policy.window_seconds,
        )

    def snapshot(
        self,
        route_id: str,
        *,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        moment = ensure_utc(now or utcnow())
        with self._lock:
            state = self._state(route_id)
            self._prune_locked(state, moment)
            return self._snapshot_locked(route_id, state, moment)

    def reserve(
        self,
        route_id: str,
        *,
        estimated_tokens: int,
        now: datetime | None = None,
        reservation_id: str | None = None,
    ) -> ReserveResult:
        moment = ensure_utc(now or utcnow())
        try:
            estimate = int(estimated_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("estimated_tokens must be an integer") from exc
        if estimate < 0:
            raise ValueError("estimated_tokens must be non-negative")

        with self._lock:
            state = self._state(route_id)
            self._prune_locked(state, moment)
            snapshot = self._snapshot_locked(route_id, state, moment)

            if estimate > state.policy.max_single_request_tokens:
                return ReserveResult(
                    allowed=False,
                    reservation=None,
                    reason="single-request-token-limit",
                    snapshot=snapshot,
                )

            if state.provider_remaining_requests is not None:
                if state.provider_remaining_requests <= 0:
                    return ReserveResult(
                        allowed=False,
                        reservation=None,
                        reason="provider-request-budget",
                        snapshot=snapshot,
                        retry_at=state.provider_reset_at,
                    )

            if state.provider_remaining_tokens is not None:
                if state.provider_remaining_tokens < estimate:
                    return ReserveResult(
                        allowed=False,
                        reservation=None,
                        reason="provider-token-budget",
                        snapshot=snapshot,
                        retry_at=state.provider_reset_at,
                    )

            if snapshot.requests_used + 1 > snapshot.request_limit:
                return ReserveResult(
                    allowed=False,
                    reservation=None,
                    reason="request-budget",
                    snapshot=snapshot,
                    retry_at=self.next_window_release(route_id, now=moment),
                )

            if snapshot.tokens_used + estimate > snapshot.token_limit:
                return ReserveResult(
                    allowed=False,
                    reservation=None,
                    reason="token-budget",
                    snapshot=snapshot,
                    retry_at=self.next_window_release(route_id, now=moment),
                )

            if state.active_concurrency >= state.policy.concurrency_limit:
                return ReserveResult(
                    allowed=False,
                    reservation=None,
                    reason="concurrency-budget",
                    snapshot=snapshot,
                )

            key = (
                str(reservation_id).strip()
                if reservation_id is not None
                else f"reserve-{uuid.uuid4()}"
            )
            if not key:
                raise ValueError("reservation_id must not be empty")
            if key in state.reservations:
                existing = state.reservations[key]
                if existing.estimated_tokens != estimate:
                    raise ValueError(
                        "reservation_id already exists with different token estimate"
                    )
                return ReserveResult(
                    allowed=True,
                    reservation=existing,
                    reason="idempotent-reservation",
                    snapshot=self._snapshot_locked(route_id, state, moment),
                )

            reservation = Reservation(
                reservation_id=key,
                route_id=route_id,
                created_at=moment,
                expires_at=moment
                + timedelta(seconds=state.policy.reservation_ttl_seconds),
                estimated_tokens=estimate,
            )
            state.reservations[key] = reservation
            state.active_concurrency += 1
            if state.provider_remaining_requests is not None:
                state.provider_remaining_requests = max(
                    0,
                    state.provider_remaining_requests - 1,
                )
            if state.provider_remaining_tokens is not None:
                state.provider_remaining_tokens = max(
                    0,
                    state.provider_remaining_tokens - estimate,
                )

            return ReserveResult(
                allowed=True,
                reservation=reservation,
                reason="reserved",
                snapshot=self._snapshot_locked(route_id, state, moment),
            )

    def commit(
        self,
        reservation_id: str,
        *,
        actual_tokens: int,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        moment = ensure_utc(now or utcnow())
        try:
            tokens = int(actual_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("actual_tokens must be an integer") from exc
        if tokens < 0:
            raise ValueError("actual_tokens must be non-negative")

        with self._lock:
            route_id, state, reservation = self._find_reservation_locked(
                reservation_id
            )
            self._prune_locked(state, moment)
            if reservation_id not in state.reservations:
                raise KeyError(reservation_id)
            if reservation.committed:
                return self._snapshot_locked(route_id, state, moment)
            if tokens > state.policy.max_single_request_tokens:
                raise ValueError("actual_tokens exceeds max_single_request_tokens")

            state.events.append(
                UsageEvent(
                    occurred_at=moment,
                    requests=1,
                    tokens=tokens,
                )
            )
            state.reservations.pop(reservation_id, None)
            if state.active_concurrency > 0:
                state.active_concurrency -= 1
            return self._snapshot_locked(route_id, state, moment)

    def rollback(
        self,
        reservation_id: str,
        *,
        now: datetime | None = None,
        charge_request: bool = True,
        charge_tokens: int = 0,
    ) -> BudgetSnapshot:
        moment = ensure_utc(now or utcnow())
        try:
            token_charge = int(charge_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("charge_tokens must be an integer") from exc
        if token_charge < 0:
            raise ValueError("charge_tokens must be non-negative")

        with self._lock:
            route_id, state, reservation = self._find_reservation_locked(
                reservation_id
            )
            self._prune_locked(state, moment)
            if reservation_id not in state.reservations:
                raise KeyError(reservation_id)
            if reservation.committed:
                return self._snapshot_locked(route_id, state, moment)

            state.reservations.pop(reservation_id, None)
            if state.active_concurrency > 0:
                state.active_concurrency -= 1
            if charge_request or token_charge:
                state.events.append(
                    UsageEvent(
                        occurred_at=moment,
                        requests=1 if charge_request else 0,
                        tokens=token_charge,
                    )
                )
            return self._snapshot_locked(route_id, state, moment)

    def release(
        self,
        reservation_id: str,
        *,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        return self.rollback(
            reservation_id,
            now=now,
            charge_request=False,
            charge_tokens=0,
        )

    def _find_reservation_locked(
        self,
        reservation_id: str,
    ) -> tuple[str, _RouteBudgetState, Reservation]:
        key = str(reservation_id or "").strip()
        if not key:
            raise ValueError("reservation_id must not be empty")
        for route_id, state in self._states.items():
            reservation = state.reservations.get(key)
            if reservation is not None:
                return route_id, state, reservation
        raise KeyError(key)

    def observe_usage(
        self,
        route_id: str,
        *,
        requests: int = 1,
        tokens: int = 0,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        moment = ensure_utc(now or utcnow())
        try:
            request_count = int(requests)
            token_count = int(tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("requests and tokens must be integers") from exc
        if request_count < 0 or token_count < 0:
            raise ValueError("requests and tokens must be non-negative")

        with self._lock:
            state = self._state(route_id)
            self._prune_locked(state, moment)
            state.events.append(
                UsageEvent(
                    occurred_at=moment,
                    requests=request_count,
                    tokens=token_count,
                )
            )
            return self._snapshot_locked(route_id, state, moment)

    def observe_provider_limits(
        self,
        route_id: str,
        *,
        request_limit: int | None = None,
        token_limit: int | None = None,
        remaining_requests: int | None = None,
        remaining_tokens: int | None = None,
        reset_at: datetime | None = None,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        moment = ensure_utc(now or utcnow())
        values = {
            "request_limit": request_limit,
            "token_limit": token_limit,
            "remaining_requests": remaining_requests,
            "remaining_tokens": remaining_tokens,
        }
        parsed: dict[str, int | None] = {}
        for name, raw in values.items():
            if raw is None:
                parsed[name] = None
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer") from exc
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            parsed[name] = value

        with self._lock:
            state = self._state(route_id)
            self._prune_locked(state, moment)
            if parsed["request_limit"] is not None:
                state.provider_request_limit = parsed["request_limit"]
            if parsed["token_limit"] is not None:
                state.provider_token_limit = parsed["token_limit"]
            if parsed["remaining_requests"] is not None:
                state.provider_remaining_requests = parsed["remaining_requests"]
            if parsed["remaining_tokens"] is not None:
                state.provider_remaining_tokens = parsed["remaining_tokens"]
            if reset_at is not None:
                state.provider_reset_at = ensure_utc(reset_at)
            return self._snapshot_locked(route_id, state, moment)

    def clear_provider_limits(
        self,
        route_id: str,
        *,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        moment = ensure_utc(now or utcnow())
        with self._lock:
            state = self._state(route_id)
            state.provider_request_limit = None
            state.provider_token_limit = None
            state.provider_remaining_requests = None
            state.provider_remaining_tokens = None
            state.provider_reset_at = None
            self._prune_locked(state, moment)
            return self._snapshot_locked(route_id, state, moment)

    def next_window_release(
        self,
        route_id: str,
        *,
        now: datetime | None = None,
    ) -> datetime | None:
        moment = ensure_utc(now or utcnow())
        with self._lock:
            state = self._state(route_id)
            self._prune_locked(state, moment)
            candidates: list[datetime] = []
            if state.events:
                candidates.append(
                    state.events[0].occurred_at
                    + timedelta(seconds=state.policy.window_seconds)
                )
            if state.provider_reset_at is not None:
                candidates.append(state.provider_reset_at)
            if not candidates:
                return None
            return max(moment, min(candidates))

    def active_reservations(
        self,
        route_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[Reservation, ...]:
        moment = ensure_utc(now or utcnow())
        with self._lock:
            state = self._state(route_id)
            self._prune_locked(state, moment)
            return tuple(
                sorted(
                    state.reservations.values(),
                    key=lambda reservation: (
                        reservation.created_at,
                        reservation.reservation_id,
                    ),
                )
            )

    def set_policy(
        self,
        route_id: str,
        policy: BudgetPolicy,
        *,
        now: datetime | None = None,
    ) -> BudgetSnapshot:
        if not isinstance(policy, BudgetPolicy):
            raise TypeError("policy must be BudgetPolicy")
        moment = ensure_utc(now or utcnow())
        with self._lock:
            state = self._state(route_id)
            state.policy = policy
            self._route_policies[route_id] = policy
            self._prune_locked(state, moment)
            if state.active_concurrency > policy.concurrency_limit:
                # Existing work is not killed, but new admissions will block
                # until usage naturally drops below the tightened limit.
                pass
            return self._snapshot_locked(route_id, state, moment)

    def policy_for(self, route_id: str) -> BudgetPolicy:
        with self._lock:
            return self._state(route_id).policy

    def route_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._states))

    def snapshots(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[BudgetSnapshot, ...]:
        moment = ensure_utc(now or utcnow())
        with self._lock:
            result: list[BudgetSnapshot] = []
            for route_id in sorted(self._states):
                state = self._states[route_id]
                self._prune_locked(state, moment)
                result.append(
                    self._snapshot_locked(route_id, state, moment)
                )
            return tuple(result)

    def reset_route(
        self,
        route_id: str,
        *,
        preserve_policy: bool = True,
    ) -> None:
        with self._lock:
            state = self._states.get(route_id)
            if state is None:
                return
            policy = state.policy
            self._states.pop(route_id, None)
            if preserve_policy:
                self._route_policies[route_id] = policy
            else:
                self._route_policies.pop(route_id, None)

    def export_state(
        self,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        moment = ensure_utc(now or utcnow())
        with self._lock:
            routes: dict[str, Any] = {}
            for route_id in sorted(self._states):
                state = self._states[route_id]
                self._prune_locked(state, moment)
                routes[route_id] = {
                    "policy": {
                        "request_limit": state.policy.request_limit,
                        "token_limit": state.policy.token_limit,
                        "concurrency_limit": state.policy.concurrency_limit,
                        "window_seconds": state.policy.window_seconds,
                        "reservation_ttl_seconds": state.policy.reservation_ttl_seconds,
                        "max_single_request_tokens": state.policy.max_single_request_tokens,
                    },
                    "events": [
                        {
                            "occurred_at": event.occurred_at.isoformat(),
                            "requests": event.requests,
                            "tokens": event.tokens,
                        }
                        for event in state.events
                    ],
                    "reservations": [
                        {
                            "reservation_id": reservation.reservation_id,
                            "route_id": reservation.route_id,
                            "created_at": reservation.created_at.isoformat(),
                            "expires_at": reservation.expires_at.isoformat(),
                            "estimated_tokens": reservation.estimated_tokens,
                            "committed": reservation.committed,
                        }
                        for reservation in state.reservations.values()
                    ],
                    "active_concurrency": state.active_concurrency,
                    "provider_request_limit": state.provider_request_limit,
                    "provider_token_limit": state.provider_token_limit,
                    "provider_remaining_requests": state.provider_remaining_requests,
                    "provider_remaining_tokens": state.provider_remaining_tokens,
                    "provider_reset_at": (
                        state.provider_reset_at.isoformat()
                        if state.provider_reset_at is not None
                        else None
                    ),
                }
            return {
                "version": 1,
                "captured_at": moment.isoformat(),
                "routes": routes,
            }

    @classmethod
    def from_state(
        cls,
        payload: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> "BudgetLedger":
        if int(payload.get("version", 0)) != 1:
            raise ValueError("unsupported budget ledger state version")
        routes = payload.get("routes", {})
        if not isinstance(routes, Mapping):
            raise ValueError("budget ledger routes must be an object")
        ledger = cls()
        moment = ensure_utc(now or utcnow())
        with ledger._lock:
            for route_id, raw_state in routes.items():
                if not isinstance(raw_state, Mapping):
                    raise ValueError("route state must be an object")
                raw_policy = raw_state.get("policy", {})
                if not isinstance(raw_policy, Mapping):
                    raise ValueError("route policy must be an object")
                policy = BudgetPolicy(
                    request_limit=int(raw_policy.get("request_limit", 60)),
                    token_limit=int(raw_policy.get("token_limit", 120_000)),
                    concurrency_limit=int(raw_policy.get("concurrency_limit", 8)),
                    window_seconds=float(raw_policy.get("window_seconds", 60.0)),
                    reservation_ttl_seconds=float(
                        raw_policy.get("reservation_ttl_seconds", 120.0)
                    ),
                    max_single_request_tokens=int(
                        raw_policy.get("max_single_request_tokens", 64_000)
                    ),
                )
                state = _RouteBudgetState(policy=policy)
                raw_events = raw_state.get("events", [])
                if not isinstance(raw_events, list):
                    raise ValueError("events must be an array")
                for raw_event in raw_events:
                    if not isinstance(raw_event, Mapping):
                        raise ValueError("usage event must be an object")
                    occurred_at = datetime.fromisoformat(
                        str(raw_event["occurred_at"]).replace("Z", "+00:00")
                    )
                    state.events.append(
                        UsageEvent(
                            occurred_at=occurred_at,
                            requests=int(raw_event.get("requests", 0)),
                            tokens=int(raw_event.get("tokens", 0)),
                        )
                    )
                raw_reservations = raw_state.get("reservations", [])
                if not isinstance(raw_reservations, list):
                    raise ValueError("reservations must be an array")
                for raw_reservation in raw_reservations:
                    if not isinstance(raw_reservation, Mapping):
                        raise ValueError("reservation must be an object")
                    reservation = Reservation(
                        reservation_id=str(raw_reservation["reservation_id"]),
                        route_id=str(raw_reservation["route_id"]),
                        created_at=datetime.fromisoformat(
                            str(raw_reservation["created_at"]).replace(
                                "Z",
                                "+00:00",
                            )
                        ),
                        expires_at=datetime.fromisoformat(
                            str(raw_reservation["expires_at"]).replace(
                                "Z",
                                "+00:00",
                            )
                        ),
                        estimated_tokens=int(
                            raw_reservation.get("estimated_tokens", 0)
                        ),
                        committed=bool(raw_reservation.get("committed", False)),
                    )
                    state.reservations[reservation.reservation_id] = reservation
                state.active_concurrency = int(
                    raw_state.get(
                        "active_concurrency",
                        len(state.reservations),
                    )
                )
                for attr in (
                    "provider_request_limit",
                    "provider_token_limit",
                    "provider_remaining_requests",
                    "provider_remaining_tokens",
                ):
                    raw = raw_state.get(attr)
                    setattr(state, attr, int(raw) if raw is not None else None)
                raw_reset = raw_state.get("provider_reset_at")
                if raw_reset:
                    state.provider_reset_at = datetime.fromisoformat(
                        str(raw_reset).replace("Z", "+00:00")
                    )
                ledger._states[str(route_id)] = state
                ledger._route_policies[str(route_id)] = policy
                ledger._prune_locked(state, moment)
        return ledger


@dataclass(frozen=True, slots=True)
class RetryBudgetPolicy:
    max_total_attempts: int = 6
    max_same_route_attempts: int = 3
    max_fallback_attempts: int = 3
    max_total_delay_seconds: float = 90.0
    max_single_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        for field_name in (
            "max_total_attempts",
            "max_same_route_attempts",
            "max_fallback_attempts",
        ):
            try:
                value = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if value < 1:
                raise ValueError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)
        if self.max_same_route_attempts > self.max_total_attempts:
            raise ValueError(
                "max_same_route_attempts cannot exceed max_total_attempts"
            )
        if self.max_fallback_attempts > self.max_total_attempts:
            raise ValueError(
                "max_fallback_attempts cannot exceed max_total_attempts"
            )
        object.__setattr__(
            self,
            "max_total_delay_seconds",
            positive(
                self.max_total_delay_seconds,
                name="max_total_delay_seconds",
            ),
        )
        object.__setattr__(
            self,
            "max_single_delay_seconds",
            positive(
                self.max_single_delay_seconds,
                name="max_single_delay_seconds",
            ),
        )


@dataclass(slots=True)
class RetryBudget:
    policy: RetryBudgetPolicy = field(default_factory=RetryBudgetPolicy)
    attempts_total: int = 0
    attempts_by_route: dict[str, int] = field(default_factory=dict)
    accumulated_delay_seconds: float = 0.0
    fallback_attempts: int = 0

    def may_attempt(
        self,
        route_id: str,
        *,
        is_fallback: bool,
    ) -> bool:
        if self.attempts_total >= self.policy.max_total_attempts:
            return False
        route_attempts = self.attempts_by_route.get(route_id, 0)
        if route_attempts >= self.policy.max_same_route_attempts:
            return False
        if is_fallback and self.fallback_attempts >= self.policy.max_fallback_attempts:
            return False
        return True

    def record_attempt(
        self,
        route_id: str,
        *,
        is_fallback: bool,
    ) -> None:
        if not self.may_attempt(route_id, is_fallback=is_fallback):
            raise PermissionError("retry budget does not admit another attempt")
        self.attempts_total += 1
        self.attempts_by_route[route_id] = (
            self.attempts_by_route.get(route_id, 0) + 1
        )
        if is_fallback:
            self.fallback_attempts += 1

    def may_delay(self, delay_seconds: float) -> bool:
        delay = nonnegative(delay_seconds, name="delay_seconds")
        if delay > self.policy.max_single_delay_seconds:
            return False
        return (
            self.accumulated_delay_seconds + delay
            <= self.policy.max_total_delay_seconds
        )

    def record_delay(self, delay_seconds: float) -> None:
        delay = nonnegative(delay_seconds, name="delay_seconds")
        if not self.may_delay(delay):
            raise PermissionError("retry delay budget exhausted")
        self.accumulated_delay_seconds += delay

    @property
    def exhausted(self) -> bool:
        return self.attempts_total >= self.policy.max_total_attempts

    def as_json(self) -> dict[str, Any]:
        return {
            "policy": {
                "max_total_attempts": self.policy.max_total_attempts,
                "max_same_route_attempts": self.policy.max_same_route_attempts,
                "max_fallback_attempts": self.policy.max_fallback_attempts,
                "max_total_delay_seconds": self.policy.max_total_delay_seconds,
                "max_single_delay_seconds": self.policy.max_single_delay_seconds,
            },
            "attempts_total": self.attempts_total,
            "attempts_by_route": dict(sorted(self.attempts_by_route.items())),
            "accumulated_delay_seconds": self.accumulated_delay_seconds,
            "fallback_attempts": self.fallback_attempts,
            "exhausted": self.exhausted,
        }


__all__ = [
    "BudgetLedger",
    "BudgetPolicy",
    "Reservation",
    "ReserveResult",
    "RetryBudget",
    "RetryBudgetPolicy",
    "UsageEvent",
]
