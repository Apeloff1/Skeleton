"""Fail-closed cooperative CPU token-capacity reservations.

This module only reserves bounded in-process resources. A reservation is
neither backend authorization nor a model-execution lease. Restart/fork
invalidates every reservation; hardware and disk claims remain observational.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from secrets import token_hex
from threading import Lock
from time import monotonic_ns
from typing import Callable

from .long_context_fairness import _bounded
from .long_context_pressure_latch import LongContextPressureLatch
from .long_context_progress import LongContextProgressHead, _name
from .long_context_spool import LongContextSpoolError, _digest
from .long_context_telemetry_fusion import LongContextTelemetryFusion

_MAX_CLOCK = 2**63 - 1


@dataclass(frozen=True, slots=True)
class CpuCapacityRequest:
    principal: str
    stream_id: str
    checkpoint_digest: str
    tokenizer_digest: str
    generation: int
    max_tokens: int
    requested_bytes: int = 0

    def __post_init__(self) -> None:
        if (type(self.principal) is not str or not 1 <= len(self.principal) <= 96
                or not all(c.isascii() and (c.isalnum() or c in "_-.")
                           for c in self.principal)):
            raise LongContextSpoolError("invalid principal")
        _name(self.stream_id)
        _digest(self.checkpoint_digest, "checkpoint")
        _digest(self.tokenizer_digest, "tokenizer")
        _bounded(self.generation, "generation", 0, _MAX_CLOCK)
        _bounded(self.max_tokens, "max_tokens", 1, 4096)
        _bounded(self.requested_bytes, "requested_bytes", 0, 64 * 1024**2)


@dataclass(frozen=True, slots=True)
class CpuCapacityLimits:
    max_active: int = 8
    max_tokens: int = 8192
    max_bytes: int = 64 * 1024**2
    lifetime_ns: int = 1_000_000_000
    # Keep legacy positional constructor arguments stable.
    max_active_per_principal: int = 4

    def __post_init__(self) -> None:
        _bounded(self.max_active, "max_active", 1, 64)
        _bounded(self.max_active_per_principal,
                 "max_active_per_principal", 1, 64)
        _bounded(self.max_tokens, "max_tokens", 1, 65536)
        _bounded(self.max_bytes, "max_bytes", 1, 1024**3)
        _bounded(self.lifetime_ns, "lifetime_ns", 1, 5_000_000_000)


@dataclass(slots=True)
class _Reservation:
    request: CpuCapacityRequest
    window_digest: str
    expires_ns: int
    state: str = "reserved"


class LongContextCpuCapacityGuard:
    """Cooperative absent -> reserved -> claimed -> released state machine.

    Caller supplies an independently trusted, non-reentrant principal verifier.
    All calls are serialized within this process. This is NOT cross-process
    admission and never grants model execution.
    """

    def __init__(self, heads: LongContextProgressHead,
                 monitor: LongContextTelemetryFusion,
                 verifier: Callable[[CpuCapacityRequest], bool], *,
                 limits: CpuCapacityLimits = CpuCapacityLimits(),
                 clock: Callable[[], int] = monotonic_ns) -> None:
        if not isinstance(heads, LongContextProgressHead):
            raise LongContextSpoolError("invalid progress coordinator")
        if not isinstance(monitor, LongContextTelemetryFusion):
            raise LongContextSpoolError("invalid monitor")
        if not callable(verifier) or not callable(clock):
            raise LongContextSpoolError("invalid verifier or clock")
        if not isinstance(limits, CpuCapacityLimits):
            raise LongContextSpoolError("invalid limits")
        self._heads, self._verifier, self._clock = heads, verifier, clock
        self._limits = limits
        self._latch = LongContextPressureLatch(monitor, clock=clock)
        self._pid, self._lock = os.getpid(), Lock()
        self._last_ns: int | None = None
        self._reservations: dict[str, _Reservation] = {}
        self._closed = False
        self._revocations = 0

    def _pid_guard(self) -> None:
        if os.getpid() != self._pid:
            raise LongContextSpoolError("inherited capacity lock after fork")

    def _revoke_all(self) -> None:
        """Account for every invalidated reservation, including claimed ones."""
        self._revocations += len(self._reservations)
        self._reservations.clear()

    def _now(self) -> int:
        try:
            now = self._clock()
        except Exception as exc:
            self._revoke_all()
            raise LongContextSpoolError("capacity clock unavailable") from exc
        if (type(now) is not int or not 0 <= now <= _MAX_CLOCK
                or (self._last_ns is not None and now <= self._last_ns)):
            self._revoke_all()
            raise LongContextSpoolError("capacity clock regressed")
        self._last_ns = now
        expired = [key for key, item in self._reservations.items()
                   if item.expires_ns <= now]
        for key in expired:
            del self._reservations[key]
        self._revocations += len(expired)
        return now

    def _pressure(self) -> str:
        try:
            result = self._latch.sample()
            state = result["state"]
            if (result.get("is_execution_lease") is not False
                    or result.get("is_admission_grant") is not False
                    or result.get("device_qualified") is not False
                    or result.get("requires_live_backend_revalidation") is not True
                    or state not in ("hold", "warming", "repeated_normal_observed")):
                state = "hold"
        except Exception:
            state = "hold"
        # Warming after a sampling gap is not a stable safe observation.
        # Revoke previously reserved capacity on every non-normal state.
        if state != "repeated_normal_observed":
            self._revoke_all()
        return state

    def _authorized(self, request: CpuCapacityRequest) -> bool:
        try:
            return self._verifier(request) is True
        except Exception:
            return False

    def _window(self, request: CpuCapacityRequest) -> str:
        result = self._heads.compare_window(
            request.stream_id,
            expected_checkpoint_digest=request.checkpoint_digest,
            expected_generation=request.generation,
            expected_tokenizer_digest=request.tokenizer_digest,
            max_tokens=request.max_tokens,
        )
        if (type(result) is not dict
                or result.get("is_execution_lease") is not False
                or result.get("checkpoint_digest") != request.checkpoint_digest
                or result.get("tokenizer_digest") != request.tokenizer_digest
                or result.get("generation") != request.generation):
            raise LongContextSpoolError("stale capacity head")
        window = result.get("window")
        if (type(window) is not dict
                or type(window.get("start")) is not int
                or type(window.get("stop")) is not int
                or not 0 <= window["start"] < window["stop"]
                or window["stop"] - window["start"] > request.max_tokens):
            raise LongContextSpoolError("invalid capacity window")
        return _digest(window.get("digest"), "window")

    def _disk_observed_sufficient(self, requested_bytes: int) -> bool:
        """Validate a fresh, non-authorizing quota/volume observation.

        This is never a disk lease: guarded publication must recheck the
        filesystem and quotas under its own cross-process lock.
        """
        snapshot = self._heads.spool.capacity_snapshot(
            requested_bytes=requested_bytes)
        if type(snapshot) is not dict:
            return False
        if (snapshot.get("schema") != "skeleton.ai.long-context-capacity.v1"
                or snapshot.get("state") != "observed_available"
                or snapshot.get("is_admission_lease") is not False
                or snapshot.get("hardware_qualification") != "not_assessed"
                or snapshot.get("request_observed_sufficient") is not True):
            return False
        fields = ("used_bytes", "quota_bytes", "quota_remaining_bytes",
                  "volume_available_bytes", "disk_reserve_bytes",
                  "observed_publishable_bytes", "requested_bytes")
        if any(type(snapshot.get(name)) is not int or snapshot[name] < 0
               for name in fields):
            return False
        used, quota = snapshot["used_bytes"], snapshot["quota_bytes"]
        available, reserve = (snapshot["volume_available_bytes"],
                              snapshot["disk_reserve_bytes"])
        remaining = snapshot["quota_remaining_bytes"]
        publishable = snapshot["observed_publishable_bytes"]
        if (used > quota or remaining != quota - used
                or publishable != min(remaining, max(0, available - reserve))
                or snapshot["requested_bytes"] != requested_bytes):
            return False
        return (publishable > 0 if requested_bytes == 0
                else publishable >= requested_bytes)

    def _principal_room(self, requests: tuple[CpuCapacityRequest, ...]) -> bool:
        """Prevent a verified principal monopolizing in-process capacity."""
        counts: dict[str, int] = {}
        for item in self._reservations.values():
            principal = item.request.principal
            counts[principal] = counts.get(principal, 0) + 1
        limit = min(self._limits.max_active, self._limits.max_active_per_principal)
        for request in requests:
            principal = request.principal
            counts[principal] = counts.get(principal, 0) + 1
            if counts[principal] > limit:
                return False
        return True

    def _snapshot(self, state: str) -> dict[str, object]:
        items = tuple(self._reservations.values())
        return {
            "schema": "skeleton.ai.cpu-capacity-guard.v1",
            "state": state,
            "active": len(items),
            "reserved_tokens": sum(x.request.max_tokens for x in items),
            "reserved_bytes": sum(x.request.requested_bytes for x in items),
            "revocations": self._revocations,
            "max_active_per_principal": self._limits.max_active_per_principal,
            "device": "cpu", "device_qualified": False,
            "cross_process_exclusive": False,
            "is_execution_lease": False, "is_admission_grant": False,
            "requires_live_backend_revalidation": True,
        }

    def observe(self) -> dict[str, object]:
        self._pid_guard()
        with self._lock:
            self._now()
            return self._snapshot(self._pressure())

    def reserve(self, request: CpuCapacityRequest) -> dict[str, object]:
        if not isinstance(request, CpuCapacityRequest):
            raise LongContextSpoolError("invalid capacity request")
        self._pid_guard()
        with self._lock:
            if self._closed:
                raise LongContextSpoolError("capacity guard closed")
            now = self._now()
            state = self._pressure()
            if state != "repeated_normal_observed":
                return {**self._snapshot(state), "reservation_id": None}
            if not self._authorized(request):
                return {**self._snapshot("hold"), "reservation_id": None,
                        "reason": "principal_unverified"}
            if not self._principal_room((request,)):
                return {**self._snapshot("hold"), "reservation_id": None,
                        "reason": "principal_capacity_exhausted"}
            if any(x.request.stream_id == request.stream_id
                   for x in self._reservations.values()):
                return {**self._snapshot("hold"), "reservation_id": None,
                        "reason": "duplicate_stream"}
            status = self._snapshot(state)
            if (status["active"] >= self._limits.max_active
                    or status["reserved_tokens"] + request.max_tokens > self._limits.max_tokens
                    or status["reserved_bytes"] + request.requested_bytes > self._limits.max_bytes):
                return {**status, "state": "hold", "reservation_id": None,
                        "reason": "budget_exhausted"}
            try:
                digest = self._window(request)
                if not self._disk_observed_sufficient(request.requested_bytes):
                    raise LongContextSpoolError("disk capacity hold")
            except (LongContextSpoolError, OSError, ValueError, TypeError):
                return {**self._snapshot("hold"), "reservation_id": None,
                        "reason": "custody_or_disk_unverified"}
            if now > _MAX_CLOCK - self._limits.lifetime_ns:
                raise LongContextSpoolError("capacity clock overflow")
            key = token_hex(32)
            if key in self._reservations:
                raise LongContextSpoolError("capacity identity collision")
            self._reservations[key] = _Reservation(
                request, digest, now + self._limits.lifetime_ns)
            return {**self._snapshot("reserved"), "reservation_id": key,
                    "window_digest": digest, "expires_ns": now + self._limits.lifetime_ns}

    def reserve_fair_cycle(
        self, requests: tuple[CpuCapacityRequest, ...], *,
        quantum_tokens: int = 256,
    ) -> dict[str, object]:
        """All-or-nothing, one-quantum-per-stream cooperative CPU cycle.

        No first-fit partial admission: if any candidate cannot be checked,
        the entire cycle holds. This is fairness *within this call*, not a
        guarantee across processes or independent callers. Every backend
        must independently revalidate before actual token consumption.
        """
        if type(requests) is not tuple or not 1 <= len(requests) <= 64:
            raise LongContextSpoolError("invalid fair cycle")
        _bounded(quantum_tokens, "quantum_tokens", 1, 4096)
        names: set[str] = set()
        for request in requests:
            if not isinstance(request, CpuCapacityRequest):
                raise LongContextSpoolError("invalid fair cycle request")
            if request.stream_id in names:
                raise LongContextSpoolError("duplicate fair cycle stream")
            names.add(request.stream_id)
        self._pid_guard()
        with self._lock:
            if self._closed:
                raise LongContextSpoolError("capacity guard closed")
            now = self._now()
            state = self._pressure()
            if state != "repeated_normal_observed":
                return {**self._snapshot("hold"), "reservations": [],
                        "reason": "pressure_not_stable"}
            active = self._snapshot(state)
            requested_tokens = sum(r.max_tokens for r in requests)
            requested_bytes = sum(r.requested_bytes for r in requests)
            if (len(self._reservations) + len(requests) > self._limits.max_active
                    or active["reserved_tokens"] + requested_tokens >
                    self._limits.max_tokens
                    or active["reserved_bytes"] + requested_bytes >
                    self._limits.max_bytes
                    or any(r.max_tokens > quantum_tokens for r in requests)
                    or any(r.stream_id in
                           (item.request.stream_id for item in self._reservations.values())
                           for r in requests)):
                return {**active, "state": "hold", "reservations": [],
                        "reason": "fair_cycle_budget_or_duplicate"}
            ordered = sorted(requests, key=lambda r: _name(r.stream_id))
            if not all(self._authorized(r) for r in ordered):
                return {**active, "state": "hold", "reservations": [],
                        "reason": "principal_unverified"}
            if not self._principal_room(tuple(ordered)):
                return {**active, "state": "hold", "reservations": [],
                        "reason": "fair_cycle_principal_capacity"}
            try:
                windows = [(r, self._window(r)) for r in ordered]
                if not self._disk_observed_sufficient(requested_bytes):
                    raise LongContextSpoolError("disk capacity hold")
            except (LongContextSpoolError, OSError, ValueError, TypeError):
                return {**active, "state": "hold", "reservations": [],
                        "reason": "fair_cycle_custody_unverified"}
            if now > _MAX_CLOCK - self._limits.lifetime_ns:
                raise LongContextSpoolError("capacity clock overflow")
            keys = [token_hex(32) for _ in windows]
            if len(set(keys)) != len(keys) or any(
                key in self._reservations for key in keys
            ):
                raise LongContextSpoolError("capacity identity collision")
            expires = now + self._limits.lifetime_ns
            receipts = []
            for key, (request, digest) in zip(keys, windows):
                self._reservations[key] = _Reservation(request, digest, expires)
                receipts.append({
                    "stream_digest": _name(request.stream_id),
                    "reservation_id": key,
                    "window_digest": digest,
                    "max_tokens": request.max_tokens,
                    "expires_ns": expires,
                })
            return {**self._snapshot("reserved"), "reservations": receipts,
                    "cycle_atomic_within_process": True,
                    "cross_process_exclusive": False}

    def claim(self, reservation_id: str, request: CpuCapacityRequest) -> dict[str, object]:
        self._validate_key(reservation_id)
        if not isinstance(request, CpuCapacityRequest):
            raise LongContextSpoolError("invalid claim request")
        self._pid_guard()
        with self._lock:
            if self._closed:
                raise LongContextSpoolError("capacity guard closed")
            self._now()
            state = self._pressure()
            item = self._reservations.get(reservation_id)
            if (state != "repeated_normal_observed" or item is None
                    or item.state != "reserved" or item.request != request):
                return {**self._snapshot("hold"), "claimed": False}
            if not self._authorized(request):
                self._reservations.pop(reservation_id, None)
                self._revocations += 1
                return {**self._snapshot("hold"), "claimed": False}
            try:
                if self._window(request) != item.window_digest:
                    raise LongContextSpoolError("window changed before claim")
                # The reservation-time disk observation may have expired or
                # another process may have consumed the available quota.
                if not self._disk_observed_sufficient(request.requested_bytes):
                    raise LongContextSpoolError("disk capacity changed before claim")
            except (LongContextSpoolError, OSError, ValueError, TypeError):
                self._reservations.pop(reservation_id, None)
                self._revocations += 1
                return {**self._snapshot("hold"), "claimed": False}
            item.state = "claimed"
            return {**self._snapshot("claimed"), "claimed": True,
                    "window_digest": item.window_digest}

    @staticmethod
    def _validate_key(key: str) -> None:
        if (type(key) is not str or len(key) != 64
                or any(c not in "0123456789abcdef" for c in key)):
            raise LongContextSpoolError("invalid reservation identity")

    def release(self, reservation_id: str) -> bool:
        self._validate_key(reservation_id)
        self._pid_guard()
        with self._lock:
            self._now()
            return self._reservations.pop(reservation_id, None) is not None

    def status(self) -> dict[str, object]:
        self._pid_guard()
        with self._lock:
            self._now()
            return self._snapshot("closed" if self._closed else "diagnostic")

    def close(self) -> None:
        self._pid_guard()
        with self._lock:
            self._revoke_all()
            self._closed = True


__all__ = ["CpuCapacityLimits", "CpuCapacityRequest", "LongContextCpuCapacityGuard"]
