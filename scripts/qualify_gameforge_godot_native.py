"""Actual-engine acceptance of original GameForge Godot 2D playable loops.

The corresponding Actions job supplies an official SHA-256-pinned Godot
archive. Do not call this a device, display, GPU, input-latency, installer
or release-provenance qualification: the checks run HEADLESS on Linux.

Six *independent* projects are emitted and replayed: 3 baseline slices and
3 bounded mechanically tuned slices. A run passes only after a real Godot
import plus a real scene boot with the exact completion marker, exit code 0
and zero script/load/runtime error headlines. Nothing is uploaded or reused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from skeleton.context.pipeline import GameForgeRun
from skeleton.forge.archetype_content import (
    COMPLETE_MARKER,
    FAILED_MARKER,
    content_archetypes,
    verify_archetype_content,
)
from skeleton.forge.playable_portal import verify_playable_portal
from skeleton.forge.playtest import scan_log
from skeleton.forge.projector import write_project
from skeleton.forge.source_manifest import source_manifest


def _require(condition: bool, explanation: str) -> None:
    if not condition:
        raise AssertionError(explanation)


def _launch(exe: Path, args: list[str], cwd: Path, *, timeout: int) -> dict[str, Any]:
    try:
        process = subprocess.run(
            [str(exe), "--headless", *args],
            cwd=str(cwd),
            env={**os.environ, "GODOT_SILENCE_ROOT_WARNING": "1"},
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=timeout,
        )
        output = (process.stdout or "") + "\n" + (process.stderr or "")
        return {
            "exit": process.returncode,
            "timeout": False,
            "errors": scan_log(output)[:12],
            "output": output[-6000:],
        }
    except subprocess.TimeoutExpired as error:
        data = error.stdout or b""
        stderr = error.stderr or b""
        def as_text(value: bytes | str) -> str:
            return value.decode("utf-8", "replace") if isinstance(value, bytes) else value
        return {
            "exit": -1,
            "timeout": True,
            "errors": ["native Godot command timed out"],
            "output": (as_text(data) + as_text(stderr))[-6000:],
        }


def _scenario(exe: Path, name: str, axes: dict[str, float], root: Path) -> dict[str, Any]:
    args = {"archetype": name, "playable_content": True, "operator_axes": axes}
    response = GameForgeRun().execute(
        "Original local-only " + name.replace("_", " ") + " project",
        **args,
    )
    _require(response.get("succeeded") is True, name + ": GameForge stages failed")
    files = response["files"]
    _require(verify_archetype_content(files, name, operator_axes=axes),
             name + ": native mechanics differ from submitted source")
    _require(verify_playable_portal(files, name),
             name + ": in-game return portal failed source verification")
    manifest = source_manifest(files)
    _require(response.get("source_manifest") == manifest,
             name + ": delivered source manifest mismatch")
    tune = response.get("playable_mechanics") or {}
    _require(tune.get("source_verified") is True,
             name + ": native source not marked verified")
    _require(tune.get("archetype") == name, name + ": wrong receipt archetype")
    _require(tune.get("schema") == "skeleton.forge.playable_mechanics.v1",
             name + ": wrong mechanical receipt schema")
    _require(bool(tune.get("applied_axes")) == bool(axes),
             name + ": explicit tuning receipt missing or invented")

    project = root / ("baseline-" if not axes else "tuned-")
    project = project.with_name(project.name + name)
    write_project(project, files, overwrite=False)
    engine_import = _launch(
        exe, ["--path", str(project), "--import"], project, timeout=90,
    )
    _require(engine_import["exit"] == 0 and not engine_import["timeout"]
             and not engine_import["errors"],
             f"{name}: actual Godot import failed: {engine_import}")
    scene = f"res://scenes/archetypes/{name}/main.tscn"
    boot = _launch(
        exe,
        ["--fixed-fps", "60", "--quit-after", "10000",
         "--path", str(project), scene],
        project, timeout=120,
    )
    expected = f"{COMPLETE_MARKER} {name}"
    failed = f"{FAILED_MARKER} {name}"
    lines = boot["output"].splitlines()
    _require(boot["exit"] == 0 and not boot["timeout"] and not boot["errors"]
             and any(line.strip().startswith(expected) for line in lines)
             and not any(line.strip().startswith(failed) for line in lines),
             f"{name}: real native playable loop did not finish: {boot}")

    return {
        "archetype": name,
        "scenario": "tuned" if axes else "baseline",
        "source_manifest_sha256": manifest["sha256"],
        "files": len(files),
        "applied_axes": tune["applied_axes"],
        "import_exit": engine_import["exit"],
        "playback_exit": boot["exit"],
        "completion_marker": expected,
        "script_errors": 0,
        "native_headless_passed": True,
        "native_device_verified": False,
        "release_qualified": False,
    }


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--godot", required=True, type=Path)
    cli.add_argument("--archive-sha256", required=True)
    args = cli.parse_args()
    exe = args.godot.resolve(strict=True)
    _require(exe.is_file() and os.access(exe, os.X_OK),
             "native Godot binary missing or not executable")
    _require(len(args.archive_sha256) == 64
             and all(c in "0123456789abcdef" for c in args.archive_sha256),
             "Godot archive SHA-256 must be pinned by the calling job")
    expected_names = ("combat_loop", "extraction", "pipeline")
    _require(content_archetypes() == expected_names,
             "native suite must be reviewed when archetype inventory changes")

    variants = [
        ("combat_loop", {}),
        ("extraction", {}),
        ("pipeline", {}),
        ("combat_loop", {"tempo": 0.8, "agency": 1.0, "grind": 0.25, "lethality": 0.5}),
        ("extraction", {"tempo": 0.75, "agency": 1.0, "risk": 0.15, "scarcity": 0.1}),
        ("pipeline", {"tempo": 1.0, "agency": 1.0, "grind": 0.0, "risk": 0.0}),
    ]
    with tempfile.TemporaryDirectory(prefix="gameforge-native-") as temp:
        root = Path(temp)
        evidence = [_scenario(exe, kind, axes, root) for kind, axes in variants]
    _require(len(evidence) == 6 and all(x["native_headless_passed"] for x in evidence),
             "native GameForge qualification did not complete all six scenarios")
    print(json.dumps({
        "schema": "skeleton.forge.native_scenarios.v1",
        "godot_archive_sha256": args.archive_sha256,
        "godot_binary_sha256": hashlib.file_digest(exe.open("rb"), "sha256").hexdigest(),
        "headless_godot_executed": True,
        "independent_scenarios": len(evidence),
        "real_device_qualified": False,
        "release_qualified": False,
        "scenarios": evidence,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
