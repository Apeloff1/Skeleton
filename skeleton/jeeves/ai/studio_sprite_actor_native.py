"""Independent *real-engine* load check for source-bound Expedition player sprites.

A host must authorize the exact original game, binary and actor before this
function can be used. A successful import demonstrates that the actual Godot
scene instantiates an AnimatedSprite3D beneath the moving player's actor with
the authored SpriteFrames. It is NOT pixel-perfect rendered-frame approval or
proof of a gameplay win. The existing route verifier covers gameplay separately.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping

from .studio_frontier_godot_package import compile_original_godot_candidate
from .studio_interaction_contract import digest
from .studio_sprite_actor_binding import SpriteBindingError
from .studio_sprite_native_import import NativeSpriteImportError, _file_sha256

PREFIX = "JEEVES_AVATAR_OBSERVED "
MAX_ENGINE_LOG = 256 * 1024
CHECK_SCHEMA = "skeleton.jeeves.godot4_actor_avatar_observed.v1"

_INSPECT = '''extends SceneTree

func _initialize() -> void:
    call_deferred("_inspect")

func _inspect() -> void:
    var scene = load("res://game/frontier/expedition.tscn")
    if not (scene is PackedScene):
        quit(7)
        return
    var game = scene.instantiate()
    root.add_child(game)
    var actor = game.get("actor")
    if not (actor is MeshInstance3D):
        quit(8)
        return
    var avatar = actor.get_node_or_null("OriginalAuthoredAvatar")
    if not (avatar is AnimatedSprite3D):
        quit(9)
        return
    var frames = avatar.sprite_frames
    if not (frames is SpriteFrames):
        quit(10)
        return
    var expected = JSON.parse_string(EXPECTED_LITERAL)
    if not (expected is Dictionary):
        quit(11)
        return
    var animation = StringName(expected["animation"])
    if not frames.has_animation(animation):
        quit(12)
        return
    if avatar.animation != animation:
        quit(13)
        return
    if abs(avatar.pixel_size - expected["pixel_size"]) > 0.00001:
        quit(14)
        return
    if abs(avatar.position.y - expected["vertical_offset_m"]) > 0.00001:
        quit(15)
        return
    if expected["hide_capsule"] and actor.mesh != null:
        quit(16)
        return
    if frames.get_frame_count(animation) != expected["frame_count"]:
        quit(17)
        return
    if not avatar.is_playing():
        quit(18)
        return
    var result = {
        "schema_version": "skeleton.jeeves.godot4_actor_avatar_observed.v1",
        "asset_id": expected["asset_id"],
        "animation": expected["animation"],
        "actor_instantiated": true,
        "animated_sprite_child_bound": true,
        "frame_count_observed": frames.get_frame_count(animation),
        "real_godot_process_executed": true,
        "rendered_frame_pixels_verified": false,
        "gameplay_route_completed": false
    }
    print("JEEVES_AVATAR_OBSERVED " + JSON.stringify(result))
    game.queue_free()
    quit(0)
'''


class NativeAvatarError(ValueError):
    """The actual Godot game did not independently prove its player sprite."""


def inspect_native_expedition_avatar(
    project_id: str, records: Mapping[str, Mapping[str, Any]],
    *, source_head_sha256: str | None,
    godot_executable: str, timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Exercise exact emitted authored game files in an installed Godot 4."""
    if (type(godot_executable) is not str or not godot_executable.strip()
            or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300):
        raise NativeAvatarError("native Godot4 authority needs binary and bounded deadline")
    binary = Path(godot_executable)
    if not binary.is_absolute() or not binary.is_file() or binary.is_symlink():
        raise NativeAvatarError("host-authorized Godot 4 executable does not exist")
    candidate = compile_original_godot_candidate(
        project_id, records, source_head_sha256=source_head_sha256,
    )
    binding = candidate["receipt"]["authored_player_avatar_binding"]
    if not isinstance(binding, dict):
        raise NativeAvatarError("original game lacks a reviewed player avatar binding")
    sprite = next((
        item for item in candidate["receipt"]["packaged_original_sprites"]
        if item["asset_id"] == binding["asset_id"]
    ), None)
    if sprite is None:
        raise NativeAvatarError("player animation is not in original Godot source")
    meta = next((
        record["document"] for record in records.values()
        if record.get("record_id") == sprite["source_record_id"]
    ), None)
    if not isinstance(meta, Mapping):
        raise NativeAvatarError("sprite source record was not retained")
    frame_count = len(next(
        item["frame_ids"] for item in meta["animations"]
        if item["name"] == binding["animation"]
    ))
    before = _file_sha256(binary)
    try:
        version = subprocess.run(
            [str(binary), "--version"], capture_output=True,
            stdin=subprocess.DEVNULL, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NativeAvatarError("real Godot4 version probe could not complete") from exc
    if (version.returncode or len(version.stdout) > 1000
            or not version.stdout.decode("utf-8", "replace").strip().startswith("4.")):
        raise NativeAvatarError("verified Godot4 executable required for native actor import")
    expected = {
        "asset_id": binding["asset_id"],
        "animation": binding["animation"],
        "pixel_size": binding["pixel_size"],
        "vertical_offset_m": binding["vertical_offset_m"],
        "hide_capsule": binding["hide_capsule"],
        "frame_count": frame_count,
    }
    native_script = _INSPECT.replace(
        "EXPECTED_LITERAL", json.dumps(
            json.dumps(expected, sort_keys=True, separators=(",", ":")),
            ensure_ascii=True,
        ),
    )
    with tempfile.TemporaryDirectory(prefix="jeeves-original-avatar-") as temp:
        directory = Path(temp)
        files = {
            **{name: text.encode("utf-8")
               for name, text in candidate["files"].items()},
            **candidate["binary_assets"],
            "inspect_avatar.gd": native_script.encode("utf-8"),
        }
        if sum(len(data) for data in files.values()) > 16 * 1024 * 1024:
            raise NativeAvatarError("game package is too large for native avatar inspection")
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with tempfile.TemporaryFile() as output:
            try:
                process = subprocess.run(
                    [str(binary), "--headless", "--path", str(directory),
                     "--script", "res://inspect_avatar.gd"],
                    cwd=directory, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT,
                    timeout=timeout_seconds, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise NativeAvatarError("native engine failed to inspect player avatar") from exc
            length = output.tell()
            if length > MAX_ENGINE_LOG:
                raise NativeAvatarError("native gameplay inspector log exceeds evidence limit")
            output.seek(0)
            log = output.read().decode("utf-8", errors="replace")
    if _file_sha256(binary) != before:
        raise NativeAvatarError("Godot4 binary changed while reviewing avatar")
    if process.returncode != 0:
        raise NativeAvatarError("Godot4 rejected original game/avatar resource")
    observations = [
        line[len(PREFIX):] for line in log.splitlines()
        if line.startswith(PREFIX)
    ]
    if len(observations) != 1 or len(observations[0]) > 4096:
        raise NativeAvatarError("real engine did not emit one trusted player observation")
    try:
        observed = json.loads(observations[0])
    except ValueError as exc:
        raise NativeAvatarError("native avatar observation is invalid JSON") from exc
    expected_observation = {
        "schema_version": CHECK_SCHEMA,
        "asset_id": binding["asset_id"],
        "animation": binding["animation"],
        "actor_instantiated": True,
        "animated_sprite_child_bound": True,
        "frame_count_observed": frame_count,
        "real_godot_process_executed": True,
        "rendered_frame_pixels_verified": False,
        "gameplay_route_completed": False,
    }
    if observed != expected_observation:
        raise NativeAvatarError("native player animation differs from authorized game source")
    evidence = {
        **expected_observation,
        "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "sprite_binding_receipt_sha256": binding["receipt_sha256"],
        "godot_candidate_receipt_sha256": candidate["receipt"]["receipt_sha256"],
        "godot_executable_sha256": before,
        "native_log_sha256": sha256(log.encode("utf-8")).hexdigest(),
        "native_engine_avatar_verified": True,
        "visual_art_grade_certified": False,
    }
    evidence["receipt_sha256"] = digest(evidence)
    return evidence


__all__ = ["NativeAvatarError", "inspect_native_expedition_avatar"]
