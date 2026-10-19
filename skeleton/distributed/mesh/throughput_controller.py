"""Throughput controller — AIMD concurrency control per subsystem.

Additive-increase/multiplicative-decrease concurrency limits (like
TCP Vegas): inflight limit grows slowly on success, halves on
latency spikes or errors. Finds the optimal concurrency per subsystem
without manual tuning, and coordinates with the load shedder.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class HardwareTelemetry:
    """Live host and target-console hardware telemetry for hardware-aware AIMD control."""

    cpu_cores: int = 4
    cpu_load_ratio: float = 0.25
    memory_pressure: float = 0.30
    vram_pressure: float = 0.20
    thermal_c: float = 48.0
    simd_width_bits: int = 256
    l2_cache_kb: int = 1024
    target_console_profile: str = "host"
    console_cpu_mhz: float = 0.0
    console_ram_bytes: int = 0
    console_frame_budget_ms: float = 16.67

    def hardware_scale_factor(self) -> float:
        """Compute composite concurrency multiplier in [0.15, 2.50] from hardware headroom."""
        core_boost = min(2.0, max(0.5, (max(1, self.cpu_cores) / 4.0) ** 0.5))
        cpu_headroom = max(0.20, 1.0 - max(0.0, min(0.95, self.cpu_load_ratio)) * 0.80)
        mem_headroom = max(0.15, 1.0 - max(0.0, min(0.98, self.memory_pressure)) * 0.85)
        vram_headroom = max(0.25, 1.0 - max(0.0, min(0.98, self.vram_pressure)) * 0.70)
        thermal_factor = 1.0
        if self.thermal_c > 75.0:
            thermal_factor = max(0.20, 1.0 - (self.thermal_c - 75.0) / 30.0)
        scale = core_boost * cpu_headroom * min(mem_headroom, vram_headroom) * thermal_factor
        return round(max(0.15, min(2.50, scale)), 4)

    def under_severe_pressure(self) -> bool:
        return (
            self.cpu_load_ratio >= 0.90
            or self.memory_pressure >= 0.88
            or self.vram_pressure >= 0.90
            or self.thermal_c >= 85.0
        )

    def optimal_batch_size(self, base_batch_size: int = 8, item_bytes: int = 1024) -> int:
        """Compute SIMD-lane and L2-cache-aware batch size scaled by live hardware headroom."""
        base = max(1, int(base_batch_size))
        simd_lanes = max(1, int(self.simd_width_bits) // 64)
        cache_cap = max(1, (max(64, int(self.l2_cache_kb)) * 1024) // max(64, int(item_bytes) * 2))
        scaled = int(round(base * self.hardware_scale_factor()))
        aligned = max(1, (scaled // simd_lanes) * simd_lanes) if scaled >= simd_lanes else max(1, scaled)
        return max(1, min(cache_cap, 256, aligned))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "cpu_load_ratio": round(self.cpu_load_ratio, 4),
            "memory_pressure": round(self.memory_pressure, 4),
            "vram_pressure": round(self.vram_pressure, 4),
            "thermal_c": round(self.thermal_c, 2),
            "simd_width_bits": self.simd_width_bits,
            "l2_cache_kb": self.l2_cache_kb,
            "target_console_profile": self.target_console_profile,
            "console_cpu_mhz": round(self.console_cpu_mhz, 3),
            "console_ram_bytes": self.console_ram_bytes,
            "console_frame_budget_ms": round(self.console_frame_budget_ms, 3),
            "hardware_scale_factor": self.hardware_scale_factor(),
            "under_severe_pressure": self.under_severe_pressure(),
        }


@dataclass
class Lane:
    subsystem: str
    limit: float = 10.0
    min_limit: float = 1.0
    max_limit: float = 200.0
    inflight: int = 0
    target_latency_ms: float = 200.0
    increase_step: float = 1.0
    decrease_factor: float = 0.5
    successes: int = 0
    backoffs: int = 0
    ewma_latency_ms: float = 0.0
    min_latency_ms: float = 0.0


class ThroughputController:
    """AIMD + Vegas gradient concurrency limiter per subsystem lane with hardware awareness."""

    def __init__(
        self,
        *,
        initial_limit: float = 10.0,
        default_limit: Optional[float] = None,
        hardware_aware: bool = False,
    ):
        self._default_limit: float = float(default_limit if default_limit is not None else initial_limit)
        self._lanes: Dict[str, Lane] = {}
        self._rejected = 0
        self._hardware_aware: bool = bool(hardware_aware)
        self.hardware: HardwareTelemetry = HardwareTelemetry(
            cpu_cores=max(1, int(os.cpu_count() or 4)),
        )
        if self._hardware_aware:
            self.probe_hardware()

    def probe_hardware(self) -> Dict[str, Any]:
        """Probe live host CPU cores, OS load average, and /proc/meminfo memory pressure."""
        self._hardware_aware = True
        cores = max(1, int(os.cpu_count() or 4))
        self.hardware.cpu_cores = cores
        try:
            load1, _, _ = os.getloadavg()
            self.hardware.cpu_load_ratio = max(0.0, min(1.0, float(load1) / float(cores)))
        except (AttributeError, OSError):
            pass
        try:
            mem_total = 0
            mem_avail = 0
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail = int(line.split()[1])
                    if mem_total and mem_avail:
                        break
            if mem_total > 0:
                used_ratio = 1.0 - (float(mem_avail) / float(mem_total))
                self.hardware.memory_pressure = max(0.0, min(1.0, used_ratio))
        except OSError:
            pass
        info = self.hardware.to_dict()
        info["scale_factor"] = self.hardware.hardware_scale_factor()
        return info

    def update_hardware_telemetry(
        self,
        *,
        cpu_cores: Optional[int] = None,
        cpu_load_ratio: Optional[float] = None,
        memory_pressure: Optional[float] = None,
        vram_pressure: Optional[float] = None,
        thermal_c: Optional[float] = None,
        simd_width_bits: Optional[int] = None,
        l2_cache_kb: Optional[int] = None,
        target_console_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update hardware telemetry signals and enable hardware-aware concurrency & batching."""
        self._hardware_aware = True
        if cpu_cores is not None:
            self.hardware.cpu_cores = max(1, int(cpu_cores))
        if cpu_load_ratio is not None:
            self.hardware.cpu_load_ratio = max(0.0, min(1.0, float(cpu_load_ratio)))
        if memory_pressure is not None:
            self.hardware.memory_pressure = max(0.0, min(1.0, float(memory_pressure)))
        if vram_pressure is not None:
            self.hardware.vram_pressure = max(0.0, min(1.0, float(vram_pressure)))
        if thermal_c is not None:
            self.hardware.thermal_c = max(0.0, float(thermal_c))
        if simd_width_bits is not None:
            self.hardware.simd_width_bits = max(64, int(simd_width_bits))
        if l2_cache_kb is not None:
            self.hardware.l2_cache_kb = max(64, int(l2_cache_kb))
        if target_console_profile is not None:
            self.bind_console_target(target_console_profile)
        return self.hardware_report()

    def bind_console_target(self, profile_key: str) -> Dict[str, Any]:
        """Calibrate hardware telemetry and frame latency targets against a console/ROM hardware profile."""
        self._hardware_aware = True
        key = str(profile_key or "host").strip().lower()
        self.hardware.target_console_profile = key
        try:
            from skeleton.forge.hardware import get_console_rom_profile

            prof = get_console_rom_profile(key)
            cpu_mhz = float(prof.get("cpu_clock_mhz", 4.194) or 4.194)
            wram_b = int(prof.get("wram_bytes", 8192) or 8192)
            fps = float(prof.get("refresh_hz", 60.0) or 60.0)
            frame_ms = 1000.0 / max(1.0, fps)
            self.hardware.console_cpu_mhz = cpu_mhz
            self.hardware.console_ram_bytes = wram_b
            self.hardware.console_frame_budget_ms = round(frame_ms, 3)
        except Exception:  # noqa: BLE001
            self.hardware.console_cpu_mhz = 1000.0
            self.hardware.console_ram_bytes = 64 * 1024 * 1024
            self.hardware.console_frame_budget_ms = 16.67
        return self.hardware.to_dict()

    def effective_limit(self, subsystem: str) -> int:
        lane = self.lane(subsystem)
        if not self._hardware_aware:
            return max(1, int(lane.limit))
        scaled = lane.limit * self.hardware.hardware_scale_factor()
        return max(int(lane.min_limit), min(int(lane.max_limit), max(1, int(round(scaled)))))

    def optimal_batch_size(self, subsystem: str, *, base_batch_size: int = 8, item_bytes: int = 1024) -> int:
        """Compute optimal hardware-aware vectorized batch size for `subsystem`."""
        lane = self.lane(subsystem)
        hw_batch = self.hardware.optimal_batch_size(base_batch_size=base_batch_size, item_bytes=item_bytes)
        eff = self.effective_limit(subsystem)
        if lane.ewma_latency_ms > lane.target_latency_ms > 0:
            hw_batch = max(1, hw_batch // 2)
        return max(1, min(hw_batch, max(2, eff * 2)))

    def hardware_report(self) -> Dict[str, Any]:
        return {
            "kind": "throughput-hardware-report",
            "hardware_aware": self._hardware_aware,
            "telemetry": self.hardware.to_dict(),
            "effective_limits": {name: self.effective_limit(name) for name in self._lanes},
            "optimal_batch_sizes": {name: self.optimal_batch_size(name) for name in self._lanes},
        }

    def lane(self, subsystem: str, target_latency_ms: float = 200.0) -> Lane:
        if subsystem not in self._lanes:
            self._lanes[subsystem] = Lane(subsystem=subsystem, target_latency_ms=target_latency_ms)
        return self._lanes[subsystem]

    def acquire(self, subsystem: str, *, priority: str = "normal") -> bool:
        lane = self.lane(subsystem)
        eff_limit = self.effective_limit(subsystem)
        if lane.inflight >= eff_limit:
            self._rejected += 1
            return False
        prio = str(priority or "normal").lower()
        if self._hardware_aware and self.hardware.under_severe_pressure() and prio in {"background", "shed_first"}:
            self._rejected += 1
            return False
        util = float(lane.inflight) / float(eff_limit)
        if prio in {"background", "shed_first"} and eff_limit >= 2 and util >= 0.75:
            self._rejected += 1
            return False
        if prio == "normal" and eff_limit >= 4 and util >= 0.90:
            self._rejected += 1
            return False
        lane.inflight += 1
        return True

    def release(self, subsystem: str, latency_ms: float, error: bool = False) -> None:
        lane = self.lane(subsystem)
        lane.inflight = max(0, lane.inflight - 1)
        lat = max(0.0, float(latency_ms))
        if lane.ewma_latency_ms <= 0.0:
            lane.ewma_latency_ms = lat
        else:
            lane.ewma_latency_ms = 0.8 * lane.ewma_latency_ms + 0.2 * lat
        if lane.min_latency_ms <= 0.0 or (lat > 0.0 and lat < lane.min_latency_ms):
            lane.min_latency_ms = lat
        hw_scale = self.hardware.hardware_scale_factor() if self._hardware_aware else 1.0
        if error or lat > lane.target_latency_ms * 1.5 or (self._hardware_aware and self.hardware.under_severe_pressure() and lat > lane.target_latency_ms):
            dec = lane.decrease_factor * (0.85 if (self._hardware_aware and self.hardware.under_severe_pressure()) else 1.0)
            lane.limit = max(lane.min_limit, lane.limit * max(0.25, dec))
            lane.backoffs += 1
        else:
            gradient = (lane.min_latency_ms / max(lane.ewma_latency_ms, 1e-3)) if lane.min_latency_ms > 0 else 1.0
            step = lane.increase_step * max(0.5, min(1.5, gradient)) * max(0.5, min(1.5, hw_scale))
            lane.limit = min(lane.max_limit, lane.limit + step / max(1, int(lane.limit)))
            lane.successes += 1

    def execute(self, subsystem: str, fn: Callable[[], Any], *, priority: str = "normal") -> Dict[str, Any]:
        if not self.acquire(subsystem, priority=priority):
            return {"executed": False, "reason": "concurrency limit", "priority": priority}
        start = time.time_ns()
        error = False
        result: Any = None
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            error = True
            result = exc
        latency_ms = (time.time_ns() - start) / 1e6
        self.release(subsystem, latency_ms, error)
        if error:
            raise result
        return {"executed": True, "result": result, "latency_ms": round(latency_ms, 2), "priority": priority}

    def current_limit(self, subsystem: str) -> float:
        return self.lane(subsystem).limit

    def utilization(self, subsystem: str) -> float:
        lane = self.lane(subsystem)
        return lane.inflight / lane.limit if lane.limit else 0.0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "throughput-controller-card",
            "hardware_aware": self._hardware_aware,
            "hardware": self.hardware.to_dict(),
            "lanes": {n: {
                "limit": round(l.limit, 2),
                "effective_limit": self.effective_limit(n),
                "optimal_batch_size": self.optimal_batch_size(n),
                "inflight": l.inflight,
                "utilization": round(self.utilization(n), 3),
                "successes": l.successes,
                "backoffs": l.backoffs,
            } for n, l in self._lanes.items()},
            "rejected": self._rejected,
        }

    def execute_coalesced_batch(
        self,
        subsystem: str,
        items: List[Any],
        batch_fn: Callable[[List[Any]], List[Any]],
        *,
        max_batch_size: int = 8,
        auto_hardware_batch: bool = False,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """Coalesce multiple micro-requests into bounded vectorized batches under lane admission control."""
        if not items:
            return {"executed": True, "results": [], "batches_run": 0, "coalesced_items": 0}
        b_size = (
            self.optimal_batch_size(subsystem, base_batch_size=max_batch_size)
            if auto_hardware_batch
            else max(1, int(max_batch_size))
        )
        results: List[Any] = []
        batches_run = 0
        total_latency_ms = 0.0
        for idx in range(0, len(items), b_size):
            chunk = items[idx:idx + b_size]
            if not self.acquire(subsystem, priority=priority):
                return {
                    "executed": False,
                    "reason": "concurrency limit",
                    "priority": priority,
                    "batches_run": batches_run,
                    "partial_results": results,
                }
            start = time.time_ns()
            error = False
            chunk_out: Any = None
            try:
                chunk_out = batch_fn(chunk)
            except Exception as exc:  # noqa: BLE001
                error = True
                chunk_out = exc
            lat_ms = (time.time_ns() - start) / 1e6
            total_latency_ms += lat_ms
            self.release(subsystem, lat_ms, error)
            if error:
                raise chunk_out
            if isinstance(chunk_out, list):
                results.extend(chunk_out)
            else:
                results.append(chunk_out)
            batches_run += 1
        return {
            "executed": True,
            "results": results,
            "batches_run": batches_run,
            "coalesced_items": len(items),
            "total_latency_ms": round(total_latency_ms, 2),
            "priority": priority,
        }
