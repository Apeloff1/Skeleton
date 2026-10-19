#!/usr/bin/env python3
"""Run a user-supplied, pinned Godot 4 binary against an exported scene.

Two stages: headless editor import, then headless scene fixed-step playback.
The result is local *Godot invocation evidence*, not a signed GPU framebuffer
or claim of world-story/gameplay completion. The binary must be explicitly
chosen and its SHA-256 supplied by the operator; no downloads or shell.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

_ROOT=Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0,str(_ROOT))

from skeleton.jeeves.game_frontier_frame_coherence import digest


class GodotQualificationError(ValueError):
    pass


def _hash_file(path: Path) -> str:
    state=sha256()
    with path.open("rb") as source:
        while True:
            chunk=source.read(1024*1024)
            if not chunk:
                break
            state.update(chunk)
    return state.hexdigest()


def qualify_project(*, binary: Path, expected_sha256: str,
                    project: Path, frames: int = 60,
                    timeout_seconds: int = 120) -> dict:
    """Check real subprocess return codes and parse errors, no shell launch."""
    if type(frames) is not int or not 1 <= frames <= 20_000:
        raise GodotQualificationError("native frame limit out of bounds")
    if type(timeout_seconds) is not int or not 2 <= timeout_seconds <= 600:
        raise GodotQualificationError("native subprocess deadline out of bounds")
    if (type(expected_sha256) is not str or len(expected_sha256)!=64 or
        any(c not in "0123456789abcdef" for c in expected_sha256)):
        raise GodotQualificationError("explicit lowercase binary sha256 pin required")
    if (not binary.is_file() or binary.is_symlink() or
        not project.is_dir() or project.is_symlink()):
        raise GodotQualificationError("native binary/project must be explicit regular paths")
    if _hash_file(binary)!=expected_sha256:
        raise GodotQualificationError("local Godot executable failed operator hash pin")
    assets=("project.godot","frontier/frontier_scene.tscn",
            "frontier/frontier_scene.gd","frontier/data/scene.json")
    for name in assets:
        file=project/name
        if not file.is_file() or file.is_symlink():
            raise GodotQualificationError(f"required Godot asset missing: {name}")
    if (project/"frontier/data/scene.json").stat().st_size>24*1024*1024:
        raise GodotQualificationError("oversized game scene data")
    data=json.loads((project/"frontier/data/scene.json").read_text())
    if (not isinstance(data,dict) or
        data.get("schema")!="skeleton.game.frontier_godot_overlay.v1" or
        not isinstance(data.get("native_capture"),dict)):
        raise GodotQualificationError("scene not produced by authorized Frontier overlay schema")
    for src in ("frontier/frontier_scene.gd","frontier/frontier_scene.tscn"):
        if (project/src).stat().st_size>5*1024*1024:
            raise GodotQualificationError("excessive generated Godot script/scene size")
    stages=(
        ("import",("--headless","--path",str(project),"--import")),
        ("play",("--headless","--path",str(project),"--quit-after",
                 str(frames),"--scene","res://frontier/frontier_scene.tscn")),
    )
    receipts=[]
    for stage,args in stages:
        try:
            process=subprocess.run([str(binary),*args],check=False,cwd=str(project),
                text=True,capture_output=True,timeout=timeout_seconds)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise GodotQualificationError(f"{stage} engine invocation failed") from exc
        output=(process.stdout or "")+"\n"+(process.stderr or "")
        if process.returncode!=0 or re.search(
            r"(?im)(?:SCRIPT ERROR:|Parse Error:|Failed to load script|Failed loading resource|^ERROR:)",
            output,
        ):
            raise GodotQualificationError(
                f"{stage} engine returned failure or native script errors: "+
                output[-1800:])
        receipts.append({
            "stage":stage,"exit_code":process.returncode,
            "stdout_sha256":sha256(process.stdout.encode()).hexdigest(),
            "stderr_sha256":sha256(process.stderr.encode()).hexdigest(),
            "captured_output_bytes":len(output.encode()),
        })
    record={
        "schema":"skeleton.game.native_godot_headless_qualification.v1",
        "expected_godot_binary_sha256":expected_sha256,
        "scene_data_sha256":_hash_file(project/"frontier/data/scene.json"),
        "scene_script_sha256":_hash_file(project/"frontier/frontier_scene.gd"),
        "native_playback_frames_requested":frames,
        "native_stages":receipts,
        "all_invocations_passed":True,
        "authority":"operator_run_local_headless_import_play_not_GPU_or_gameplay_attestation",
    }
    record["receipt_digest"]=digest(record)
    return record


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot",type=Path,required=True)
    parser.add_argument("--godot-sha256",required=True)
    parser.add_argument("--project",type=Path,required=True)
    parser.add_argument("--frames",type=int,default=60)
    parser.add_argument("--timeout-seconds",type=int,default=120)
    args=parser.parse_args(argv)
    try:
        report=qualify_project(binary=args.godot,expected_sha256=args.godot_sha256,
                               project=args.project,frames=args.frames,
                               timeout_seconds=args.timeout_seconds)
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(f"native Godot qualification rejected: {exc}",file=sys.stderr)
        return 2
    print(json.dumps(report,sort_keys=True,separators=(",",":")))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
