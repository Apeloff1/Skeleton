"""Incomplete kernel CPU thermal zones must not authorize local inference.

These are simulated sysfs fixtures, not hardware qualification.
"""
from __future__ import annotations

import sys

import pytest

from skeleton.app.offline_cpu_thermal import probe_cpu_thermal, CPUThermalController

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux sysfs fixture contract",
)


def zone(root, name, *, kind="cpu-thermal", temp="50000", trip="90000"):
    directory = root / name
    directory.mkdir()
    (directory / "type").write_text(kind, encoding="ascii")
    (directory / "temp").write_text(temp, encoding="ascii")
    (directory / "trip_point_0_type").write_text("critical", encoding="ascii")
    (directory / "trip_point_0_temp").write_text(trip, encoding="ascii")
    return directory


def test_all_measured_cpu_zones_remain_visible(tmp_path):
    zone(tmp_path, "thermal_zone0")
    zone(tmp_path, "thermal_zone1", kind="soc-thermal", temp="55000")
    sensors = probe_cpu_thermal(tmp_path)
    assert len(sensors) == 2
    assert all(sensor.trip_c == 90.0 for sensor in sensors)
    controller = CPUThermalController()
    controller.observe(sensors)
    assert controller.snapshot()["trip_measured"] is True


@pytest.mark.parametrize("missing", [
    "type", "temp", "trip_point_0_type", "trip_point_0_temp",
])
def test_missing_cpu_zone_evidence_invalidates_whole_sample(tmp_path, missing):
    zone(tmp_path, "thermal_zone0")
    second = zone(tmp_path, "thermal_zone1", kind="soc-thermal")
    (second / missing).unlink()
    assert probe_cpu_thermal(tmp_path) == ()


@pytest.mark.parametrize("corrupt", [
    ("temp", "unknown"), ("trip_point_0_temp", "nan"),
])
def test_corrupt_cpu_telemetry_invalidates_whole_sample(tmp_path, corrupt):
    zone(tmp_path, "thermal_zone0")
    second = zone(tmp_path, "thermal_zone1")
    (second / corrupt[0]).write_text(corrupt[1], encoding="ascii")
    assert probe_cpu_thermal(tmp_path) == ()


def test_irrelevant_sensor_does_not_certify_missing_cpu_trip(tmp_path):
    zone(tmp_path, "thermal_zone0", kind="gpu", temp="40000")
    second = zone(tmp_path, "thermal_zone1", kind="cpu")
    (second / "trip_point_0_temp").unlink()
    assert probe_cpu_thermal(tmp_path) == ()


def test_unknown_trip_type_does_not_mask_lowest_trip(tmp_path):
    first = zone(tmp_path, "thermal_zone0")
    (first / "trip_point_0_type").unlink()
    (first / "trip_point_1_type").write_text("critical", encoding="ascii")
    (first / "trip_point_1_temp").write_text("95000", encoding="ascii")
    assert probe_cpu_thermal(tmp_path) == ()
