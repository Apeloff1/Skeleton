"""Live, conservative CPU stream budgets using canonical OS pressure probes.

This is a local read-only admission controller, not a device qualification,
physical memory reservation, token executor, or a hardware capability claim.
A long-lived instance retains hysteresis across calls. Callers must re-probe
and enforce backend allocation limits at the actual dispatch boundary.
"""
from __future__ import annotations

from threading import RLock
import sys

from skeleton.app.offline_resources import probe_local_resources
from skeleton.app.offline_cgroup_memory_headroom import probe_cgroup_memory_headroom
from skeleton.app.offline_cgroup_swap_headroom import probe_cgroup_swap_headroom
from skeleton.app.offline_cpu_thermal import CPUThermalController, probe_cpu_thermal
from skeleton.app.offline_cgroup_events import CgroupPressureTracker, probe_cgroup_events
from skeleton.app.offline_io_pressure import IOPressureController, probe_io_pressure
from skeleton.app.offline_cpu_throttle import CPUThrottleController, probe_cpu_throttle
from skeleton.app.offline_swap_churn import SwapChurnController, probe_swap_counters
from skeleton.app.offline_reclaim_pressure import (
    ReclaimPressureController, probe_reclaim_counters,
)
from .fair_stream_queue import MAX_TOKENS, MeasuredStreamBudget


class LiveStreamBudgetSampler:
    """Serialize OS observations and retain conservative pressure hysteresis.

    The sampler is intentionally process-local. It cannot make cross-process
    allocations safe, so a dispatch owner must still enforce its own quotas.
    Missing auxiliary Linux telemetry never increases stream fan-out. A hard
    OOM/thermal/disk hold admits zero work. No GPU budgets are produced.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._thermal = CPUThermalController()
        self._cgroup = CgroupPressureTracker()
        self._io = IOPressureController()
        self._cpu = CPUThrottleController()
        self._swap = SwapChurnController()
        self._reclaim = ReclaimPressureController()

    def sample(
        self, *, token_budget: int, storage_path: str = ".",
    ) -> tuple[MeasuredStreamBudget, dict[str, object]]:
        if type(token_budget) is not int or not 1 <= token_budget <= MAX_TOKENS:
            raise ValueError("positive bounded token budget required")
        if type(storage_path) is not str or not storage_path:
            raise ValueError("selected storage volume required")
        with self._lock:
            host = probe_local_resources(storage_path)
            # A container can have far less RAM than its host. The separate
            # cgroup capacity probe is conservative across concurrent usage.
            cgroup_memory = probe_cgroup_memory_headroom()
            cgroup_swap = probe_cgroup_swap_headroom()
            available_ram = host.available_ram_bytes
            if cgroup_memory is not None and cgroup_memory.headroom_bytes is not None:
                available_ram = min(available_ram, cgroup_memory.headroom_bytes)
            if host.available_ram_bytes <= 0:
                raise ValueError("no measured RAM headroom")
            self._thermal.observe(probe_cpu_thermal())
            thermal = self._thermal.snapshot()
            self._io.observe(probe_io_pressure())
            io = self._io.snapshot()
            self._cgroup.sample(probe_cgroup_events())
            cgroup = self._cgroup.snapshot()
            self._cpu.observe(probe_cpu_throttle())
            cpu = self._cpu.snapshot()
            self._swap.observe(
                probe_swap_counters(), physical_ram_bytes=host.total_ram_bytes,
            )
            swap = self._swap.snapshot()
            self._reclaim.observe(
                probe_reclaim_counters(), physical_ram_bytes=host.total_ram_bytes,
            )
            reclaim = self._reclaim.snapshot()
            # OS and model allocations are not reserved by this sampler.
            # Keep a proportional RAM margin for system, weights, UI and KV.
            reserve = max(
                available_ram // 3,
                min(available_ram, 64 * 1024 * 1024),
            )
            pressure = max(
                host.memory_pressure_ratio,
                min(1.0, max(0.0, host.cpu_load_ratio - 0.5)),
            )
            if cgroup_memory is not None:
                pressure = max(pressure, cgroup_memory.pressure_ppm / 1_000_000)
            if host.total_swap_bytes:
                used = 1 - host.free_swap_bytes / host.total_swap_bytes
                if used >= 0.85:
                    pressure = max(pressure, 0.85)
            if io["measured"]:
                pressure = max(
                    pressure,
                    min(1.0, float(io["some_avg10_percent"]) / 100),
                )
            if cpu["observed_throttled_ratio"] is not None:
                pressure = max(pressure, float(cpu["observed_throttled_ratio"]))
            # Rate controllers need two or more real samples to identify
            # stress. Their unknown initial state must not imply spare slots.
            missing = (
                sys.platform != "linux"
                or cgroup_memory is None
                or not io["measured"]
                or not cgroup["measured"]
                or not cpu["measured"]
                or not swap["measured"]
                or reclaim["scanned_ram_fraction_per_s"] is None
            )
            holds = {
                "thermal": bool(thermal["thermal_backpressure"]),
                "cgroup_high": bool(cgroup["high_backpressure"]),
                "cgroup_oom": bool(cgroup["oom_backpressure"]),
                "cgroup_memory": bool(cgroup_memory and cgroup_memory.hard_hold),
                "cgroup_swap_spill": bool(cgroup_swap is None or not cgroup_swap.spill_allowed),
                "io": bool(io["congested"]),
                "cpu_throttle": bool(cpu["backpressure"]),
                "swap_churn": bool(swap["backpressure"]),
                "reclaim": bool(reclaim["backpressure"]),
                "disk_reserve": host.free_disk_bytes <= max(
                    host.total_disk_bytes // 100, 64 * 1024 * 1024,
                ),
            }
            if holds["cgroup_high"] or holds["io"] or holds["cpu_throttle"]:
                pressure = max(pressure, 0.85)
            if holds["swap_churn"] or holds["reclaim"]:
                pressure = max(pressure, 0.90)
            hard_hold = (
                holds["thermal"] or holds["cgroup_oom"]
                or holds["cgroup_memory"] or holds["disk_reserve"]
            )
            if hard_hold:
                pressure = 1.0
            slots = min(64, host.suggested_index_jobs)
            if missing or any(holds.values()):
                slots = min(slots, 1)
            if hard_hold:
                slots = 0
            # Unmeasured auxiliary sensors cannot authorize large batches.
            # This is a temporary per-probe quantum, never a user file limit.
            bounded_tokens = min(token_budget, 128) if missing else token_budget
            budget = MeasuredStreamBudget(
                available_ram_bytes=available_ram,
                reserved_ram_bytes=reserve,
                token_budget=bounded_tokens,
                stream_slots=slots,
                pressure_ppm=min(1_000_000, max(0, int(pressure * 1_000_000))),
                thermal_hold=hard_hold,
                measurement="os_probe",
            )
            evidence: dict[str, object] = {
                "schema": "skeleton.ai.live-stream-pressure.v1",
                "measurement": "os_probe",
                "auxiliary_telemetry_incomplete": missing,
                "cgroup_swap_spill_allowed": bool(cgroup_swap and cgroup_swap.spill_allowed),
                "cgroup_swap_limit_measured": bool(
                    cgroup_swap and cgroup_swap.limit_bytes is not None
                ),
                "cgroup_memory_limit_measured": bool(
                    cgroup_memory and cgroup_memory.limit_bytes is not None
                ),
                "thermal_trip_measured": bool(thermal["trip_measured"]),
                "holds": holds,
                "gpu_device_qualified": False,
                "physical_memory_reserved": False,
                "cross_process_admission_guaranteed": False,
            }
            return budget, evidence
