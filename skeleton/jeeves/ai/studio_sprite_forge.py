"""Deterministic, original PNG sprite forge from host-reviewed pixel designs.

A weight-bearing Jeeves model may PROPOSE palette/frame data using the existing
creator schema. Only host-authorized persistence promotes it to project source.
This compiler emits actual lossless RGBA PNG bytes and timed animation atlases,
not mock asset references. It requires explicitly authored pixels: no claim of
diffusion, generative-image checkpoint execution or an artist's approval.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import re
import struct
from typing import Any
import zlib

from .studio_interaction_contract import digest, identifier
from .studio_sprite_geometry import (
    AtlasGeometryError, layout_policy, rasterize_atlas,
)

SCHEMA = "skeleton.jeeves.authored_sprite_atlas.v1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLOR = re.compile(r"^#[0-9a-fA-F]{8}$")
MAX_ASSETS = 128
MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 1024 * 1024


class StudioSpriteError(ValueError):
    """Authored image does not satisfy the original lossless asset contract."""


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise StudioSpriteError(name + " is outside sprite authoring bounds")
    return value


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise StudioSpriteError(label + " must have only canonical declared fields")
    return value


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return (
        struct.pack(">I", len(data)) + payload
        + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    )


def _encode_rgba_png(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height * 4:
        raise StudioSpriteError("RGBA surface has inconsistent source dimensions")
    stride = width * 4
    rows = b"".join(
        b"\x00" + pixels[start:start + stride]
        for start in range(0, len(pixels), stride)
    )
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _decode_verified_png(image: bytes, width: int, height: int) -> bytes:
    """Independently reconstruct every source pixel and validate PNG chunks."""
    if not image.startswith(PNG_SIGNATURE):
        raise StudioSpriteError("sprite lacks a real PNG signature")
    at = len(PNG_SIGNATURE)
    chunks = []
    while at < len(image):
        if len(image) - at < 12:
            raise StudioSpriteError("truncated PNG source")
        length = struct.unpack_from(">I", image, at)[0]
        at += 4
        if length > MAX_BYTES or at + length + 8 > len(image):
            raise StudioSpriteError("PNG contains oversized or truncated chunk")
        tag = image[at:at + 4]
        at += 4
        raw = image[at:at + length]
        at += length
        crc = struct.unpack_from(">I", image, at)[0]
        at += 4
        if zlib.crc32(tag + raw) & 0xFFFFFFFF != crc:
            raise StudioSpriteError("sprite PNG CRC differs from authored pixels")
        chunks.append((tag, raw))
        if tag == b"IEND":
            break
    if at != len(image) or [x[0] for x in chunks] != [
        b"IHDR", b"IDAT", b"IEND",
    ]:
        raise StudioSpriteError("sprite PNG contains unknown or inconsistent chunks")
    if chunks[0][1] != struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0):
        raise StudioSpriteError("PNG dimensions or color mode changed")
    expanded_size = height * (width * 4 + 1)
    try:
        inflater = zlib.decompressobj()
        decompressed = inflater.decompress(chunks[1][1], expanded_size + 1)
    except zlib.error as exc:
        raise StudioSpriteError("PNG pixel compression is invalid") from exc
    if (not inflater.eof or inflater.unused_data or inflater.unconsumed_tail
            or len(decompressed) != expanded_size):
        raise StudioSpriteError("PNG pixel stream size differs from authored image")
    stride = width * 4 + 1
    if any(decompressed[offset] != 0 for offset in range(0, len(decompressed), stride)):
        raise StudioSpriteError("PNG uses unsupported per-row transformations")
    return b"".join(
        decompressed[offset + 1:offset + stride]
        for offset in range(0, len(decompressed), stride)
    )


def compile_authored_sprite(record: Mapping[str, Any]) -> dict[str, Any]:
    """Produce one actual spritesheet, metadata and independently checked pixels."""
    if not isinstance(record, Mapping) or record.get("facet") != "sprite_forge":
        raise StudioSpriteError("sprite asset must originate from an approved sprite forge record")
    base_fields = {
        "kind", "asset_id", "width", "height", "palette",
        "frames", "animations", "pixel_scale",
    }
    doc = record.get("document")
    if (not isinstance(doc, dict)
            or set(doc) not in (base_fields, base_fields | {"atlas"})):
        raise StudioSpriteError("sprite document has undeclared or missing source fields")
    if doc["kind"] != "pixel_sprite":
        raise StudioSpriteError("cannot compile unknown sprite asset source kind")
    # The compiler must not promote arbitrary model-supplied metadata as
    # a persisted, versioned original asset. Validate against the SAME
    # exact SHA input used by CreatorProjectSourceStore._documents.
    record_id = identifier(record.get("record_id"), "original game sprite record")
    revision = record.get("revision")
    depends_on = record.get("depends_on")
    if (type(revision) is not int or revision < 1
            or type(depends_on) is not list
            or len(depends_on) > 32
            or any(type(dependency) is not str for dependency in depends_on)):
        raise StudioSpriteError("sprite source lacks reviewed durable revision provenance")
    expected_source = digest([
        record_id, "sprite_forge", revision, doc, depends_on,
    ])
    if record.get("source_sha256") != expected_source:
        raise StudioSpriteError("sprite source content differs from original SQLite revision")
    asset = identifier(doc["asset_id"], "original sprite asset")
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", asset) is None:
        raise StudioSpriteError("sprite file identity must be portable lowercase ASCII")
    width = _integer(doc["width"], "sprite width", 1, 64)
    height = _integer(doc["height"], "sprite height", 1, 64)
    scale = _integer(doc["pixel_scale"], "pixel art integer scale", 1, 8)
    palette = doc["palette"]
    if (type(palette) is not list or not 1 <= len(palette) <= 256
            or any(type(color) is not str or COLOR.fullmatch(color) is None
                   for color in palette)):
        raise StudioSpriteError("sprite requires explicit bounded 8-digit RGBA palette")
    colors = [bytes.fromhex(color[1:]) for color in palette]
    frames = doc["frames"]
    if type(frames) is not list or not 1 <= len(frames) <= 64:
        raise StudioSpriteError("sprite atlas requires 1..64 authored pixel frames")
    ids: set[str] = set()
    frame_meta: list[dict[str, Any]] = []
    for frame_index, candidate in enumerate(frames):
        frame = _exact(candidate, {"frame_id", "duration_ms", "pixels"}, "sprite frame")
        frame_id = identifier(frame["frame_id"], "sprite frame")
        if frame_id in ids:
            raise StudioSpriteError("sprite frame identity repeated")
        ids.add(frame_id)
        duration = _integer(frame["duration_ms"], "frame duration", 10, 60_000)
        frame_meta.append({
            "frame_id": frame_id, "duration_ms": duration,
            "source_order": frame_index,
        })
    try:
        policy = layout_policy(
            doc.get("atlas"), frame_count=len(frames),
            width=width, height=height, scale=scale,
        )
        if policy["extrude_edges"] and any(
            color[3] == 0 and color[:3] != bytes(3) for color in colors
        ):
            raise StudioSpriteError(
                "bleed-safe extrusion requires zero RGB for fully transparent palette entries"
            )
        atlas = rasterize_atlas(
            colors, frames, width=width, height=height, scale=scale,
            policy=policy,
        )
    except AtlasGeometryError as exc:
        raise StudioSpriteError(str(exc)) from exc
    for frame, geometry in zip(frame_meta, atlas["frames"], strict=True):
        frame.update(geometry)
    sheet_width = atlas["sheet_width_px"]
    sheet_height = atlas["sheet_height_px"]

    animations = doc["animations"]
    if type(animations) is not list or not 1 <= len(animations) <= 32:
        raise StudioSpriteError("sprite requires original authored animation states")
    used: set[str] = set()
    animation_meta = []
    for candidate in animations:
        state = _exact(candidate, {"name", "frame_ids", "loop"}, "animation state")
        name = identifier(state["name"], "animation state")
        if name in used:
            raise StudioSpriteError("animation state names must be unique")
        used.add(name)
        sequence = state["frame_ids"]
        if (type(sequence) is not list or not 1 <= len(sequence) <= 256
                or any(type(key) is not str or key not in ids for key in sequence)
                or type(state["loop"]) is not bool):
            raise StudioSpriteError("animation references missing source frames")
        durations = {
            frame["frame_id"]: frame["duration_ms"] for frame in frame_meta
        }
        animation_meta.append({
            "name": name, "frame_ids": list(sequence), "loop": state["loop"],
            "duration_ms": sum(durations[key] for key in sequence),
        })
    surface = atlas["pixels"]
    image = _encode_rgba_png(sheet_width, sheet_height, surface)
    if _decode_verified_png(image, sheet_width, sheet_height) != surface:
        raise StudioSpriteError("independent PNG pixel reconstruction disagrees")
    metadata = {
        "schema_version": SCHEMA,
        "record_id": record.get("record_id"),
        "record_revision": record.get("revision"),
        "source_sha256": record.get("source_sha256"),
        "asset_id": asset, "frame_width_px": width * scale,
        "frame_height_px": height * scale,
        "sheet_width_px": sheet_width, "sheet_height_px": sheet_height,
        "rgba_palette_size": len(colors), "pixel_scale": scale,
        "atlas_geometry": atlas["geometry"],
        "frames": frame_meta, "animations": animation_meta,
        "png_sha256": sha256(image).hexdigest(),
        "pixel_content_sha256": sha256(surface).hexdigest(),
        "pixels_losslessly_verified": True,
        "source_revision_independently_verified": True,
        "generated_with_model_image_weights": False,
        "native_engine_sprite_binding_verified": False,
    }
    metadata["receipt_sha256"] = digest(metadata)
    # An independent verifier samples source pixels from the actual decoded
    # PNG, reconstructs the complete atlas, and checks alpha masks and timing.
    from .studio_sprite_verify import verify_published_sprite
    checked = verify_published_sprite(image, metadata)
    return {
        "png": image, "metadata": metadata,
        "independent_pixel_replay": checked,
    }


def compile_sprite_collection(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Compile every original sprite in an immutable project generation."""
    if not isinstance(records, Mapping) or len(records) > 50_000:
        raise StudioSpriteError("original project source map exceeds sprite scan bound")
    candidates = [
        record for _, record in sorted(records.items())
        if isinstance(record.get("document"), dict)
        and record["document"].get("kind") == "pixel_sprite"
    ]
    if not 1 <= len(candidates) <= MAX_ASSETS:
        raise StudioSpriteError("sprite compilation requires 1..128 original sprite records")
    results = [compile_authored_sprite(item) for item in candidates]
    names = [asset["metadata"]["asset_id"] for asset in results]
    if len(names) != len(set(names)):
        raise StudioSpriteError("separate records claim the same original sprite asset id")
    return {
        "schema_version": SCHEMA,
        "assets": results,
        "count": len(results),
        "atlas_hashes": {
            entry["metadata"]["asset_id"]: entry["metadata"]["png_sha256"]
            for entry in results
        },
    }


__all__ = [
    "StudioSpriteError", "compile_authored_sprite",
    "compile_sprite_collection", "_decode_verified_png",
]
