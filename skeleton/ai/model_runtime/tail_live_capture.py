"""Live CPU inference timing capture with conservative OS resource evidence.

This is an instrumentation seam for the actual native/provider execution
owner. No JSON input can claim measured timestamps. Device qualification,
GPU residency and tokenizer correctness require separate direct evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from threading import RLock
from time import monotonic_ns
from typing import Callable

from skeleton.app.offline_resources import LocalResourceSnapshot, probe_local_resources
from skeleton.app.offline_cpu_thermal import CPUThermalController, probe_cpu_thermal
from .execution_telemetry import ExecutionTiming
from .tail_latency_profile import (
    LocalTailProfiler, ProfileIdentity, ResourceObservation,
)

MAX_ACTIVE = 64


@dataclass(slots=True)
class _Active:
    request_id: str
    prompt_tokens: int
    started_ns: int
    resource: ResourceObservation
    first_token_ns: int | None = None


class LiveTailCapture:
    """Thread-safe event capture from an app-owned local execution lifecycle.

    Calls must originate from the trusted native/provider execution owner,
    not from operator-supplied JSON. Each active request has a bounded
    in-memory state machine: started -> first_token -> committed/aborted.
    An incomplete or cancelled request is never counted as completed.
    """

    def __init__(
        self, identity: ProfileIdentity, *,
        storage_path: str,
        max_active: int = MAX_ACTIVE,
        clock: Callable[[], int] | None = None,
        resource_probe: Callable[[str], LocalResourceSnapshot] | None = None,
    ) -> None:
        if not isinstance(identity, ProfileIdentity):
            raise ValueError("source-bound profile identity required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected storage volume required")
        if type(max_active) is not int or not 1 <= max_active <= MAX_ACTIVE:
            raise ValueError("bounded active request capacity required")
        if (clock is not None or resource_probe is not None) and identity.evidence != "simulated":
            raise ValueError("injected timing or hardware probes must be simulated")
        self._clock = monotonic_ns if clock is None else clock
        self._probe = probe_local_resources if resource_probe is None else resource_probe
        self._path = storage_path
        self._thermal = CPUThermalController()
        self._profile = LocalTailProfiler(identity)
        self._lock = RLock()
        self._active: dict[str, _Active] = {}
        self._finished: set[str] = set()
        self._max_active = max_active

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or value < 0:
            raise ValueError("invalid monotonic clock")
        return value

    def _resource(self) -> ResourceObservation:
        snapshot = self._probe(self._path)
        if not isinstance(snapshot, LocalResourceSnapshot):
            raise ValueError("canonical resource snapshot required")
        if not math.isfinite(snapshot.cpu_load_ratio):
            raise ValueError("invalid CPU load")
        self._thermal.observe(probe_cpu_thermal() if self._probe is probe_local_resources else ())
        thermal = self._thermal.snapshot()
        if not thermal["trip_measured"]:
            state = "unavailable"
        elif thermal["thermal_backpressure"]:
            state = "measured_hold"
        else:
            state = "measured_ok"
        return ResourceObservation(
            ram_available_bytes=snapshot.available_ram_bytes,
            ram_total_bytes=snapshot.total_ram_bytes,
            swap_free_bytes=snapshot.free_swap_bytes,
            swap_total_bytes=snapshot.total_swap_bytes,
            cpu_load_ppm=min(1_000_000, max(0, int(snapshot.cpu_load_ratio * 1_000_000))),
            thermal=state,
            gpu_free_bytes=None,
            gpu_total_bytes=None,
        )

    def begin(self, *, request_id: str, prompt_tokens: int) -> None:
        if type(request_id) is not str or not request_id or len(request_id.encode("utf-8")) > 128:
            raise ValueError("bounded request ID required")
        if type(prompt_tokens) is not int or not 0 <= prompt_tokens <= (1 << 24):
            raise ValueError("bounded prompt token count required")
        with self._lock:
            if request_id in self._active or request_id in self._finished:
                raise ValueError("duplicate local execution request")
            if len(self._active) >= self._max_active:
                raise ValueError("active execution telemetry capacity exhausted")
            # Both the resource observation and the clock must succeed before
            # an active record can be published.
            resource = self._resource()
            start = self._now()
            self._active[request_id] = _Active(request_id, prompt_tokens, start, resource)

    def first_token(self, request_id: str) -> None:
        with self._lock:
            state = self._active.get(request_id)
            if state is None or state.first_token_ns is not None:
                raise ValueError("first-token transition unavailable")
            stamp = self._now()
            if stamp < state.started_ns:
                raise ValueError("monotonic clock moved backwards")
            state.first_token_ns = stamp

    def complete(
        self, request_id: str, *, output_tokens: int, prefix_reused_tokens: int = 0,
    ) -> ExecutionTiming:
        with self._lock:
            state = self._active.get(request_id)
            if state is None or state.first_token_ns is None:
                raise ValueError("cannot complete without first token")
            if type(output_tokens) is not int or not 1 <= output_tokens <= (1 << 24):
                raise ValueError("bounded output token count required")
            if type(prefix_reused_tokens) is not int or not 0 <= prefix_reused_tokens <= state.prompt_tokens:
                raise ValueError("invalid prefix reuse")
            end = self._now()
            timing = ExecutionTiming(
                request_id=request_id, started_ns=state.started_ns,
                first_token_ns=state.first_token_ns, completed_ns=end,
                output_tokens=output_tokens, prompt_tokens=state.prompt_tokens,
                prefix_reused_tokens=prefix_reused_tokens,
            )
            # If recording fails, retain the active record; never report
            # success for a profile that was not committed.
            self._profile.record(timing, state.resource)
            del self._active[request_id]
            self._finished.add(request_id)
            return timing

    def abort(self, request_id: str) -> None:
        with self._lock:
            if request_id not in self._active:
                raise ValueError("unknown active execution")
            del self._active[request_id]
            self._finished.add(request_id)

    def snapshot(self, *, ttft_slo_ms: int, inter_token_slo_ms: int, e2e_slo_ms: int) -> dict[str, object]:
        with self._lock:
            return self._profile.summary(
                ttft_slo_ms=ttft_slo_ms,
                inter_token_slo_ms=inter_token_slo_ms,
                e2e_slo_ms=e2e_slo_ms,
            )

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active)
