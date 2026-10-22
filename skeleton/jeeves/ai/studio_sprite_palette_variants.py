"""Rights- and source-bound palette skin compiler for original sprites.

Produces *real* lossless color variants of author-approved source pixels.
Every change is an explicit RGBA->RGBA mapping; no inference, fake new frames,
silent transparency edits or unsupported claims of independent art creation.
The source/variant records both keep real SQLite revision SHA identities.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import re
from typing import Any

from .studio_interaction_contract import digest
from .studio_sprite_forge import compile_authored_sprite

_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{8}$")
VARIANT_FIELDS = frozenset({
    "kind", "asset_id", "parent_record_id", "color_map",
})
SCHEMA = "skeleton.jeeves.original_sprite_palette_variant.v1"


class SpritePaletteVariantError(ValueError):
    """Palette variant lacks exact reviewed original source or pixel equivalence."""


def _reviewed_identity(record: Mapping[str, Any], *, kind: str) -> None:
    if (not isinstance(record, Mapping) or record.get("facet") != "sprite_forge"
            or not isinstance(record.get("document"), dict)
            or record["document"].get("kind") != kind):
        raise SpritePaletteVariantError("original palette variant needs reviewed sprite source")
    record_id = record.get("record_id")
    revision = record.get("revision")
    deps = record.get("depends_on")
    if (type(record_id) is not str or not record_id
            or type(revision) is not int or revision < 1
            or type(deps) is not list
            or any(type(x) is not str for x in deps)
            or len(deps) > 32):
        raise SpritePaletteVariantError("palette skin record has invalid source revision")
    if digest([record_id, "sprite_forge", revision, record["document"], deps]) != record.get("source_sha256"):
        raise SpritePaletteVariantError("palette variant source hash differs from durable revision")


def compile_original_palette_variant(
    original: Mapping[str, Any], variant: Mapping[str, Any],
) -> dict[str, Any]:
    """Generate color-swapped PNG+metadata, independently checking each RGBA source."""
    _reviewed_identity(original, kind="pixel_sprite")
    _reviewed_identity(variant, kind="sprite_palette_variant")
    doc = variant["document"]
    if set(doc) != VARIANT_FIELDS or doc["parent_record_id"] != original["record_id"]:
        raise SpritePaletteVariantError("variant must name one exact original sprite record")
    if original["record_id"] not in variant["depends_on"]:
        raise SpritePaletteVariantError("variant must depend on its real source record")
    asset_id = doc["asset_id"]
    parent_name = original["document"].get("asset_id")
    if (type(asset_id) is not str or _ID.fullmatch(asset_id) is None
            or asset_id == parent_name):
        raise SpritePaletteVariantError("palette skin needs a distinct portable original asset ID")
    changes = doc["color_map"]
    source_palette = original["document"]["palette"]
    if (not isinstance(changes, dict) or not 1 <= len(changes) <= 256
            or type(source_palette) is not list
            or any(type(old) is not str or _COLOR.fullmatch(old) is None
                   or type(new) is not str or _COLOR.fullmatch(new) is None
                   for old, new in changes.items())):
        raise SpritePaletteVariantError("palette mapping must explicitly map hexadecimal RGBA colors")
    palette_by_color = {
        color.casefold(): index for index, color in enumerate(source_palette)
    }
    if len(palette_by_color) != len(source_palette):
        raise SpritePaletteVariantError("ambiguous repeated original RGBA palette color")
    normalized = {old.casefold(): new.casefold() for old, new in changes.items()}
    if len(normalized) != len(changes) or not set(normalized) <= set(palette_by_color):
        raise SpritePaletteVariantError("variant attempts to replace absent or duplicate palette colors")
    new_palette = [color.casefold() for color in source_palette]
    for old, new in sorted(normalized.items()):
        if old == new:
            raise SpritePaletteVariantError("palette skin cannot claim an unchanged color")
        if int(old[7:9], 16) != int(new[7:9], 16):
            raise SpritePaletteVariantError("palette skin cannot change authored sprite collision alpha")
        if new[7:9] == "00" and new[1:7] != "000000":
            raise SpritePaletteVariantError("fully transparent skin pixels must keep zero RGB")
        new_palette[palette_by_color[old]] = new
    updated = deepcopy(original["document"])
    updated["asset_id"] = asset_id
    updated["palette"] = new_palette
    # This is a synthetic compilation representation, NOT a fabricated
    # persisted authoring record. The derived original variant record is
    # carried separately, and its exact source SHA is used in the receipts.
    compiled_id = variant["record_id"]
    canonical_source = {
        "record_id": compiled_id,
        "facet": "sprite_forge",
        "revision": variant["revision"],
        "depends_on": list(variant["depends_on"]),
        "document": updated,
    }
    canonical_source["source_sha256"] = digest([
        compiled_id, "sprite_forge", variant["revision"],
        updated, canonical_source["depends_on"],
    ])
    base = compile_authored_sprite(original)
    derived = compile_authored_sprite(canonical_source)
    source_frames = base["metadata"]["frames"]
    derived_frames = derived["metadata"]["frames"]
    if (len(source_frames) != len(derived_frames)
            or any(
                source["collision_mask_sha256"] != target["collision_mask_sha256"]
                or source["collision_mask_bits_hex"] != target["collision_mask_bits_hex"]
                or source["rect_px"] != target["rect_px"]
                or source["duration_ms"] != target["duration_ms"]
                for source, target in zip(source_frames, derived_frames, strict=True)
            )
            or base["metadata"]["animations"] != derived["metadata"]["animations"]):
        raise SpritePaletteVariantError(
            "palette skin alters collision, animation timing or original geometry"
        )
    proof = {
        "schema_version": SCHEMA,
        "asset_id": asset_id,
        "base_asset_id": parent_name,
        "original_source_record_id": original["record_id"],
        "original_source_revision_sha256": original["source_sha256"],
        "variant_source_record_id": variant["record_id"],
        "variant_source_revision_sha256": variant["source_sha256"],
        "derived_compile_source_sha256": canonical_source["source_sha256"],
        "source_png_sha256": base["metadata"]["png_sha256"],
        "derived_png_sha256": derived["metadata"]["png_sha256"],
        "explicit_color_map": normalized,
        "unchanged_collision_masks_verified": True,
        "unchanged_frame_timings_verified": True,
        "model_repaint_performed": False,
        "independent_creative_review_performed": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return {
        **derived, "palette_variant_receipt": proof,
    }


def compile_original_palette_collection(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    from .studio_sprite_forge import compile_sprite_collection
    owned = compile_sprite_collection(records)
    base = [
        (record_id, record) for record_id, record in sorted(records.items())
        if isinstance(record.get("document"), dict)
        and record["document"].get("kind") == "pixel_sprite"
    ]
    bases = dict(base)
    outputs = list(owned["assets"])
    for record_id, record in sorted(records.items()):
        doc = record.get("document")
        if not isinstance(doc, dict) or doc.get("kind") != "sprite_palette_variant":
            continue
        original = bases.get(doc.get("parent_record_id"))
        if original is None:
            raise SpritePaletteVariantError("skin references a nonexistent original sprite")
        if len(outputs) >= 128:
            raise SpritePaletteVariantError("skin collection exceeds bounded game atlas count")
        outputs.append(compile_original_palette_variant(original, record))
    names = [entry["metadata"]["asset_id"] for entry in outputs]
    if len(set(names)) != len(names):
        raise SpritePaletteVariantError("variant output collides with an original asset name")
    return {
        "schema_version": SCHEMA,
        "assets": outputs, "count": len(outputs),
        "atlas_hashes": {
            entry["metadata"]["asset_id"]: sha256(entry["png"]).hexdigest()
            for entry in outputs
        },
        "palette_variant_receipts": [
            entry["palette_variant_receipt"] for entry in outputs
            if "palette_variant_receipt" in entry
        ],
    }


__all__ = [
    "SpritePaletteVariantError", "compile_original_palette_variant",
    "compile_original_palette_collection",
]
