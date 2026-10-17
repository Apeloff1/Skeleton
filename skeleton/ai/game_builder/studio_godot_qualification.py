"""Actual Godot 4 headless replay of canonical original game project source.

Executes the existing Godot _verify_native_proof() in an isolated temporary
copy. This verifies GDScript engine execution and Python/engine final-state
parity; it does NOT verify visible 2D pixels, GPU performance, interactive
controller handling, exported binaries or release readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .contracts import canonical_digest
from .studio_build_qualification import _regular

SCHEMA = "skeleton.game_builder.godot_headless_qualification.v1"
_GOOD = re.compile(r"NATIVE_REPLAY_OK ([0-9a-f]{64}) actions=([0-9]+)")
_INPUTS = (
    "project.godot", "scenes/main.tscn", "scripts/main.gd",
    "world.json", "proof.json",
)


class StudioGodotQualificationError(ValueError):
    """Godot cannot be qualified from the current exact generated project."""


@dataclass(frozen=True, slots=True)
class GodotReplayQualification:
    world_digest: str
    source_identity: str
    godot_available: bool
    engine_executed: bool
    game_winning_replay_verified: bool
    action_count: int
    failure: str | None
    receipt_digest: str

    def as_receipt(self) -> dict:
        body = {
            "schema": SCHEMA, "world_digest": self.world_digest,
            "source_identity": self.source_identity,
            "godot_available": self.godot_available,
            "engine_executed": self.engine_executed,
            "game_winning_replay_verified": self.game_winning_replay_verified,
            "action_count": self.action_count, "failure": self.failure,
            "godot_script_loaded": self.game_winning_replay_verified,
            "graphical_framebuffer_verified": False,
            "native_binary_exported": False,
            "hardware_controller_tested": False,
            "rights_or_release_approved": False,
        }
        if canonical_digest(body) != self.receipt_digest:
            raise StudioGodotQualificationError("Godot qualification receipt modified")
        return {**body, "receipt_digest": self.receipt_digest}


def _receipt(world: str, source_identity: str, *, available: bool,
             executed: bool = False, passed: bool = False, steps: int = 0,
             failure: str | None = None) -> GodotReplayQualification:
    body = {
        "schema": SCHEMA, "world_digest": world,
        "source_identity": source_identity,
        "godot_available": available, "engine_executed": executed,
        "game_winning_replay_verified": passed,
        "action_count": steps, "failure": failure,
        "godot_script_loaded": passed,
        "graphical_framebuffer_verified": False,
        "native_binary_exported": False,
        "hardware_controller_tested": False,
        "rights_or_release_approved": False,
    }
    return GodotReplayQualification(
        world, source_identity, available, executed, passed, steps,
        failure, canonical_digest(body),
    )


def godot_inputs(root: Path) -> tuple[dict[str, bytes], str, int, str]:
    """Verify against the exact dual-engine manifest, including sprite pixels."""
    if not root.is_dir() or root.is_symlink():
        raise StudioGodotQualificationError("existing generated engine directory required")
    try:
        release = json.loads(_regular(root / "release.json", 128_000))
    except (OSError, UnicodeError, ValueError) as exc:
        raise StudioGodotQualificationError("unreadable canonical release manifest") from exc
    if (type(release) is not dict
            or release.get("schema") != "skeleton.game_builder.dual_runtime_package.v1"
            or type(release.get("files")) is not dict
            or canonical_digest({k: v for k, v in release.items()
                                 if k != "manifest_digest"}) != release.get("manifest_digest")):
        raise StudioGodotQualificationError("engine release manifest is not canonical")
    files: dict[str, bytes] = {}
    optional = (
        "studio_art.json",
        "audio/ambient.wav", "audio/collectible.wav", "audio/hazard.wav",
        "parallax/layer_00.png", "parallax/layer_01.png", "parallax/layer_02.png",
    )
    paths = _INPUTS + tuple(
        relative for relative in optional
        if "godot/" + relative in release["files"]
    )
    for relative in paths:
        full = "godot/" + relative
        if full not in release["files"]:
            raise StudioGodotQualificationError("Godot project is missing essential source")
        try:
            data = _regular(root / full, 384_000)
        except (ValueError, OSError) as exc:
            raise StudioGodotQualificationError("Godot original source missing") from exc
        if sha256(data).hexdigest() != release["files"][full]:
            raise StudioGodotQualificationError("Godot source has changed since engine export")
        files[relative] = data
    try:
        world_doc = json.loads(files["world.json"])
        proof_doc = json.loads(files["proof.json"])
    except (UnicodeError, ValueError) as exc:
        raise StudioGodotQualificationError("Godot source/replay JSON not valid") from exc
    if (world_doc.get("schema") != "skeleton.game_builder.godot_world.v1"
            or world_doc.get("world_digest") != release.get("world_digest")
            or proof_doc.get("schema") != "skeleton.game_builder.solution_trace.v1"
            or proof_doc.get("world_digest") != release["world_digest"]
            or proof_doc.get("final_state", {}).get("status") != "won"
            or type(proof_doc.get("actions")) is not list
            or not 1 <= len(proof_doc["actions"]) <= 20_000
            or any(step not in ("up", "left", "right", "down")
                   for step in proof_doc["actions"])):
        raise StudioGodotQualificationError("Godot source and replay are not the same proved game")
    if "studio_art.json" in files:
        if ("audio/ambient.wav" in files
                and not all(name in files for name in (
                    "audio/collectible.wav", "audio/hazard.wav"
                ))):
            raise StudioGodotQualificationError("incomplete original soundtrack/cue source")
        for name, payload in files.items():
            if name.startswith("audio/") and not payload.startswith(b"RIFF"):
                raise StudioGodotQualificationError("Godot original WAV asset is invalid")
            if name.startswith("parallax/") and not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                raise StudioGodotQualificationError("Godot original parallax PNG invalid")
        try:
            art = json.loads(files["studio_art.json"])
        except ValueError as exc:
            raise StudioGodotQualificationError("Godot artwork not valid JSON") from exc
        if (art.get("pack_digest") != release.get("studio_art_pack_digest")
                or art.get("world_digest") != release["world_digest"]):
            raise StudioGodotQualificationError("Godot sprite art is not current canonical pack")
    source_digest = canonical_digest({
        "world_digest": release["world_digest"],
        "files": {name: sha256(blob).hexdigest() for name, blob in sorted(files.items())},
    })
    return files, release["world_digest"], len(proof_doc["actions"]), source_digest


def qualify_godot_headless(
    engine_source: str | Path, *, authorized: bool, execute: bool,
    timeout_seconds: int = 45,
) -> GodotReplayQualification:
    if authorized is not True:
        raise PermissionError("native engine execution requires local operator authorization")
    if type(execute) is not bool or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise StudioGodotQualificationError("native engine execution parameters must be bounded")
    files, world, count, source_identity = godot_inputs(Path(engine_source))
    executable = shutil.which("godot") or shutil.which("godot4")
    if executable is None:
        return _receipt(world, source_identity, available=False,
                        failure="godot4_executable_not_installed")
    if not execute:
        return _receipt(world, source_identity, available=True,
                        failure="native_engine_execution_not_authorized")
    with tempfile.TemporaryDirectory(prefix="skeleton-godot-probe-") as scratch:
        project = Path(scratch) / "godot"
        project.mkdir()
        for relative, payload in files.items():
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(payload)
        # Generated source can execute code inside Godot; this requires
        # operator approval and an externally controlled trusted runtime.
        try:
            log = Path(scratch) / "godot-proof.log"
            with log.open("wb") as output:
                result = subprocess.run(
                    [executable, "--headless", "--path", str(project),
                     "--", "--verify-proof"],
                    cwd=scratch, shell=False, check=False,
                    timeout=timeout_seconds, stdout=output,
                    stderr=subprocess.STDOUT,
                    env={"PATH": os.defpath, "HOME": scratch,
                         "XDG_DATA_HOME": scratch, "XDG_CONFIG_HOME": scratch,
                         "LC_ALL": "C"},
                )
            if result.returncode != 0 or log.stat().st_size > 64_000:
                return _receipt(world, source_identity, available=True,
                                executed=True, failure="godot_headless_replay_failed")
            output_text = log.read_text("utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _receipt(world, source_identity, available=True, executed=True,
                            failure="godot_process_failed:" + type(exc).__name__)
    match = _GOOD.search(output_text)
    if not match or match.group(1) != world or int(match.group(2)) != count:
        return _receipt(world, source_identity, available=True, executed=True,
                        failure="godot_world_or_replay_identity_mismatch")
    return _receipt(world, source_identity, available=True, executed=True,
                    passed=True, steps=count)


__all__ = [
    "StudioGodotQualificationError", "GodotReplayQualification",
    "qualify_godot_headless", "godot_inputs",
]
