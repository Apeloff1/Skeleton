"""Execute a real Godot 4 SpriteFrames import inspection when a host allows it.

Builds an original AnimatedSprite2D candidate and asks an INSTALLED Godot 4
binary to load it, instantiate it and check AtlasTexture regions, animation
state names and authored per-frame durations. Output is bounded untrusted
engine evidence, matched against the original sprite receipt and binary SHA.
This does not claim screenshots, visual art quality or collision gameplay.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .studio_interaction_contract import digest
from .studio_sprite_forge import compile_authored_sprite
from .studio_sprite_godot_resources import compile_godot_sprite_resources

MAX_LOG_BYTES = 256 * 1024
IMPORT_PREFIX = "JEEVES_SPRITE_IMPORT "
FORMAT = "skeleton.jeeves.native_sprite_import.v1"


class NativeSpriteImportError(ValueError):
    """Real Godot import/scene inspection cannot be independently confirmed."""


_GD_CHECK = """extends SceneTree

func _initialize() -> void:
    call_deferred("_verify")

func _verify() -> void:
    var expected = JSON.parse_string(EXPECTED_LITERAL)
    if not (expected is Dictionary):
        quit(7)
        return
    var scene = load("res://game/frontier/sprites/ASSET_ID.tscn")
    if not (scene is PackedScene):
        quit(8)
        return
    var node = scene.instantiate()
    if not (node is AnimatedSprite2D):
        quit(9)
        return
    var atlas = node.sprite_frames
    if not (atlas is SpriteFrames):
        quit(10)
        return
    if atlas.get_animation_names().size() != expected["animations"].size():
        quit(11)
        return
    var checked = 0
    for state in expected["animations"]:
        var name = StringName(state["name"])
        if not atlas.has_animation(name):
            quit(12)
            return
        if atlas.get_frame_count(name) != state["count"]:
            quit(13)
            return
        if atlas.get_animation_loop(name) != state["loop"]:
            quit(14)
            return
        if abs(atlas.get_animation_speed(name) - 10.0) > 0.0001:
            quit(15)
            return
        for i in range(state["count"]):
            var tex = atlas.get_frame_texture(name, i)
            if not (tex is AtlasTexture):
                quit(16)
                return
            var rect = tex.region
            if abs(rect.size.x - expected["width"]) > 0.001 or abs(rect.size.y - expected["height"]) > 0.001:
                quit(17)
                return
            if abs(atlas.get_frame_duration(name, i) * 100.0 - state["durations_ms"][i]) > 0.01:
                quit(18)
                return
            checked += 1
    var report = {
        "schema_version": "skeleton.jeeves.native_sprite_import.v1",
        "asset_id": "ASSET_ID",
        "animation_states_checked": expected["animations"].size(),
        "texture_regions_checked": checked,
        "engine_import_succeeded": true,
        "native_gameplay_playthrough_verified": false
    }
    print("JEEVES_SPRITE_IMPORT " + JSON.stringify(report))
    node.free()
    quit(0)
"""


def _file_sha256(path: Path) -> str:
    result = sha256()
    with path.open("rb") as source:
        while True:
            buffer = source.read(1024 * 1024)
            if not buffer:
                break
            result.update(buffer)
    return result.hexdigest()


def inspect_godot_sprite_import(
    record: dict[str, Any], *, godot_executable: str,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    if (type(godot_executable) is not str or not godot_executable
            or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 300):
        raise NativeSpriteImportError("host must supply an actual bounded Godot 4 command")
    binary = Path(godot_executable)
    if (not binary.is_absolute() or not binary.is_file()
            or binary.is_symlink()):
        raise NativeSpriteImportError("approved absolute Godot 4 executable is missing")
    try:
        version = subprocess.run(
            [str(binary), "--version"], stdin=subprocess.DEVNULL,
            capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NativeSpriteImportError("could not independently identify native Godot binary") from exc
    if (version.returncode != 0 or len(version.stdout) > 1000
            or not version.stdout.decode("utf-8", "replace").strip().startswith("4.")):
        raise NativeSpriteImportError("real installed Godot 4 binary is required")
    candidate = compile_authored_sprite(record)
    meta = candidate["metadata"]
    resources = compile_godot_sprite_resources(meta)
    asset_id = meta["asset_id"]
    name_to_time = {frame["frame_id"]: frame["duration_ms"] for frame in meta["frames"]}
    expected = {
        "width": meta["frame_width_px"],
        "height": meta["frame_height_px"],
        "animations": [
            {
                "name": state["name"],
                "count": len(state["frame_ids"]),
                "loop": state["loop"],
                "durations_ms": [
                    name_to_time[key] for key in state["frame_ids"]
                ],
            }
            for state in meta["animations"]
        ],
    }
    gdscript = _GD_CHECK.replace(
        "EXPECTED_LITERAL", json.dumps(json.dumps(expected, separators=(",", ":")),
                                       ensure_ascii=True),
    ).replace("ASSET_ID", asset_id)
    with tempfile.TemporaryDirectory(prefix="jeeves-native-sprite-") as folder:
        root = Path(folder)
        for name, data in {
            **{name: body.encode("utf-8") for name, body in resources.items()},
            f"game/frontier/sprites/{asset_id}.png": candidate["png"],
            "project.godot": b"config_version=5\n",
            "verify_sprite.gd": gdscript.encode("utf-8"),
        }.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        with tempfile.TemporaryFile() as output:
            try:
                execution = subprocess.run(
                    [str(binary), "--headless", "--path", str(root),
                     "--script", "res://verify_sprite.gd"],
                    cwd=root, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT,
                    timeout=timeout_seconds, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise NativeSpriteImportError("native Godot sprite inspection did not finish") from exc
            size = output.tell()
            if size > MAX_LOG_BYTES:
                raise NativeSpriteImportError("native sprite engine log exceeds evidence budget")
            output.seek(0)
            log = output.read().decode("utf-8", errors="replace")
    if execution.returncode != 0:
        raise NativeSpriteImportError(
            "real Godot SpriteFrames import failed with return code "
            + str(execution.returncode)
        )
    messages = [
        line[len(IMPORT_PREFIX):]
        for line in log.splitlines() if line.startswith(IMPORT_PREFIX)
    ]
    if len(messages) != 1 or len(messages[0]) > 8192:
        raise NativeSpriteImportError("native sprite import lacks unique bounded engine receipt")
    try:
        native = json.loads(messages[0])
    except (ValueError, TypeError) as exc:
        raise NativeSpriteImportError("native sprite engine emitted invalid completion data") from exc
    required = {
        "schema_version": FORMAT, "asset_id": asset_id,
        "animation_states_checked": len(expected["animations"]),
        "texture_regions_checked": sum(
            item["count"] for item in expected["animations"]
        ),
        "engine_import_succeeded": True,
        "native_gameplay_playthrough_verified": False,
    }
    if type(native) is not dict or native != required:
        raise NativeSpriteImportError("native sprite resource observation contradicts source")
    result = {
        **required,
        "source_revision_sha256": meta["source_sha256"],
        "sprite_png_sha256": meta["png_sha256"],
        "sprite_metadata_sha256": meta["receipt_sha256"],
        "godot_executable_sha256": _file_sha256(binary),
        "godot_version": version.stdout.decode("utf-8", "replace").strip()[:100],
        "native_log_sha256": sha256(log.encode("utf-8")).hexdigest(),
        "native_process_executed": True,
        "pixel_data_independently_verified": True,
        "visual_rendering_verified": False,
    }
    result["receipt_sha256"] = digest(result)
    return result


__all__ = ["NativeSpriteImportError", "inspect_godot_sprite_import"]
