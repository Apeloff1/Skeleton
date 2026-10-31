"""Offline battery/thermal observation and conservative background admission.

Read-only platform probes. No hardware clocks, fans, RAM, OS power settings,
model weights, provider credentials or network endpoints are modified.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Sequence

from skeleton.app.offline_cpu_budget import (
    CpuBudgetError, CpuWorkerPlan, plan_cpu_workers,
    probe_cpu_topology, probe_memory_topology,
)

SCHEMA = "skeleton.offline.energy-admission.v1"


class EnergyError(ValueError):
    """Invalid power telemetry or unsafe background energy admission."""


@dataclass(frozen=True, slots=True)
class PowerObservation:
    battery_percent: int | None
    on_ac: bool | None
    cpu_temperature_c: float | None
    battery_source: str
    ac_source: str
    thermal_source: str

    def __post_init__(self) -> None:
        if self.battery_percent is not None and (
            type(self.battery_percent) is not int or not 0 <= self.battery_percent <= 100
        ):
            raise EnergyError("invalid battery percentage")
        if self.on_ac is not None and type(self.on_ac) is not bool:
            raise EnergyError("invalid AC line observation")
        if self.cpu_temperature_c is not None and (
            type(self.cpu_temperature_c) not in (int, float)
            or not math.isfinite(self.cpu_temperature_c)
            or not -30 <= self.cpu_temperature_c <= 150
        ):
            raise EnergyError("invalid CPU thermal reading")
        for source in (self.battery_source, self.ac_source, self.thermal_source):
            if type(source) is not str or not 1 <= len(source) <= 128:
                raise EnergyError("invalid evidence source")


@dataclass(frozen=True, slots=True)
class EnergyPolicy:
    low_battery_pct: int = 20
    critical_battery_pct: int = 8
    warm_cpu_c: float = 75.0
    critical_cpu_c: float = 88.0

    def __post_init__(self) -> None:
        if type(self.low_battery_pct) is not int or type(self.critical_battery_pct) is not int:
            raise EnergyError("invalid battery policy")
        if not 0 <= self.critical_battery_pct < self.low_battery_pct <= 100:
            raise EnergyError("battery policy thresholds must be ordered")
        if type(self.warm_cpu_c) not in (int, float) or type(self.critical_cpu_c) not in (int, float):
            raise EnergyError("invalid thermal policy")
        if not math.isfinite(self.warm_cpu_c) or not math.isfinite(self.critical_cpu_c):
            raise EnergyError("nonfinite thermal policy")
        if not 0 < self.warm_cpu_c < self.critical_cpu_c <= 120:
            raise EnergyError("thermal policy thresholds must be ordered")


@dataclass(frozen=True, slots=True)
class EnergyAdmission:
    allowed_workers: int
    base_workers: int
    reason: str
    digest: str
    observation: PowerObservation
    policy: EnergyPolicy


def _bounded(path: Path, limit: int = 256) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            return None
        return data.decode("ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        return None


def _percent(raw: str | None) -> int | None:
    if raw is None or not re.fullmatch(r"[0-9]{1,3}", raw):
        return None
    number = int(raw)
    return number if 0 <= number <= 100 else None


def _linux_power() -> tuple[int | None, bool | None, str, str]:
    root = Path("/sys/class/power_supply")
    try:
        members = sorted(root.iterdir(), key=lambda item: item.name)[:32]
    except OSError:
        return None, None, "unavailable", "unavailable"
    batteries: list[int] = []
    online: list[bool] = []
    for entry in members:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", entry.name):
            continue
        kind = _bounded(entry / "type", 64)
        if kind == "Battery":
            capacity = _percent(_bounded(entry / "capacity", 16))
            if capacity is not None:
                batteries.append(capacity)
        elif kind in ("Mains", "USB", "USB_C"):
            state = _bounded(entry / "online", 8)
            if state in ("0", "1"):
                online.append(state == "1")
    battery = min(batteries) if batteries else None
    ac = any(online) if online else None
    return battery, ac, "linux-sysfs-battery" if batteries else "unavailable", \
        "linux-sysfs-line-power" if online else "unavailable"


def _linux_thermal() -> tuple[float | None, str]:
    root = Path("/sys/class/thermal")
    try:
        zones = sorted(root.glob("thermal_zone*"), key=lambda item: item.name)[:64]
    except OSError:
        return None, "unavailable"
    values = []
    for zone in zones:
        label = (_bounded(zone / "type", 64) or "").lower()
        if not any(tag in label for tag in ("cpu", "package", "soc", "coretemp")):
            continue
        raw = _bounded(zone / "temp", 32)
        if raw is None or not re.fullmatch(r"-?[0-9]{1,9}", raw):
            continue
        celsius = int(raw) / 1000.0
        if -30 <= celsius <= 150:
            values.append(celsius)
    if values:
        return max(values), "linux-sysfs-cpu-labelled-thermal-zone"
    return None, "unavailable"


def _darwin_power() -> tuple[int | None, bool | None, str, str]:
    try:
        run = subprocess.run(["/usr/bin/pmset", "-g", "batt"], capture_output=True,
                             text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None, None, "unavailable", "unavailable"
    if run.returncode or len(run.stdout) > 4096:
        return None, None, "unavailable", "unavailable"
    found = re.findall(r"([0-9]{1,3})%", run.stdout)
    batteries = [n for n in (_percent(raw) for raw in found) if n is not None]
    battery = min(batteries) if batteries else None
    ac = True if "AC Power" in run.stdout else False if "Battery Power" in run.stdout else None
    return battery, ac, "darwin-pmset" if battery is not None else "unavailable", \
        "darwin-pmset" if ac is not None else "unavailable"


def _windows_power() -> tuple[int | None, bool | None, str, str]:
    try:
        import ctypes

        class SystemPowerStatus(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte),
                        ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte),
                        ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong),
                        ("BatteryFullLifeTime", ctypes.c_ulong)]

        status = SystemPowerStatus()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            battery = int(status.BatteryLifePercent) if status.BatteryLifePercent <= 100 else None
            ac = bool(status.ACLineStatus) if status.ACLineStatus in (0, 1) else None
            return battery, ac, "windows-GetSystemPowerStatus" if battery is not None else "unavailable", \
                "windows-GetSystemPowerStatus" if ac is not None else "unavailable"
    except (AttributeError, OSError, ValueError):
        pass
    return None, None, "unavailable", "unavailable"


def probe_power() -> PowerObservation:
    system = platform.system()
    battery, ac, battery_source, ac_source = None, None, "unavailable", "unavailable"
    temperature, thermal_source = None, "unavailable"
    if system == "Linux":
        battery, ac, battery_source, ac_source = _linux_power()
        temperature, thermal_source = _linux_thermal()
    elif system == "Darwin":
        battery, ac, battery_source, ac_source = _darwin_power()
    elif system == "Windows":
        battery, ac, battery_source, ac_source = _windows_power()
    return PowerObservation(battery, ac, temperature,
                            battery_source, ac_source, thermal_source)


def plan_energy_workers(
    base: CpuWorkerPlan,
    observed: PowerObservation,
    *,
    policy: EnergyPolicy | None = None,
) -> EnergyAdmission:
    if not isinstance(base, CpuWorkerPlan) or not isinstance(observed, PowerObservation):
        raise EnergyError("measured worker plan and power observation required")
    policy = policy or EnergyPolicy()
    if not isinstance(policy, EnergyPolicy):
        raise EnergyError("invalid energy policy")
    workers = base.workers
    reason = "within_operator_energy_policy"
    if observed.cpu_temperature_c is not None:
        if observed.cpu_temperature_c >= policy.critical_cpu_c:
            workers, reason = 0, "cpu_thermal_critical"
        elif observed.cpu_temperature_c >= policy.warm_cpu_c:
            workers, reason = min(workers, max(1, workers // 2)), "cpu_thermal_warm"
    elif workers > 2:
        workers, reason = 2, "thermal_telemetry_unavailable"
    if observed.on_ac is False and reason != "cpu_thermal_critical":
        if observed.battery_percent is None:
            workers, reason = min(workers, 1), "battery_telemetry_unavailable"
        elif observed.battery_percent <= policy.critical_battery_pct:
            workers, reason = 0, "battery_critical"
        elif observed.battery_percent <= policy.low_battery_pct:
            workers, reason = min(workers, 1), "battery_low"
        elif workers > 2:
            workers, reason = 2, "battery_conservation"
    elif observed.on_ac is None and workers > 1:
        workers, reason = 1, "ac_telemetry_unavailable"
    body = {"schema": SCHEMA, "base_digest": base.digest, "base_workers": base.workers,
            "observation": asdict(observed), "policy": asdict(policy),
            "allowed_workers": workers, "reason": reason}
    digest = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return EnergyAdmission(workers, base.workers, reason, digest, observed, policy)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton.app.offline_energy_budget")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--memory-per-worker-mib", type=int, default=256)
    parser.add_argument("--memory-reserve-mib", type=int, default=512)
    parser.add_argument("--interactive-reserve", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        base = plan_cpu_workers(
            probe_cpu_topology(), probe_memory_topology(),
            operator_max_workers=args.max_workers,
            bytes_per_worker=args.memory_per_worker_mib * 1024**2,
            memory_reserve_bytes=args.memory_reserve_mib * 1024**2,
            interactive_cpu_reserve=args.interactive_reserve,
        )
        result = plan_energy_workers(base, probe_power())
    except (CpuBudgetError, EnergyError) as exc:
        print("energy admission rejected: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, "allowed_workers": result.allowed_workers,
                      "base_workers": result.base_workers, "reason": result.reason,
                      "digest": result.digest, "power": asdict(result.observation),
                      "policy": asdict(result.policy), "cpu_plan_digest": base.digest},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
