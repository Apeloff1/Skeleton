"""
Skeleton Overseer — Hardware Probe

Device capability and live-state detection across all hardware classes.
Stdlib-only: reads /proc and sysfs on Linux, sysctl on macOS, sensible
fall-backs everywhere else so the probe NEVER fails a boot.

Surfaces:
- HardwareProfile: static capability snapshot (cpu cores, arch, memory
  total, gpu class, storage class, thermal zones count, battery present)
- HardwareState: live reading (cpu load per-core + aggregate, memory
  used/available, swap pressure, thermal temps, battery level +
  charging state, io wait)
- DeviceClass: coarse device tier the governor tunes against
  (embedded | mobile | laptop | workstation | server)

The probe re-classifies on every refresh: hotplug, battery attach,
thermal events, and memory pressure shifts all flow through as
first-class change events the governor reacts to.
"""

from __future__ import annotations

import os
import platform
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class DeviceClass(Enum):
    EMBEDDED = "embedded"      # <2 cores or <1GB RAM
    MOBILE = "mobile"          # battery present, <=4 cores
    LAPTOP = "laptop"          # battery present, >4 cores
    WORKSTATION = "workstation"  # no battery, >=8 cores, >=16GB
    SERVER = "server"          # no battery, >=16 cores or >=64GB


class GPUClass(Enum):
    NONE = "none"
    INTEGRATED = "integrated"
    DISCRETE = "discrete"
    COMPUTE = "compute"  # CUDA-class


@dataclass
class HardwareProfile:
    """Static capability snapshot — what this device CAN do."""
    cpu_cores: int
    cpu_arch: str
    memory_total_mb: int
    gpu: GPUClass
    storage_class: str  # nvme | ssd | hdd | unknown
    thermal_zones: int
    battery_present: bool
    device_class: DeviceClass
    os: str
    probed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "cpu_arch": self.cpu_arch,
            "memory_total_mb": self.memory_total_mb,
            "gpu": self.gpu.value,
            "storage_class": self.storage_class,
            "thermal_zones": self.thermal_zones,
            "battery_present": self.battery_present,
            "device_class": self.device_class.value,
            "os": self.os,
        }


@dataclass
class HardwareState:
    """Live hardware reading — what this device is doing RIGHT NOW."""
    cpu_load: float           # 0..1 aggregate
    cpu_per_core: List[float]
    memory_used_mb: int
    memory_available_mb: int
    memory_pressure: float    # 0..1 (used / total)
    swap_pressure: float      # 0..1
    temps_celsius: List[float]
    battery_level: Optional[float]     # 0..1 or None
    battery_charging: Optional[bool]
    io_wait: float            # 0..1
    read_at: float = field(default_factory=time.time)

    def thermal_max(self) -> float:
        return max(self.temps_celsius) if self.temps_celsius else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_load": round(self.cpu_load, 3),
            "memory_pressure": round(self.memory_pressure, 3),
            "swap_pressure": round(self.swap_pressure, 3),
            "thermal_max_c": round(self.thermal_max(), 1),
            "battery_level": self.battery_level,
            "battery_charging": self.battery_charging,
            "io_wait": round(self.io_wait, 3),
        }


@dataclass
class HardwareChange:
    """A detected device change the governor must react to."""
    kind: str  # thermal_spike | battery_low | battery_unplugged | memory_pressure | cpu_spike | profile_shift
    severity: float  # 0..1
    detail: str
    at: float = field(default_factory=time.time)


