"""Jeeves faithful pixel-asset upscaling over the existing console asset codec.

Implements real integer-scale nearest-neighbor and Scale2x/EPX primitives.
Historical style, aspect-ratio, and display intent remain explicit. This is
NOT a 3D/AI super-resolution engine or a claim of native console support.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

MAX_PIXELS = 1024 * 1024
MAX_INPUT = 1024 * 1024
PIXEL_MODES = frozenset({"nearest", "scale2x"})
SCHEMA = "skeleton.game.fidelity_upscale.v1"


class UpscaleError(ValueError):
    pass


def _path(root: Path, relative: str, *, must_exist: bool) -> Path:
    from skeleton.developer.game_cli import _load
    _load(root)
    if not isinstance(relative, str) or len(relative) > 256 or "\\" in relative:
        raise UpscaleError("unsafe asset path")
    parts = relative.split("/")
    path = PurePosixPath(relative)
    if len(parts) < 2 or parts[0] != "assets" or path.is_absolute() or any(
        p in {"", ".", ".."} for p in parts
    ) or not path.name.lower().endswith(".png"):
        raise UpscaleError("upscaling requires a PNG under project assets/")
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise UpscaleError("symlinked asset path forbidden")
    if must_exist and (not target.is_file() or target.stat().st_size > MAX_INPUT):
        raise UpscaleError("input PNG missing or over bounded codec size")
    if not must_exist and target.exists():
        raise UpscaleError("destination exists: never overwrite an approved asset")
    return target


def _nearest(pixels: bytes, width: int, height: int, factor: int) -> bytes:
    row_bytes = width * 4
    out = bytearray()
    for y in range(height):
        row = pixels[y * row_bytes:(y + 1) * row_bytes]
        expanded = b"".join(row[x:x+4] * factor for x in range(0, row_bytes, 4))
        out.extend(expanded * factor)
    return bytes(out)


def _scale2x(pixels: bytes, width: int, height: int) -> bytes:
    """Classic edge-aware EPX conditional replication, no fabricated colors."""
    out = bytearray(width * height * 16)
    width2 = width * 2
    def px(x: int, y: int) -> bytes:
        offset = (y * width + x) * 4
        return pixels[offset:offset+4]
    for y in range(height):
        for x in range(width):
            e = px(x,y)
            b = px(x,y-1) if y > 0 else e
            d = px(x-1,y) if x > 0 else e
            f = px(x+1,y) if x + 1 < width else e
            h = px(x,y+1) if y + 1 < height else e
            if b != h and d != f:
                e0 = d if d == b else e
                e1 = f if b == f else e
                e2 = d if d == h else e
                e3 = f if h == f else e
            else:
                e0 = e1 = e2 = e3 = e
            p = (y * 2 * width2 + x * 2) * 4
            out[p:p+8] = e0 + e1
            q = p + width2 * 4
            out[q:q+8] = e2 + e3
    return bytes(out)


def _expand(pixels: bytes, w: int, h: int, factor: int, mode: str) -> bytes:
    if mode == "nearest":
        return _nearest(pixels, w, h, factor)
    if factor not in {2, 4}:
        raise UpscaleError("Scale2x supports 2x or two-pass 4x; choose nearest otherwise")
    buffer = _scale2x(pixels, w, h)
    if factor == 4:
        buffer = _scale2x(buffer, w * 2, h * 2)
    return buffer


def _policy(target_id: str) -> dict[str, Any]:
    from skeleton.jeeves.game_console_catalog import resolve_console
    from skeleton.jeeves.game_engine_lab import ERA_PROFILES
    target = resolve_console(target_id)
    profile = ERA_PROFILES[target.era]
    pixel_eras = {"pong_discrete_1972", "vector_sprite_1977",
                  "eight_bit_tile_1983", "sixteen_bit_raster_1989"}
    is_pixel = target.era.value in pixel_eras
    return {
        "target_id": target.target_id,
        "era": target.era.value,
        "render_path": profile.render_path,
        "historical_tick_hz": profile.tick_hz,
        "pixel_pipeline": is_pixel,
        "recommended_mode": "nearest" if is_pixel else "nearest",
        "art_direction_rules": (
            ["preserve_original_palette", "integer_scale_only",
             "no_blur", "source_grid_aligned", "respect_original_aspect_ratio"]
            if is_pixel else
            ["preserve_authoring_style", "preserve_texture_silhouette",
             "resample_only_existing_pixels", "do_not_claim_mesh_enhancement"]
        ),
        "native_hardware_qualified": False,
        "original_game_engine_qualified": False,
        "GPU_acceleration": False,
        "model_super_resolution": False,
    }


def upscale(root: Path, *, source: str, output: str, target: str,
            mode: str = "nearest", factor: int = 2,
            dry_run: bool = False) -> dict[str, Any]:
    if type(factor) is not int or factor < 1 or factor > 8:
        raise UpscaleError("factor must be an integer between 1 and 8 per bounded pass")
    if mode not in PIXEL_MODES:
        raise UpscaleError("unknown fidelity upscaling mode")
    if type(dry_run) is not bool:
        raise UpscaleError("dry_run must be boolean")
    if mode == "scale2x" and factor not in (2, 4):
        raise UpscaleError("Scale2x requires 2x or 4x")
    policy = _policy(target)
    input_path = _path(root, source, must_exist=True)
    dest = _path(root, output, must_exist=False)
    if input_path == dest:
        raise UpscaleError("source and destination must differ")
    from skeleton.jeeves.game_console_assets import decode_png, png_rgba
    from skeleton.developer.jeeves_game_authoring import _create_only
    raw = input_path.read_bytes()
    w, h, pixels = decode_png(raw)
    if w * h * factor * factor > MAX_PIXELS:
        raise UpscaleError("render would exceed the canonical PNG pixel budget; use tiled passes")
    scaled = _expand(pixels, w, h, factor, mode)
    # RGB(A) values can move to new positions but no colors are generated.
    palette_in = {pixels[i:i+4] for i in range(0, len(pixels), 4)}
    palette_out = {scaled[i:i+4] for i in range(0, len(scaled), 4)}
    if not palette_out.issubset(palette_in):
        raise UpscaleError("upscaler created unapproved palette values")
    encoded = png_rgba(scaled, w * factor, h * factor)
    sha_in = hashlib.sha256(raw).hexdigest()
    sha_out = hashlib.sha256(encoded).hexdigest()
    if not dry_run:
        _create_only(dest, encoded)
    return {
        "ok": True, "action": "upscale", "schema": SCHEMA,
        "source": source, "output": output, "input_sha256": sha_in,
        "output_sha256": sha_out,
        "dimensions_in": [w, h], "dimensions_out": [w * factor, h * factor],
        "mode": mode, "factor": factor,
        "source_palette_size": len(palette_in),
        "output_palette_size": len(palette_out),
        "no_new_colors": True,
        "source_unchanged": input_path.read_bytes() == raw,
        "target_policy": policy, "dry_run": dry_run,
        "style_fidelity_static_checks": True,
        "native_console_quality_verified": False,
        "subjective_fidelity_verified": False,
        "production_qualified": False,
    }


def fidelity_plan(target: str) -> dict[str, Any]:
    return {"ok": True, "action": "fidelity-plan",
            "schema": SCHEMA, **_policy(target),
            "techniques": ["integer-nearest", "scale2x-edge-aware"],
            "resolution_limits": "canonical PNG 1M pixel bound per local pass; tiled jobs required above it",
            "preserve_original_aesthetics": True,
            "HD_upgrade_without_source_replacement": True,
            "full_era_console_rendering": False}



def fidelity_matrix() -> dict[str, Any]:
    """Inspect ALL currently declared canonical console targets, no invented cores.

    Source adaptation is not a native executable renderer. If a target is
    absent, not runnable or unqualified, emit its gap rather than substitute
    another console's renderer or call a reference simulator a hardware test.
    """
    from skeleton.jeeves.game_console_catalog import console_catalog
    from skeleton.jeeves.game_engine_lab import ERA_PROFILES, EngineEra
    targets = console_catalog()
    records = []
    ids: set[str] = set()
    by_era: dict[str, dict[str, int]] = {}
    for target in targets:
        ident = target["target_id"]
        if not isinstance(ident, str) or ident in ids:
            raise UpscaleError("duplicate or malformed console registry identity")
        ids.add(ident)
        era = target["engine_era"]
        try:
            profile = ERA_PROFILES[EngineEra(era)]
        except (KeyError, ValueError) as exc:
            raise UpscaleError("unknown canonical render-era identity") from exc
        pixel = era in {"pong_discrete_1972", "vector_sprite_1977",
                        "eight_bit_tile_1983", "sixteen_bit_raster_1989"}
        kind = str(target.get("runtime_kind") or "unspecified")
        caps = target.get("capabilities") or {}
        ready = target.get("readiness") or {}
        row = {
            "target_id": ident, "era": era,
            "generation": target.get("generation_id"),
            "render_path": profile.render_path,
            "runtime_kind": kind,
            "reference_simulator": bool(target.get("reference_supported")),
            "native_source_or_emulator_status": (
                ready.get("status") if isinstance(ready, dict) else "unknown"
            ),
            "declared_hardware_emulation": bool(target.get("full_hardware_emulation")),
            "actual_framebuffer_supported": (
                caps.get("actual_framebuffer") is True if isinstance(caps, dict) else False
            ),
            "implemented_pixel_upscale": True,
            "upscale_kind": "native_grid_integer_and_scale2x" if pixel else "texture_pixel_resampling_only",
            "original_game_native_rendering_qualified": False,
            "cross_console_visual_parity_verified": False,
            "upscaling_quality_verified": False,
            "missing_qualifications": [
                "original_game_full_renderer",
                "native_target_export_and_install",
                "console_specific_pixel_aspect_and_display_tests",
                "quality_against_independently_sourced_period_references",
                "sustained_playthrough_and_frame_timings",
            ],
        }
        by_era.setdefault(era, {"declared": 0, "production_qualified": 0})
        by_era[era]["declared"] += 1
        records.append(row)
    return {
        "ok": True, "action": "fidelity-matrix", "schema": SCHEMA,
        "declared_console_targets": len(records),
        "engine_eras": len(by_era), "by_era": by_era,
        "targets": records,
        "missing_native_production_qualifications": len(records),
        "any_console_fully_certified_by_this_tool": False,
        "catalogue_complete_for_all_historical_hardware": False,
        "reason": "A console registration, editor or emulation candidate is not full native game creation/rendering capability",
    }
