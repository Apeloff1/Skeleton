"""Conservative in-flight CPU token pressure watchdog for local inference.

Every admitted token quantum is re-probed against OS RAM, swap, disk, CPU and
measured CPU thermal trip points. Unknown telemetry is a HOLD, not an assumed
GPU/Metal/ROCm qualification. This is a cooperative execution control: the
trusted backend MUST stop emitting tokens when continue_execution is false.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from threading import RLock
from time import monotonic_ns
from typing import Callable

from skeleton.app.offline_resources import (
    LocalResourceSnapshot, probe_local_resources,
)
from skeleton.app.offline_cpu_thermal import (
    CPUThermalController, CPUThermalSensor, probe_cpu_thermal,
)

SCHEMA = "skeleton.ai.tail-inflight-pressure.v1"
MAX_TOKENS = 1 << 24
MAX_QUANTUM = 4096
MAX_QUANTUM_DURATION_NS = 30_000_000_000
MAX_HOLD_DURATION_NS = 3_600_000_000_000


@dataclass(frozen=True, slots=True)
class InFlightPressurePolicy:
    min_ram_bytes: int
    min_disk_bytes: int
    max_cpu_load_ppm: int
    max_memory_pressure_ppm: int
    max_generated_tokens: int
    max_quantum_tokens: int = 256
    resume_good_samples: int = 2
    max_quantum_duration_ns: int = 5_000_000_000
    max_hold_duration_ns: int = 120_000_000_000

    def __post_init__(self) -> None:
        for name in ("min_ram_bytes", "min_disk_bytes"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value < (1 << 63):
                raise ValueError("invalid " + name)
        for name in ("max_cpu_load_ppm", "max_memory_pressure_ppm"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 1_000_000:
                raise ValueError("invalid " + name)
        if (
            type(self.max_generated_tokens) is not int
            or not 1 <= self.max_generated_tokens <= MAX_TOKENS
            or type(self.max_quantum_tokens) is not int
            or not 1 <= self.max_quantum_tokens <= MAX_QUANTUM
            or type(self.resume_good_samples) is not int
            or not 1 <= self.resume_good_samples <= 16
            or type(self.max_quantum_duration_ns) is not int
            or not 1 <= self.max_quantum_duration_ns <= MAX_QUANTUM_DURATION_NS
            or type(self.max_hold_duration_ns) is not int
            or not 1 <= self.max_hold_duration_ns <= MAX_HOLD_DURATION_NS
        ):
            raise ValueError("invalid bounded token or hysteresis policy")


@dataclass(frozen=True, slots=True)
class InFlightPressureDecision:
    schema: str
    state: str
    reason: str
    generation: int
    generated_tokens: int
    continue_execution: bool
    gpu_device_qualified: bool = False
    authorized_quantum_tokens: int = 0


class InFlightPressureDenied(RuntimeError):
    """Execution cannot proceed from the current guarded state."""


class InFlightCPUResourceGuard:
    """Per-request NEW -> RUNNING <-> HOLD -> COMPLETED/ABORTED controller.

    No restart reconstructs a RUNNING state. The app must journal execution
    separately and never automatically replay a partially executed request.
    Injected probes are allowed only with simulated=True; simulated decisions
    cannot be used as evidence of qualified hardware execution.
    """

    def __init__(
        self, policy: InFlightPressurePolicy, *, storage_path: str,
        simulated: bool = False,
        resource_probe: Callable[[str], LocalResourceSnapshot] | None = None,
        thermal_probe: Callable[[], tuple[CPUThermalSensor, ...]] | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(policy, InFlightPressurePolicy):
            raise ValueError("typed in-flight pressure policy required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected storage volume required")
        if type(simulated) is not bool:
            raise ValueError("explicit simulation flag required")
        if (resource_probe is not None or thermal_probe is not None
                or clock is not None) and not simulated:
            raise ValueError("injected hardware probes require simulation")
        if resource_probe is not None and not callable(resource_probe):
            raise ValueError("resource probe must be callable")
        if thermal_probe is not None and not callable(thermal_probe):
            raise ValueError("thermal probe must be callable")
        if clock is not None and not callable(clock):
            raise ValueError("monotonic clock must be callable")
        # A forked child inherits Python locks and state, not execution rights.
        self._owner_pid = os.getpid()
        self.policy = policy
        self._path = storage_path
        self._resource_probe = resource_probe or probe_local_resources
        self._thermal_probe = thermal_probe or probe_cpu_thermal
        self._clock = monotonic_ns if clock is None else clock
        self._thermal = CPUThermalController()
        self._simulated = simulated
        self._lock = RLock()
        self._state = "new"
        self._reason = "not_started"
        self._generation = 0
        self._generated = 0
        self._good = 0
        self._authorized_quantum = 0
        self._quantum_started_ns: int | None = None
        self._last_clock_ns: int | None = None
        self._hold_started_ns: int | None = None

    def _require_owner_process(self) -> None:
        """Reject inherited CPU quantum before touching a potentially dead lock."""
        try:
            pid = os.getpid()
        except BaseException:
            pid = None
        if type(pid) is not int or pid != self._owner_pid:
            # The child has its own copy of this object. No inherited RLock
            # can be safely acquired because the owning thread may be gone.
            if self._reason != "process_identity_changed":
                self._generation += 1
            self._state = "aborted"
            self._reason = "process_identity_changed"
            self._authorized_quantum = 0
            self._quantum_started_ns = None
            self._hold_started_ns = None
            raise InFlightPressureDenied("forked CPU pressure lease is invalid")

    def _abort_quantum(self, reason: str) -> None:
        self._authorized_quantum = 0
        self._quantum_started_ns = None
        self._hold_started_ns = None
        self._state = "aborted"
        self._reason = reason
        self._generation += 1
        raise InFlightPressureDenied(reason)

    def _clock_now(self) -> int:
        try:
            now = self._clock()
            if (type(now) is not int or now < 0
                    or (self._last_clock_ns is not None
                        and now < self._last_clock_ns)):
                raise ValueError("invalid monotonic clock")
        except Exception:
            self._abort_quantum("monotonic_clock_unavailable")
        self._last_clock_ns = now
        return now

    def _check_quantum_deadline(self) -> None:
        if self._authorized_quantum:
            start = self._quantum_started_ns
            now = self._clock_now()
            if start is None or now - start > self.policy.max_quantum_duration_ns:
                self._abort_quantum("quantum_deadline_exceeded")

    def _enter_hold(self, reason: str) -> None:
        """Latch first HOLD timestamp; repeated bad probes never reset timeout."""
        if self._state != "hold":
            self._hold_started_ns = self._clock_now()
        elif self._hold_started_ns is None:
            self._abort_quantum("missing_hold_deadline")
        self._state = "hold"
        self._reason = reason
        self._good = 0

    def _check_hold_deadline(self) -> None:
        if self._state != "hold":
            return
        started = self._hold_started_ns
        now = self._clock_now()
        if started is None or now - started > self.policy.max_hold_duration_ns:
            self._abort_quantum("hold_deadline_exceeded")

    def _observe(self) -> str:
        try:
            snapshot = self._resource_probe(self._path)
            sensors = self._thermal_probe()
            if not isinstance(snapshot, LocalResourceSnapshot):
                return "unknown_resource_telemetry"
            if type(sensors) is not tuple or any(
                not isinstance(sensor, CPUThermalSensor) for sensor in sensors
            ):
                return "unknown_thermal_telemetry"
            # Observe even an empty inventory: disappearance after a valid
            # sample must permanently fence the previous sensor identity.
            # A healthy replacement zone cannot clear a prior thermal hold.
            self._thermal.observe(sensors)
            thermal = self._thermal.snapshot()
            if thermal["sensor_identity_drift"]:
                return "thermal_zone_identity_changed"
            # A measured trip on ONE CPU zone does not certify the others.
            if not sensors or not thermal["trip_measured"]:
                return "unknown_thermal_trip"
            if thermal["thermal_backpressure"]:
                return "measured_thermal_hold"
            if (
                not math.isfinite(snapshot.cpu_load_ratio)
                or not math.isfinite(snapshot.memory_pressure_ratio)
                or snapshot.available_ram_bytes < self.policy.min_ram_bytes
                or snapshot.free_disk_bytes < self.policy.min_disk_bytes
            ):
                return "memory_or_disk_pressure"
            if (
                snapshot.cpu_load_ratio * 1_000_000 > self.policy.max_cpu_load_ppm
                or snapshot.memory_pressure_ratio * 1_000_000
                > self.policy.max_memory_pressure_ppm
            ):
                return "cpu_or_memory_pressure"
            if (
                snapshot.total_swap_bytes > 0
                and snapshot.free_swap_bytes * 10 < snapshot.total_swap_bytes
            ):
                return "swap_exhaustion"
            return "measured_cpu_headroom"
        except Exception:
            # Vendor telemetry adapters may fail with unexpected ordinary
            # exceptions. Never convert probe failure into an admission.
            return "unavailable_resource_telemetry"

    def _receipt(self) -> InFlightPressureDecision:
        return InFlightPressureDecision(
            schema=SCHEMA, state=self._state, reason=self._reason,
            generation=self._generation, generated_tokens=self._generated,
            continue_execution=(
                self._state == "running" and not self._simulated
                and self._authorized_quantum > 0
            ),
            authorized_quantum_tokens=self._authorized_quantum,
        )

    def start(self) -> InFlightPressureDecision:
        self._require_owner_process()
        with self._lock:
            if self._state != "new":
                raise InFlightPressureDenied("request already started")
            reason = self._observe()
            if reason == "measured_cpu_headroom":
                self._state = "running"
                self._reason = reason
            else:
                self._enter_hold(reason)
            self._generation += 1
            return self._receipt()

    def admit_quantum(self, *, requested_tokens: int) -> InFlightPressureDecision:
        """Reserve a single bounded token quantum before invoking the model.

        A fresh CPU/thermal probe is required for every new quantum. The
        reservation is process-local, not a physical memory reservation.
        Simulated receipts never authorize production execution.
        """
        if (type(requested_tokens) is not int
                or not 1 <= requested_tokens <= self.policy.max_quantum_tokens):
            raise ValueError("bounded positive requested token quantum required")
        self._require_owner_process()
        with self._lock:
            if self._state != "running":
                raise InFlightPressureDenied("execution is not running")
            if self._authorized_quantum:
                raise InFlightPressureDenied("previous quantum not accounted")
            remaining = self.policy.max_generated_tokens - self._generated
            if remaining <= 0:
                self._state = "aborted"
                self._reason = "token_budget_exhausted"
                self._generation += 1
                raise InFlightPressureDenied("token budget exhausted")
            reason = self._observe()
            if reason != "measured_cpu_headroom":
                self._enter_hold(reason)
                self._generation += 1
                return self._receipt()
            # A measured resource sample does not authorize an unbounded
            # time slice. Record a monotonic start before issuing the lease.
            started = self._clock_now()
            self._authorized_quantum = min(requested_tokens, remaining)
            self._quantum_started_ns = started
            self._reason = "measured_cpu_headroom"
            self._generation += 1
            return self._receipt()

    def validate_quantum_lease(
        self, *, generation: int, required_tokens: int = 1,
    ) -> InFlightPressureDecision:
        """Re-probe before a backend consumes a previously issued quantum.

        A stale generation, expired deadline or inadequate reservation never
        grants token execution. A new pressure HOLD revokes the whole quantum,
        not just the requested token count. Rechecks cannot extend the lease.
        This is a cooperative boundary; the backend must call it immediately
        before emitting tokens and still enforce actual allocation limits.
        """
        self._require_owner_process()
        with self._lock:
            if (type(generation) is not int or generation < 0
                    or type(required_tokens) is not int
                    or not 1 <= required_tokens <= self.policy.max_quantum_tokens):
                raise InFlightPressureDenied("invalid CPU quantum lease identity")
            self._check_quantum_deadline()
            if (self._state != "running"
                    or self._authorized_quantum < required_tokens
                    or generation != self._generation):
                raise InFlightPressureDenied("stale or insufficient CPU quantum lease")
            reason = self._observe()
            if reason != "measured_cpu_headroom":
                self._authorized_quantum = 0
                self._quantum_started_ns = None
                self._enter_hold(reason)
                self._generation += 1
                return self._receipt()
            # Vendor sampling may itself outlive a short quantum deadline.
            self._check_quantum_deadline()
            return self._receipt()

    def checkpoint(self, *, generated_tokens: int) -> InFlightPressureDecision:
        """Check AFTER at most one bounded token quantum, before next quantum."""
        if type(generated_tokens) is not int or not 0 <= generated_tokens <= self.policy.max_quantum_tokens:
            raise ValueError("bounded generated token quantum required")
        self._require_owner_process()
        with self._lock:
            if self._state != "running":
                raise InFlightPressureDenied("execution is not running")
            if not self._simulated and self._authorized_quantum == 0:
                raise InFlightPressureDenied("quantum must be admitted before execution")
            self._check_quantum_deadline()
            if self._authorized_quantum and generated_tokens > self._authorized_quantum:
                self._authorized_quantum = 0
                self._quantum_started_ns = None
                self._state = "aborted"
                self._reason = "quantum_accounting_violation"
                self._generation += 1
                raise InFlightPressureDenied("unaccounted generated token quantum")
            self._authorized_quantum = 0
            self._quantum_started_ns = None
            self._generated += generated_tokens
            if self._generated > self.policy.max_generated_tokens:
                self._state = "aborted"
                self._reason = "token_budget_exhausted"
            else:
                self._reason = self._observe()
                if self._reason != "measured_cpu_headroom":
                    self._enter_hold(self._reason)
            self._generation += 1
            return self._receipt()

    def resume(self) -> InFlightPressureDecision:
        self._require_owner_process()
        with self._lock:
            if self._state != "hold":
                raise InFlightPressureDenied("no paused request to resume")
            # Never let repeated resume attempts extend a stalled lease.
            self._check_hold_deadline()
            reason = self._observe()
            self._reason = reason
            if reason == "measured_cpu_headroom":
                self._good += 1
                if self._good >= self.policy.resume_good_samples:
                    self._state = "running"
                    self._good = 0
                    self._hold_started_ns = None
            else:
                self._good = 0
            self._check_hold_deadline()
            self._generation += 1
            return self._receipt()

    def complete(self) -> InFlightPressureDecision:
        self._require_owner_process()
        with self._lock:
            if self._state != "running":
                raise InFlightPressureDenied("completion requires running execution")
            if self._authorized_quantum:
                raise InFlightPressureDenied("outstanding quantum must be accounted")
            reason = self._observe()
            if reason != "measured_cpu_headroom":
                self._enter_hold(reason)
            else:
                self._state = "completed"
                self._hold_started_ns = None
                self._reason = "completed"
            self._generation += 1
            return self._receipt()

    def abort(self) -> InFlightPressureDecision:
        self._require_owner_process()
        with self._lock:
            if self._state in ("completed", "aborted"):
                raise InFlightPressureDenied("terminal execution cannot be restarted")
            self._state = "aborted"
            self._authorized_quantum = 0
            self._quantum_started_ns = None
            self._hold_started_ns = None
            self._reason = "operator_abort"
            self._generation += 1
            return self._receipt()

    def status(self) -> InFlightPressureDecision:
        self._require_owner_process()
        with self._lock:
            # Never expose an expired cooperative authorization as live.
            self._check_quantum_deadline()
            self._check_hold_deadline()
            return self._receipt()
