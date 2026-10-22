"""Compile source-bound original NPC sprite visuals into the REAL Godot cast.

The existing Expedition world is authoritative for NPC identity and movement.
A reviewed scene_forge record may supply an original animated PNG/SpriteFrames
resource to one of those real NPCs. Only trusted, known GDScript anchors may be
extended. The baseline capsule remains if no binding was authored; no image is
invented and source-only compilation never claims observed rendering.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import math
import re
from typing import Any

from .studio_interaction_contract import digest

NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
NPC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
DOCUMENT_KEYS = frozenset({
    "kind", "npc_id", "asset_id", "animation", "pixel_size",
    "vertical_offset_m", "billboard", "hide_capsule",
})
SOURCE_SCHEMA = "skeleton.jeeves.npc_sprite_binding.v1"
MARKER = '            npc_markers[str(profile.get("npc_id", ""))] = npc'


class NpcSpriteBindingError(ValueError):
    """Original NPC pixel art cannot be safely bound to the real game cast."""


def _float(value: Any, name: str, low: float, high: float) -> float:
    if type(value) not in (float, int):
        raise NpcSpriteBindingError(name + " must be an explicit real number")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise NpcSpriteBindingError(name + " exceeds reviewed game limits")
    return number


def _npc_cast_names(files: Mapping[str, str]) -> set[str]:
    payload = files.get("game/frontier/npcs.json")
    if payload is None:
        return set()
    if type(payload) is not str or len(payload) > 2_000_000:
        raise NpcSpriteBindingError("real expedition cast JSON is not bounded text")
    try:
        source = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise NpcSpriteBindingError("real expedition NPC cast cannot be parsed") from exc
    cast = source.get("cast") if isinstance(source, dict) else None
    if not isinstance(cast, list) or len(cast) > 64:
        raise NpcSpriteBindingError("real native game NPC cast is invalid")
    names: set[str] = set()
    for entry in cast:
        if not isinstance(entry, dict) or not isinstance(entry.get("design"), dict):
            raise NpcSpriteBindingError("NPC cast requires original design records")
        identity = entry["design"].get("npc_id")
        if type(identity) is not str or NPC_ID.fullmatch(identity) is None or identity in names:
            raise NpcSpriteBindingError("NPC cast has ambiguous or unsafe native identity")
        names.add(identity)
    return names


def authored_npc_sprite_bindings(
    records: Mapping[str, Mapping[str, Any]],
    sprites: list[dict[str, Any]],
    files: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Select exact reviewed NPC visual records; never invent cast members."""
    allowed = _npc_cast_names(files)
    selected: dict[str, dict[str, Any]] = {}
    by_asset = {sprite["asset_id"]: sprite for sprite in sprites}
    if len(by_asset) != len(sprites):
        raise NpcSpriteBindingError("original authored sprites have duplicate asset names")
    for record_id, record in sorted(records.items()):
        source = record.get("document")
        if not isinstance(source, Mapping) or source.get("kind") != "sprite_npc_binding":
            continue
        if (record.get("record_id") != record_id
                or record.get("facet") != "scene_forge"
                or set(source) != DOCUMENT_KEYS):
            raise NpcSpriteBindingError("NPC sprite requires complete scene-owned source")
        npc_id = source["npc_id"]
        if type(npc_id) is not str or NPC_ID.fullmatch(npc_id) is None or npc_id not in allowed:
            raise NpcSpriteBindingError("NPC sprite references an absent original world character")
        if npc_id in selected:
            raise NpcSpriteBindingError("multiple original sprite owners for one NPC")
        asset_id, animation = source["asset_id"], source["animation"]
        if (type(asset_id) is not str or NAME.fullmatch(asset_id) is None
                or type(animation) is not str or NAME.fullmatch(animation) is None):
            raise NpcSpriteBindingError("NPC sprite resource names must be portable")
        asset = by_asset.get(asset_id)
        if asset is None or animation not in asset["animation_names"]:
            raise NpcSpriteBindingError("NPC references an uncreated sprite or animation")
        dependencies = record.get("depends_on")
        if (type(dependencies) is not list
                or asset["source_record_id"] not in dependencies):
            raise NpcSpriteBindingError("NPC visual lacks its real sprite source dependency")
        if type(source["billboard"]) is not bool or type(source["hide_capsule"]) is not bool:
            raise NpcSpriteBindingError("NPC visibility modes must be typed booleans")
        body = {
            "schema_version": SOURCE_SCHEMA, "source_record_id": record_id,
            "npc_id": npc_id, "asset_id": asset_id, "animation": animation,
            "sprite_source_record_id": asset["source_record_id"],
            "sprite_png_sha256": asset["png_sha256"],
            "sprite_frames_resource_sha256": asset["godot_spriteframes_resource_sha256"],
            "pixel_size": _float(source["pixel_size"], "NPC pixel scale", 0.001, 0.25),
            "vertical_offset_m": _float(
                source["vertical_offset_m"], "NPC sprite vertical offset", -10, 30,
            ),
            "billboard": source["billboard"],
            "hide_capsule": source["hide_capsule"],
            "native_npc_sprite_render_observed": False,
        }
        body["receipt_sha256"] = digest(body)
        selected[npc_id] = body
    return [selected[name] for name in sorted(selected)]


