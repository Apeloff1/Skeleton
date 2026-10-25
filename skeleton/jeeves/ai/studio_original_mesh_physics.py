"""Authored Godot 4 collision/physics compiler for real original 3D meshes.

Geometry is rebuilt from reviewed parametric source. The StaticBody3D,
RigidBody3D or Area3D scene refers to the actual GLB/LOD PackedScene, not a
placeholder collider. Convex collision points, shapes, author permissions,
mass and physical materials are source-verified and SHA-replayable.
"""
from __future__ import annotations

from typing import Any

from collections.abc import Mapping
from hashlib import sha256
from math import pi
import json

from .studio_interaction_contract import digest
from .studio_original_mesh import (
    OriginalMeshError, _geometry, _source, compile_original_mesh,
)

SCHEMA = "skeleton.jeeves.original_mesh_physics.v1"
DOC_KEYS = frozenset({
    "kind", "base_record_id", "asset_id", "body_type",
    "density_kg_m3", "friction_per_mille", "restitution_per_mille",
    "collision_layer", "collision_mask",
})
BODY_TYPES = frozenset({"static", "rigid", "area"})
MAX_PHYSICS_BODIES = 64
MAX_CONVEX_POINTS = 512


class OriginalMeshPhysicsError(ValueError):
    """Original 3D physics source, geometry, or Godot scene is not trustworthy."""


def _author(base: Mapping[str, Any], physics: Mapping[str, Any]) -> dict[str, Any]:
    try:
        mesh = _source(base)
    except OriginalMeshError as exc:
        raise OriginalMeshPhysicsError("physics base is not reviewed mesh geometry") from exc
    if (not isinstance(physics, Mapping) or physics.get("facet") != "physics"
            or type(physics.get("document")) is not dict):
        raise OriginalMeshPhysicsError("physics source must use the physics facet")
    doc = physics["document"]
    if (set(doc) != DOC_KEYS or doc["kind"] != "procedural_mesh_physics"
            or doc["base_record_id"] != base["record_id"]
            or doc["asset_id"] != mesh["asset_id"]
            or type(doc["body_type"]) is not str
            or doc["body_type"] not in BODY_TYPES):
        raise OriginalMeshPhysicsError("physics source requires matching GLB identity")
    for key, lower, upper in (
        ("density_kg_m3", 100, 30000),
        ("friction_per_mille", 0, 1000),
        ("restitution_per_mille", 0, 1000),
        ("collision_layer", 1, 1048575),
        ("collision_mask", 0, 1048575),
    ):
        val = doc[key]
        if type(val) is not int or not lower <= val <= upper:
            raise OriginalMeshPhysicsError(key + " outside bounded physics policy")
    if mesh["primitive"] == "plane" and doc["body_type"] == "rigid":
        raise OriginalMeshPhysicsError("a source plane cannot be a rigid volume")
    deps = physics.get("depends_on")
    rid, version = physics.get("record_id"), physics.get("revision")
    if (type(rid) is not str or not rid
            or type(version) is not int or not 1 <= version <= 1_000_000
            or type(deps) is not list or len(deps) > 32
            or base["record_id"] not in deps
            or len(set(deps)) != len(deps)
            or any(type(x) is not str for x in deps)
            or physics.get("source_sha256") != digest([
                rid, "physics", version, doc, deps,
            ])):
        raise OriginalMeshPhysicsError("physics settings lack approved revision lineage")
    return doc


def _float(value: float) -> str:
    if not -1e9 < value < 1e9:
        raise OriginalMeshPhysicsError("non-finite or unbounded geometry coordinate")
    rendered = format(value, ".8f")
    return "0.00000000" if rendered == "-0.00000000" else rendered


