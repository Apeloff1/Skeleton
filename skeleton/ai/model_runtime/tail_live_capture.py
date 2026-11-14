"""Live CPU inference timing capture with conservative OS resource evidence.

This is an instrumentation seam for the actual native/provider execution
owner. No JSON input can claim measured timestamps. Device qualification,
GPU residency and tokenizer correctness require separate direct evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
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
MAX_FINISHED = 10_000


def _worst_resource(first: ResourceObservation, last: ResourceObservation) -> ResourceObservation:
    """Use the more restrictive of start/end evidence, never the best sample.

    Unknown thermal/GPU telemetry stays unknown. A late measured thermal hold
    overrides an earlier healthy sample. This is telemetry, not a hardware
    reservation; the execution owner must independently enforce quotas.
    """
    thermal = (
        "measured_hold" if "measured_hold" in (first.thermal, last.thermal)
        else "unavailable" if "unavailable" in (first.thermal, last.thermal)
        else "measured_ok"
    )
    gpu_available = (
        first.gpu_free_bytes is not None and last.gpu_free_bytes is not None
    )
    return ResourceObservation(
        ram_available_bytes=min(first.ram_available_bytes, last.ram_available_bytes),
        ram_total_bytes=min(first.ram_total_bytes, last.ram_total_bytes),
        swap_free_bytes=min(first.swap_free_bytes, last.swap_free_bytes),
        swap_total_bytes=min(first.swap_total_bytes, last.swap_total_bytes),
        cpu_load_ppm=max(first.cpu_load_ppm, last.cpu_load_ppm),
        thermal=thermal,
        gpu_free_bytes=(
            min(first.gpu_free_bytes, last.gpu_free_bytes) if gpu_available else None
        ),
        gpu_total_bytes=(
            min(first.gpu_total_bytes, last.gpu_total_bytes) if gpu_available else None
        ),
    )


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
        try:
            pid = os.getpid()
        except BaseException as exc:
            raise RuntimeError("live tail process identity unavailable") from exc
        if type(pid) is not int or pid <= 0:
            raise RuntimeError("live tail process identity unavailable")
        self._owner_pid = pid

    def _require_owner_process(self) -> None:
        """An inherited lock/profile cannot grant a child execution evidence."""
        try:
            pid = os.getpid()
        except BaseException as exc:
            raise RuntimeError("live tail process identity unavailable") from exc
        if type(pid) is not int or pid != self._owner_pid:
            raise RuntimeError("forked live tail capture requires new owner")

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
        self._require_owner_process()
        if type(request_id) is not str or not request_id:
            raise ValueError("bounded request ID required")
        try:
            encoded = request_id.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError("bounded request ID required") from exc
        if len(encoded) > 128 or any(ord(ch) < 32 or ord(ch) == 127 for ch in request_id):
            raise ValueError("bounded request ID required")
        if type(prompt_tokens) is not int or not 0 <= prompt_tokens <= (1 << 24):
            raise ValueError("bounded prompt token count required")
        with self._lock:
            if request_id in self._active or request_id in self._finished:
                raise ValueError("duplicate local execution request")
            if len(self._finished) >= MAX_FINISHED:
                raise ValueError("completed identity window exhausted; rotate source session")
            if len(self._active) >= self._max_active:
                raise ValueError("active execution telemetry capacity exhausted")
            # Both the resource observation and the clock must succeed before
            # an active record can be published.
            resource = self._resource()
            start = self._now()
            self._active[request_id] = _Active(request_id, prompt_tokens, start, resource)

    def first_token(self, request_id: str) -> None:
        self._require_owner_process()
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
        self._require_owner_process()
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
            # Re-probe AFTER completion before committing the profile.
            # A thermal trip, swap spike, or RAM collapse during execution
            # must never be hidden by a healthy start-of-request sample.
            # Probe failure retains the active record and grants no evidence.
            end_resource = self._resource()
            self._profile.record(timing, _worst_resource(state.resource, end_resource))
            del self._active[request_id]
            self._finished.add(request_id)
            return timing

    def abort(self, request_id: str) -> None:
        self._require_owner_process()
        with self._lock:
            if request_id not in self._active:
                raise ValueError("unknown active execution")
            del self._active[request_id]
            self._finished.add(request_id)

    def snapshot(self, *, ttft_slo_ms: int, inter_token_slo_ms: int, e2e_slo_ms: int) -> dict[str, object]:
        self._require_owner_process()
        with self._lock:
            return self._profile.summary(
                ttft_slo_ms=ttft_slo_ms,
                inter_token_slo_ms=inter_token_slo_ms,
                e2e_slo_ms=e2e_slo_ms,
            )

    @property
    def active_count(self) -> int:
        self._require_owner_process()
        with self._lock:
            return len(self._active)
