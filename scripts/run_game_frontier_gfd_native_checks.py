#!/usr/bin/env python3
"""GF-D native Godot headless checks (GF-P0-38/74/96 scope, no GPU claims).

Emits a tiny original Godot 4 project with a static slope, a RigidBody3D, a
pinned SoftBody3D and a Camera3D, runs the pinned binary with ``--headless
--import`` (emitted-scene import + GDScript parse) and then a fixed-tick probe
scene, and verifies the JSON lines it prints:

* no GDScript parse/compile or script errors in either run;
* the emitted ``.tscn`` loads and instantiates after import;
* RigidBody3D keeps its exported mass, touches the slope, and moves down-slope;
* SoftBody3D keeps its pinned vertex fixed while free vertices fall/settle,
  with its exported total mass and collision layer.

Headless Godot uses the dummy renderer, so screenshots, shadow casters and
GPU/physics timestep equivalence are *not* attested here. Logs are written to
``--log-dir`` for CI upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROBE_TAG = "GFD_PROBE "
ERROR_MARKERS = ("SCRIPT ERROR", "Parse Error", "Failed to load script", "Compile Error")

PROJECT_GODOT = """config_version=5

[application]
config/name="GF-D native checks"
run/main_scene="res://gfd/probe.tscn"

[physics]
common/physics_ticks_per_second=60
"""

SCENE_TSCN = """[gd_scene load_steps=8 format=3]

[ext_resource type="Script" path="res://gfd/probe.gd" id="1"]

[sub_resource type="BoxShape3D" id="slope_shape"]
size = Vector3(20, 1, 20)

[sub_resource type="BoxShape3D" id="ground_shape"]
size = Vector3(60, 1, 60)

[sub_resource type="SphereShape3D" id="ball_shape"]
radius = 0.5

[sub_resource type="BoxMesh" id="cloth_mesh"]
size = Vector3(1, 0.1, 1)
subdivide_width = 2
subdivide_depth = 2

[sub_resource type="PhysicsMaterial" id="ball_mat"]
friction = 0.2
bounce = 0.1

[sub_resource type="Environment" id="env"]

[node name="GFDProbe" type="Node3D"]
script = ExtResource("1")

[node name="Slope" type="StaticBody3D" parent="."]
transform = Transform3D(0.9659258, 0.2588190, 0, -0.2588190, 0.9659258, 0, 0, 0, 1, 0, 0, 0)

[node name="Shape" type="CollisionShape3D" parent="Slope"]
shape = SubResource("slope_shape")

