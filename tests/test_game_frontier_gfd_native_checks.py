"""Unit tests for GF-D native Godot checks (no Godot binary required)."""
from __future__ import annotations

import json

import pytest

from scripts import run_game_frontier_gfd_native_checks as gfd


def _log(final_overrides: dict | None = None) -> str:
    ready = {"kind": "ready", "engine": "4.7.2-stable (official)", "ball_mass": 2.5,
             "cloth_mass": 1.5, "cloth_layer": 1, "camera_current": True,
             "ticks_per_second": 60}
    final = {"kind": "final", "ticks": 180, "ball_start": [0, 2, 0], "ball_end": [-6.9, -0.8, 0],
             "ball_max_contacts": 2, "soft_points": 64, "pin_drift": 0.0, "free_drop": 1.2,
             "pinned": True}
    final.update(final_overrides or {})
    return "noise\n" + gfd.PROBE_TAG + json.dumps(ready) + "\n" + gfd.PROBE_TAG + json.dumps(final) + "\n"


def test_emit_project_writes_scene_and_script(tmp_path) -> None:
    digests = gfd.emit_project(tmp_path)
    assert set(digests) == {"project.godot", "gfd/probe.tscn", "gfd/probe.gd"}
    scene = (tmp_path / "gfd/probe.tscn").read_text()
    for node in ("RigidBody3D", "SoftBody3D", "StaticBody3D", "Camera3D"):
        assert f'type="{node}"' in scene


def test_native_slope_geometry_descends_toward_negative_x() -> None:
    # Godot's serialized Transform3D uses basis *columns*: the second
    # component of the first axis is the local +X axis' world Y component.
    # A positive component means the slope rises to +X, hence downhill -X.
    scene = gfd.SCENE_TSCN.split('[node name="Slope" type="StaticBody3D" parent="."]', 1)[1]
    transform = scene.split("transform = Transform3D(", 1)[1].split(")", 1)[0]
    axes = [float(part.strip()) for part in transform.split(",")]
    assert len(axes) == 12
    assert axes[1] > 0.2, "native fixture slope must rise toward +X"
    assert axes[3] < -0.2, "rotation must be a right-handed 15 degree incline"
    assert axes[4] > 0.9
    # Keep the independent motion assertion aligned with the fixture.
    assert gfd.evaluate(gfd.parse_probe(_log()))["checks"]["rigid_down_slope"]


def test_passing_probe_reports_no_gpu_or_screenshot_claims() -> None:
    report = gfd.evaluate(gfd.parse_probe(_log()))
    assert report["passed"]
    assert report["gpu_attested"] is False and report["screenshot_attested"] is False


@pytest.mark.parametrize("override,check", [
    ({"ball_end": [0.1, 1.9, 0]}, "rigid_down_slope"),
    ({"ball_max_contacts": 0}, "rigid_contact"),
    ({"pin_drift": 0.5}, "soft_pin_held"),
    ({"free_drop": 0.0}, "soft_free_moved"),
    ({"ticks": 10}, "fixed_ticks"),
])
def test_failed_physics_checks_are_reported(override, check) -> None:
    report = gfd.evaluate(gfd.parse_probe(_log(override)))
    assert not report["passed"] and report["checks"][check] is False


def test_native_probe_fails_if_engine_did_not_use_60hz() -> None:
    baseline = _log()
    corrupted = baseline.replace('"ticks_per_second": 60', '"ticks_per_second": 30', 1)
    assert corrupted != baseline
    report = gfd.evaluate(gfd.parse_probe(corrupted))
    assert report["checks"]["native_tick_rate_60hz"] is False
    assert report["passed"] is False


def test_missing_probe_records_fail_closed() -> None:
    with pytest.raises(AssertionError):
        gfd.evaluate(gfd.parse_probe("no probe output"))


def test_script_errors_detected() -> None:
    out = 'SCRIPT ERROR: Parse Error: x\nERROR: Failed to load script "res://a.gd"\nok'
    assert len(gfd.script_errors(out)) == 2
