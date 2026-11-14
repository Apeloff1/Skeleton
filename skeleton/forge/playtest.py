"""Headless Godot playtest gate: does the emitted project actually boot?

The forge verifier and ``gdscript_check`` are static. This module is the
dynamic half of "verified, playable": it writes the emitted files to a
scratch directory, runs ``godot --headless --import`` and then boots the main
scene for a bounded number of frames (``--quit-after``), and scans the engine
log for script/parse/runtime errors.

Binary resolution (first hit wins):

1. explicit ``binary=`` argument (operator choice);
2. :class:`skeleton.artifact_plane.godot_locate.GodotLocator` (fail-closed,
   sha256-verified against ``backend/godot.artifact.json``);
3. ``SKELETON_GODOT_BIN`` / ``GODOT_BINARY`` environment variables;
4. ``godot4`` / ``godot`` on ``PATH``.

Sources 1, 3 and 4 are reported with ``verified: False`` — the build ran, but
not against the admitted engine artefact. With no binary at all the result is
``status="unavailable"``; callers decide whether that is fatal
(``GameForgeRun.execute(playtest="require")``) or informative
(``playtest="auto"``).
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

PLAYTEST_MODES = ("off", "auto", "require")
DEFAULT_FRAMES = 300
DEFAULT_TIMEOUT_S = 120.0

# Engine log lines that mean the build is not playable. Godot prints the
# offending location on the following "at:" line; we keep the headline.
_ERROR_PATTERNS = (
    re.compile(r"^\s*SCRIPT ERROR:"),
    re.compile(r"^\s*Parse Error:"),
    re.compile(r"^\s*ERROR:"),
    re.compile(r"Failed to load script"),
    re.compile(r"Cannot open file"),
)
# Known-benign engine noise under --headless (no GPU / audio / templates).
_BENIGN = (
    re.compile(r"No export template found"),
    re.compile(r"Project export for preset"),
    re.compile(r"audio driver", re.I),
    re.compile(r"Condition \"!_is_class_editor_hint"),
    re.compile(r"_fs_changed"),
)


def normalise_mode(mode: Optional[str]) -> str:
    if mode is None or mode is False:
        return "off"
    if mode is True:
        return "auto"
    value = str(mode).strip().lower()
    if value not in PLAYTEST_MODES:
        raise ValueError(f"playtest mode must be one of {PLAYTEST_MODES}, got {mode!r}")
    return value


def resolve_binary(binary: Optional[str] = None,
                   root: Optional[str | Path] = None) -> Tuple[Optional[str], str, bool]:
    """Return ``(path, source, verified)``; ``path`` is None when absent."""
    if binary:
        path = Path(binary)
        return (str(path), "argument", False) if path.is_file() else (None, "argument-missing", False)
    try:
        from skeleton.artifact_plane.godot_locate import GodotLocator
        card = GodotLocator(root or Path(__file__).resolve().parents[2]).locate()
        found = card.get("found") if isinstance(card, dict) else None
        if found is None and isinstance(card, dict):
            found = (card.get("extra") or {}).get("found")
        path = card.get("path") if isinstance(card, dict) else None
        if path is None and isinstance(card, dict):
            path = (card.get("extra") or {}).get("path")
        if found and path and Path(path).is_file():
            return str(path), "artifact-plane", True
    except Exception:
        pass
    for env in ("SKELETON_GODOT_BIN", "GODOT_BINARY"):
        value = os.environ.get(env)
        if value and Path(value).is_file():
            return value, f"env:{env}", False
    for name in ("godot4", "godot"):
        found_path = shutil.which(name)
        if found_path:
            return found_path, f"path:{name}", False
    return None, "missing-godot-binary", False


def scan_log(text: str) -> List[str]:
    """Return the error headlines in a Godot log (benign noise removed)."""
    errors: List[str] = []
    for line in (text or "").splitlines():
        if not any(p.search(line) for p in _ERROR_PATTERNS):
            continue
        if any(b.search(line) for b in _BENIGN):
            continue
        errors.append(line.strip())
    return errors


def _run(cmd: List[str], cwd: Path, timeout: float) -> Tuple[int, str, bool]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              timeout=timeout, check=False,
                              env=dict(os.environ, GODOT_SILENCE_ROOT_WARNING="1"))
        return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), False
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        err = exc.stderr or b""
        text = (out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)) + \
               (err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err))
        return -1, text, True


def playtest(files: Mapping[str, str], *, binary: Optional[str] = None,
             frames: int = DEFAULT_FRAMES, timeout: float = DEFAULT_TIMEOUT_S,
             workdir: Optional[str | Path] = None, keep: bool = False,
             deadline: Optional[float] = None) -> Dict[str, Any]:
    """Boot the emitted project headless and report whether it is playable.

    Returns ``{"status": "passed"|"failed"|"unavailable", "passed": bool, ...}``.
    """
    if not isinstance(files, Mapping) or "project.godot" not in files:
        raise ValueError("playtest needs an emitted Godot file map with project.godot")
    if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1:
        raise ValueError("frames must be a positive int")
    path, source, verified = resolve_binary(binary)
    base: Dict[str, Any] = {
        "binary": path, "binary_source": source, "verified": verified,
        "frames": frames, "errors": [], "passed": False,
    }
    if path is None:
        return {**base, "status": "unavailable", "reason": source}

    started = time.monotonic()
    owned = workdir is None
    root = Path(tempfile.mkdtemp(prefix="forge-playtest-")) if owned else Path(workdir)
    try:
        from skeleton.forge.projector import write_project
        write_project(root, dict(files), overwrite=True)
        steps: List[Dict[str, Any]] = []
        errors: List[str] = []
        for name, cmd in (
            ("import", [path, "--headless", "--path", str(root), "--import"]),
            ("boot", [path, "--headless", "--path", str(root), "--quit-after", str(frames)]),
        ):
            step_timeout = timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    errors.append("deadline exceeded")
                    steps.append({
                        "step": name, "returncode": None, "timed_out": True,
                        "errors": ["deadline exceeded"], "log_tail": "",
                    })
                    break
                step_timeout = min(timeout, remaining)
            code, log, timed_out = _run(cmd, root, step_timeout)
            found = scan_log(log)
            steps.append({"step": name, "returncode": code, "timed_out": timed_out,
                          "errors": found[:20], "log_tail": log[-2000:]})
            errors.extend(found)
            if code != 0:
                errors.append(f"{name}: engine exited {code}")
            if timed_out:
                errors.append(f"{name}: timed out after {step_timeout:.0f}s")
            if name == "import" and (timed_out or found or code != 0):
                break
        boot = next((s for s in steps if s["step"] == "boot"), None)
        passed = bool(boot) and not errors and boot["returncode"] == 0
        return {
            **base,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "errors": errors[:50],
            "steps": steps,
            "elapsed_s": round(time.monotonic() - started, 3),
            "workdir": str(root) if keep or not owned else None,
        }
    finally:
        if owned and not keep:
            shutil.rmtree(root, ignore_errors=True)


def playtest_archetype_scene(
    files: Mapping[str, str],
    archetype: str,
    *,
    binary: Optional[str] = None,
    frames: int = 6000,
    timeout: float = 180.0,
) -> Dict[str, Any]:
    """Independently complete one of the eight real, source-backed Godot scenes.

    The generated world's successful default-scene boot is not proof that its
    separate native mini-game runs to completion. This is an isolated
    import-and-play run against the exact emitted scene source. Model-generated
    code, network downloads and permanent output paths are never admitted.
    """
    from skeleton.forge.archetype_content import (
        COMPLETE_MARKER, FAILED_MARKER, content_archetypes,
    )
    from skeleton.forge.projector import write_project

    if type(archetype) is not str or archetype not in content_archetypes():
        raise ValueError("unknown original playable archetype")
    if type(frames) is not int or not 1 <= frames <= 12000:
        raise ValueError("scene frame budget must be 1..12000")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 300:
        raise ValueError("scene timeout must be finite and 1..300 seconds")
    scene = f"scenes/archetypes/{archetype}/main.tscn"
    required = (
        "project.godot", scene,
        f"scripts/archetypes/{archetype}/core_loop.gd",
        f"scripts/archetypes/{archetype}/player_controller.gd",
    )
    if not isinstance(files, Mapping) or any(
        path not in files or type(files[path]) is not str for path in required
    ):
        raise ValueError("playable scene source is incomplete")

    executable, source, verified = resolve_binary(binary)
    receipt: Dict[str, Any] = {
        "schema": "skeleton.gameforge.native_playable_scene.v1",
        "scene": "res://" + scene,
        "archetype": archetype,
        "binary_source": source,
        "verified": verified,
        "frames": frames,
        "passed": False,
    }
    if executable is None:
        return {**receipt, "status": "unavailable", "reason": source, "errors": []}

    root = Path(tempfile.mkdtemp(prefix="forge-native-scene-"))
    start = time.monotonic()
    deadline = start + float(timeout)
    errors: List[str] = []
    steps: List[Dict[str, Any]] = []
    completed = False
    try:
        write_project(root, dict(files), overwrite=True)
        success = f"{COMPLETE_MARKER} {archetype} "
        failure = f"{FAILED_MARKER} {archetype} "
        for name, command in (
            ("import", [executable, "--headless", "--path", str(root), "--import"]),
            ("scene", [
                executable, "--headless", "--fixed-fps", "60",
                "--quit-after", str(frames), "--path", str(root),
                "res://" + scene,
            ]),
        ):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.append("playable scene deadline exceeded")
                break
            code, output, timed_out = _run(command, root, remaining)
            found = scan_log(output)
            lines = tuple(line.strip() for line in output.splitlines())
            success_seen = name == "scene" and any(line.startswith(success) for line in lines)
            failure_seen = any(line.startswith(failure) for line in lines)
            errors.extend(found[:12])
            if code != 0:
                errors.append(f"{name}: engine exited {code}")
            if timed_out:
                errors.append(f"{name}: deadline exceeded")
            if failure_seen:
                errors.append("native playable loop reported failure")
            if name == "scene":
                completed = success_seen and not failure_seen
                if not success_seen:
                    errors.append("native playable completion marker missing")
            steps.append({
                "step": name, "returncode": code, "timed_out": timed_out,
                "errors": found[:12], "log_tail": output[-2000:],
                "completion_marker": success_seen, "failure_marker": failure_seen,
            })
            if errors:
                break
        passed = completed and not errors and len(steps) == 2
        return {
            **receipt,
            "status": "passed" if passed else "failed",
            "passed": bool(passed), "errors": errors[:24],
            "steps": steps,
            "elapsed_s": round(time.monotonic() - start, 3),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


__all__ = ["PLAYTEST_MODES", "normalise_mode", "resolve_binary", "scan_log", "playtest", "playtest_archetype_scene"]