[node name="Ground" type="StaticBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, -6, 0)

[node name="Shape" type="CollisionShape3D" parent="Ground"]
shape = SubResource("ground_shape")

[node name="Ball" type="RigidBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0)
mass = 2.5
physics_material_override = SubResource("ball_mat")
contact_monitor = true
max_contacts_reported = 4

[node name="Shape" type="CollisionShape3D" parent="Ball"]
shape = SubResource("ball_shape")

[node name="Cloth" type="SoftBody3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 12, 6, 0)
mesh = SubResource("cloth_mesh")
total_mass = 1.5
collision_layer = 1
collision_mask = 1

[node name="Camera" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 4, 18)
current = true

[node name="World" type="WorldEnvironment" parent="."]
environment = SubResource("env")
"""

PROBE_GD = """extends Node3D

const FRAMES := 180
var _tick := 0
var _start := Vector3.ZERO
var _contacts := 0
var _pin_start := Vector3.ZERO
var _free_start := Vector3.ZERO
var _free_index := -1

func _emit(kind: String, data: Dictionary) -> void:
	data["kind"] = kind
	print("GFD_PROBE " + JSON.stringify(data))

func _ready() -> void:
	var ball: RigidBody3D = $Ball
	_start = ball.global_position
	var cloth: SoftBody3D = $Cloth
	cloth.set_point_pinned(0, true)
	_emit("ready", {
		"engine": Engine.get_version_info()["string"],
		"ball_mass": ball.mass,
		"cloth_mass": cloth.total_mass,
		"cloth_layer": cloth.collision_layer,
		"camera_current": $Camera.current,
		"ticks_per_second": Engine.physics_ticks_per_second,
	})

func _physics_process(_delta: float) -> void:
	_tick += 1
	var ball: RigidBody3D = $Ball
	_contacts = max(_contacts, ball.get_contact_count())
	var cloth: SoftBody3D = $Cloth
	var verts: PackedVector3Array = cloth.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var count: int = verts.size()
	if _tick == 2 and count > 1:
		_pin_start = cloth.get_point_transform(0)
		_free_index = count - 1
		_free_start = cloth.get_point_transform(_free_index)
	if _tick >= FRAMES:
		var pin_now: Vector3 = cloth.get_point_transform(0) if count > 0 else Vector3.ZERO
		var free_now: Vector3 = cloth.get_point_transform(_free_index) if _free_index >= 0 else Vector3.ZERO
		_emit("final", {
			"ticks": _tick,
			"ball_start": [_start.x, _start.y, _start.z],
			"ball_end": [ball.global_position.x, ball.global_position.y, ball.global_position.z],
			"ball_max_contacts": _contacts,
			"soft_points": count,
			"pin_drift": (pin_now - _pin_start).length(),
			"free_drop": _free_start.y - free_now.y,
			"pinned": cloth.is_point_pinned(0),
		})
		get_tree().quit(0)
"""


def emit_project(root: Path) -> dict[str, str]:
    files = {
        "project.godot": PROJECT_GODOT,
        "gfd/probe.tscn": SCENE_TSCN,
        "gfd/probe.gd": PROBE_GD,
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return {rel: hashlib.sha256(t.encode()).hexdigest() for rel, t in files.items()}


def parse_probe(output: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        idx = line.find(PROBE_TAG)
        if idx >= 0:
            rec = json.loads(line[idx + len(PROBE_TAG):])
            records[rec.pop("kind")] = rec
    return records


def script_errors(output: str) -> list[str]:
    return [ln for ln in output.splitlines() if any(m in ln for m in ERROR_MARKERS)]


def evaluate(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ready, final = records.get("ready"), records.get("final")
    if ready is None or final is None:
        raise AssertionError(f"probe did not report ready/final: {sorted(records)}")
    start, end = final["ball_start"], final["ball_end"]
    checks = {
        "engine_4x": str(ready["engine"]).startswith("4."),
        "rigid_mass_kept": abs(float(ready["ball_mass"]) - 2.5) < 1e-6,
        "rigid_contact": int(final["ball_max_contacts"]) >= 1,
        # Slope tilts down toward -x; gravity must carry the ball down-slope.
        "rigid_down_slope": end[0] < start[0] - 0.5 and end[1] < start[1],
        "soft_mass_kept": abs(float(ready["cloth_mass"]) - 1.5) < 1e-6,
        "soft_layer_kept": int(ready["cloth_layer"]) == 1,
        "soft_points": int(final["soft_points"]) > 1,
        "soft_pin_held": bool(final["pinned"]) and float(final["pin_drift"]) < 1e-3,
        "soft_free_moved": float(final["free_drop"]) > 0.05,
        "camera_current": bool(ready["camera_current"]),
        "native_tick_rate_60hz": int(ready["ticks_per_second"]) == 60,
        "fixed_ticks": int(final["ticks"]) >= 180,
    }
    return {"checks": checks, "passed": all(checks.values()), "ready": ready, "final": final,
            "gpu_attested": False, "screenshot_attested": False}


def _invoke_godot(godot: str, args: list[str], timeout: int) -> tuple[int, str]:
    """Run a pinned headless engine, retaining bounded failure diagnostics."""
    try:
        proc = subprocess.run(
            [godot, "--headless", *args], capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return 124, str(stdout)[-2000:] + "\n" + str(stderr)[-2000:] + "\nGodot timed out"
    except OSError as exc:
        return 127, "Godot launch failed: " + type(exc).__name__
    return proc.returncode, proc.stdout + "\n" + proc.stderr


def run(godot: str, project: Path, log_dir: Path, timeout: int = 120) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    digests = emit_project(project)
    imp_code, imp_out = _invoke_godot(
        godot, ["--path", str(project), "--import"], timeout,
    )
    (log_dir / "gfd-import.log").write_text(imp_out, encoding="utf-8")
    # A broken import must not be followed by a pointless engine launch.
    if imp_code == 0 and not script_errors(imp_out):
        play_code, play_out = _invoke_godot(
            godot, ["--path", str(project), "--quit-after", "600"], timeout,
        )
    else:
        play_code, play_out = 125, "Native playback skipped because import failed"
    (log_dir / "gfd-probe.log").write_text(play_out, encoding="utf-8")
    errors = script_errors(imp_out) + script_errors(play_out)
    report: dict[str, Any] = {
        "source_sha256": digests,
        "engine_exits": {"import": imp_code, "play": play_code},
        "gpu_attested": False,
        "screenshot_attested": False,
    }
    if imp_code != 0 or play_code != 0 or errors:
        report.update({
            "passed": False,
            "failure_kind": "engine_import_or_playback",
            "error_lines": errors[:10],
        })
    else:
        try:
            report.update(evaluate(parse_probe(play_out)))
        except (AssertionError, ValueError, KeyError, TypeError) as exc:
            report.update({
                "passed": False,
                "failure_kind": "invalid_native_probe",
                "error_type": type(exc).__name__,
            })
    (log_dir / "gfd-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8",
    )
    if not report["passed"]:
        raise AssertionError(
            f"GF-D native checks failed: {report.get('failure_kind', report.get('checks'))}"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--godot", required=True)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--log-dir", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args(argv)
    report = run(args.godot, args.project, args.log_dir, args.timeout)
    print(json.dumps({"passed": report["passed"], "checks": report["checks"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
