"""Deterministic original-asset descriptors and searchable studio catalogue.

2026-facing descriptor format for exportable game assets: JSON-first,
content-addressed, explicit author semantics, byte-measured rendering/audio
properties, rights *assertions* (never automatic legal clearance), accessibility,
engine targeting, bounded deterministic retrieval and portable glTF extras.
This is metadata for real compiler outputs, not an image/audio understanding model.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import re
import struct
from typing import Any

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.asset_descriptor.v2"
CATALOG_SCHEMA = "skeleton.jeeves.asset_catalog.v2"
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ASSETS = 192
MAX_LABEL = 128
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
TAG = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
LOCALE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
RIGHTS = frozenset({
    "not_reviewed", "self_authored_asserted", "third_party_permission_asserted",
    "public_domain_asserted",
})
ROLE = frozenset({
    "character", "npc", "terrain", "environment", "prop", "item", "ui",
    "vfx", "tile", "cinematic", "ambience", "music", "dialogue", "sfx", "other",
})
OVERLAY_KEYS = frozenset({
    "kind", "target_record_id", "target_asset_id", "title", "description",
    "alt_text", "tags", "roles", "locale", "rights_status", "attribution",
})


class AssetDescriptorError(ValueError):
    """Asset descriptors cannot be justified from the retained source bytes."""


def _json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise AssetDescriptorError("descriptor must be finite JSON") from exc


def _text(value: Any, name: str, *, maximum: int, blank: bool = False) -> str:
    if (type(value) is not str or len(value) > maximum
            or (not blank and not value.strip())
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise AssetDescriptorError(name + " must be bounded printable text")
    return value


def _list(value: Any, name: str, allowed: frozenset[str] | None,
          limit: int) -> list[str]:
    if (type(value) is not list or len(value) > limit
            or any(type(part) is not str or not TAG.fullmatch(part)
                   for part in value)
            or len(set(value)) != len(value)
            or (allowed is not None and any(part not in allowed for part in value))):
        raise AssetDescriptorError(name + " requires unique portable semantic labels")
    return sorted(value)


def _hex(value: Any, name: str) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise AssetDescriptorError(name + " requires SHA-256")
    return value


def _review_overlay(record: Mapping[str, Any]) -> dict[str, Any]:
    """Never accept AI-generated narrative without persisted source identity."""
    if (not isinstance(record, Mapping) or record.get("facet") != "asset_forge"
            or type(record.get("document")) is not dict):
        raise AssetDescriptorError("asset descriptor needs reviewed asset_forge source")
    doc = record["document"]
    if set(doc) != OVERLAY_KEYS or doc["kind"] != "asset_descriptor":
        raise AssetDescriptorError("asset descriptor source schema is incomplete")
    record_id = record.get("record_id")
    if type(record_id) is not str or not ID.fullmatch(record_id):
        raise AssetDescriptorError("descriptor source ID is not portable")
    if type(record.get("revision")) is not int or record["revision"] < 1:
        raise AssetDescriptorError("descriptor revision must be positive")
    deps = record.get("depends_on")
    if (type(deps) is not list or doc["target_record_id"] not in deps
            or len(deps) > 32 or len(set(deps)) != len(deps)
            or any(type(x) is not str for x in deps)):
        raise AssetDescriptorError("descriptor must explicitly depend on target")
    for field in ("target_record_id", "target_asset_id"):
        if type(doc[field]) is not str or not ID.fullmatch(doc[field]):
            raise AssetDescriptorError("descriptor references an unsafe asset identity")
    for field, limit in (("title", 120), ("description", 1400),
                         ("alt_text", 512), ("attribution", 320)):
        _text(doc[field], field, maximum=limit, blank=field in ("alt_text", "attribution"))
    _list(doc["tags"], "tags", None, 24)
    _list(doc["roles"], "roles", ROLE, 12)
    if type(doc["locale"]) is not str or not LOCALE.fullmatch(doc["locale"]):
        raise AssetDescriptorError("descriptor locale requires a BCP-47 language code")
    if doc["rights_status"] not in RIGHTS:
        raise AssetDescriptorError("rights assertion is outside reviewed vocabulary")
    if (doc["rights_status"] in {
            "third_party_permission_asserted", "public_domain_asserted",
        } and not doc["attribution"].strip()):
        raise AssetDescriptorError("external origin claims require an attribution")
    if record.get("source_sha256") != digest([
        record_id, "asset_forge", record["revision"], doc, deps,
    ]):
        raise AssetDescriptorError("descriptor record does not match original source hash")
    return dict(record)


def _content_digest(meta: Mapping[str, Any], *, sprite: bool) -> str:
    if not isinstance(meta, Mapping):
        raise AssetDescriptorError("compiled asset metadata is missing")
    body = dict(meta)
    receipt = body.pop("receipt_sha256", None)
    if receipt != digest(body):
        raise AssetDescriptorError("compiled asset receipt was altered")
    if sprite:
        return _hex(meta.get("png_sha256"), "original sprite PNG")
    return _hex(meta.get("wav_sha256"), "original WAV")


def _sprite_metrics(sprite: Mapping[str, Any]) -> dict[str, Any]:
    from .studio_sprite_forge import _decode_verified_png
    from .studio_sprite_verify import verify_published_sprite
    meta, png = sprite["metadata"], sprite["png"]
    verified = verify_published_sprite(png, meta)
    if verified.get("layout_and_padding_reproduced") is not True:
        raise AssetDescriptorError("sprite pixels did not independently replay")
    w, h = meta["sheet_width_px"], meta["sheet_height_px"]
    pixels = _decode_verified_png(png, w, h)
    counts: Counter[str] = Counter()
    visible = 0
    xmin, ymin, xmax, ymax = w, h, -1, -1
    alpha_sum = 0
    for y in range(h):
        for x in range(w):
            offset = (y * w + x) * 4
            rgba = pixels[offset:offset + 4]
            if rgba[3]:
                visible += 1
                alpha_sum += rgba[3]
                counts[rgba.hex()] += 1
                xmin, ymin = min(xmin, x), min(ymin, y)
                xmax, ymax = max(xmax, x), max(ymax, y)
    frames = meta["frames"]
    animations = meta["animations"]
    return {
        "pixel_format": "PNG_RGBA8_sRGB_source",  # no ICC transform is claimed
        "atlas_dimensions_px": [w, h],
        "frame_dimensions_px": [meta["frame_width_px"], meta["frame_height_px"]],
        "pixel_scale": meta["pixel_scale"],
        "frame_count": len(frames),
        "animation_count": len(animations),
        "animations": [{
            "name": state["name"], "frame_ids": list(state["frame_ids"]),
            "duration_ms": state["duration_ms"], "loop": state["loop"],
        } for state in animations],
        "visible_atlas_pixels": visible,
        "mean_nonzero_alpha": (alpha_sum // visible if visible else 0),
        "visible_atlas_bounds_xywh": [
            xmin, ymin, xmax - xmin + 1, ymax - ymin + 1,
        ] if visible else None,
        "top_rgba_hex": [
            "#" + rgba for rgba, _ in sorted(
                counts.items(), key=lambda kv: (-kv[1], kv[0]),
            )[:12]
        ],
        "normal_png_sha256": (
            meta["normal_map"]["normal_png_sha256"]
            if meta.get("normal_map") else None
        ),
        "frame_cue_ids": sorted(
            cue["event_id"] for cue in meta.get("frame_cues", {}).get("cues", [])
        ) if meta.get("frame_cues") else [],
        "pixel_exact_collision_masks_available": all(
            isinstance(frame.get("collision_mask_bits_hex"), str) for frame in frames
        ),
        "native_framebuffer_render_verified": False,
    }


def _audio_metrics(sound: Mapping[str, Any]) -> dict[str, Any]:
    meta, wav = sound["metadata"], sound["wav"]
    if (not isinstance(wav, bytes) or len(wav) < 44
            or sha256(wav).hexdigest() != meta["wav_sha256"]
            or len(wav) != 44 + meta["sample_count"] * 2):
        raise AssetDescriptorError("WAV descriptor cannot prove source audio bytes")
    if meta.get("channels") != 1 or meta.get("bits_per_sample") != 16:
        raise AssetDescriptorError("unexpected PCM format in audio descriptor")
    count = meta["sample_count"]
    if count <= 0 or count > 132300:
        raise AssetDescriptorError("audio descriptor PCM size outside bounds")
    peak, sum_abs, energy = 0, 0, 0
    for (sample,) in struct.iter_unpack("<h", wav[44:]):
        peak = max(peak, abs(sample))
        sum_abs += abs(sample)
        energy += sample * sample
    return {
        "codec": "PCM_S16LE", "channels": 1,
        "sample_rate_hz": meta["sample_rate_hz"],
        "sample_count": count, "duration_ms": meta["duration_ms"],
        "waveform": meta["waveform"],
        "peak_abs_pcm": peak,
        "mean_abs_pcm": sum_abs // count,
        "rms_pcm_x1000": __import__("math").isqrt(energy * 1_000_000 // count),
        "peak_dbfs_estimate_available": False,
        "native_audio_playback_verified": False,
    }


def _asset(sprite: Mapping[str, Any] | None, sound: Mapping[str, Any] | None,
           overlay: Mapping[str, Any] | None) -> dict[str, Any]:
    if (sprite is None) == (sound is None):
        raise AssetDescriptorError("exactly one compiled asset modality is required")
    source = sprite if sprite is not None else sound
    assert source is not None
    meta = source["metadata"]
    is_sprite = sprite is not None
    target = meta.get("record_id") if is_sprite else meta.get("source_record_id")
    origin = meta.get("source_sha256")
    # Palette skins are derivative sources: their original variant record
    # and parent source form a separate immutable, explicit provenance link.
    variant = sprite.get("palette_variant_receipt") if is_sprite else None
    if variant is not None:
        target = variant["variant_source_record_id"]
        origin = variant["variant_source_revision_sha256"]
    if (type(target) is not str or not ID.fullmatch(target)
            or not isinstance(meta.get("asset_id"), str)
            or not ID.fullmatch(meta["asset_id"])):
        raise AssetDescriptorError("compiled asset lost durable source identity")
    content_sha = _content_digest(meta, sprite=is_sprite)
    actual = source["png"] if is_sprite else source["wav"]
    if not isinstance(actual, bytes) or sha256(actual).hexdigest() != content_sha:
        raise AssetDescriptorError("descriptor references different output bytes")
    document = overlay["document"] if overlay else None
    if document is not None and (document["target_record_id"] != target
                                  or document["target_asset_id"] != meta["asset_id"]):
        raise AssetDescriptorError("reviewed descriptor targets different compiler output")
    metrics = _sprite_metrics(sprite) if sprite is not None else _audio_metrics(sound)  # type: ignore[arg-type]
    label = meta["asset_id"].replace("-", " ").replace("_", " ")
    fallback = (
        f"Original pixel sprite {meta['asset_id']}: {len(meta['animations'])} "
        f"animation state(s), {len(meta['frames'])} frame(s)."
        if is_sprite else
        f"Original procedural sound {meta['asset_id']}: "
        f"{meta['duration_ms']} ms {meta['waveform']} waveform."
    )
    return {
        "schema_version": SCHEMA,
        "asset_id": meta["asset_id"],
        "kind": "pixel_sprite" if is_sprite else "procedural_sound",
        "source_record_id": target, "source_sha256": _hex(origin, "source lineage"),
        "source_compiler_receipt_sha256": meta["receipt_sha256"],
        "content_sha256": content_sha,
        "content_media_type": "image/png" if is_sprite else "audio/wav",
        "title": document["title"] if document else label.title(),
        "description": document["description"] if document else fallback,
        "alt_text": document["alt_text"] if document else fallback,
        "locale": document["locale"] if document else "en",
        "tags": _list(document["tags"], "tags", None, 24) if document else [],
        "roles": _list(document["roles"], "roles", ROLE, 12) if document else [],
        "rights": {
            "status": document["rights_status"] if document else "not_reviewed",
            "attribution": document["attribution"] if document else "",
            "legally_cleared_by_compiler": False,
        },
        "semantic_evidence": {
            "status": "authored_reviewed_source" if overlay else "structural_only",
            "source_record_id": overlay["record_id"] if overlay else None,
            "source_revision_sha256": overlay["source_sha256"] if overlay else None,
            "scene_content_recognized_by_model": False,
        },
        "engine_targets": (
            ["godot4_2d", "godot4_sprite3d_diffuse"]
            if is_sprite else ["godot4_wav"]
        ),
        "metrics": metrics,
    }


def compile_asset_catalog(
    *, project_id: str, source_head_sha256: str | None,
    records: Mapping[str, Mapping[str, Any]],
    sprites: Sequence[Mapping[str, Any]] = (),
    sounds: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a reproducible, searchable catalogue from actual compiled bytes."""
    _text(project_id, "project", maximum=128)
    if source_head_sha256 is not None:
        _hex(source_head_sha256, "project source head")
    if len(sprites) + len(sounds) > MAX_ASSETS:
        raise AssetDescriptorError("asset catalog exceeds checked compiler budget")
    overlays = {}
    overlay_sources = []
    for _, record in sorted(records.items()):
        doc = record.get("document") if isinstance(record, Mapping) else None
        if not isinstance(doc, dict) or doc.get("kind") != "asset_descriptor":
            continue
        checked = _review_overlay(record)
        key = (doc["target_record_id"], doc["target_asset_id"])
        if key in overlays:
            raise AssetDescriptorError("ambiguous duplicate semantic descriptor")
        overlays[key] = checked
        overlay_sources.append(checked)
    descriptors: list[dict[str, Any]] = []
    keys: set[tuple[str, str]] = set()
    ids: set[tuple[str, str]] = set()
    for sprite, sound in (
        [(entry, None) for entry in sprites]
        + [(None, entry) for entry in sounds]
    ):
        item = _asset(sprite, sound, None)
        key = (item["source_record_id"], item["asset_id"])
        if key in keys or (item["kind"], item["asset_id"]) in ids:
            raise AssetDescriptorError("duplicate compiled asset identity")
        keys.add(key)
        ids.add((item["kind"], item["asset_id"]))
        item = _asset(sprite, sound, overlays.get(key))
        item["receipt_sha256"] = digest(item)
        descriptors.append(item)
    if set(overlays) - keys:
        raise AssetDescriptorError("reviewed description references uncompiled asset")
    descriptors.sort(key=lambda item: (item["kind"], item["asset_id"]))
    terms: dict[str, list[str]] = {}
    for item in descriptors:
        terms.setdefault(item["kind"], [])
        index = item["kind"] + ":" + item["asset_id"]
        for term in set(re.findall(
            r"[a-z0-9]+", " ".join((
                item["asset_id"], item["title"], item["description"],
                item["alt_text"], " ".join(item["tags"]), " ".join(item["roles"]),
            )).casefold(),
        )):
            terms.setdefault(term, []).append(index)
    indexed = {term: sorted(set(values)) for term, values in sorted(terms.items())}
    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "project_id": project_id, "source_head_sha256": source_head_sha256,
        "descriptor_count": len(descriptors),
        "descriptors": descriptors,
        "reviewed_overlay_sources": overlay_sources,
        "inverted_index": indexed,
        "all_asset_pixels_or_samples_independently_replayed": True,
        "narrative_meaning_inferred_from_pixels": False,
        "rights_clearance_certified": False,
        "model_weights_trained": False,
    }
    catalog["receipt_sha256"] = sha256(_json(catalog)).hexdigest()
    if len(_json(catalog)) > MAX_CATALOG_BYTES:
        raise AssetDescriptorError("asset catalog exceeds deterministic storage budget")
    return catalog