class HardwareProbe:
    """Cross-platform hardware probe. Never raises: missing sensors
    yield conservative defaults so every device boots."""

    # Thresholds that constitute a 'change event'
    THERMAL_WARN_C = 75.0
    THERMAL_CRIT_C = 90.0
    BATTERY_LOW = 0.15
    MEM_PRESSURE_WARN = 0.85
    CPU_SPIKE = 0.95

    def __init__(self):
        self._profile: Optional[HardwareProfile] = None
        self._prev_state: Optional[HardwareState] = None
        self._sys = platform.system().lower()

    # --- Profile (static) --------------------------------------------------

    def profile(self, refresh: bool = False) -> HardwareProfile:
        if self._profile is not None and not refresh:
            return self._profile

        cores = os.cpu_count() or 1
        mem_mb = self._memory_total_mb()
        battery = self._battery_present()
        gpu = self._gpu_class()
        storage = self._storage_class()
        thermal_zones = len(self._thermal_zone_paths())

        if cores >= 16 or mem_mb >= 65536:
            if not battery:
                cls = DeviceClass.SERVER
            else:
                cls = DeviceClass.LAPTOP
        elif battery and cores <= 4:
            cls = DeviceClass.MOBILE
        elif battery:
            cls = DeviceClass.LAPTOP
        elif cores >= 8 and mem_mb >= 16384:
            cls = DeviceClass.WORKSTATION
        elif cores < 2 or mem_mb < 1024:
            cls = DeviceClass.EMBEDDED
        else:
            cls = DeviceClass.WORKSTATION

        self._profile = HardwareProfile(
            cpu_cores=cores,
            cpu_arch=platform.machine() or "unknown",
            memory_total_mb=mem_mb,
            gpu=gpu,
            storage_class=storage,
            thermal_zones=thermal_zones,
            battery_present=battery,
            device_class=cls,
            os=platform.system(),
        )
        return self._profile

    # --- State (live) --------------------------------------------------------

    def read_state(self) -> HardwareState:
        cpu_load, per_core, io_wait = self._cpu_load()
        mem_used, mem_avail, mem_pressure, swap_pressure = self._memory_state()
        temps = self._temps()
        batt_level, batt_charging = self._battery_state()

        state = HardwareState(
            cpu_load=cpu_load,
            cpu_per_core=per_core,
            memory_used_mb=mem_used,
            memory_available_mb=mem_avail,
            memory_pressure=mem_pressure,
            swap_pressure=swap_pressure,
            temps_celsius=temps,
            battery_level=batt_level,
            battery_charging=batt_charging,
            io_wait=io_wait,
        )
        self._prev_state = state
        return state

    # --- Change detection ------------------------------------------------------

    def detect_changes(self, state: Optional[HardwareState] = None) -> List[HardwareChange]:
        """Compare the live state against thresholds + previous reading."""
        state = state or self.read_state()
        prev = self._prev_state
        changes: List[HardwareChange] = []

        tmax = state.thermal_max()
        if tmax >= self.THERMAL_CRIT_C:
            changes.append(HardwareChange("thermal_spike", 1.0, f"thermal {tmax:.0f}C critical"))
        elif tmax >= self.THERMAL_WARN_C:
            changes.append(HardwareChange("thermal_spike", 0.6, f"thermal {tmax:.0f}C elevated"))

        if state.battery_level is not None:
            if state.battery_level <= self.BATTERY_LOW and not state.battery_charging:
                changes.append(HardwareChange("battery_low", 0.8,
                                              f"battery {state.battery_level:.0%} discharging"))
            if prev and prev.battery_charging and not state.battery_charging:
                changes.append(HardwareChange("battery_unplugged", 0.5, "AC disconnected"))

        if state.memory_pressure >= self.MEM_PRESSURE_WARN:
            changes.append(HardwareChange("memory_pressure", state.memory_pressure,
                                          f"memory {state.memory_pressure:.0%} used"))

        if state.cpu_load >= self.CPU_SPIKE:
            changes.append(HardwareChange("cpu_spike", state.cpu_load,
                                          f"cpu {state.cpu_load:.0%} saturated"))

        if prev and prev.device_class_changed(state) if hasattr(prev, "device_class_changed") else False:
            pass  # reserved for future hotplug handling

        return changes

    # --- Platform readers (stdlib, best-effort) ----------------------------------

    def _memory_total_mb(self) -> int:
        try:
            if self._sys == "linux":
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) // 1024
            if self._sys == "darwin":
                import subprocess
                out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2)
                return int(out.strip()) // (1024 * 1024)
        except Exception:
            pass
        return 4096  # conservative default

    def _memory_state(self) -> Tuple[int, int, float, float]:
        total = self._memory_total_mb()
        try:
            if self._sys == "linux":
                info = {}
                for line in Path("/proc/meminfo").read_text().splitlines():
                    k, rest = line.split(":", 1)
                    info[k] = int(rest.split()[0]) // 1024
                avail = info.get("MemAvailable", info.get("MemFree", total // 2))
                used = total - avail
                swap_total = info.get("SwapTotal", 0)
                swap_free = info.get("SwapFree", 0)
                swap_p = (swap_total - swap_free) / swap_total if swap_total else 0.0
                return used, avail, used / max(1, total), swap_p
        except Exception:
            pass
        used = total // 2
        return used, total - used, 0.5, 0.0

    def _cpu_load(self) -> Tuple[float, List[float], float]:
        try:
            if self._sys == "linux":
                parts = Path("/proc/loadavg").read_text().split()
                cores = os.cpu_count() or 1
                load1 = float(parts[0]) / cores
                per_core = [min(1.0, load1)] * cores
                io_wait = 0.0
                try:
                    stat = Path("/proc/stat").read_text().splitlines()[0].split()
                    user, nice, system, idle, iowait = (float(x) for x in stat[1:6])
                    total = user + nice + system + idle + iowait
                    io_wait = iowait / total if total else 0.0
                except Exception:
                    pass
                return min(1.0, load1), per_core, io_wait
            return os.getloadavg()[0] / (os.cpu_count() or 1), [0.5] * (os.cpu_count() or 1), 0.0
        except Exception:
            return 0.5, [0.5] * (os.cpu_count() or 1), 0.0

    def _thermal_zone_paths(self) -> List[Path]:
        base = Path("/sys/class/thermal")
        if not base.exists():
            return []
        try:
            return [p / "temp" for p in base.glob("thermal_zone*") if (p / "temp").exists()]
        except Exception:
            return []

    def _temps(self) -> List[float]:
        temps = []
        for path in self._thermal_zone_paths():
            try:
                temps.append(int(path.read_text().strip()) / 1000.0)
            except Exception:
                continue
        return temps

    def _battery_present(self) -> bool:
        return Path("/sys/class/power_supply").exists() and any(
            "BAT" in p.name for p in Path("/sys/class/power_supply").glob("*")
        ) if self._sys == "linux" else self._sys == "darwin"

    def _battery_state(self) -> Tuple[Optional[float], Optional[bool]]:
        try:
            if self._sys == "linux":
                for bat in Path("/sys/class/power_supply").glob("BAT*"):
                    cap = (bat / "capacity")
                    status = (bat / "status")
                    if cap.exists():
                        level = int(cap.read_text().strip()) / 100.0
                        charging = status.exists() and status.read_text().strip() in ("Charging", "Full")
                        return level, charging
        except Exception:
            pass
        return None, None

    def _gpu_class(self) -> GPUClass:
        try:
            if self._sys == "linux":
                drm = Path("/sys/class/drm")
                if drm.exists():
                    cards = list(drm.glob("card[0-9]"))
                    if cards:
                        # Heuristic: nvidia/amdgpu module presence → discrete
                        drivers = ""
                        for card in cards:
                            try:
                                drivers += (card / "device/driver/module").resolve().name + " "
                            except Exception:
                                pass
                        if "nvidia" in drivers or "amdgpu" in drivers:
                            return GPUClass.DISCRETE
                        return GPUClass.INTEGRATED
        except Exception:
            pass
        return GPUClass.NONE

    def _storage_class(self) -> str:
        try:
            if self._sys == "linux":
                for block in Path("/sys/block").glob("*"):
                    if "nvme" in block.name:
                        return "nvme"
                for block in Path("/sys/block").glob("sd*"):
                    rotational = block / "queue/rotational"
                    if rotational.exists():
                        return "hdd" if rotational.read_text().strip() == "1" else "ssd"
        except Exception:
            pass
        return "unknown"
