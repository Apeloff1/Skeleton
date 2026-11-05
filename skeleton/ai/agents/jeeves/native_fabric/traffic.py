"""Fair, bounded offline native request traffic without speculative model retries.

This is a host-side admission scheduler. Actual model execution, grant
checking, durable intent, session ownership, effect custody and replay are
owned by the canonical native execution spine. A queue ticket cannot create
a provider, authorize a tool or turn an uncertain effect into a new request.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from hashlib import sha256
import math
import threading
import time
from typing import Callable, Mapping, Sequence

from .contracts import (
    ContractHold, canonical_bytes, digest, exact_integer, finite,
    fingerprint, identifier, text,
)


class TrafficHold(ContractHold):
    """A request is ambiguous, unapproved or outside local admission limits."""


@dataclass(frozen=True, slots=True)
class TrafficRequest:
    request_id: str
    scope_sha256: str
    prompt_sha256: str
    session_id: str
    output_token_ceiling: int
    priority: int
    created_ns: int
    deadline_ns: int
    cohort: str = "default"
    tool_actions_allowed: bool = False

    def __post_init__(self):
        identifier(self.request_id, "request")
        digest(self.scope_sha256)
        digest(self.prompt_sha256)
        identifier(self.session_id, "session")
        exact_integer(self.output_token_ceiling, minimum=1, maximum=8192)
        exact_integer(self.priority, maximum=1000)
        exact_integer(self.created_ns, maximum=10**30)
        exact_integer(self.deadline_ns, maximum=10**30)
        if self.deadline_ns <= self.created_ns:
            raise TrafficHold("request deadline predates admission")
        identifier(self.cohort, "cohort")
        if type(self.tool_actions_allowed) is not bool:
            raise TrafficHold("strict tool action consent required")

    @property
    def binding(self) -> str:
        return fingerprint({
            "schema": "jeeves.fabric.traffic_request.v1",
            "request_id": self.request_id,
            "scope": self.scope_sha256,
            "prompt": self.prompt_sha256,
            "session": self.session_id,
            "output": self.output_token_ceiling,
            "cohort": self.cohort,
            "tools": self.tool_actions_allowed,
        })


@dataclass(frozen=True, slots=True)
class TrafficTicket:
    request: TrafficRequest
    state: str
    sequence: int
    claimed_ns: int | None = None
    completed_ns: int | None = None
    committed_receipt_sha256: str | None = None
    hold_code: str | None = None

    def __post_init__(self):
        if not isinstance(self.request, TrafficRequest):
            raise TrafficHold("typed traffic request required")
        if self.state not in ("queued", "claimed", "committed", "held", "cancelled"):
            raise TrafficHold("unknown traffic ticket lifecycle")
        exact_integer(self.sequence, minimum=1)
        if self.claimed_ns is not None:
            exact_integer(self.claimed_ns, maximum=10**30)
        if self.completed_ns is not None:
            exact_integer(self.completed_ns, maximum=10**30)
        if self.committed_receipt_sha256 is not None:
            digest(self.committed_receipt_sha256)
        if self.hold_code is not None:
            identifier(self.hold_code, "hold code")
        if self.state == "committed":
            if self.committed_receipt_sha256 is None or self.completed_ns is None:
                raise TrafficHold("committed ticket requires authoritative receipt")
        elif self.committed_receipt_sha256 is not None:
            raise TrafficHold("uncommitted ticket cannot claim a native receipt")


class FairTrafficQueue:
    """In-process fair cohorts with no implicit dequeue of uncertain effects.

    Applications should persist higher-level admission intentions in the
    already reviewed SQLite durable custody. This queue's process memory
    cannot be used to claim restart-safe exactly-once execution.
    """

    def __init__(
        self, *, maximum_pending: int = 10000,
        maximum_active: int = 4,
        maximum_per_scope: int = 1,
        maximum_cohorts: int = 128,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ):
        exact_integer(maximum_pending, minimum=1, maximum=100000)
        exact_integer(maximum_active, minimum=1, maximum=10000)
        exact_integer(maximum_per_scope, minimum=1, maximum=1000)
        exact_integer(maximum_cohorts, minimum=1, maximum=1000)
        if not callable(clock_ns):
            raise TrafficHold("monotonic native request clock required")
        self.maximum_pending = maximum_pending
        self.maximum_active = maximum_active
        self.maximum_per_scope = maximum_per_scope
        self.maximum_cohorts = maximum_cohorts
        self.clock_ns = clock_ns
        self._tickets: dict[str, TrafficTicket] = {}
        self._cohorts: dict[str, deque[str]] = {}
        self._rotation: deque[str] = deque()
        self._active: set[str] = set()
        self._seq = 0
        self._lock = threading.RLock()

    def _now(self) -> int:
        value = self.clock_ns()
        exact_integer(value, maximum=10**30)
        return value

    def _pending_count(self) -> int:
        return sum(t.state == "queued" for t in self._tickets.values())

    def submit(self, request: TrafficRequest) -> TrafficTicket:
        if not isinstance(request, TrafficRequest):
            raise TrafficHold("typed native traffic request required")
        with self._lock:
            now = self._now()
            if now >= request.deadline_ns:
                raise TrafficHold("request already expired before admission")
            if request.request_id in self._tickets:
                raise TrafficHold("request identity already allocated")
            if self._pending_count() >= self.maximum_pending:
                raise TrafficHold("bounded native request queue full")
            if (request.cohort not in self._cohorts
                and len(self._cohorts) >= self.maximum_cohorts):
                raise TrafficHold("cohort inventory exceeded")
            self._seq += 1
            ticket = TrafficTicket(request, "queued", self._seq)
            self._tickets[request.request_id] = ticket
            if request.cohort not in self._cohorts:
                self._cohorts[request.cohort] = deque()
                self._rotation.append(request.cohort)
            self._cohorts[request.cohort].append(request.request_id)
            return ticket

    def _expire(self, now: int) -> None:
        for key, ticket in tuple(self._tickets.items()):
            if ticket.state == "queued" and now >= ticket.request.deadline_ns:
                self._tickets[key] = replace(
                    ticket, state="cancelled", completed_ns=now,
                    hold_code="admission_expired",
                )
            elif ticket.state == "claimed" and now >= ticket.request.deadline_ns:
                # A claim may have entered a native generation. Never
                # auto-release capacity as if the effect never happened.
                self._tickets[key] = replace(
                    ticket, state="held", completed_ns=now,
                    hold_code="unknown_native_effect",
                )

    def claim_next(self) -> TrafficTicket | None:
        with self._lock:
            now = self._now()
            self._expire(now)
            if len(self._active) >= self.maximum_active:
                return None
            if not self._rotation:
                return None
            cohort_count = len(self._rotation)
            for _ in range(cohort_count):
                cohort = self._rotation[0]
                self._rotation.rotate(-1)
                queue = self._cohorts[cohort]
                # Clear retired IDs and find the highest priority ready
                # candidate within the cohort, then rotate across cohorts.
                while queue and self._tickets[queue[0]].state != "queued":
                    queue.popleft()
                if not queue:
                    continue
                feasible = []
                active_scopes = {}
                for rid in self._active:
                    ticket = self._tickets[rid]
                    active_scopes[ticket.request.scope_sha256] = (
                        active_scopes.get(ticket.request.scope_sha256, 0) + 1
                    )
                for rid in queue:
                    ticket = self._tickets[rid]
                    if ticket.state != "queued":
                        continue
                    if active_scopes.get(ticket.request.scope_sha256, 0) >= self.maximum_per_scope:
                        continue
                    feasible.append(ticket)
                if not feasible:
                    continue
                best = min(
                    feasible, key=lambda x: (-x.request.priority, x.sequence),
                )
                queue.remove(best.request.request_id)
                claimed = replace(best, state="claimed", claimed_ns=now)
                self._tickets[best.request.request_id] = claimed
                self._active.add(best.request.request_id)
                return claimed
            return None

    def commit(
        self, request_id: str, *,
        authoritative_receipt_sha256: str,
    ) -> TrafficTicket:
        identifier(request_id, "request")
        digest(authoritative_receipt_sha256)
        with self._lock:
            ticket = self._tickets.get(request_id)
            if ticket is None or ticket.state != "claimed":
                raise TrafficHold("no active native claim to commit")
            now = self._now()
            if now >= ticket.request.deadline_ns:
                self._tickets[request_id] = replace(
                    ticket, state="held", completed_ns=now,
                    hold_code="commit_after_deadline",
                )
                raise TrafficHold("late native completion requires reconciliation")
            committed = replace(
                ticket, state="committed", completed_ns=now,
                committed_receipt_sha256=authoritative_receipt_sha256,
            )
            self._tickets[request_id] = committed
            self._active.discard(request_id)
            return committed

    def hold(self, request_id: str, *, code: str = "effect_uncertain") -> TrafficTicket:
        identifier(request_id, "request")
        identifier(code, "hold code")
        with self._lock:
            ticket = self._tickets.get(request_id)
            if ticket is None or ticket.state != "claimed":
                raise TrafficHold("only claimed native requests can enter custody hold")
            held = replace(
                ticket, state="held", completed_ns=self._now(),
                hold_code=code,
            )
            self._tickets[request_id] = held
            # Keep an in-process slot held as a fail-closed signal; only
            # a separate authorized recovery lane can reconcile effects.
            return held

    def cancel_before_claim(self, request_id: str) -> TrafficTicket:
        identifier(request_id, "request")
        with self._lock:
            ticket = self._tickets.get(request_id)
            if ticket is None or ticket.state != "queued":
                raise TrafficHold("cannot cancel a possibly executing request")
            cancelled = replace(
                ticket, state="cancelled", completed_ns=self._now(),
                hold_code="operator_cancelled_before_claim",
            )
            self._tickets[request_id] = cancelled
            return cancelled

    def inspect(self, request_id: str) -> TrafficTicket:
        identifier(request_id)
        with self._lock:
            ticket = self._tickets.get(request_id)
            if ticket is None:
                raise TrafficHold("native request not found")
            return ticket

    def inventory(self) -> tuple[TrafficTicket, ...]:
        with self._lock:
            return tuple(
                sorted(self._tickets.values(), key=lambda x: x.sequence)
            )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            self._expire(self._now())
            counts = {
                state: sum(x.state == state for x in self._tickets.values())
                for state in ("queued", "claimed", "committed", "held", "cancelled")
            }
            return {
                "schema": "jeeves.fabric.traffic_snapshot.v1",
                "counts": counts,
                "active_slots": len(self._active),
                "active_cohorts": sum(bool(q) for q in self._cohorts.values()),
                "max_pending": self.maximum_pending,
                "max_active": self.maximum_active,
                "max_per_scope": self.maximum_per_scope,
                "durable_restart_qualified": False,
                "native_effects_reconciled": False,
                "release_certified": False,
            }


__all__ = [
    "TrafficHold", "TrafficRequest", "TrafficTicket", "FairTrafficQueue",
]
