"""Original authored 3D scene rendering via the canonical reference rasterizer.

No new GPU/runtime implementation: the historical 3D reference renderer,
and the historical console asset PNG encoder, own pixel production.
Supported pipelines: painter, fixed-function and programmable simulation.
This deliberately does NOT claim console-accurate native hardware export.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "skeleton.game.reference_scene.v1"


class ReferenceSceneError(ValueError):
    pass


def _number(value: Any, name: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ReferenceSceneError(f"invalid scene {name}")
    return float(value)


def _scene_path(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    from skeleton.developer.jeeves_game_quality import _read
    data, sha256 = _read(root, relative, 256 * 1024)
    return data, sha256


def render_reference(root: Path, *, source: str, output: str,
                     target: str, dry_run: bool = False) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_upscale import _policy, _path
    from skeleton.jeeves.game_engine_rendering import (
        RenderVertex, RenderTriangle, RasterPipeline,
        render_reference_image, MAX_RASTER_WIDTH, MAX_RASTER_HEIGHT,
    )
    from skeleton.jeeves.game_console_assets import png_rgba
    from skeleton.developer.jeeves_game_authoring import _create_only
    policy = _policy(target)
    pipelines = {
        "early_3d_software_1993": RasterPipeline.PAINTER,
        "fixed_function_3d_1996": RasterPipeline.FIXED,
        "shader_console_2001": RasterPipeline.PROGRAMMABLE,
    }
    pipeline = pipelines.get(policy["era"])
    if pipeline is None:
        raise ReferenceSceneError(
            "target uses another renderer family; reference triangle rasterizer does not emulate this hardware"
        )
    payload, source_sha = _scene_path(root, source)
    if set(payload) != {
        "schema", "width", "height", "near", "far", "fov_y_deg", "triangles"
    } or payload["schema"] != SCHEMA:
        raise ReferenceSceneError("unsupported 3D scene contract")
    width, height = payload["width"], payload["height"]
    if type(width) is not int or not 8 <= width <= MAX_RASTER_WIDTH:
        raise ReferenceSceneError("reference rasterizer width exceeds canonical bound")
    if type(height) is not int or not 8 <= height <= MAX_RASTER_HEIGHT:
        raise ReferenceSceneError("reference rasterizer height exceeds canonical bound")
    near = _number(payload["near"], "near")
    far = _number(payload["far"], "far")
    fov = _number(payload["fov_y_deg"], "fov")
    if not 0 < near < far or not 10 <= fov <= 150:
        raise ReferenceSceneError("camera and depth projection invalid")
    rows = payload["triangles"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
        raise ReferenceSceneError("scene must contain 1..4096 original triangles")
    triangles = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
            "object_id", "material", "vertices", "shader", "shader_phase"
        }:
            raise ReferenceSceneError(f"invalid triangle fields at index {i}")
        verts = row["vertices"]
        if not isinstance(verts, list) or len(verts) != 3:
            raise ReferenceSceneError("triangle needs exactly three vertices")
        sampled = []
        for v in verts:
            if not isinstance(v, list) or len(v) != 3:
                raise ReferenceSceneError("each vertex must contain xyz")
            sampled.append(RenderVertex(*[_number(n, "vertex") for n in v]))
        material = row["material"]
        if type(material) is not int or not 0 <= material <= 65535:
            raise ReferenceSceneError("invalid render material")
        object_id = row["object_id"]
        if not isinstance(object_id, str) or not 1 <= len(object_id) <= 64:
            raise ReferenceSceneError("invalid renderer object id")
        shader = row["shader"]
        if not isinstance(shader, str) or shader not in {"fixed", "skinned"}:
            raise ReferenceSceneError("unsupported historical shader mode")
        triangles.append(RenderTriangle(
            object_id=object_id, material=material, vertices=tuple(sampled),
            shader=shader, shader_phase=_number(row["shader_phase"], "phase"),
        ))
    image = render_reference_image(
        triangles, width=width, height=height, near=near, far=far,
        fov_y_deg=fov, pipeline=pipeline,
    )
    if image.frame.stats.rasterized_triangles == 0 or image.frame.stats.covered_pixels == 0:
        raise ReferenceSceneError("raster scene produced no visible triangles")
    rgba = b"".join(image.pixels[i:i+3] + b"\xff"
                    for i in range(0, len(image.pixels), 3))
    encoded = png_rgba(rgba, width, height)
    destination = _path(root, output, must_exist=False)
    candidate = None
    if not dry_run:
        _create_only(destination, encoded)
        from skeleton.developer.jeeves_game_upscale_queue import record_output
        candidate = record_output(
            root, category="3d_reference", source=source, output=output,
            input_sha256=source_sha, output_sha256=hashlib.sha256(encoded).hexdigest(),
            target=policy["target_id"], quality="requires_review",
        )
    return {
        "ok": True, "action": "render-reference", "target": target,
        "pipeline": pipeline.value, "scene_sha256": source_sha,
        "output": output, "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "render_color_sha256": image.frame.color_digest,
        "frame_digest": image.frame.digest,
        "resolution": [width, height],
        "triangle_count": len(triangles),
        "rasterized_triangles": image.frame.stats.rasterized_triangles,
        "covered_pixels": image.frame.stats.covered_pixels,
        "measured_reference_render": True,
        "source_game_assets_originality_requires_review": True,
        "console_hardware_fidelity_qualified": False,
        "production_qualified": False,
        "dry_run": dry_run,
        "training_candidate": candidate,
    }
