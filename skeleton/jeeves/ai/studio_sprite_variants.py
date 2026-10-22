"""Exact, signed directional pixel variants from reviewed original sprite frames.

No inferred frames, diffuse upscaling or invisible model-generated repainting:
every optional variant names an already authored source frame and one explicit
lossless geometric transform. Variant pixels and all timing are deterministically
reconstructed, and the reviewer verifies transformations again from the final
decoded image rather than trusting claimed transformation evidence.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from .studio_interaction_contract import digest

TRANSFORMS = frozenset({"flip_horizontal", "flip_vertical", "rotate_180"})
MAX_VARIANTS = 64


class SpriteVariantError(ValueError):
    """Source-defined directional sprite cannot be derived safely."""


def _rgba_digest(frame: Mapping[str, Any], *, colors: list[bytes]) -> str:
    return sha256(b"".join(colors[index] for index in frame["pixels"])).hexdigest()


def _transform_indices(
    indices: list[int], width: int, height: int, mode: str,
) -> list[int]:
    if mode not in TRANSFORMS:
        raise SpriteVariantError("unapproved directional frame transformation")
    return [
        indices[(
            (height - y - 1 if mode in ("flip_vertical", "rotate_180") else y)
            * width
            + (width - x - 1 if mode in ("flip_horizontal", "rotate_180") else x)
        )]
        for y in range(height) for x in range(width)
    ]


def derive_original_sprite_variants(
    document: Mapping[str, Any], *,
    colors: list[bytes], width: int, height: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return source + new exact frames, and cross-checkable variant receipts.

    Newly generated frames must refer to one of the ORIGINAL source frames.
    Variants cannot target one another, avoiding transform-loop and order risks.
    """
    originals = document.get("frames")
    values = document.get("variants", [])
    if type(originals) is not list or type(values) is not list:
        raise SpriteVariantError("original sprites and variants must be explicit arrays")
    if len(values) > MAX_VARIANTS or len(originals) + len(values) > 64:
        raise SpriteVariantError("derived frames exceed bounded sprite atlas budget")
    sources: dict[str, dict[str, Any]] = {}
    for frame in originals:
        if (not isinstance(frame, dict) or set(frame) != {
                "frame_id", "duration_ms", "pixels",
            } or type(frame["frame_id"]) is not str
                or frame["frame_id"] in sources or type(frame["pixels"]) is not list
                or len(frame["pixels"]) != width * height
                or any(type(index) is not int or not 0 <= index < len(colors)
                       for index in frame["pixels"])):
            raise SpriteVariantError("directional variants require reviewed full source pixels")
        sources[frame["frame_id"]] = frame
    if len(sources) != len(originals):
        raise SpriteVariantError("duplicate original frame identities")
    derived: list[dict[str, Any]] = []
    proofs: list[dict[str, Any]] = []
    used = set(sources)
    for variant in values:
        if not isinstance(variant, dict) or set(variant) != {
            "frame_id", "source_frame_id", "transform", "duration_ms",
        }:
            raise SpriteVariantError("derived frame requires exact geometry, source and timing")
        frame_id = variant["frame_id"]
        parent_id = variant["source_frame_id"]
        mode = variant["transform"]
        duration = variant["duration_ms"]
        if (type(frame_id) is not str or not frame_id or len(frame_id) > 64
                or any(not (c.isascii() and (c.isalnum() or c in "-_")) for c in frame_id)
                or frame_id in used):
            raise SpriteVariantError("derived frame identity must be unique portable ASCII")
        if type(parent_id) is not str or parent_id not in sources:
            raise SpriteVariantError("variant source must be an original authored frame")
        if mode not in TRANSFORMS:
            raise SpriteVariantError("unknown or lossy sprite frame transform")
        if type(duration) is not int or not 10 <= duration <= 60_000:
            raise SpriteVariantError("directional animation requires authored frame duration")
        parent = sources[parent_id]
        new_indices = _transform_indices(parent["pixels"], width, height, mode)
        generated = {
            "frame_id": frame_id,
            "duration_ms": duration,
            "pixels": new_indices,
        }
        proof = {
            "frame_id": frame_id,
            "source_frame_id": parent_id,
            "transform": mode,
            "source_rgba_sha256": _rgba_digest(parent, colors=colors),
            "derived_rgba_sha256": _rgba_digest(generated, colors=colors),
            "pixel_geometry_preserved": True,
            "artwork_generated_using_model": False,
        }
        proof["receipt_sha256"] = digest(proof)
        proofs.append(proof)
        derived.append(generated)
        used.add(frame_id)
    return [*originals, *derived], proofs


def verify_directional_rgba_variants(
    frame_pixels: Mapping[str, bytes], *,
    width: int, height: int, proofs: list[dict[str, Any]],
) -> int:
    """Independent output verification against decoded source and variant bytes."""
    if type(proofs) is not list or len(proofs) > MAX_VARIANTS:
        raise SpriteVariantError("source proof list exceeds bounded variants")
    found: set[str] = set()
    for proof in proofs:
        if not isinstance(proof, dict) or set(proof) != {
            "frame_id", "source_frame_id", "transform",
            "source_rgba_sha256", "derived_rgba_sha256",
            "pixel_geometry_preserved", "artwork_generated_using_model",
            "receipt_sha256",
        }:
            raise SpriteVariantError("directional output proof has invalid schema")
        signed = dict(proof)
        attested = signed.pop("receipt_sha256")
        if (attested != digest(signed)
                or proof["pixel_geometry_preserved"] is not True
                or proof["artwork_generated_using_model"] is not False):
            raise SpriteVariantError("directional source evidence was altered")
        name = proof["frame_id"]
        parent = proof["source_frame_id"]
        mode = proof["transform"]
        if (name in found or name == parent or parent not in frame_pixels
                or name not in frame_pixels or mode not in TRANSFORMS):
            raise SpriteVariantError("directional variant has missing or reused source pixels")
        orig, derived = frame_pixels[parent], frame_pixels[name]
        if len(orig) != width * height * 4 or len(derived) != len(orig):
            raise SpriteVariantError("directional frame byte geometry is incompatible")
        pixels = [
            orig[i:i + 4] for i in range(0, len(orig), 4)
        ]
        transformed = b"".join(
            pixels[i] for i in _transform_indices(
                list(range(width * height)), width, height, mode,
            )
        )
        if (transformed != derived
                or sha256(orig).hexdigest() != proof["source_rgba_sha256"]
                or sha256(derived).hexdigest() != proof["derived_rgba_sha256"]):
            raise SpriteVariantError("sprite direction pixels differ from authored transform")
        found.add(name)
    return len(found)


__all__ = [
    "SpriteVariantError", "TRANSFORMS",
    "derive_original_sprite_variants", "verify_directional_rgba_variants",
]
