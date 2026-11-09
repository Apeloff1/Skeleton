"""Deterministic Linux thermal trip-point and serving controller regressions."""
from __future__ import annotations
import pytest
from skeleton.ai.runtime.inference.adaptive_serving import AdaptiveServingController, ServingResources
from skeleton.ai.runtime.inference.linux_thermal import (
    ThermalTelemetryError, sample_linux_thermal,
)

ROOT = "/sys/class/thermal/thermal_zone0"

def _reader(temp: str, trip: str = "90000", kind: str = "critical"):
    def read(path: str) -> str:
        if path.endswith("/temp"):
            return temp
        if path.endswith("/trip_point_0_type"):
            return kind
        if path.endswith("/trip_point_0_temp"):
            return trip
        raise FileNotFoundError(path)
    return read

def test_measured_thermal_headroom_levels() -> None:
    for temp, expected in (("50000", "normal"), ("80000", "elevated"), ("87000", "critical")):
        result = sample_linux_thermal(_reader(temp), paths=[ROOT])
        assert result.level == expected
        assert result.measured_zones == 1
        assert result.source == "linux_sysfs_thermal"

def test_missing_trip_is_unknown_not_normal() -> None:
    result = sample_linux_thermal(_reader("40000", kind="passive"), paths=[ROOT])
    assert result.level is None

def test_missing_sensor_is_unknown_not_zero() -> None:
    result = sample_linux_thermal(lambda path: (_ for _ in ()).throw(FileNotFoundError(path)), paths=[ROOT])
    assert result.level is None

def test_multiple_zones_use_worst_measured_headroom() -> None:
    other = "/sys/class/thermal/thermal_zone1"
    def read(path: str) -> str:
        if path.endswith("/temp"):
            return "87000" if "zone1" in path else "40000"
        if path.endswith("/trip_point_0_type"):
            return "critical"
        if path.endswith("/trip_point_0_temp"):
            return "90000"
        raise FileNotFoundError(path)
    result = sample_linux_thermal(read, paths=[ROOT, other])
    assert result.level == "critical"
    assert result.minimum_headroom_c == 3.0

@pytest.mark.parametrize("path", [
    "/tmp/thermal_zone0", "/sys/class/thermal/../thermal_zone0",
    "/sys/class/thermal/thermal_zone0/../../etc/passwd",
])
def test_reject_untrusted_sysfs_path(path: str) -> None:
    with pytest.raises(ThermalTelemetryError):
        sample_linux_thermal(_reader("40000"), paths=[path])

def test_thermal_budget_fail_closed() -> None:
    with pytest.raises(ThermalTelemetryError):
        sample_linux_thermal(_reader("40000"), paths=[], max_zones=0)
    result = sample_linux_thermal(_reader("40000"), paths=[ROOT] * 65)
    assert result.level is None

def test_critical_thermal_pressure_throttles_background_work() -> None:
    ctl = AdaptiveServingController(operator_max=8)
    ctl.update(ServingResources(thermal_level="critical", thermal_headroom_c=3.0), now=1.0, queued=8)
    assert ctl.reason == "thermal_critical"
    assert ctl.effective_concurrency == 4
    assert ctl.background_limit == 0

def test_elevated_thermal_pressure_and_hysteresis() -> None:
    ctl = AdaptiveServingController(operator_max=4)
    ctl.configure({"cooldown_seconds": 0.5, "recovery_samples": 2}, now=0.0)
    ctl.update(ServingResources(thermal_level="elevated"), now=1.0, queued=4)
    assert ctl.reason == "thermal_pressure"
    assert ctl.effective_concurrency == 3
    ctl.update(ServingResources(thermal_level="normal"), now=2.0, queued=4)
    ctl.update(ServingResources(thermal_level="normal"), now=3.0, queued=4)
    assert ctl.effective_concurrency == 4

@pytest.mark.parametrize("level", ["danger", "", 0, True])
def test_invalid_thermal_level_is_rejected(level: object) -> None:
    with pytest.raises(ValueError):
        ServingResources(thermal_level=level)
