"""Actual-engine acceptance of original GameForge Godot 2D playable loops.

The operator supplies the Godot archive and an independently established
SHA-256 digest. This harness verifies archive bytes AND that the launched
executable is an exact archive member; the digest's official origin is NOT
verified in this tool. Do not call this device, display, GPU, input-latency,
installer or release-provenance qualification: it runs HEADLESS on Linux.

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
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def verify_engine_archive(
    exe: Path, archive: Path, expected_archive_sha256: str,
) -> dict[str, str]:
    """Bind the launched Godot executable to a pinned, local ZIP archive.

    No downloads, no extraction, no command execution. In particular, a
    plausible-looking 64-character hash alone is never provenance evidence.
    The caller is still responsible for admitting the EXPECTED digest from a
    trusted official release manifest.
    """
    if (len(expected_archive_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_archive_sha256)):
        raise ValueError("archive SHA-256 must be a lowercase trusted digest")
    if not exe.is_file() or not archive.is_file() or exe.resolve() == archive.resolve():
        raise ValueError("archive and actual engine executable must be distinct files")
    if not (0 < archive.stat().st_size <= 350 * 1024 * 1024):
        raise ValueError("Godot distribution archive size outside source-custody bounds")
    if not (0 < exe.stat().st_size <= 400 * 1024 * 1024):
        raise ValueError("Godot executable size outside source-custody bounds")
    archive_actual = _sha256_file(archive)
    if archive_actual != expected_archive_sha256:
        raise ValueError("Godot archive does not match expected SHA-256")
    actual_binary = _sha256_file(exe)
    matching_members: list[str] = []
    with zipfile.ZipFile(archive, "r") as distribution:
        records = distribution.infolist()
        if len(records) > 32:
            raise ValueError("Godot release archive contains too many members")
        names: set[str] = set()
        for item in records:
            name = item.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or "\\" in name
                    or any(part in ("", ".", "..") for part in parts)
                    or name.casefold() in names):
                raise ValueError("Godot archive has unsafe or duplicate source paths")
            names.add(name.casefold())
            mode = (item.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError("Godot archive contains a symbolic link")
            if item.flag_bits & 1:
                raise ValueError("encrypted Godot archive member is unsupported")
            if item.is_dir():
                continue
            if item.file_size > 400 * 1024 * 1024:
                raise ValueError("Godot archive entry exceeds bounded binary size")
            # Only candidate executable names are hashed; other artifacts
            # cannot masquerade as the engine under an arbitrary name.
            if not PurePosixPath(name).name.casefold().startswith("godot"):
                continue
            hash_member = hashlib.sha256()
            with distribution.open(item, "r") as stream:
                length = 0
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    length += len(chunk)
                    if length > 400 * 1024 * 1024:
                        raise ValueError("Godot archive decompression size exceeded")
                    hash_member.update(chunk)
            if hash_member.hexdigest() == actual_binary:
                matching_members.append(name)
    if len(matching_members) != 1:
        raise ValueError("Godot executable does not match exactly one pinned archive member")
    return {
        "archive_sha256": archive_actual,
        "godot_binary_sha256": actual_binary,
        "archive_member": matching_members[0],
        # This proves only cryptographic custody against the caller's
        # expected hash, not official origin or desktop/device correctness.
        "binary_matches_archive": "true",
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
    cli.add_argument("--archive", required=True, type=Path,
                     help="Local Godot ZIP distribution containing the executable")
    cli.add_argument("--archive-sha256", required=True,
                     help="Expected SHA-256 from an independently admitted release manifest")
    args = cli.parse_args()
    exe = args.godot.resolve(strict=True)
    _require(exe.is_file() and os.access(exe, os.X_OK),
             "native Godot binary missing or not executable")
    custody = verify_engine_archive(exe, args.archive, args.archive_sha256)
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
        "godot_archive_sha256": custody["archive_sha256"],
        "godot_binary_sha256": custody["godot_binary_sha256"],
        "godot_archive_member": custody["archive_member"],
        "binary_matches_pinned_archive": True,
        "expected_digest_origin_verified": False,
        "headless_godot_executed": True,
        "independent_scenarios": len(evidence),
        "real_device_qualified": False,
        "release_qualified": False,
        "scenarios": evidence,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
