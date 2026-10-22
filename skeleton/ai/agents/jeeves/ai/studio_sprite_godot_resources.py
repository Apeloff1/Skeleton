"""Godot 4 SpriteFrames and live AnimatedSprite2D preview from original atlases.

Godot files contain genuine AtlasTexture subresources, timed SpriteFrames and
an AnimatedSprite2D node with the authored pivot, not disconnected PNG imports.
Generation remains a candidate until the independently controlled Godot
loader actually opens the scene and an engine run verifies it.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import re

from .studio_interaction_contract import digest

PORTABLE_ASSET = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class SpriteResourceError(ValueError):
    """A resource name, frame position or animation cannot be serialized safely."""


def _label(value: Any, what: str) -> str:
    if type(value) is not str or PORTABLE_ASSET.fullmatch(value) is None:
        raise SpriteResourceError(what + " must be a portable lowercase resource identifier")
    return value


def compile_godot_sprite_resources(meta: Mapping[str, Any], *,
                                   directory: str = "game/frontier/sprites") -> dict[str, str]:
    """Create exact versioned Godot 4 .tres and .tscn for authored PNG atlas."""
    if not isinstance(meta, Mapping):
        raise SpriteResourceError("reviewed sprite receipt required")
    asset = _label(meta.get("asset_id"), "sprite resource name")
    if directory not in ("game/frontier/sprites", "sprites"):
        raise SpriteResourceError("Godot source resources must use a known relative project root")
    frames = meta.get("frames")
    animations = meta.get("animations")
    if (type(frames) is not list or not 1 <= len(frames) <= 64
            or type(animations) is not list or not 1 <= len(animations) <= 32):
        raise SpriteResourceError("reviewed frames and original timed states required")
    if any(not isinstance(frame, Mapping) for frame in frames):
        raise SpriteResourceError("sprite frame is not typed")
    # A Godot CanvasTexture carries both diffuse and independently authored
    # normal atlases through the SAME AtlasTexture UVs, frame by frame. This
    # enables 2D light-normal sampling without changing any source pixels.
    lighting = meta.get("normal_map")
    has_normals = lighting is not None
    if has_normals:
        if not isinstance(lighting, Mapping):
            raise SpriteResourceError("normal atlas needs a canonical reviewed receipt")
        receipt = dict(lighting)
        pinned = receipt.pop("receipt_sha256", None)
        if (not isinstance(pinned, str) or pinned != digest(receipt)
                or lighting.get("schema_version") !=
                "skeleton.jeeves.authored_sprite_normal_atlas.v1"
                or lighting.get("color_png_sha256") != meta.get("png_sha256")
                or lighting.get("normal_image_width_px") != meta.get("sheet_width_px")
                or lighting.get("normal_image_height_px") != meta.get("sheet_height_px")
                or lighting.get("source_heights_authored") is not True
                or lighting.get("normal_map_loaded_in_native_engine") is not False
                or not isinstance(lighting.get("normal_png_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", lighting["normal_png_sha256"]) is None):
            raise SpriteResourceError("normal atlas source identity is not verified")
    ids: dict[str, int] = {}
    lines = [
        f"[gd_resource type=\"SpriteFrames\" load_steps={len(frames) + 2} format=3]",
        "",
        f"[ext_resource type=\"Texture2D\" path=\"res://{directory}/{asset}.png\" id=\"1\"]",
        "",
    ]
    for index, frame in enumerate(frames):
        fid = _label(frame.get("frame_id"), "frame identity")
        if fid in ids:
            raise SpriteResourceError("duplicate frame ID in resource")
        ids[fid] = index
        rect = frame.get("rect_px")
        if (type(rect) is not list or len(rect) != 4
                or any(type(v) is not int for v in rect)
                or rect[0] < 0 or rect[1] < 0
                or rect[2] < 1 or rect[3] < 1):
            raise SpriteResourceError("original sprite UV region is invalid")
        if (rect[0] + rect[2] > meta.get("sheet_width_px", 0)
                or rect[1] + rect[3] > meta.get("sheet_height_px", 0)):
            raise SpriteResourceError("resource frame exceeds original PNG surface")
        lines.extend([
            f"[sub_resource type=\"AtlasTexture\" id=\"Atlas_{index}\"]",
            'atlas = ExtResource("1")',
            f"region = Rect2({rect[0]}, {rect[1]}, {rect[2]}, {rect[3]})",
            "",
        ])
    defined: set[str] = set()
    blocks: list[str] = []
    for entry in animations:
        if not isinstance(entry, Mapping):
            raise SpriteResourceError("animation source must be an object")
        name = _label(entry.get("name"), "animation state")
        if name in defined:
            raise SpriteResourceError("duplicate animation name")
        defined.add(name)
        fids = entry.get("frame_ids")
        if (type(fids) is not list or not fids
                or len(fids) > 256
                or any(type(key) is not str or key not in ids for key in fids)
                or type(entry.get("loop")) is not bool):
            raise SpriteResourceError("animation contains missing frame or invalid loop")
        frames_source = []
        total_ms = 0
        for fid in fids:
            idx = ids[fid]
            duration = frames[idx].get("duration_ms")
            if type(duration) is not int or not 10 <= duration <= 60_000:
                raise SpriteResourceError("original animation duration is invalid")
            total_ms += duration
            frames_source.append(
                '{ "duration": ' + format(duration / 100.0, ".6f")
                + ', "texture": SubResource("Atlas_' + str(idx) + '") }'
            )
        if total_ms != entry.get("duration_ms"):
            raise SpriteResourceError("animation timing differs from authored frame durations")
        blocks.append(
            '{ "frames": [' + ", ".join(frames_source)
            + '], "loop": ' + ("true" if entry["loop"] else "false")
            + ', "name": &"' + name + '", "speed": 10.0 }'
        )
    first = _label(animations[0]["name"], "initial animation")
    lines.extend([
        "[resource]",
        "animations = [",
        ",\n".join(blocks),
        "]",
        "",
    ])
    # A CanvasTexture is NOT supported for Sprite3D. Keep the historical
    # diffuse-only .tres for AnimatedSprite3D gameplay. When normals are
    # authored, emit an additional .lit.tres for the 2D preview and its
    # DirectionalLight2D. Both variants retain identical atlas UVs and timing.
    normal_preview = None
    if has_normals:
        lit_lines = list(lines)
        lit_lines[0] = (
            f'[gd_resource type="SpriteFrames" load_steps={len(frames) + 4} format=3]'
        )
        lit_lines[4:4] = [
            f'[ext_resource type="Texture2D" path="res://{directory}/{asset}.normal.png" id="2"]',
            "",
            '[sub_resource type="CanvasTexture" id="CanvasSurface"]',
            'diffuse_texture = ExtResource("1")',
            'normal_texture = ExtResource("2")',
            "",
        ]
        normal_preview = "\n".join(lit_lines).replace(
            'atlas = ExtResource("1")',
            'atlas = SubResource("CanvasSurface")',
        )
    # The preview scene is an AnimatedSprite2D, never a 3D CanvasTexture user.
    first_frame = frames[0]
    pivot = first_frame.get("pivot_px")
    if (type(pivot) is not list or len(pivot) != 2
            or any(type(v) is not int or v < 0 for v in pivot)):
        raise SpriteResourceError("original animation requires exact pivot coordinates")
    rect = first_frame["rect_px"]
    offset_x = rect[2] / 2.0 - pivot[0]
    offset_y = rect[3] / 2.0 - pivot[1]
    preview_resource = asset + (".lit.tres" if has_normals else ".tres")
    scene_lines = [
        "[gd_scene load_steps=2 format=3]",
        "",
        f'[ext_resource type="SpriteFrames" path="res://{directory}/{preview_resource}" id="1"]',
        "",
        '[node name="OriginalAnimatedSprite" type="AnimatedSprite2D"]',
        'sprite_frames = ExtResource("1")',
        f'animation = &"{first}"',
        f'autoplay = "{first}"',
        f"offset = Vector2({offset_x:.3f}, {offset_y:.3f})",
        "texture_filter = 1",
        "",
    ]
    if has_normals:
        scene_lines.extend([
            '[node name="OriginalNormalPreviewLight" type="DirectionalLight2D" parent="."]',
            "rotation = 0.785398",
            "energy = 0.8",
            "",
        ])
    result = {
        f"{directory}/{asset}.tres": "\n".join(lines),
        f"{directory}/{asset}.tscn": "\n".join(scene_lines),
    }
    if normal_preview is not None:
        result[f"{directory}/{asset}.lit.tres"] = normal_preview
    return result


def verify_godot_sprite_resources(
    meta: Mapping[str, Any], files: Mapping[str, str],
    *, directory: str = "game/frontier/sprites",
) -> dict[str, Any]:
    """Regenerate byte-identical Godot engine resources from the approved atlas."""
    expected = compile_godot_sprite_resources(meta, directory=directory)
    if set(files) != set(expected) or any(files[name] != raw for name, raw in expected.items()):
        raise SpriteResourceError("Godot SpriteFrames resource differs from original source")
    result = {
        "schema_version": "skeleton.jeeves.godot_sprite_resources.v1",
        "asset_id": meta["asset_id"],
        "source_sprite_receipt_sha256": meta["receipt_sha256"],
        "resource_paths": sorted(expected),
        "source_resource_reproducible": True,
        "canvas_normal_resource_compiled": bool(meta.get("normal_map")),
        "three_dimensional_diffuse_resource_preserved": True,
        "two_dimensional_lighting_preview_compiled": bool(meta.get("normal_map")),
        "normal_image_sha256": (meta["normal_map"]["normal_png_sha256"]
                                if meta.get("normal_map") else None),
        "in_engine_loaded_and_rendered": False,
    }
    result["receipt_sha256"] = digest(result)
    return result


__all__ = [
    "SpriteResourceError", "compile_godot_sprite_resources",
    "verify_godot_sprite_resources",
]