def _collider(mesh: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    primitive = mesh["primitive"]
    dims = [value / 1000 for value in mesh["size_mm"]]
    if primitive in ("box", "plane"):
        sx, sy, sz = dims
        height = sy if primitive == "box" else 0.01
        props = [
            '[sub_resource type="BoxShape3D" id="ColliderShape"]',
            "size = Vector3(" + ", ".join(map(_float, (sx, height, sz))) + ")",
        ]
        return props, {
            "shape": "BoxShape3D",
            "dimensions_m": [sx, height, sz],
            "source_is_finite_plane": primitive == "plane",
            "convex_point_count": 0,
            "convex_geometry_sha256": None,
        }
    if primitive == "uv_sphere" and len(set(mesh["size_mm"])) == 1:
        radius = dims[0] / 2
        return [
            '[sub_resource type="SphereShape3D" id="ColliderShape"]',
            "radius = " + _float(radius),
        ], {
            "shape": "SphereShape3D",
            "dimensions_m": dims,
            "source_is_finite_plane": False,
            "convex_point_count": 0, "convex_geometry_sha256": None,
        }
    if primitive == "cylinder" and mesh["size_mm"][0] == mesh["size_mm"][2]:
        return [
            '[sub_resource type="CylinderShape3D" id="ColliderShape"]',
            "height = " + _float(dims[1]),
            "radius = " + _float(dims[0] / 2),
        ], {
            "shape": "CylinderShape3D",
            "dimensions_m": dims,
            "source_is_finite_plane": False,
            "convex_point_count": 0, "convex_geometry_sha256": None,
        }
    # An ellipsoid or elliptical cylinder cannot be represented by a uniform
    # primitive without distorting collision geometry. Build a real convex
    # point shape from the EXACT source-generated GLB position vertices.
    vertices, _ = _geometry(mesh)
    point_lookup: dict[tuple[str, ...], None] = {}
    for vertex in vertices:
        point_lookup[tuple(_float(x) for x in vertex[:3])] = None
    points = sorted(point_lookup)
    if not 4 <= len(points) <= MAX_CONVEX_POINTS:
        raise OriginalMeshPhysicsError("convex collider exceeds explicit vertex budget")
    rendered = ", ".join(
        "Vector3(" + ", ".join(position) + ")" for position in points
    )
    return [
        '[sub_resource type="ConvexPolygonShape3D" id="ColliderShape"]',
        "points = PackedVector3Array([" + rendered + "])",
    ], {
        "shape": "ConvexPolygonShape3D",
        "dimensions_m": dims,
        "source_is_finite_plane": False,
        "convex_point_count": len(points),
        "convex_geometry_sha256": digest(points),
    }


def _volume(mesh: Mapping[str, Any]) -> float:
    x, y, z = [dim / 1000 for dim in mesh["size_mm"]]
    if mesh["primitive"] == "box":
        return x * y * z
    if mesh["primitive"] == "cylinder":
        return pi * x * y * z / 4
    if mesh["primitive"] == "uv_sphere":
        return pi * x * y * z / 6
    raise OriginalMeshPhysicsError("a zero-volume plane cannot carry rigid mass")


def compile_original_mesh_physics(
    mesh_record: Mapping[str, Any], source_record: Mapping[str, Any],
    *, has_lod: bool = False,
) -> dict[str, Any]:
    if type(has_lod) is not bool:
        raise OriginalMeshPhysicsError("LOD binding must be explicit")
    doc = _author(mesh_record, source_record)
    primitive = _source(mesh_record)
    compiled_glb = compile_original_mesh(mesh_record)["metadata"]
    shape, collider = _collider(primitive)
    body_type = doc["body_type"]
    mass_kg = None
    if body_type == "rigid":
        mass_kg = _volume(primitive) * doc["density_kg_m3"]
        if not 0.01 <= mass_kg <= 200000:
            raise OriginalMeshPhysicsError("derived rigid mass exceeds stable bounds")
    asset = primitive["asset_id"]
    root = "game/frontier/meshes/" + asset
    model_scene = root + (".lod.tscn" if has_lod else ".glb")
    model_type = "PackedScene"
    lines = [
        "[gd_scene load_steps=" + ("3" if body_type == "area" else "4")
        + " format=3]",
        "",
        '[ext_resource type="' + model_type + '" path="res://' + model_scene
        + '" id="OriginalModel"]',
        "",
    ]
    if body_type != "area":
        lines += [
            '[sub_resource type="PhysicsMaterial" id="OriginalPhysicsMaterial"]',
            "friction = " + _float(doc["friction_per_mille"] / 1000),
            "bounce = " + _float(doc["restitution_per_mille"] / 1000),
            "",
        ]
    lines += shape + [
        "",
        '[node name="OriginalPhysicsBody" type="' + {
            "static": "StaticBody3D",
            "rigid": "RigidBody3D",
            "area": "Area3D",
        }[body_type] + '"]',
        "collision_layer = " + str(doc["collision_layer"]),
        "collision_mask = " + str(doc["collision_mask"]),
    ]
    if body_type != "area":
        lines.append(
            'physics_material_override = SubResource("OriginalPhysicsMaterial")'
        )
    if body_type == "rigid":
        lines += [
            "mass = " + _float(mass_kg),
            "continuous_cd = true",
        ]
    if body_type == "area":
        lines += [
            "monitoring = true",
            "monitorable = true",
        ]
    lines += [
        "",
        '[node name="ImportedVisuals" parent="." instance=ExtResource("OriginalModel")]',
        "",
        '[node name="CollisionShape" type="CollisionShape3D" parent="."]',
        'shape = SubResource("ColliderShape")',
        "",
    ]
    scene = "\n".join(lines)
    metadata = {
        "schema_version": SCHEMA,
        "asset_id": asset, "body_type": body_type,
        "mesh_source_record_id": mesh_record["record_id"],
        "mesh_source_sha256": mesh_record["source_sha256"],
        "mesh_glb_sha256": compiled_glb["glb_sha256"],
        "physics_source_record_id": source_record["record_id"],
        "physics_source_sha256": source_record["source_sha256"],
        "lod_bound": has_lod, "visual_resource": model_scene,
        "physics_material_friction": doc["friction_per_mille"] / 1000,
        "physics_material_bounce": doc["restitution_per_mille"] / 1000,
        "collision_layer": doc["collision_layer"],
        "collision_mask": doc["collision_mask"],
        "collider": collider, "rigid_mass_kg": mass_kg,
        "scene_sha256": sha256(scene.encode("utf-8")).hexdigest(),
        "collision_geometry_from_original_mesh": True,
        "runtime_physics_executed": False,
        "actual_collision_observed": False,
    }
    metadata["receipt_sha256"] = digest(metadata)
    return {"metadata": metadata, "scene": scene}


def verify_original_mesh_physics(
    mesh_record: Mapping[str, Any], source_record: Mapping[str, Any],
    scene: str, metadata: Mapping[str, Any], *, has_lod: bool = False,
) -> dict[str, Any]:
    if not isinstance(scene, str) or not isinstance(metadata, Mapping):
        raise OriginalMeshPhysicsError("published physics resource is incomplete")
    checked = compile_original_mesh_physics(
        mesh_record, source_record, has_lod=has_lod,
    )
    if scene != checked["scene"] or dict(metadata) != checked["metadata"]:
        raise OriginalMeshPhysicsError(
            "Godot physics body/shape/material differs from authored mesh source"
        )
    return {
        "schema_version": "skeleton.jeeves.original_mesh_physics_replay.v1",
        "scene_sha256": sha256(scene.encode("utf-8")).hexdigest(),
        "source_receipt_sha256": metadata["receipt_sha256"],
        "collision_shape_replayed_from_original_mesh": True,
        "native_collision_observed": False,
    }


def compile_original_mesh_physics_collection(
    records: Mapping[str, Mapping[str, Any]], *,
    lod_asset_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(records, Mapping):
        raise OriginalMeshPhysicsError("physics compiler needs source record graph")
    if not isinstance(lod_asset_ids, frozenset):
        raise OriginalMeshPhysicsError("LOD source selection must be immutable")
    results = []
    seen: set[str] = set()
    for _, record in sorted(records.items()):
        doc = record.get("document") if isinstance(record, Mapping) else None
        if not isinstance(doc, dict) or doc.get("kind") != "procedural_mesh_physics":
            continue
        asset = doc.get("asset_id")
        base = records.get(doc.get("base_record_id"))
        if asset in seen or not isinstance(base, Mapping):
            raise OriginalMeshPhysicsError("missing or duplicate physics base mesh")
        seen.add(asset)
        compiled = compile_original_mesh_physics(
            base, record, has_lod=asset in lod_asset_ids,
        )
        results.append({
            "source_record": record, "base_record": base,
            "metadata": compiled["metadata"], "scene": compiled["scene"],
        })
    if len(results) > MAX_PHYSICS_BODIES:
        raise OriginalMeshPhysicsError("original physics resources exceed model budget")
    return {
        "schema_version": SCHEMA, "count": len(results),
        "assets": results, "native_engine_physics_verified": False,
    }


__all__ = [
    "OriginalMeshPhysicsError", "compile_original_mesh_physics",
    "verify_original_mesh_physics", "compile_original_mesh_physics_collection",
]
