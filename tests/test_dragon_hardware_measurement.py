"""Dragon admission must distinguish measured RAM from safe boot fallbacks."""
from dataclasses import replace
from pathlib import Path

from skeleton.automation.overseer.hardware import (
    DeviceClass, GPUClass, HardwareProbe, HardwareProfile, HardwareState,
)
from skeleton.ai.webcrawler.dragon_live_hardware import DragonLiveHardware
from skeleton.ai.webcrawler.dragon_resource_session import plan_resources


class DummyProbe:
    def __init__(self, *, verified=True, memory_mb=256, hot=False, battery_present=False):
        self._profile = HardwareProfile(
            cpu_cores=4, cpu_arch="x86_64", memory_total_mb=512,
            gpu=GPUClass.NONE, storage_class="unknown", thermal_zones=1,
            battery_present=battery_present, device_class=DeviceClass.LAPTOP,
            os="linux",
        )
        self._state = HardwareState(
            cpu_load=.1, cpu_per_core=[.1] * 4,
            memory_used_mb=256, memory_available_mb=memory_mb,
            memory_pressure=.3, swap_pressure=.05,
            temps_celsius=[80.0 if hot else 50.0],
            battery_level=None, battery_charging=None,
            io_wait=0.0, read_at=10.0, memory_sample_verified=verified,
        )

    def profile(self):
        return self._profile

    def read_state(self):
        return self._state


def test_unverified_hardware_memory_prevents_new_work():
    sample = DragonLiveHardware(DummyProbe(verified=False)).sample()
    assert sample.available_memory_bytes == 0
    denied = plan_resources(sample, now=10, foreground=True)
    assert denied.effort == "defer"
    assert denied.reason == "memory_reserve"


def test_verified_memory_allows_resource_planning_only():
    sample = DragonLiveHardware(DummyProbe()).sample()
    assert sample.available_memory_bytes == 256 * 1024 ** 2
    plan = plan_resources(sample, now=10, foreground=True)
    assert plan.memory_bytes > 0
    assert plan.context_bytes <= 65536


def test_hot_hardware_refuses_admission_even_with_valid_memory():
    sample = DragonLiveHardware(DummyProbe(hot=True)).sample()
    assert sample.thermal_limited
    assert plan_resources(sample, now=10, foreground=True).effort == "defer"


def test_unknown_mobile_battery_blocks_idle_but_not_user():
    sample = DragonLiveHardware(DummyProbe(battery_present=True)).sample()
    assert sample.battery_fraction == 0
    assert not sample.charging
    assert not plan_resources(sample, now=10, foreground=False).background_allowed
    assert plan_resources(sample, now=10, foreground=True).memory_bytes > 0


def test_linux_meminfo_with_measured_available_memory_is_verified(monkeypatch):
    probe = HardwareProbe()
    probe._sys = "linux"
    meminfo = (
        "MemTotal: 16777216 kB\nMemAvailable: 8388608 kB\nMemFree: 1024 kB\n"
        "SwapTotal: 1024 kB\nSwapFree: 1024 kB\n"
    )
    monkeypatch.setattr(Path, "read_text", lambda self: meminfo if str(self) == "/proc/meminfo" else "")
    used, available, pressure, swap, verified = probe._memory_state()
    assert verified is True
    assert available == 8192
    assert used == 8192
    assert pressure == .5
    assert swap == 0


def test_linux_missing_memavailable_falls_back_without_claiming_measurement(monkeypatch):
    probe = HardwareProbe()
    probe._sys = "linux"
    meminfo = "MemTotal: 16777216 kB\nMemFree: 1048576 kB\n"
    monkeypatch.setattr(Path, "read_text", lambda self: meminfo if str(self) == "/proc/meminfo" else "")
    used, available, pressure, swap, verified = probe._memory_state()
    assert verified is False
    assert available == 1024
    assert pressure > 0