def catalog_bytes(catalog: Mapping[str, Any]) -> bytes:
    raw = _json(catalog)
    if len(raw) > MAX_CATALOG_BYTES:
        raise AssetDescriptorError("descriptor catalog exceeds storage budget")
    return raw


def verify_asset_catalog(
    raw: bytes, *, project_id: str, source_head_sha256: str | None,
    sprites: Sequence[Mapping[str, Any]] = (),
    sounds: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Replay descriptors/index and prove exact identity against shipped bytes."""
    if not isinstance(raw, bytes) or len(raw) > MAX_CATALOG_BYTES:
        raise AssetDescriptorError("published asset catalogue lacks bounded bytes")
    try:
        published = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AssetDescriptorError("asset catalogue contains invalid JSON") from exc
    if not isinstance(published, dict) or catalog_bytes(published) != raw:
        raise AssetDescriptorError("asset catalogue is not canonical JSON")
    records = {
        record["record_id"]: record
        for record in published.get("reviewed_overlay_sources", [])
    }
    if len(records) != len(published.get("reviewed_overlay_sources", [])):
        raise AssetDescriptorError("duplicate semantic source record in archive")
    expected = compile_asset_catalog(
        project_id=project_id, source_head_sha256=source_head_sha256,
        records=records, sprites=sprites, sounds=sounds,
    )
    if published != expected:
        raise AssetDescriptorError("catalog semantics/index/lineage differ from real assets")
    return {
        "schema_version": "skeleton.jeeves.asset_catalog_replay.v2",
        "catalog_sha256": sha256(raw).hexdigest(),
        "descriptor_count": expected["descriptor_count"],
        "source_head_sha256": source_head_sha256,
        "pixels_samples_descriptors_and_index_replayed": True,
        "copyright_review_performed": False,
    }


def search_asset_catalog(catalog: Mapping[str, Any], query: str,
                         *, limit: int = 12,
                         kind: str | None = None) -> dict[str, Any]:
    """Retrieval is deterministic, source-bounded and never an LLM guess."""
    if type(query) is not str or not 1 <= len(query.strip()) <= 512:
        raise AssetDescriptorError("asset search requires bounded text")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise AssetDescriptorError("asset search limit out of bounds")
    if kind is not None and kind not in ("pixel_sprite", "procedural_sound"):
        raise AssetDescriptorError("unknown asset modality")
    words = set(re.findall(r"[a-z0-9]+", query.casefold()))
    index = catalog.get("inverted_index")
    descriptors = catalog.get("descriptors")
    if not isinstance(index, Mapping) or not isinstance(descriptors, list):
        raise AssetDescriptorError("asset search requires a compiled index")
    weights: Counter[str] = Counter()
    for word in words:
        for key in index.get(word, []):
            weights[key] += 1
    matches = []
    for item in descriptors:
        key = item["kind"] + ":" + item["asset_id"]
        if weights[key] and (kind is None or item["kind"] == kind):
            matches.append((-weights[key], key, item))
    matches.sort(key=lambda entry: (entry[0], entry[1]))
    selected = [item for _, _, item in matches[:limit]]
    return {
        "schema_version": "skeleton.jeeves.asset_catalog_search.v2",
        "catalog_receipt_sha256": catalog.get("receipt_sha256"),
        "query": query, "kind": kind, "total_matches": len(matches),
        "results": selected, "result_receipts": [
            item["receipt_sha256"] for item in selected
        ],
        "neural_retrieval_performed": False,
    }


def gltf_extras_for_asset(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Portable metadata in glTF 2.0 asset.extras; NOT a mesh exporter."""
    if (descriptor.get("schema_version") != SCHEMA
            or not isinstance(descriptor.get("receipt_sha256"), str)):
        raise AssetDescriptorError("glTF extras need a verified asset descriptor")
    expected = dict(descriptor)
    receipt = expected.pop("receipt_sha256")
    if receipt != digest(expected):
        raise AssetDescriptorError("descriptor receipt differs before glTF projection")
    return {
        "skeletonJeevesAsset": {
            "descriptorSchema": SCHEMA,
            "descriptorReceiptSha256": receipt,
            "assetId": descriptor["asset_id"],
            "contentSha256": descriptor["content_sha256"],
            "kind": descriptor["kind"],
            "title": descriptor["title"],
            "rightsAssertion": descriptor["rights"]["status"],
        }
    }


__all__ = [
    "AssetDescriptorError", "compile_asset_catalog", "catalog_bytes",
    "verify_asset_catalog", "search_asset_catalog", "gltf_extras_for_asset",
    "SCHEMA", "CATALOG_SCHEMA",
]
