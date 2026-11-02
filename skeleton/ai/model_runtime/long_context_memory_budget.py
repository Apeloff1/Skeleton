"""Cooperative, non-authorizing RAM reservations for guarded offline inference.

This process-local ledger binds an independently verified principal to a
bounded memory request. It does not allocate RAM or grant model execution.
Every claim re-observes kernel memory; restart/fork loses all reservations.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from secrets import token_hex
from threading import Lock
from time import monotonic_ns
from typing import Callable

from .long_context_memory_envelope import observe_memory_envelope
from .long_context_spool import LongContextSpoolError

_MAX = 2**63 - 1


def _bounded(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise LongContextSpoolError("invalid " + name)
    return value


@dataclass(frozen=True, slots=True)
class MemoryBudgetRequest:
    principal: str
    stream_id: str
    requested_bytes: int

    def __post_init__(self) -> None:
        for name, value in (("principal", self.principal), ("stream", self.stream_id)):
            if (type(value) is not str or not 1 <= len(value) <= 96
                    or not value[0].isascii() or not value[0].isalnum()
                    or not all(c.isascii() and (c.isalnum() or c in "_.-") for c in value)):
                raise LongContextSpoolError("invalid " + name)
        _bounded(self.requested_bytes, "memory bytes", 1, 1024**3)


@dataclass(frozen=True, slots=True)
class MemoryBudgetLimits:
    max_active: int = 8
    max_bytes: int = 512 * 1024**2
    max_bytes_per_principal: int = 256 * 1024**2
    lifetime_ns: int = 1_000_000_000

    def __post_init__(self) -> None:
        _bounded(self.max_active, "active memory reservations", 1, 64)
        _bounded(self.max_bytes, "memory budget", 1, 1024**3)
        _bounded(self.max_bytes_per_principal, "principal memory budget", 1, 1024**3)
        _bounded(self.lifetime_ns, "memory reservation lifetime", 1, 5_000_000_000)


@dataclass(slots=True)
class _Entry:
    request: MemoryBudgetRequest
    expires_ns: int
    state: str = "reserved"


class LongContextMemoryBudgetGuard:
    """absent -> reserved -> claimed -> released/expired/revoked.

    Caller verifier is trusted, synchronous, and non-reentrant. In-process
    locking prevents this guard's own overbooking; external allocators and
    other processes are outside its authority and must independently gate.
    """

    def __init__(
        self, verifier: Callable[[MemoryBudgetRequest], bool], *,
        observer: Callable[..., dict[str, object]] = observe_memory_envelope,
        limits: MemoryBudgetLimits = MemoryBudgetLimits(),
        clock: Callable[[], int] = monotonic_ns,
    ) -> None:
        if not callable(verifier) or not callable(observer) or not callable(clock):
            raise LongContextSpoolError("invalid memory guard callback")
        if not isinstance(limits, MemoryBudgetLimits):
            raise LongContextSpoolError("invalid memory limits")
        self._verifier, self._observer = verifier, observer
        self._clock, self._limits = clock, limits
        self._pid = os.getpid()
        self._lock = Lock()
        self._last_ns: int | None = None
        self._entries: dict[str, _Entry] = {}
        self._closed = False
        self._revocations = 0

    def _pid_guard(self) -> None:
        if os.getpid() != self._pid:
            raise LongContextSpoolError("memory guard inherited across fork")

    def _open(self) -> None:
        self._pid_guard()
        if self._closed:
            raise LongContextSpoolError("memory guard closed")

    def _revoke_all(self) -> None:
        self._revocations += len(self._entries)
        self._entries.clear()

    def _now(self) -> int:
        try:
            value = self._clock()
        except Exception as exc:
            self._revoke_all()
            raise LongContextSpoolError("memory guard clock unavailable") from exc
        if (type(value) is not int or not 0 <= value <= _MAX
                or (self._last_ns is not None and value <= self._last_ns)):
            self._revoke_all()
            raise LongContextSpoolError("memory guard clock regressed")
        self._last_ns = value
        expired = [key for key, item in self._entries.items()
                   if item.expires_ns <= value]
        for key in expired:
            del self._entries[key]
        self._revocations += len(expired)
        return value

    def _authorized(self, request: MemoryBudgetRequest) -> bool:
        try:
            return self._verifier(request) is True
        except Exception:
            return False

    def _headroom(self, required: int) -> bool:
        try:
            result = self._observer(requested_bytes=required)
            if type(result) is not dict or result.get("schema") != (
                "skeleton.ai.long-context-memory-envelope.v1"
            ):
                return False
            for name in ("device_qualified", "is_admission_grant",
                         "is_execution_lease", "is_memory_reservation",
                         "cross_source_snapshot_atomic"):
                if result.get(name) is not False:
                    return False
            if result.get("requires_live_backend_revalidation") is not True:
                return False
            if result.get("state") != "observed_headroom" or (
                result.get("reason") != "observed_only"
            ):
                return False
            headroom = result.get("observed_headroom_bytes")
            requested = result.get("requested_bytes")
            if (type(headroom) is not int or not 0 <= headroom <= _MAX
                    or type(requested) is not int or requested != required
                    or result.get("request_observed_sufficient") is not (required <= headroom)):
                return False
            host = result.get("host_available_bytes")
            group = result.get("cgroup_remaining_bytes")
            host_total = result.get("host_total_bytes")
            group_limit = result.get("cgroup_effective_limit_bytes")
            reserve = result.get("reserve_bytes")
            if (any(type(value) is not int for value in
                    (host, group, host_total, group_limit, reserve))
                    or not 0 <= host <= host_total <= _MAX
                    or not 0 <= group <= group_limit <= _MAX
                    or not 0 <= reserve <= 1024**4
                    or headroom != max(0, min(host, group) - reserve)):
                return False
            return required <= headroom
        except Exception:
            return False

    def _totals(self) -> tuple[int, dict[str, int]]:
        total = 0
        owners: dict[str, int] = {}
        for item in self._entries.values():
            total += item.request.requested_bytes
            owner = item.request.principal
            owners[owner] = owners.get(owner, 0) + item.request.requested_bytes
        return total, owners

    @staticmethod
    def _receipt(state: str, reason: str, key: str | None = None) -> dict[str, object]:
        return {
            "schema": "skeleton.ai.long-context-memory-budget.v1",
            "state": state, "reason": reason, "reservation_id": key,
            "is_admission_grant": False, "is_execution_lease": False,
            "is_memory_allocation": False, "device_qualified": False,
            "requires_live_backend_revalidation": True,
        }

    def reserve_fair_cycle(
        self, requests: tuple[MemoryBudgetRequest, ...],
    ) -> dict[str, object]:
        """Atomically reserve one bounded RAM quantum for each distinct stream.

        This is cooperative process-local accounting, never backend admission.
        No partial publication is permitted on failed identity, telemetry,
        clock, quota, nonce generation, or collision checks. Concurrent callers
        serialize through the same guard lock as single-stream reservations.
        """
        if type(requests) is not tuple or not 1 <= len(requests) <= 64:
            raise LongContextSpoolError("invalid memory fair cycle")
        if any(not isinstance(item, MemoryBudgetRequest) for item in requests):
            raise LongContextSpoolError("invalid memory fair cycle request")
        names = [item.stream_id for item in requests]
        if len(set(names)) != len(names):
            raise LongContextSpoolError("duplicate memory fair cycle stream")
        self._pid_guard()  # Never wait on a potentially inherited fork lock.
        with self._lock:
            self._open()  # Must be checked under the same lock as close().
            now = self._now()
            ordered = tuple(sorted(requests, key=lambda item: item.stream_id))
            if any(not self._authorized(item) for item in ordered):
                return {**self._receipt("hold", "principal_unverified"),
                        "reservations": []}
            existing = {item.request.stream_id for item in self._entries.values()}
            if any(item.stream_id in existing for item in ordered):
                return {**self._receipt("hold", "duplicate_stream"),
                        "reservations": []}
            total, owners = self._totals()
            incoming = sum(item.requested_bytes for item in ordered)
            for item in ordered:
                owners[item.principal] = owners.get(item.principal, 0) + item.requested_bytes
            if (len(self._entries) + len(ordered) > self._limits.max_active
                    or total + incoming > self._limits.max_bytes
                    or any(value > self._limits.max_bytes_per_principal
                           for value in owners.values())):
                return {**self._receipt("hold", "memory_budget_exhausted"),
                        "reservations": []}
            if not self._headroom(total + incoming):
                self._revoke_all()
                return {**self._receipt("hold", "memory_telemetry_unverified"),
                        "reservations": []}
            after = self._now()
            if (after - now >= self._limits.lifetime_ns
                    or after > _MAX - self._limits.lifetime_ns):
                return {**self._receipt("hold", "memory_observation_expired"),
                        "reservations": []}
            try:
                keys = [token_hex(24) for _ in ordered]
            except Exception:
                return {**self._receipt("hold", "reservation_identity_unavailable"),
                        "reservations": []}
            if (len(set(keys)) != len(keys)
                    or any(type(key) is not str or len(key) != 48
                           or any(c not in "0123456789abcdef" for c in key)
                           or key in self._entries for key in keys)):
                return {**self._receipt("hold", "reservation_collision"),
                        "reservations": []}
            expires = after + self._limits.lifetime_ns
            receipts = []
            for item, key in zip(ordered, keys):
                self._entries[key] = _Entry(item, expires)
                receipts.append({
                    "stream_digest": sha256(item.stream_id.encode("ascii")).hexdigest(),
                    "reservation_id": key,
                    "requested_bytes": item.requested_bytes,
                    "expires_ns": expires,
                })
            return {**self._receipt("reserved", "cooperative_only"),
                    "reservations": receipts,
                    "cycle_atomic_within_process": True,
                    "cross_process_exclusive": False}

    def reserve(self, request: MemoryBudgetRequest) -> dict[str, object]:
        if not isinstance(request, MemoryBudgetRequest):
            raise LongContextSpoolError("invalid memory request")
        self._pid_guard()
        with self._lock:
            self._open()
            now = self._now()
            if not self._authorized(request):
                return self._receipt("hold", "principal_unverified")
            total, owners = self._totals()
            if any(item.request.stream_id == request.stream_id
                   for item in self._entries.values()):
                return self._receipt("hold", "duplicate_stream")
            if (len(self._entries) >= self._limits.max_active
                    or total + request.requested_bytes > self._limits.max_bytes
                    or owners.get(request.principal, 0) + request.requested_bytes
                    > self._limits.max_bytes_per_principal):
                return self._receipt("hold", "memory_budget_exhausted")
            required = total + request.requested_bytes
            if not self._headroom(required):
                self._revoke_all()
                return self._receipt("hold", "memory_telemetry_unverified")
            # A slow or adversarial observation cannot publish an expired
            # reservation. Re-observe after the bounded monotonic interval.
            after = self._now()
            if after - now >= self._limits.lifetime_ns:
                return self._receipt("hold", "memory_observation_expired")
            key = token_hex(24)
            if key in self._entries:
                return self._receipt("hold", "reservation_collision")
            self._entries[key] = _Entry(request, after + self._limits.lifetime_ns)
            return self._receipt("reserved", "cooperative_only", key)

    def claim(self, key: str, request: MemoryBudgetRequest) -> dict[str, object]:
        if type(key) is not str or len(key) != 48 or any(
            c not in "0123456789abcdef" for c in key
        ) or not isinstance(request, MemoryBudgetRequest):
            raise LongContextSpoolError("invalid memory claim")
        self._pid_guard()
        with self._lock:
            self._open()
            self._now()
            entry = self._entries.get(key)
            if entry is None or entry.state != "reserved" or entry.request != request:
                return self._receipt("hold", "reservation_not_claimable")
            if not self._authorized(request):
                self._revoke_all()
                return self._receipt("hold", "principal_unverified")
            total, _ = self._totals()
            if not self._headroom(total):
                self._revoke_all()
                return self._receipt("hold", "memory_telemetry_unverified")
            now = self._now()
            if key not in self._entries or self._entries[key].expires_ns <= now:
                return self._receipt("hold", "reservation_expired")
            self._entries[key].state = "claimed"
            return self._receipt("claimed", "cooperative_only", key)

    def release(self, key: str) -> bool:
        if type(key) is not str:
            raise LongContextSpoolError("invalid memory reservation id")
        self._pid_guard()
        with self._lock:
            self._open()
            self._now()
            return self._entries.pop(key, None) is not None

    def status(self) -> dict[str, object]:
        self._pid_guard()
        with self._lock:
            self._open()
            self._now()
            total, _ = self._totals()
            return {
                "schema": "skeleton.ai.long-context-memory-budget-status.v1",
                "active": len(self._entries),
                "reserved_bytes": total,
                "revocations": self._revocations,
                "is_execution_lease": False,
                "is_admission_grant": False,
            }

    def close(self) -> None:
        self._pid_guard()
        with self._lock:
            self._revoke_all()
            self._closed = True


__all__ = ["MemoryBudgetRequest", "MemoryBudgetLimits", "LongContextMemoryBudgetGuard"]
