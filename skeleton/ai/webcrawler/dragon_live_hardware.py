"""Dragon adapter for the canonical native hardware probe, not guessed RAM."""
from __future__ import annotations
from math import isfinite
from skeleton.automation.overseer.hardware import HardwareProbe
from .dragon_resource_session import HardwareSample


class DragonLiveHardware:
    def __init__(self, probe: HardwareProbe | None = None):
        self.probe = probe or HardwareProbe()

    def sample(self) -> HardwareSample:
        profile = self.probe.profile()
        state = self.probe.read_state()
        verified = state.memory_sample_verified is True
        pressure = max(state.cpu_load, state.memory_pressure, state.swap_pressure)
        if not isfinite(pressure) or not 0 <= pressure <= 1:
            verified = False
            pressure = 1.0
        # Unknown battery on a battery-powered device blocks new background
        # acquisition; it is never silently treated as plugged in.
        battery = state.battery_level if state.battery_level is not None else (
            0.0 if profile.battery_present else 1.0)
        charging = state.battery_charging is True if profile.battery_present else True
        return HardwareSample(state.memory_available_mb * 1024**2 if verified else 0,
            max(1, min(1024, profile.cpu_cores)), pressure, battery, charging,
            any(not isfinite(t) or t >= HardwareProbe.THERMAL_WARN_C for t in state.temps_celsius),
            state.read_at)
