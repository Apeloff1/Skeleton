"""Source-bound real-Godot frame telemetry for original campaign quality.

The candidate's Godot project is compiled from canonical source. This probe
runs the actual engine; headless rendering measurements are NOT GPU or device
performance attestations, and may only support headless profile budgets.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .production_quality import QualityGateError, _digest, audit_frame_budget

_PREFIX = "SKELETON_GAME_QUALITY "
_SCRIPT = '''extends SceneTree

const SCENE_PATH := "res://game/frontier/expedition.tscn"
const PREFIX := "SKELETON_GAME_QUALITY "
const COUNT := 30

func _initialize() -> void:
    call_deferred("_sample")

func _sample() -> void:
    var scene = load(SCENE_PATH)
    if scene == null or not (scene is PackedScene):
        push_error("quality probe scene was not compiled")
        quit(2)
        return
    var instance = scene.instantiate()
    get_root().add_child(instance)
    for frame in range(COUNT):
        await process_frame
        var observed := {
            "frame": frame,
            "process_ms": Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
            "draw_calls": int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)),
            "engine": Engine.get_version_info().get("major", 0),
            "renderer": "headless_unattested"
        }
        print(PREFIX + JSON.stringify(observed))
    quit(0)
'''


def _verify_sample_log(log: str, count: int) -> list[dict]:
    if type(log) is not str or len(log.encode("utf-8")) > 4_000_000:
        raise QualityGateError("native log exceeds evidence budget")
    frames = []
    for line in log.splitlines():
        if not line.startswith(_PREFIX):
            continue
        try:
            row = json.loads(line[len(_PREFIX):])
        except (ValueError, TypeError) as exc:
            raise QualityGateError("malformed native observation") from exc
        if (type(row) is not dict or set(row) !=
            {"frame", "process_ms", "draw_calls", "engine", "renderer"}
            or type(row["frame"]) is not int or row["frame"] != len(frames)
            or row["engine"] != 4 or row["renderer"] != "headless_unattested"):
            raise QualityGateError("native frame sequence or engine identity changed")
        frames.append({"ms": row["process_ms"], "draw_calls": row["draw_calls"]})
        if len(frames) > count:
            raise QualityGateError("native sample count exceeded source plan")
    if len(frames) != count:
        raise QualityGateError("native engine did not emit complete frame evidence")
    return frames


def run_native_quality_probe(
    files: Mapping[str, str], *, source_sha256: str, executable: str | Path,
    timeout_seconds: int = 90, max_ms: float = 16.67,
    max_draw_calls: int = 1200,
) -> dict:
    """Build isolated supplied original candidate and sample 30 actual Godot frames.

    The host selects an already approved executable. Neither model/user content
    nor a candidate project can select the executable or write outside tempdir.
    """
    from .production_deep_gates import _sha
    _sha(source_sha256, "native candidate source")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise QualityGateError("native engine deadline must be bounded")
    if not isinstance(files, Mapping) or not 2 <= len(files) <= 4096:
        raise QualityGateError("canonical compiled game files required")
    if ("project.godot" not in files or
            "game/frontier/expedition.tscn" not in files):
        raise QualityGateError("native probe requires a real compiled Godot project")
    from pathlib import PurePosixPath
    for path, body in files.items():
        if (type(path) is not str or not path or len(path) > 256 or
                PurePosixPath(path).is_absolute() or "\\" in path or
                any(x in ("", ".", "..") for x in path.split("/")) or
                type(body) is not str or len(body.encode()) > 4_000_000):
            raise QualityGateError("invalid authored candidate file")
    if "quality/observe.gd" in files:
        raise QualityGateError("quality instrumentation would overwrite game file")
    binary = Path(executable).resolve()
    if not binary.is_file():
        raise QualityGateError("host-provisioned Godot executable is absent")
    try:
        version = subprocess.run(
            [str(binary), "--version"], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise QualityGateError("cannot verify native Godot executable") from exc
    if version.returncode or not version.stdout.startswith("4."):
        raise QualityGateError("native quality telemetry requires installed Godot 4")
    with tempfile.TemporaryDirectory(prefix="skeleton-native-quality-") as root:
        project = Path(root)
        for path, body in sorted(files.items()):
            dest = project / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
        target = project / "quality" / "observe.gd"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_SCRIPT, encoding="utf-8")
        try:
            run = subprocess.run(
                [str(binary), "--headless", "--path", str(project),
                 "--script", "res://quality/observe.gd"],
                cwd=project, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise QualityGateError("native game frame probe did not finish") from exc
    if run.returncode:
        raise QualityGateError("native frame sampler exited nonzero")
    frames = _verify_sample_log(run.stdout, 30)
    result = audit_frame_budget(frames, max_ms=max_ms, max_draw_calls=max_draw_calls)
    return {
        "schema": "game.native.headless_quality.v1",
        "source_sha256": source_sha256,
        "engine_sha256": sha256(binary.read_bytes()).hexdigest(),
        "engine_version": version.stdout.strip()[:128],
        "candidate_file_digest": _digest(dict(files)),
        "native_engine_executed": True,
        "gpu_capture_attested": False,
        "device_performance_attested": False,
        "profile": "godot4_headless_unattested",
        "frames": len(frames),
        "frame_gate": result.as_dict(),
        "native_log_sha256": sha256(run.stdout.encode()).hexdigest(),
    }
