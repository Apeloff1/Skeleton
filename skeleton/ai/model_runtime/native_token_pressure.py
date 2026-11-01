"""Conservative per-token OS resource guard for real native CPU generation.

Every callback probes the canonical OS sampler. A pressure or measurement
failure aborts generation, which leaves the durable execution journal RUNNING:
the app MUST NOT automatically retry an uncertain model execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from threading import RLock
from time import monotonic_ns

from .fair_stream_live_budget import LiveStreamBudgetSampler
from .fair_stream_queue import MeasuredStreamBudget
from .fair_stream_session import DispatchPermit

MAX_PROBES_PER_LEASE = 4096
MAX_USED_LEASES = 4096  # bounded lifetime replay fence per guard instance
MAX_DURATION_NS = 86_400_000_000_000  # 24h ceiling, not a hard preemption guarantee
DEFAULT_DURATION_NS = 900_000_000_000  # 15m cooperative lease quantum


_LIVE_EVIDENCE_SCHEMA = "skeleton.ai.live-stream-pressure.v1"
_REQUIRED_HOLDS = frozenset((
    "thermal", "cgroup_high", "cgroup_oom", "cgroup_memory",
    "cgroup_swap_spill", "io", "cpu_throttle", "swap_churn",
    "reclaim", "disk_reserve",
))
_HARD_HOLDS = frozenset((
    "thermal", "cgroup_oom", "cgroup_memory", "disk_reserve",
))


def _verified_live_evidence(
    budget: MeasuredStreamBudget, evidence: object,
) -> bool:
    """Cross-check independently reported OS holds against actual admission.

    A forged or partially upgraded sampler must not silently turn an OOM,
    thermal, or missing-sensor observation into a CPU execution permit.
    The canonical sampler remains observational, never a RAM reservation.
    """
    if type(evidence) is not dict:
        return False
    if (evidence.get("schema") != _LIVE_EVIDENCE_SCHEMA
            or evidence.get("measurement") != "os_probe"
            or evidence.get("gpu_device_qualified") is not False
            or evidence.get("physical_memory_reserved") is not False
            or evidence.get("cross_process_admission_guaranteed") is not False):
        return False
    for field in (
        "auxiliary_telemetry_incomplete", "thermal_trip_measured",
        "cgroup_swap_spill_allowed", "cgroup_swap_limit_measured",
        "cgroup_memory_limit_measured",
    ):
        if type(evidence.get(field)) is not bool:
            return False
    holds = evidence.get("holds")
    if (type(holds) is not dict or set(holds) != _REQUIRED_HOLDS
            or any(type(value) is not bool for value in holds.values())):
        return False
    if holds["cgroup_swap_spill"] == evidence["cgroup_swap_spill_allowed"]:
        return False
    if any(holds[field] for field in _HARD_HOLDS) and (
        not budget.thermal_hold or budget.effective_slots != 0
    ):
        return False
    # Unknown auxiliary/thermal telemetry or any OS hold cannot authorize
    # multiple concurrent streams, regardless of a forged slot count.
    if budget.stream_slots > 1 and (
        evidence["auxiliary_telemetry_incomplete"]
        or not evidence["thermal_trip_measured"]
        or any(holds.values())
    ):
        return False
    # The canonical sampler caps an incomplete OS observation to a small
    # cooperative quantum. A forged large token grant must not override it.
    if (evidence["auxiliary_telemetry_incomplete"]
            or not evidence["thermal_trip_measured"]) and budget.token_budget > 128:
        return False
    if (not evidence["cgroup_memory_limit_measured"]
            and not evidence["auxiliary_telemetry_incomplete"]):
        return False
    if (evidence["cgroup_swap_spill_allowed"]
            and not evidence["cgroup_swap_limit_measured"]):
        return False
    if any(holds[k] for k in ("cgroup_high", "io", "cpu_throttle")):
        if budget.pressure_ppm < 850_000:
            return False
    if holds["swap_churn"] or holds["reclaim"]:
        if budget.pressure_ppm < 900_000:
            return False
    return True


class NativePressureInterrupted(RuntimeError):
    """Native execution must stop; no replay without explicit reconciliation."""


@dataclass(frozen=True, slots=True)
class NativePressureStatus:
    schema: str
    samples: int
    stopped: bool
    last_pressure_ppm: int | None
    gpu_device_qualified: bool = False


def _canonical_cpu_permit(permit: object) -> bool:
    """Reject Python bool/int aliasing and forged mutable lease identities."""
    if type(permit) is not DispatchPermit or permit.device_qualified is not False:
        return False
    for value in (permit.lease_id, permit.checkpoint_digest):
        if (type(value) is not str or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)):
            return False
    if type(permit.request_id) is not str or not permit.request_id:
        return False
    try:
        request_bytes = permit.request_id.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    if (len(request_bytes) > 128
            or any(ord(char) < 32 or ord(char) == 127
                   for char in permit.request_id)
            or type(permit.generation) is not int
            or not 0 <= permit.generation < (1 << 63)
            or type(permit.tokens) is not int
            or not 1 <= permit.tokens <= (1 << 24)
            or type(permit.bytes_reserved) is not int
            or not 0 < permit.bytes_reserved < (1 << 63)):
        return False
    return True


class NativeTokenPressureGuard:
    """App-owned, exact-source pressure sampler; never a GPU reservation.

    The guard can authorize at most one in-flight permit. It does not infer
    missing telemetry as free resources, does not silently resume a stopped
    generation and never performs a retry after any callback error.
    """

    def __init__(
        self, sampler: LiveStreamBudgetSampler, *, storage_path: str,
        max_probes: int = MAX_PROBES_PER_LEASE,
        max_duration_ns: int = DEFAULT_DURATION_NS,
    ) -> None:
        if type(sampler) is not LiveStreamBudgetSampler:
            raise ValueError("canonical OS sampler required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected storage volume required")
        if type(max_probes) is not int or not 1 <= max_probes <= MAX_PROBES_PER_LEASE:
            raise ValueError("bounded pressure probe count required")
        if (type(max_duration_ns) is not int
                or not 1_000_000 <= max_duration_ns <= MAX_DURATION_NS):
            raise ValueError("bounded monotonic execution duration required")
        # A fork inherits Python object state but not execution authority.
        # Check PID before acquiring an inherited lock or sampling hardware.
        self._owner_pid = os.getpid()
        self._sampler = sampler
        self._storage_path = storage_path
        self._max_probes = max_probes
        self._max_duration_ns = max_duration_ns
        self._lock = RLock()
        self._active: str | None = None
        self._epoch = 0
        self._used_leases: set[str] = set()
        self._samples = 0
        self._stopped = False
        self._pressure: int | None = None
        self._start_ns: int | None = None
        self._last_ns: int | None = None

    def _require_owner_process(self) -> None:
        """A copied guard in a forked worker is never a reusable CPU lease.

        Called before the lock: an inherited lock can be held by a thread
        that no longer exists in the child. The durable journal remains the
        independent cross-process replay authority.
        """
        try:
            current = os.getpid()
        except BaseException as exc:
            self._stopped = True
            raise NativePressureInterrupted(
                "native execution process identity unavailable"
            ) from exc
        if type(current) is not int or current != self._owner_pid:
            self._stopped = True
            raise NativePressureInterrupted(
                "native execution process identity changed; reauthorize"
            )

    def _check_deadline(self) -> None:
        """Fail closed on timeout, clock regression or an unreadable clock.

        The caller holds _lock. This is cooperative: a native backend must
        invoke the callback at each token; a blocked native call still needs
        an independent process-level cancellation boundary.
        """
        try:
            now = monotonic_ns()
        except BaseException as exc:
            self._stopped = True
            raise NativePressureInterrupted("monotonic execution clock unavailable") from exc
        if (type(now) is not int or now < 0 or self._start_ns is None
                or self._last_ns is None or now < self._last_ns):
            self._stopped = True
            raise NativePressureInterrupted("monotonic execution clock regressed")
        self._last_ns = now
        if now - self._start_ns > self._max_duration_ns:
            self._stopped = True
            raise NativePressureInterrupted("native execution lease deadline exceeded")

    def start(self, permit: DispatchPermit):
        """Return an interrupt callback; one active generation per guard."""
        self._require_owner_process()
        if not _canonical_cpu_permit(permit):
            raise NativePressureInterrupted("CPU-only canonical typed permit required")
        with self._lock:
            if self._active is not None or self._stopped:
                raise NativePressureInterrupted("pressure guard not available")
            # Successful generations do not authorize replay of the same lease.
            # The durable journal remains the cross-process authority; this is
            # an independent bounded in-process fence against stale callbacks.
            if permit.lease_id in self._used_leases:
                self._stopped = True
                raise NativePressureInterrupted("native pressure lease replay denied")
            if len(self._used_leases) >= MAX_USED_LEASES:
                self._stopped = True
                raise NativePressureInterrupted("native pressure lease capacity exhausted")
            try:
                started = monotonic_ns()
            except BaseException as exc:
                self._stopped = True
                raise NativePressureInterrupted("monotonic execution clock unavailable") from exc
            if type(started) is not int or started < 0:
                self._stopped = True
                raise NativePressureInterrupted("invalid monotonic execution clock")
            self._start_ns = started
            self._last_ns = started
            self._epoch += 1
            epoch = self._epoch
            self._used_leases.add(permit.lease_id)
            self._active = permit.lease_id
            self._samples = 0
            self._pressure = None

        def interrupt() -> None:
            self._require_owner_process()
            with self._lock:
                if (self._active != permit.lease_id
                        or self._epoch != epoch or self._stopped):
                    raise NativePressureInterrupted("pressure guard no longer active")
                self._check_deadline()
                if self._samples >= self._max_probes:
                    self._stopped = True
                    raise NativePressureInterrupted("per-lease probe budget exhausted")
                self._samples += 1
                try:
                    budget, evidence = self._sampler.sample(
                        token_budget=permit.tokens, storage_path=self._storage_path,
                    )
                except BaseException as exc:
                    self._stopped = True
                    raise NativePressureInterrupted("live OS pressure unavailable") from exc
                # Probe latency itself consumes the lease's deadline.
                self._check_deadline()
                if (type(budget) is not MeasuredStreamBudget
                        or budget.measurement != "os_probe"
                        or type(evidence) is not dict
                        or evidence.get("measurement") != "os_probe"
                        or evidence.get("gpu_device_qualified") is not False
                        or evidence.get("physical_memory_reserved") is not False
                        or not _verified_live_evidence(budget, evidence)):
                    self._stopped = True
                    raise NativePressureInterrupted("untrusted OS pressure provenance")
                self._pressure = budget.pressure_ppm
                if (budget.effective_slots < 1
                        or budget.effective_tokens < permit.tokens
                        or budget.available_for_streams < permit.bytes_reserved):
                    self._stopped = True
                    raise NativePressureInterrupted("live memory or thermal pressure hold")

        return interrupt

    def finish(self, *, success: bool) -> None:
        """After failure the guard remains stopped; caller must reauthorize."""
        self._require_owner_process()
        with self._lock:
            if type(success) is not bool:
                raise ValueError("explicit completion outcome required")
            if success and self._active is not None and not self._stopped:
                try:
                    self._check_deadline()
                except NativePressureInterrupted:
                    self._active = None
                    raise
            # A success without a model callback AND postflight probe, or a tripped guard
            # cannot be promoted to a reusable CPU execution permit.
            if success and (
                self._active is None or self._samples < 2 or self._stopped
            ):
                self._active = None
                self._stopped = True
                raise NativePressureInterrupted(
                    "unverified pressure guard completion"
                )
            self._active = None
            if not success:
                self._stopped = True

    def status(self) -> NativePressureStatus:
        self._require_owner_process()
        with self._lock:
            return NativePressureStatus(
                schema="skeleton.ai.native-token-pressure.v1",
                samples=self._samples, stopped=self._stopped,
                last_pressure_ppm=self._pressure,
            )
