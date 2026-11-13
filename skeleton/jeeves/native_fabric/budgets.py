"""Atomic in-memory admission ledger for bounded native work.

This ledger is a temporary admission gate, not durable recovery custody.
The existing execution spine remains the authority for any native effect.
Oversubscription, overrefund, expired reservations and duplicate identities
fail closed. Reservations are never silently recycled after uncertainty.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import threading
import time
from typing import Callable, Mapping

from .contracts import (
    ContractHold, exact_integer, finite, fingerprint, identifier,
)


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    inference_calls: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    wall_ms: int = 0

    def __post_init__(self):
        for name in (
            "inference_calls", "prompt_tokens", "output_tokens", "tool_calls",
            "bytes_read", "bytes_written", "wall_ms",
        ):
            exact_integer(getattr(self, name), maximum=10**12)

    @property
    def units(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in (
            "inference_calls", "prompt_tokens", "output_tokens", "tool_calls",
            "bytes_read", "bytes_written", "wall_ms",
        )}

    def covers(self, other: "ResourceBudget") -> bool:
        if not isinstance(other, ResourceBudget):
            raise ContractHold("typed budget required")
        return all(self.units[key] >= value for key, value in other.units.items())

    def add(self, other: "ResourceBudget") -> "ResourceBudget":
        if not isinstance(other, ResourceBudget):
            raise ContractHold("typed budget required")
        return ResourceBudget(**{
            key: self.units[key] + value for key, value in other.units.items()
        })

    def subtract(self, other: "ResourceBudget") -> "ResourceBudget":
        if not self.covers(other):
            raise ContractHold("resource reservation cannot overdraw")
        return ResourceBudget(**{
            key: self.units[key] - value for key, value in other.units.items()
        })

    @property
    def empty(self) -> bool:
        return all(value == 0 for value in self.units.values())


@dataclass(frozen=True, slots=True)
class BudgetTicket:
    reservation_id: str
    scope_sha256: str
    approved: ResourceBudget
    consumed: ResourceBudget
    state: str
    created_at: float
    deadline: float
    issue_sequence: int

    def __post_init__(self):
        identifier(self.reservation_id)
        if self.state not in ("reserved", "committed", "held"):
            raise ContractHold("invalid budget ticket lifecycle")
        if not isinstance(self.approved, ResourceBudget) or not isinstance(self.consumed, ResourceBudget):
            raise ContractHold("typed budget quantities required")
        if not self.approved.covers(self.consumed):
            raise ContractHold("consumption exceeds reservation")
        finite(self.created_at, maximum=10**12)
        finite(self.deadline, maximum=10**12)
        if self.deadline <= self.created_at:
            raise ContractHold("reservation deadline must be future")
        exact_integer(self.issue_sequence)
        if self.state == "committed" and self.consumed != self.approved:
            # Partial consumption is allowed in a future verified-release
            # protocol, but not silently here.
            raise ContractHold("finalized resource ledger must reconcile")

    @property
    def checksum(self) -> str:
        return fingerprint({
            "id": self.reservation_id, "scope": self.scope_sha256,
            "approved": self.approved.units, "consumed": self.consumed.units,
            "state": self.state, "sequence": self.issue_sequence,
        })


class BudgetLedger:
    """Serialize access to reservations; never infer safe effects from timeouts."""

    def __init__(
        self, ceiling: ResourceBudget, *,
        clock: Callable[[], float] = time.monotonic,
        maximum_tickets: int = 10000,
    ):
        if not isinstance(ceiling, ResourceBudget):
            raise ContractHold("typed global budget ceiling required")
        exact_integer(maximum_tickets, minimum=1, maximum=100000)
        if not callable(clock):
            raise ContractHold("monotonic clock required")
        self._ceiling = ceiling
        self._available = ceiling
        self._clock = clock
        self._maximum_tickets = maximum_tickets
        self._tickets: dict[str, BudgetTicket] = {}
        self._sequence = 0
        self._lock = threading.RLock()

    @property
    def available(self) -> ResourceBudget:
        with self._lock:
            return self._available

    @property
    def inventory(self) -> tuple[BudgetTicket, ...]:
        with self._lock:
            return tuple(self._tickets[key] for key in sorted(self._tickets))

    def reserve(
        self, reservation_id: str, scope_sha256: str,
        requested: ResourceBudget, *,
        deadline_ms: int,
    ) -> BudgetTicket:
        identifier(reservation_id, "reservation")
        if (type(scope_sha256) is not str or len(scope_sha256) != 64
            or any(c not in "0123456789abcdef" for c in scope_sha256)):
            raise ContractHold("bounded scope digest required")
        exact_integer(deadline_ms, minimum=1, maximum=600000)
        if not isinstance(requested, ResourceBudget) or requested.empty:
            raise ContractHold("nonempty typed reservation required")
        with self._lock:
            if reservation_id in self._tickets:
                raise ContractHold("reservation ID already consumed")
            if len(self._tickets) >= self._maximum_tickets:
                raise ContractHold("admission inventory full")
            if not self._available.covers(requested):
                raise ContractHold("resource ceiling would be exceeded")
            now = finite(self._clock(), maximum=10**12)
            self._sequence += 1
            ticket = BudgetTicket(
                reservation_id, scope_sha256, requested, ResourceBudget(),
                "reserved", now, now + deadline_ms / 1000,
                self._sequence,
            )
            self._tickets[reservation_id] = ticket
            self._available = self._available.subtract(requested)
            return ticket

    def reconcile(
        self, reservation_id: str, actual: ResourceBudget, *,
        authoritative_commit: bool,
    ) -> BudgetTicket:
        identifier(reservation_id)
        if not isinstance(actual, ResourceBudget):
            raise ContractHold("measured resource usage required")
        if authoritative_commit is not True:
            raise ContractHold("cannot settle without confirmed authoritative commit")
        with self._lock:
            ticket = self._tickets.get(reservation_id)
            if ticket is None or ticket.state != "reserved":
                raise ContractHold("no active reservation to reconcile")
            if not ticket.approved.covers(actual):
                raise ContractHold("resource usage exceeds reserved quantity")
            now = finite(self._clock(), maximum=10**12)
            if now >= ticket.deadline:
                raise ContractHold("expired or uncertain reservation cannot auto-refund")
            # The resource budget is a maximum reservation. Unused units are
            # released only after the authoritative native commit proves safe.
            remainder = ticket.approved.subtract(actual)
            self._available = self._available.add(remainder)
            finalized = replace(ticket, consumed=actual,
                                approved=actual, state="committed")
            self._tickets[reservation_id] = finalized
            return finalized

    def quarantine(self, reservation_id: str) -> BudgetTicket:
        identifier(reservation_id)
        with self._lock:
            ticket = self._tickets.get(reservation_id)
            if ticket is None:
                raise ContractHold("unknown reservation cannot be held")
            if ticket.state != "reserved":
                raise ContractHold("terminal ticket cannot change to held")
            held = replace(ticket, state="held")
            self._tickets[reservation_id] = held
            return held

    def assert_consistent(self) -> None:
        with self._lock:
            reserved = ResourceBudget()
            for ticket in self._tickets.values():
                if ticket.state in ("reserved", "held"):
                    reserved = reserved.add(ticket.approved)
                elif ticket.state == "committed":
                    reserved = reserved.add(ticket.consumed)
            if reserved.add(self._available) != self._ceiling:
                raise ContractHold("budget conservation or refund invariant violated")

    def public_snapshot(self) -> dict[str, object]:
        with self._lock:
            self.assert_consistent()
            return {
                "schema": "jeeves.fabric.budget_snapshot.v1",
                "ceiling": self._ceiling.units,
                "available": self._available.units,
                "tickets": len(self._tickets),
                "reserved": sum(x.state == "reserved" for x in self._tickets.values()),
                "held": sum(x.state == "held" for x in self._tickets.values()),
                "committed": sum(x.state == "committed" for x in self._tickets.values()),
                "durable_effects_certified": False,
            }


__all__ = ["ResourceBudget", "BudgetTicket", "BudgetLedger"]
