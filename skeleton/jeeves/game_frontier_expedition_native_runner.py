"""Execute a real generated Godot 4 expedition and verify complete native replay.

This is an explicit host action: Godot executable must be installed and its
version verified. We never silently replace engine execution with a simulated
outcome. The captured source, native stdout and replay receipts remain scoped
to the same original world/player/build.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .game_frontier_expedition import ExpeditionError, ExpeditionWorld, Traveler, _json
from .game_frontier_expedition_godot import (
    emit_expedition_godot_project, make_expedition_autoplay,
    verify_expedition_godot_project,
)
from .game_frontier_expedition_native_verify import inspect_native_expedition_trace

COMPLETE_PREFIX="EXPEDITION_COMPLETE "
MAX_ENGINE_LOG=8_000_000


def _file_sha(path: Path) -> str:
    digest=sha256()
    with path.open("rb") as f:
        while chunk:=f.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_headless_expedition(
    world: ExpeditionWorld, traveler: Traveler, *,
    godot_executable: str | Path | None = None,
    timeout_seconds: int = 90,
) -> dict:
    """Actually invoke Godot and independently check every gameplay action."""
    if not isinstance(world, ExpeditionWorld) or not isinstance(traveler, Traveler):
        raise ExpeditionError("native playthrough requires actual original world/player")
    if type(timeout_seconds) is not int or not 1<=timeout_seconds<=300:
        raise ExpeditionError("native playthrough timeout must be bounded")
    binary=(
        str(godot_executable) if godot_executable is not None else
        shutil.which("godot4") or shutil.which("godot")
    )
    if not binary:
        raise ExpeditionError("Godot 4 executable unavailable; no native proof")
    resolved=Path(binary).resolve() if Path(binary).is_absolute() else Path(
        shutil.which(binary) or binary
    ).resolve()
    if not resolved.is_file():
        raise ExpeditionError("requested native Godot executable does not exist")
    try:
        version=subprocess.run(
            [str(resolved),"--version"],capture_output=True,text=True,
            stdin=subprocess.DEVNULL,timeout=20,check=False,
        )
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ExpeditionError("cannot verify real Godot executable") from exc
    if version.returncode!=0 or not version.stdout.strip().startswith("4."):
        raise ExpeditionError("a real Godot 4 executable is required")
    files=emit_expedition_godot_project(
        world,traveler,include_autoplay=True,
    )
    candidate=verify_expedition_godot_project(
        files,world,traveler,include_autoplay=True,
    )
    recipe=make_expedition_autoplay(world,traveler)
    with tempfile.TemporaryDirectory(prefix="jeeves-expedition-native-") as temp:
        folder=Path(temp)
        for path,contents in files.items():
            destination=folder/path
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(contents,encoding="utf-8")
        with tempfile.TemporaryFile() as log:
            try:
                process=subprocess.run(
                    [str(resolved),"--headless","--path",str(folder),
                     "--quit-after","20","--","--expedition-autoplay"],
                    cwd=folder,stdin=subprocess.DEVNULL,
                    stdout=log,stderr=subprocess.STDOUT,
                    check=False,timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise ExpeditionError("native Godot runtime exceeded playthrough deadline") from exc
            except OSError as exc:
                raise ExpeditionError("native Godot process could not start") from exc
            size=log.tell()
            if size>MAX_ENGINE_LOG:
                raise ExpeditionError("native playthrough output exceeded evidence budget")
            log.seek(0)
            output=log.read().decode("utf-8",errors="replace")
    if process.returncode!=0:
        raise ExpeditionError(
            f"native Godot process failed with exit code {process.returncode}"
        )
    native_lines=[line[len(COMPLETE_PREFIX):] for line in output.splitlines()
                  if line.startswith(COMPLETE_PREFIX)]
    if len(native_lines)!=1:
        # Capture *bounded diagnostics only*, never full project stdout.
        # Godot may exit zero even when a GDScript attached to a scene fails
        # parsing and the scene never executes gameplay.
        diagnostics=[
            line.strip()[:240] for line in output.splitlines()
            if any(token in line.lower() for token in (
                "error:", "parse error", "parser error", "invalid call",
                "failed to load", "script error", "at: ",
                "expedition_ready",
            ))
        ][:12]
        raise ExpeditionError(
            "native engine never emitted unique full-run result; "
            "godot_diagnostics="+repr(diagnostics)
        )
    try:
        actual=json.loads(native_lines[0])
    except (ValueError,TypeError) as exc:
        raise ExpeditionError("invalid native full-run completion JSON") from exc
    if (type(actual) is not dict or set(actual)!={
        "world_digest","route_digest","completed","steps","candidate_receipt_head"
    } or actual["world_digest"]!=world.digest
            or actual["route_digest"]!=recipe["route_digest"]
            or actual["completed"] is not True
            or type(actual["steps"]) is not int
            or actual["steps"]!=len(recipe["steps"])
            or type(actual["candidate_receipt_head"]) is not str):
        raise ExpeditionError("native runtime completed a different game or route")
    checked=inspect_native_expedition_trace(
        output,world,traveler,expected_complete=True,
    )
    if (checked["native_candidate_receipt_head"]!=actual["candidate_receipt_head"]
            or checked["executed_actions"]!=len(recipe["steps"])):
        raise ExpeditionError("native observations and declared outcome disagree")
    data={
        "schema":"skeleton.game.expedition_native_complete_replay.v1",
        "project_id":world.project_id,
        "world_digest":world.digest,
        "source_digest":world.source_digest,
        "native_executable_sha256":_file_sha(resolved),
        "native_version":version.stdout.strip()[:100],
        "native_log_sha256":sha256(output.encode("utf-8")).hexdigest(),
        "candidate_files_receipt":candidate["receipt_digest"],
        "authored_route_digest":recipe["route_digest"],
        "authored_route_steps":len(recipe["steps"]),
        "observed_replay_receipt":checked["receipt_digest"],
        "observed_candidate_head":actual["candidate_receipt_head"],
        "native_process_executed":True,
        "native_gameplay_consistent":True,
        "native_origin_independently_signed":False,
        "completed":True,
    }
    return {**data,"receipt_digest":sha256(_json(data)).hexdigest()}
