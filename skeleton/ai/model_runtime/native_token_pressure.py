"""Conservative per-token OS resource guard for real native CPU generation.

Every callback probes the canonical OS sampler. A pressure or measurement
failure aborts generation, which leaves the durable execution journal RUNNING:
the app MUST NOT automatically retry an uncertain model execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from .fair_stream_live_budget import LiveStreamBudgetSampler
from .fair_stream_queue import MeasuredStreamBudget
from .fair_stream_session import DispatchPermit

MAX_PROBES_PER_LEASE = 4096


class NativePressureInterrupted(RuntimeError):
    """Native execution must stop; no replay without explicit reconciliation."""


@dataclass(frozen=True, slots=True)
class NativePressureStatus:
    schema: str
    samples: int
    stopped: bool
    last_pressure_ppm: int | None
    gpu_device_qualified: bool = False


class NativeTokenPressureGuard:
    """App-owned, exact-source pressure sampler; never a GPU reservation.

    The guard can authorize at most one in-flight permit. It does not infer
    missing telemetry as free resources, does not silently resume a stopped
    generation and never performs a retry after any callback error.
    """

    def __init__(
        self, sampler: LiveStreamBudgetSampler, *, storage_path: str,
        max_probes: int = MAX_PROBES_PER_LEASE,
    ) -> None:
        if type(sampler) is not LiveStreamBudgetSampler:
            raise ValueError("canonical OS sampler required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected storage volume required")
        if type(max_probes) is not int or not 1 <= max_probes <= MAX_PROBES_PER_LEASE:
            raise ValueError("bounded pressure probe count required")
        self._sampler = sampler
        self._storage_path = storage_path
        self._max_probes = max_probes
        self._lock = RLock()
        self._active: str | None = None
        self._samples = 0
        self._stopped = False
        self._pressure: int | None = None

    def start(self, permit: DispatchPermit):
        """Return an interrupt callback; one active generation per guard."""
        if type(permit) is not DispatchPermit or permit.device_qualified:
            raise NativePressureInterrupted("CPU-only canonical permit required")
        with self._lock:
            if self._active is not None or self._stopped:
                raise NativePressureInterrupted("pressure guard not available")
            self._active = permit.lease_id
            self._samples = 0
            self._pressure = None

        def interrupt() -> None:
            with self._lock:
                if self._active != permit.lease_id or self._stopped:
                    raise NativePressureInterrupted("pressure guard no longer active")
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
                if (type(budget) is not MeasuredStreamBudget
                        or budget.measurement != "os_probe"
                        or type(evidence) is not dict
                        or evidence.get("measurement") != "os_probe"
                        or evidence.get("gpu_device_qualified") is not False
                        or evidence.get("physical_memory_reserved") is not False
                        or type(evidence.get("auxiliary_telemetry_incomplete")) is not bool):
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
        with self._lock:
            if type(success) is not bool:
                raise ValueError("explicit completion outcome required")
            # A success with zero callbacks or an already tripped guard
            # cannot be promoted to a reusable CPU execution permit.
            if success and (
                self._active is None or self._samples == 0 or self._stopped
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
        with self._lock:
            return NativePressureStatus(
                schema="skeleton.ai.native-token-pressure.v1",
                samples=self._samples, stopped=self._stopped,
                last_pressure_ppm=self._pressure,
            )
