"""Operator-authorized JavaScript game replay of generated HTML5 source.

Actual JavaScript gameplay is executed in Node's bounded VM against a stub DOM
and Canvas2D method recorder. This is stronger than source-string tests but
is NOT browser rendering, browser security isolation, Godot playthrough, human
QA or hardware certification. No default launch by Jeeves or Dragon.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess

from .contracts import canonical_digest
from .studio_build_qualification import _regular

SCHEMA = "skeleton.game_builder.browser_js_qualification.v1"
_MAX_SOURCE = 2_000_000
_MAX_OUTPUT = 12_000


class StudioRuntimeQualificationError(ValueError):
    """A browser-runtime source, replay, binary or receipt is unqualified."""


@dataclass(frozen=True, slots=True)
class BrowserReplayQualification:
    world_digest: str
    html_sha256: str
    proof_sha256: str
    node_available: bool
    javascript_executed: bool
    winning_replay_verified: bool
    canvas_draw_calls: int
    sprite_draws_exercised: bool
    animation_tick_exercised: bool
    keyboard_input_verified: bool
    onscreen_button_input_verified: bool
    undo_replay_verified: bool
    restart_verified: bool
    original_ambient_play_method_invoked: bool
    original_overlay_draw_calls: int
    audio_hardware_verified: bool
    failure: str | None
    receipt_digest: str

    def as_receipt(self) -> dict:
        body = {
            "schema": SCHEMA,
            "world_digest": self.world_digest,
            "html_sha256": self.html_sha256,
            "proof_sha256": self.proof_sha256,
            "node_available": self.node_available,
            "javascript_executed": self.javascript_executed,
            "winning_replay_verified": self.winning_replay_verified,
            "canvas_draw_calls": self.canvas_draw_calls,
            "sprite_draws_exercised": self.sprite_draws_exercised,
            "animation_tick_exercised": self.animation_tick_exercised,
            "keyboard_input_verified": self.keyboard_input_verified,
            "onscreen_button_input_verified": self.onscreen_button_input_verified,
            "undo_replay_verified": self.undo_replay_verified,
            "restart_verified": self.restart_verified,
            "original_ambient_play_method_invoked": self.original_ambient_play_method_invoked,
            "original_overlay_draw_calls": self.original_overlay_draw_calls,
            "audio_hardware_verified": self.audio_hardware_verified,
            "graphical_browser_pixels_verified": False,
            "godot_executable_tested": False,
            "controller_hardware_tested": False,
            "release_ready": False,
            "failure": self.failure,
        }
        if canonical_digest(body) != self.receipt_digest:
            raise StudioRuntimeQualificationError("JavaScript replay receipt altered")
        return {**body, "receipt_digest": self.receipt_digest}


def _receipt(world: str, html: str, proof: str, *, available: bool,
             executed: bool = False, won: bool = False, draws: int = 0,
             sprites: bool = False, frames: bool = False,
             controls: bool = False, ambient: bool = False,
             overlays: int = 0, failure: str | None = None) -> BrowserReplayQualification:
    body = {
        "schema": SCHEMA,
        "world_digest": world, "html_sha256": html, "proof_sha256": proof,
        "node_available": available, "javascript_executed": executed,
        "winning_replay_verified": won, "canvas_draw_calls": draws,
        "sprite_draws_exercised": sprites,
        "animation_tick_exercised": frames,
        "keyboard_input_verified": controls,
        "onscreen_button_input_verified": controls,
        "undo_replay_verified": controls,
        "restart_verified": controls,
        "original_ambient_play_method_invoked": ambient,
        "original_overlay_draw_calls": overlays,
        "audio_hardware_verified": False,
        "graphical_browser_pixels_verified": False,
        "godot_executable_tested": False,
        "controller_hardware_tested": False,
        "release_ready": False, "failure": failure,
    }
    return BrowserReplayQualification(
        world, html, proof, available, executed, won, draws, sprites, frames,
        controls, controls, controls, controls, ambient, overlays, False,
        failure, canonical_digest(body),
    )


def _inputs(source: Path) -> tuple[bytes, bytes, str]:
    if not source.is_dir() or source.is_symlink():
        raise StudioRuntimeQualificationError("actual generated engine project required")
    release = source / "release.json"
    if release.is_symlink():
        raise StudioRuntimeQualificationError("release manifest must be a regular file")
    try:
        manifest = json.loads(_regular(release, 128_000))
    except (ValueError, UnicodeError) as exc:
        raise StudioRuntimeQualificationError("invalid engine manifest") from exc
    if (type(manifest) is not dict
            or manifest.get("schema") != "skeleton.game_builder.dual_runtime_package.v1"
            or type(manifest.get("files")) is not dict
            or type(manifest.get("world_digest")) is not str):
        raise StudioRuntimeQualificationError("missing original engine manifest")
    payload = {k: v for k, v in manifest.items() if k != "manifest_digest"}
    if canonical_digest(payload) != manifest.get("manifest_digest"):
        raise StudioRuntimeQualificationError("engine release manifest digest mismatch")
    files = manifest["files"]
    html_name, proof_name = "index.html", "proof/verified_solution.json"
    if html_name not in files or proof_name not in files:
        raise StudioRuntimeQualificationError("source and proof must both be in the manifest")
    try:
        html = _regular(source / html_name, _MAX_SOURCE)
        proof = _regular(source / proof_name, 128_000)
    except (OSError, ValueError) as exc:
        raise StudioRuntimeQualificationError("engine JS or replay missing") from exc
    for name, data in ((html_name, html), (proof_name, proof)):
        if files[name] != sha256(data).hexdigest():
            raise StudioRuntimeQualificationError("engine content differs from source receipt")
    try:
        replay = json.loads(proof)
    except ValueError as exc:
        raise StudioRuntimeQualificationError("source replay not parseable") from exc
    if (type(replay) is not dict
            or replay.get("schema") != "skeleton.game_builder.solution_trace.v1"
            or replay.get("world_digest") != manifest["world_digest"]
            or not isinstance(replay.get("actions"), list)
            or not isinstance(replay.get("final_state"), dict)
            or replay["final_state"].get("status") != "won"
            or len(replay["actions"]) > 20000):
        raise StudioRuntimeQualificationError("unverified or mismatched browser replay source")
    return html, proof, manifest["world_digest"]


def qualify_browser_gameplay(
    engine_source: str | Path, *, authorized: bool, execute: bool,
    timeout_seconds: int = 30,
) -> BrowserReplayQualification:
    if authorized is not True:
        raise PermissionError("actual JavaScript runtime requires explicit operator approval")
    if type(execute) is not bool or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise StudioRuntimeQualificationError("runtime controls must be bounded explicit types")
    folder = Path(engine_source)
    html, proof, world = _inputs(folder)
    html_digest, proof_digest = sha256(html).hexdigest(), sha256(proof).hexdigest()
    node = shutil.which("node")
    if node is None:
        return _receipt(world, html_digest, proof_digest,
                        available=False, failure="node_not_installed")
    if not execute:
        return _receipt(world, html_digest, proof_digest,
                        available=True, failure="javascript_execution_not_authorized")
    probe = Path(__file__).with_name("studio_browser_probe.js")
    if not probe.is_file() or probe.is_symlink():
        raise StudioRuntimeQualificationError("fixed original game runtime probe missing")
    args = [node, str(probe), str(folder / "index.html"),
            str(folder / "proof/verified_solution.json")]
    try:
        process = subprocess.run(
            args, shell=False, timeout=timeout_seconds, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": os.defpath, "HOME": str(folder), "LC_ALL": "C"},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _receipt(world, html_digest, proof_digest, available=True,
                        failure="node_runtime_failed:" + type(exc).__name__)
    output = process.stdout
    if len(output) > _MAX_OUTPUT or len(output) == 0 or process.returncode != 0:
        return _receipt(world, html_digest, proof_digest, available=True,
                        executed=True, failure="javascript_gameplay_exited_unsuccessfully")
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        return _receipt(world, html_digest, proof_digest, available=True,
                        executed=True, failure="javascript_runtime_result_invalid")
    if (type(result) is not dict
            or result.get("schema") != "skeleton.game_builder.js_playthrough_probe.v1"
            or result.get("executed") is not True or result.get("result") != "won"
            or result.get("source_sha256") != html_digest
            or result.get("proof_sha256") != proof_digest
            or any(result.get(key) is not True for key in (
                "keyboard_input_verified", "onscreen_button_input_verified",
                "undo_replay_verified", "restart_verified",
            ))
            or result.get("source_world_digest") != world
            or result.get("audio_hardware_verified") is not False
            or type(result.get("original_overlay_draw_calls")) is not int
            or not 0 <= result["original_overlay_draw_calls"] <= 50_000_000
            or type(result.get("canvas_draw_calls")) is not int
            or not 0 < result["canvas_draw_calls"] <= 50_000_000):
        return _receipt(world, html_digest, proof_digest, available=True,
                        executed=True, failure="runtime_result_did_not_match_original_proof")
    return _receipt(
        world, html_digest, proof_digest, available=True, executed=True,
        won=True, draws=result["canvas_draw_calls"],
        sprites=result.get("original_sprites_drawn") is True,
        frames=result.get("original_animation_tick_exercised") is True,
        controls=True,
        ambient=result.get("original_soundtrack_playback_method_called") is True,
        overlays=result["original_overlay_draw_calls"],
    )


__all__ = [
    "StudioRuntimeQualificationError", "BrowserReplayQualification",
    "qualify_browser_gameplay",
]
