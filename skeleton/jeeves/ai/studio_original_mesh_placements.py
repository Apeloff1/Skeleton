"""Source-authorized original mesh placements in a running Godot expedition.

Each reviewed placement is an actual instanced PackedScene in the game-world
root, not a separate editor-only asset. The compiler creates a reusable child
scene, patches the real game's .tscn conservatively, and retains complete
source/asset lineage for a separate post-publication replay.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any

from .studio_interaction_contract import digest
from .studio_original_mesh import OriginalMeshError, _source, compile_original_mesh

SCHEMA = "skeleton.jeeves.original_mesh_placement.v1"
KIND = "original_mesh_instance"
KEYS = frozenset({
    "kind", "instance_id", "base_record_id", "asset_id",
    "physics_record_id", "position_mm", "rotation_deg", "scale_per_mille",
})
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ROOT_SCENE = "game/frontier/expedition.tscn"
PLACEMENT_SCENE = "game/frontier/mesh_placements.tscn"
PLACEMENT_SOURCE = "game/frontier/mesh_placements.source.json"
MAX_INSTANCES = 128
MAX_POSITION_MM = 10_000_000


class OriginalMeshPlacementError(ValueError):
    """An unapproved mesh instance or detached game scene may not compile."""


def _vec(value: Any, *, size: int, low: int, high: int) -> list[int]:
    if (type(value) is not list or len(value) != size
            or any(type(x) is not int or not low <= x <= high for x in value)):
        raise OriginalMeshPlacementError("mesh instance transform is out of bounds")
    return value


def _format(v: float) -> str:
    return format(v, ".4f")


def _validate(
    records: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, Any],
    *, lod_assets: frozenset[str],
    physics_assets: frozenset[str],
) -> dict[str, Any]:
    if source.get("facet") != "scene_forge":
        raise OriginalMeshPlacementError("mesh instance requires scene_forge facet")
    doc = source.get("document")
    if not isinstance(doc, dict) or set(doc) != KEYS or doc["kind"] != KIND:
        raise OriginalMeshPlacementError("mesh instance source contract incomplete")
    ident, asset = doc["instance_id"], doc["asset_id"]
    if (type(ident) is not str or not ID.fullmatch(ident)
            or type(asset) is not str or not ID.fullmatch(asset)
            or type(doc["base_record_id"]) is not str):
        raise OriginalMeshPlacementError("mesh placement IDs must be portable")
    _vec(doc["position_mm"], size=3, low=-MAX_POSITION_MM, high=MAX_POSITION_MM)
    _vec(doc["rotation_deg"], size=3, low=-360, high=360)
    scale = doc["scale_per_mille"]
    if type(scale) is not int or not 100 <= scale <= 10000:
        raise OriginalMeshPlacementError("mesh instance scale must be positive and bounded")
    rid = source.get("record_id")
    version = source.get("revision")
    deps = source.get("depends_on")
    if (type(rid) is not str or not ID.fullmatch(rid)
            or type(version) is not int or version < 1
            or type(deps) is not list or len(deps) > 32
            or len(set(deps)) != len(deps)
            or doc["base_record_id"] not in deps
            or any(type(d) is not str for d in deps)
            or source.get("source_sha256") != digest([
                rid, "scene_forge", version, doc, deps,
            ])):
        raise OriginalMeshPlacementError("mesh instance lacks original source revision")
    base = records.get(doc["base_record_id"])
    try:
        if not isinstance(base, Mapping) or _source(base)["asset_id"] != asset:
            raise OriginalMeshPlacementError(
                "mesh instance target is not a reviewed original mesh"
            )
        compiled = compile_original_mesh(base)
    except OriginalMeshError as exc:
        raise OriginalMeshPlacementError("mesh instance original GLB source invalid") from exc
    body_id = doc["physics_record_id"]
    if body_id is not None:
        if (type(body_id) is not str or not ID.fullmatch(body_id)
                or body_id not in deps or asset not in physics_assets):
            raise OriginalMeshPlacementError("physics placement needs reviewed body source")
        body = records.get(body_id)
        if (not isinstance(body, Mapping) or body.get("facet") != "physics"
                or not isinstance(body.get("document"), dict)
                or body["document"].get("kind") != "procedural_mesh_physics"
                or body["document"].get("asset_id") != asset
                or body["document"].get("base_record_id") != doc["base_record_id"]):
            raise OriginalMeshPlacementError("physical mesh instance body identity differs")
        from .studio_original_mesh_physics import compile_original_mesh_physics
        compile_original_mesh_physics(
            base, body, has_lod=asset in lod_assets,
        )
        source_kind = "physics"
    else:
        source_kind = "lod" if asset in lod_assets else "visual"
    suffix = (
        ".physics.tscn" if source_kind == "physics"
        else ".lod.tscn" if source_kind == "lod"
        else ".tscn"
    )
    return {
        "instance_id": ident,
        "author_record_id": rid,
        "author_source_sha256": source["source_sha256"],
        "asset_id": asset,
        "base_record_id": base["record_id"],
        "base_source_sha256": base["source_sha256"],
        "glb_sha256": compiled["metadata"]["glb_sha256"],
        "physics_record_id": body_id,
        "visual_or_physics": source_kind,
        "resource_path": "game/frontier/meshes/" + asset + suffix,
        "position_mm": list(doc["position_mm"]),
        "rotation_deg": list(doc["rotation_deg"]),
        "scale_per_mille": scale,
    }


def _source_json(value: Any) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compile_original_mesh_placements(
    records: Mapping[str, Mapping[str, Any]], *,
    lod_assets: frozenset[str] = frozenset(),
    physics_assets: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if (not isinstance(records, Mapping)
            or type(lod_assets) is not frozenset
            or type(physics_assets) is not frozenset):
        raise OriginalMeshPlacementError("placement requires checked project source")
    authored = [
        record for _, record in sorted(records.items())
        if isinstance(record.get("document"), dict)
        and record["document"].get("kind") == KIND
    ]
    if len(authored) > MAX_INSTANCES:
        raise OriginalMeshPlacementError("mesh scene exceeds source instance budget")
    entries = [
        _validate(
            records, record, lod_assets=lod_assets,
            physics_assets=physics_assets,
        ) for record in authored
    ]
    instances = [entry["instance_id"] for entry in entries]
    if len(instances) != len(set(instances)):
        raise OriginalMeshPlacementError("mesh scene has duplicate instance names")
    entries.sort(key=lambda item: item["instance_id"])
    files = {}
    if entries:
        distinct_paths = sorted({e["resource_path"] for e in entries})
        refs = {path: i + 1 for i, path in enumerate(distinct_paths)}
        lines = [
            "[gd_scene load_steps=" + str(len(refs) + 1) + " format=3",
            "",
        ]
        for path in distinct_paths:
            lines.append(
                '[ext_resource type="PackedScene" path="res://' + path
                + '" id="' + str(refs[path]) + '"]'
            )
        lines += ["", '[node name="AuthoredMeshes" type="Node3D"]', ""]
        for entry in entries:
            name = entry["instance_id"]
            lines.append(
                '[node name="' + name + '" parent="." instance=ExtResource("'
                + str(refs[entry["resource_path"]]) + '")]'
            )
            lines.append(
                "position = Vector3(" + ", ".join(
                    _format(x / 1000) for x in entry["position_mm"]
                ) + ")"
            )
            lines.append(
                "rotation_degrees = Vector3(" + ", ".join(
                    _format(x) for x in entry["rotation_deg"]
                ) + ")"
            )
            lines.append(
                "scale = Vector3(" + ", ".join(
                    _format(entry["scale_per_mille"] / 1000) for _ in range(3)
                ) + ")"
            )
            lines.append("")
        content = "\n".join(lines)
        files[PLACEMENT_SCENE] = content
    proof = {
        "schema_version": SCHEMA,
        "instance_count": len(entries),
        "instances": entries,
        "placement_scene_sha256": (
            sha256(files[PLACEMENT_SCENE].encode("utf-8")).hexdigest()
            if entries else None
        ),
        "source_instance_ids": [item["author_record_id"] for item in entries],
        "mesh_world_instances_created": bool(entries),
        "godot_engine_scene_import_observed": False,
        "actual_gameplay_collision_observed": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return {"files": files, "metadata": proof}


def attach_authored_meshes_to_expedition(
    original_scene: str, compiled: Mapping[str, Any],
) -> str:
    """Inject one explicit child scene into the real expedition root."""
    from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCENE

    if type(original_scene) is not str or original_scene != _GODOT_SCENE:
        raise OriginalMeshPlacementError(
            "base native expedition scene changed; do not silently patch"
        )
    if not isinstance(compiled, Mapping):
        raise OriginalMeshPlacementError("mesh scene receipt required")
    proof = compiled.get("metadata")
    files = compiled.get("files")
    if (not isinstance(proof, Mapping) or not isinstance(files, Mapping)
            or proof["receipt_sha256"] != digest({
                key: value for key, value in proof.items()
                if key != "receipt_sha256"
            })):
        raise OriginalMeshPlacementError("mesh placement receipt does not replay")
    if not proof["instance_count"]:
        if files:
            raise OriginalMeshPlacementError("no-op placement may not add scene")
        return original_scene
    if set(files) != {PLACEMENT_SCENE}:
        raise OriginalMeshPlacementError("placement source scene missing or extra")
    if sha256(files[PLACEMENT_SCENE].encode("utf-8")).hexdigest() != proof[
            "placement_scene_sha256"]:
        raise OriginalMeshPlacementError("mesh child scene content differs")
    # Existing Godot source is canonical and intentionally tiny; only replace
    # its known header and append one instanced child. No arbitrary script
    # substitution, scene rebuilding or text injection is allowed.
    old_header = "[gd_scene load_steps=2 format=3]"
    new_header = "[gd_scene load_steps=3 format=3]"
    link = (
        '[ext_resource type="PackedScene" '
        'path="res://game/frontier/mesh_placements.tscn" id="OriginalMeshes"]'
    )
    if original_scene.count(old_header) != 1:
        raise OriginalMeshPlacementError("unexpected Godot expedition scene format")
    return (
        original_scene.replace(old_header, new_header, 1)
        .replace(
            '[node name="FrontierExpedition" type="Node3D"]',
            link + "\n\n[node name=\"FrontierExpedition\" type=\"Node3D\"]",
            1,
        )
        + '\n[node name="OriginalMeshInstances" parent="." '
        'instance=ExtResource("OriginalMeshes")]\n'
    )


def compile_original_mesh_placement_source_bundle(
    records: Mapping[str, Mapping[str, Any]], compiled: Mapping[str, Any],
) -> bytes:
    entries = compiled["metadata"]["instances"]
    if not entries:
        raise OriginalMeshPlacementError("empty placement does not need source bundle")
    collected = set()
    for entry in entries:
        collected.update((
            entry["author_record_id"], entry["base_record_id"],
        ))
        if entry["physics_record_id"] is not None:
            collected.add(entry["physics_record_id"])
    return _source_json({
        "records": {key: records[key] for key in sorted(collected)},
        "lod_asset_ids": sorted({
            entry["asset_id"] for entry in entries
            if entry["visual_or_physics"] == "lod"
            or entry["asset_id"] in {
                body["document"]["asset_id"]
                for body in records.values()
                if isinstance(body.get("document"), dict)
                and body["document"].get("kind") == "procedural_mesh_lod_set"
            }
        }),
        "physics_asset_ids": sorted({
            entry["asset_id"] for entry in entries
            if entry["physics_record_id"] is not None
        }),
        "metadata": compiled["metadata"],
    })


def verify_original_mesh_placement_source_bundle(
    raw: bytes, *, published_scene: str,
    published_root: str,
) -> dict[str, Any]:
    """Replay actual child scene + native root binding from retained records."""
    if not isinstance(raw, bytes) or len(raw) > 1024 * 1024:
        raise OriginalMeshPlacementError("placement source archive oversized")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise OriginalMeshPlacementError("placement source JSON invalid") from exc
    if (type(payload) is not dict or set(payload) != {
            "records", "lod_asset_ids", "physics_asset_ids", "metadata",
    } or _source_json(payload) != raw):
        raise OriginalMeshPlacementError("placement source not exact canonical JSON")
    try:
        compiled = compile_original_mesh_placements(
            payload["records"],
            lod_assets=frozenset(payload["lod_asset_ids"]),
            physics_assets=frozenset(payload["physics_asset_ids"]),
        )
        if (compiled["metadata"] != payload["metadata"]
                or compiled["files"][PLACEMENT_SCENE] != published_scene):
            raise OriginalMeshPlacementError("mesh placement differs from reviewed source")
        from skeleton.jeeves.game_frontier_expedition_godot import _GODOT_SCENE
        expected_root = attach_authored_meshes_to_expedition(
            _GODOT_SCENE, compiled,
        )
        if expected_root != published_root:
            raise OriginalMeshPlacementError(
                "published playable Godot root did not instantiate authored meshes"
            )
    except (KeyError, TypeError, OriginalMeshError) as exc:
        raise OriginalMeshPlacementError(
            "mesh source records cannot reproduce the game world"
        ) from exc
    return {
        "schema_version": "skeleton.jeeves.original_mesh_placement_replay.v1",
        "instances_replayed": compiled["metadata"]["instance_count"],
        "scene_sha256": sha256(published_scene.encode("utf-8")).hexdigest(),
        "root_sha256": sha256(published_root.encode("utf-8")).hexdigest(),
        "actual_3d_assets_instanced_in_source_scene": True,
        "native_engine_scene_import_verified": False,
        "framebuffer_render_or_collision_observed": False,
    }


__all__ = [
    "OriginalMeshPlacementError", "compile_original_mesh_placements",
    "attach_authored_meshes_to_expedition",
    "compile_original_mesh_placement_source_bundle",
    "verify_original_mesh_placement_source_bundle",
]