def preflight_original_npc_sprite_graph(
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate source references before persisting a creator edit.

    The real NPC cast is checked later against the emitted world. This stage
    instead guarantees edits cannot break already-authored sprite/animation
    references or silently lose their original dependency.
    """
    from .studio_sprite_forge import compile_authored_sprite

    bindings: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for record_id, record in records.items():
        doc = record.get("document")
        if not isinstance(doc, Mapping) or doc.get("kind") != "sprite_npc_binding":
            continue
        if (record.get("record_id") != record_id or record.get("facet") != "scene_forge"
                or set(doc) != DOCUMENT_KEYS):
            raise NpcSpriteBindingError("NPC sprite source requires exact scene-owned fields")
        if (type(doc.get("npc_id")) is not str
                or NPC_ID.fullmatch(doc["npc_id"]) is None):
            raise NpcSpriteBindingError("NPC visual identity is not portable")
        bindings.append((record_id, record, doc))
    if len(bindings) > 64:
        raise NpcSpriteBindingError("NPC visual bindings exceed original cast capacity")
    ids = [doc["npc_id"] for _, _, doc in bindings]
    if len(ids) != len(set(ids)):
        raise NpcSpriteBindingError("NPC visual identity is authored twice")
    resolved: list[str] = []
    for record_id, record, doc in bindings:
        asset_id = doc["asset_id"]
        if type(asset_id) is not str or NAME.fullmatch(asset_id) is None:
            raise NpcSpriteBindingError("NPC visual references invalid sprite name")
        candidates = [
            item for item in records.values()
            if isinstance(item.get("document"), Mapping)
            and item["document"].get("kind") == "pixel_sprite"
            and item["document"].get("asset_id") == asset_id
        ]
        if len(candidates) != 1:
            raise NpcSpriteBindingError("NPC visual references absent or ambiguous sprite source")
        chosen = candidates[0]
        if (type(record.get("depends_on")) is not list
                or chosen["record_id"] not in record["depends_on"]):
            raise NpcSpriteBindingError("NPC visual must depend on its exact original sprite record")
        source = compile_authored_sprite(chosen)["metadata"]
        animations = [state["name"] for state in source["animations"]]
        if doc["animation"] not in animations:
            raise NpcSpriteBindingError("NPC visual animation missing from original source frames")
        _float(doc["pixel_size"], "NPC pixel size", 0.001, 0.25)
        _float(doc["vertical_offset_m"], "NPC vertical offset", -10, 30)
        if type(doc["billboard"]) is not bool or type(doc["hide_capsule"]) is not bool:
            raise NpcSpriteBindingError("NPC visual policies must be reviewed booleans")
        resolved.append(record_id)
    report = {
        "schema_version": "skeleton.jeeves.npc_source_graph_preflight.v1",
        "checked_record_ids": sorted(resolved),
        "sprite_dependencies_valid": True,
        "world_npc_identity_verified": False,
    }
    report["receipt_sha256"] = digest(report)
    return report


def bind_npc_sprites_to_expedition_script(
    script: str, bindings: list[dict[str, Any]],
) -> str:
    """Make sprites real children of moving NPC actors in generated Godot."""
    if not bindings:
        return script
    if type(script) is not str or script.count(MARKER) != 1:
        raise NpcSpriteBindingError("trusted NPC spawn anchor was modified")
    if type(bindings) is not list or len(bindings) > 64:
        raise NpcSpriteBindingError("NPC sprite bindings exceed bounded cast")
    seen = set()
    blocks: list[str] = []
    for item in bindings:
        if not isinstance(item, dict):
            raise NpcSpriteBindingError("NPC sprite binding requires a source receipt")
        body = dict(item)
        receipt = body.pop("receipt_sha256", None)
        if receipt != digest(body):
            raise NpcSpriteBindingError("NPC sprite source receipt was modified")
        npc_id = item["npc_id"]
        asset = item["asset_id"]
        anim = item["animation"]
        if (type(npc_id) is not str or NPC_ID.fullmatch(npc_id) is None
                or type(asset) is not str or NAME.fullmatch(asset) is None
                or type(anim) is not str or NAME.fullmatch(anim) is None
                or npc_id in seen):
            raise NpcSpriteBindingError("NPC identity or animation changed after source review")
        seen.add(npc_id)
        _float(item["pixel_size"], "pixel size", 0.001, 0.25)
        _float(item["vertical_offset_m"], "vertical offset", -10, 30)
        if type(item["billboard"]) is not bool or type(item["hide_capsule"]) is not bool:
            raise NpcSpriteBindingError("untyped NPC rendering policies")
        blocks.append('"' + npc_id + '": {"asset": "' + asset
                      + '", "animation": "' + anim
                      + '", "pixel_size": ' + format(item["pixel_size"], ".8f")
                      + ', "offset": ' + format(item["vertical_offset_m"], ".6f")
                      + ', "billboard": ' + str(item["billboard"]).lower()
                      + ', "hide_capsule": ' + str(item["hide_capsule"]).lower() + '}')
    declaration = [
        "            # Reviewed original NPC art, not unverified model instructions.",
        '            var jeeves_npc_id := str(profile.get("npc_id", ""))',
        "            var jeeves_npc_binding: Dictionary = {",
        "                " + ",\n                ".join(blocks),
        "            }",
        "            if jeeves_npc_binding.has(jeeves_npc_id):",
        "                var jeeves_npc_visual: Dictionary = jeeves_npc_binding[jeeves_npc_id]",
        '                var jeeves_npc_frames := load("res://game/frontier/sprites/"',
        '                    + jeeves_npc_visual["asset"] + ".tres") as SpriteFrames',
        "                if jeeves_npc_frames == null or not jeeves_npc_frames.has_animation(",
        '                    jeeves_npc_visual["animation"]):',
        '                    push_error("Original NPC sprite resource missing")',
        "                else:",
        "                    var jeeves_npc_sprite := AnimatedSprite3D.new()",
        '                    jeeves_npc_sprite.name = "OriginalAuthoredNPCSprite"',
        "                    jeeves_npc_sprite.sprite_frames = jeeves_npc_frames",
        "                    jeeves_npc_sprite.animation = jeeves_npc_visual['animation']",
        "                    jeeves_npc_sprite.pixel_size = jeeves_npc_visual['pixel_size']",
        '                    jeeves_npc_sprite.position = Vector3(0.0, jeeves_npc_visual["offset"], 0.0)',
        "                    jeeves_npc_sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED",
        '                        if jeeves_npc_visual["billboard"]',
        "                        else BaseMaterial3D.BILLBOARD_DISABLED",
        "                    npc.add_child(jeeves_npc_sprite)",
        "                    jeeves_npc_sprite.play()",
        '                    if jeeves_npc_visual["hide_capsule"]:',
        "                        npc.mesh = null",
        '            npc_markers[str(profile.get("npc_id", ""))] = npc',
    ]
    # Godot GDScript does NOT support Python's multiline ternary expression.
    # Compile an ordinary if/else branch instead to preserve parseability.
    i = declaration.index("                    jeeves_npc_sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED")
    declaration[i:i + 3] = [
        '                    if jeeves_npc_visual["billboard"]:',
        "                        jeeves_npc_sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED",
        "                    else:",
        "                        jeeves_npc_sprite.billboard = BaseMaterial3D.BILLBOARD_DISABLED",
    ]
    return script.replace(MARKER, "\n".join(declaration), 1)


def verify_native_npc_binding_script(
    before: str, after: str, bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    regenerated = bind_npc_sprites_to_expedition_script(before, bindings)
    if regenerated != after:
        raise NpcSpriteBindingError("native NPC actor visual script changed from authored source")
    proof = {
        "schema_version": "skeleton.jeeves.npc_sprite_code_receipt.v1",
        "npc_bound_count": len(bindings),
        "source_receipts": [item["receipt_sha256"] for item in bindings],
        "baseline_godot_sha256": sha256(before.encode("utf-8")).hexdigest(),
        "compiled_godot_sha256": sha256(after.encode("utf-8")).hexdigest(),
        "exact_engine_source_reproduction": True,
        "native_npc_visual_render_verified": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return proof


__all__ = [
    "NpcSpriteBindingError", "authored_npc_sprite_bindings",
    "preflight_original_npc_sprite_graph",
    "bind_npc_sprites_to_expedition_script", "verify_native_npc_binding_script",
]
