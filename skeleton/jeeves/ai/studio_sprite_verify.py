"""Independent, source-reconstructing verification of completed pixel atlases.

The verifier is deliberately separate from the PNG producer. It decodes actual
RGBA image bytes, reconstructs each source palette frame from atlas pixels,
re-packs all padding and gutter pixels, checks alpha collision bit masks,
per-frame content, pivots, bounds, timing and all metadata digests. This is
an output-integrity proof, not a substitute for source-authorship review.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import re

from .studio_interaction_contract import digest
from .studio_sprite_geometry import AtlasGeometryError, rasterize_atlas
from .studio_sprite_forge import (
    StudioSpriteError, _decode_verified_png, PNG_SIGNATURE,
)

SHA = re.compile(r"^[0-9a-f]{64}$")


class SpriteVerificationError(ValueError):
    """Real emitted sprite pixels differ from declared original asset evidence."""


def verify_published_sprite(
    image: bytes, metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Full pixel replay including transparent gutters and frame collision masks."""
    if not isinstance(metadata, Mapping):
        raise SpriteVerificationError("typed original sprite receipt required")
    if type(image) is not bytes or not image.startswith(PNG_SIGNATURE):
        raise SpriteVerificationError("published sprite is not genuine PNG bytes")
    if len(image) > 16 * 1024 * 1024:
        raise SpriteVerificationError("published PNG exceeds absolute verification budget")
    body = dict(metadata)
    receipt = body.pop("receipt_sha256", None)
    if (not isinstance(receipt, str) or SHA.fullmatch(receipt) is None
            or digest(body) != receipt
            or metadata.get("schema_version") !=
            "skeleton.jeeves.authored_sprite_atlas.v1"):
        raise SpriteVerificationError("original sprite metadata ancestry changed")
    dimensions = (
        metadata.get("sheet_width_px"), metadata.get("sheet_height_px"),
    )
    if (any(type(n) is not int or not 1 <= n <= 8192 for n in dimensions)
            or dimensions[0] * dimensions[1] > 1024 * 1024):
        raise SpriteVerificationError("atlas dimensions exceed verified GPU limits")
    if sha256(image).hexdigest() != metadata.get("png_sha256"):
        raise SpriteVerificationError("sprite file hash differs from the original receipt")
    from .studio_sprite_quality_metrics import sprite_quality_metrics
    if sprite_quality_metrics(metadata) != metadata.get("objective_quality"):
        raise SpriteVerificationError("sprite quality signals or score differ from pixel evidence")
    try:
        pixels = _decode_verified_png(image, *dimensions)
    except (StudioSpriteError, ValueError, TypeError) as exc:
        raise SpriteVerificationError("published PNG image is not an exact readable RGBA image") from exc
    if sha256(pixels).hexdigest() != metadata.get("pixel_content_sha256"):
        raise SpriteVerificationError("actual RGBA bytes differ from original receipt")
    frames = metadata.get("frames")
    animations = metadata.get("animations")
    geom = metadata.get("atlas_geometry")
    scale = metadata.get("pixel_scale")
    fw = metadata.get("frame_width_px")
    fh = metadata.get("frame_height_px")
    if (type(scale) is not int or not 1 <= scale <= 8
            or type(fw) is not int or type(fh) is not int
            or fw < scale or fh < scale or fw % scale or fh % scale
            or not isinstance(geom, dict) or type(frames) is not list
            or not 1 <= len(frames) <= 64 or type(animations) is not list):
        raise SpriteVerificationError("invalid sprite layout or animation metadata")
    width, height = fw // scale, fh // scale
    if width > 64 or height > 64:
        raise SpriteVerificationError("original frame dimensions exceed sprite policy")
    required_geom = {
        "columns", "rows", "cell_width_px", "cell_height_px",
        "padding_px", "extrude_edges", "power_of_two",
        "alpha_threshold", "source_pivot_px", "unused_trailing_cells",
        "nearest_neighbor_preserved", "alpha_encoding",
    }
    if set(geom) != required_geom or geom["nearest_neighbor_preserved"] is not True:
        raise SpriteVerificationError("original atlas policies lack exact source identity")
    palette: list[bytes] = []
    index_of: dict[bytes, int] = {}
    recovered = []
    stride = dimensions[0] * 4
    for original in frames:
        if not isinstance(original, dict):
            raise SpriteVerificationError("source frame evidence has wrong type")
        rect = original.get("rect_px")
        if (type(rect) is not list or len(rect) != 4
                or any(type(x) is not int for x in rect)
                or rect[2:] != [fw, fh]
                or rect[0] < 0 or rect[1] < 0
                or rect[0] + fw > dimensions[0]
                or rect[1] + fh > dimensions[1]):
            raise SpriteVerificationError("original sprite frame rectangle lies outside PNG")
        source_pixels: list[int] = []
        for y in range(height):
            for x in range(width):
                pos = (rect[1] + y * scale) * stride + (rect[0] + x * scale) * 4
                rgba = pixels[pos:pos + 4]
                if rgba not in index_of:
                    if len(palette) >= 256:
                        raise SpriteVerificationError("too many distinct source RGBA palette colors")
                    index_of[rgba] = len(palette)
                    palette.append(rgba)
                source_pixels.append(index_of[rgba])
        recovered.append({"pixels": source_pixels})
    # Re-check directional variants from REAL emitted frame pixels, not from
    # caller-supplied claims. Authored originals must precede all variants.
    from .studio_sprite_variants import (
        SpriteVariantError, verify_directional_rgba_variants,
    )
    proofs = metadata.get("derived_frame_proofs", [])
    original_count = metadata.get("original_authored_frame_count", len(frames))
    if (type(original_count) is not int
            or not 1 <= original_count <= len(frames)
            or type(proofs) is not list
            or len(proofs) != len(frames) - original_count):
        raise SpriteVerificationError("directional sprite source lineage is incomplete")
    frames_rgba = {
        frame["frame_id"]: b"".join(palette[i] for i in item["pixels"])
        for frame, item in zip(frames, recovered, strict=True)
    }
    if len(frames_rgba) != len(frames):
        raise SpriteVerificationError("duplicate frame identity breaks direction replay")
    try:
        verified_variants = verify_directional_rgba_variants(
            frames_rgba, width=width, height=height, proofs=proofs,
        )
    except SpriteVariantError as exc:
        raise SpriteVerificationError("directional source transform differs from actual pixels") from exc
    if verified_variants != len(proofs) or any(
        item["source_frame_id"] not in {
            frame["frame_id"] for frame in frames[:original_count]
        } for item in proofs
    ) or {
        item["frame_id"] for item in proofs
    } != {
        frame["frame_id"] for frame in frames[original_count:]
    }:
        raise SpriteVerificationError("derived frames are not bound to original authoring")
    try:
        spec = {
            "columns": geom["columns"], "padding_px": geom["padding_px"],
            "extrude_edges": geom["extrude_edges"],
            "power_of_two": geom["power_of_two"],
            "alpha_threshold": geom["alpha_threshold"],
            "pivot_px": geom["source_pivot_px"],
        }
        # The independent rasterizer must also independently validate every
        # layout field before it can be used as a proof.
        from .studio_sprite_geometry import layout_policy
        spec = layout_policy(
            spec, frame_count=len(frames),
            width=width, height=height, scale=scale,
        )
        replay = rasterize_atlas(
            palette, recovered, width=width, height=height,
            scale=scale, policy=spec,
        )
    except (AtlasGeometryError, KeyError, TypeError, ValueError) as exc:
        raise SpriteVerificationError("declared atlas policies cannot reconstruct pixels") from exc
    if (replay["pixels"] != pixels
            or replay["sheet_width_px"] != dimensions[0]
            or replay["sheet_height_px"] != dimensions[1]
            or replay["geometry"] != geom):
        raise SpriteVerificationError(
            "original bitmap, sprite layout or anti-bleed padding differs from output"
        )
    for index, (actual, regenerated) in enumerate(zip(frames, replay["frames"], strict=True)):
        for field in regenerated:
            if actual.get(field) != regenerated[field]:
                raise SpriteVerificationError(
                    "sprite alpha/hitbox/frame evidence differs at position " + str(index)
                )
        if (actual.get("source_order") != index
                or type(actual.get("duration_ms")) is not int
                or not 10 <= actual["duration_ms"] <= 60_000):
            raise SpriteVerificationError("original frame ordering or duration invalid")
    ids = [frame.get("frame_id") for frame in frames]
    if len(set(ids)) != len(ids):
        raise SpriteVerificationError("duplicate original frame identity")
    if not 1 <= len(animations) <= 32:
        raise SpriteVerificationError("animation catalogue requires reviewed finite states")
    for state in animations:
        if not isinstance(state, dict):
            raise SpriteVerificationError("original animation state must be an object")
        keys = state.get("frame_ids")
        if (not isinstance(keys, list) or not 1 <= len(keys) <= 256
                or any(key not in ids for key in keys)
                or type(state.get("loop")) is not bool):
            raise SpriteVerificationError("animation refers to nonexistent original frames")
        durations = {frame["frame_id"]: frame["duration_ms"] for frame in frames}
        if sum(durations[key] for key in keys) != state.get("duration_ms"):
            raise SpriteVerificationError("animation duration differs from source timeline")
    body = {
        "schema_version": "skeleton.jeeves.sprite_pixel_replay.v1",
        "asset_id": metadata.get("asset_id"),
        "sprite_receipt_sha256": receipt,
        "png_sha256": sha256(image).hexdigest(),
        "decoded_rgba_sha256": sha256(pixels).hexdigest(),
        "source_frames_verified": len(frames),
        "animation_states_verified": len(animations),
        "collision_masks_verified": len(frames),
        "lossless_directional_variants_verified": verified_variants,
        "layout_and_padding_reproduced": True,
        "native_renderer_executed": False,
    }
    body["receipt_sha256"] = digest(body)
    return body


__all__ = ["SpriteVerificationError", "verify_published_sprite"]
