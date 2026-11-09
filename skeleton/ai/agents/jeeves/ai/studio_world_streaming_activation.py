"""Source-authored opt-in replacement of static mesh instances by Godot streaming.

A versioned scene_forge record explicitly selects streaming. The compiler
replaces precisely one existing real game-world instancing link and preserves
its scene hierarchy and all other game code. The published root can be
inverted to its exact signed static-root source for independent ZIP replay.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.world_streaming_activation.v1"
KIND = "original_world_streaming_policy"
SOURCE_PATH = "game/frontier/assets/world_streaming.source.json"
STATIC_LINK = (
    '[ext_resource type="PackedScene" '
    'path="res://game/frontier/mesh_placements.tscn" id="OriginalMeshes"]'
)
STREAM_LINK = (
    '[ext_resource type="PackedScene" '
    'path="res://game/frontier/assets/world_streamer.tscn" id="OriginalMeshes"]'
)
INSTANCE_LINK = (
    '[node name="OriginalMeshInstances" parent="." '
    'instance=ExtResource("OriginalMeshes")]'
)
MAX_SOURCE_BYTES = 32_768


class WorldStreamingActivationError(ValueError):
    """The streamer must never silently replace or duplicate game content."""


def _policy(record: Mapping[str, Any], placement: Mapping[str, Any]) -> dict[str, Any]:
    doc = record.get("document")
    if (record.get("facet") != "scene_forge"
            or type(doc) is not dict or set(doc) != {
                "kind", "mode", "view_radius_m", "instantiate_per_frame",
            } or doc["kind"] != KIND
            or doc["mode"] != "replace_static"
            or type(doc["view_radius_m"]) is not int
            or not 1 <= doc["view_radius_m"] <= 5000
            or type(doc["instantiate_per_frame"]) is not int
            or not 1 <= doc["instantiate_per_frame"] <= 32):
        raise WorldStreamingActivationError("streaming policy requires bounded source parameters")
    rid, version = record.get("record_id"), record.get("revision")
    deps = record.get("depends_on")
    approved = {
        item["author_record_id"]
        for item in placement.get("instances", [])
    }
    if (type(rid) is not str
            or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", rid) is None
            or type(version) is not int or not 1 <= version <= 1_000_000
            or type(deps) is not list or len(deps) > 32
            or len(deps) != len(set(deps))
            or any(type(x) is not str for x in deps)
            or not (set(deps) & approved)
            or record.get("source_sha256") != digest([
                rid, "scene_forge", version, doc, deps,
            ])):
        raise WorldStreamingActivationError(
            "source streaming policy needs signed lineage to a placed 3D mesh"
        )
    return doc


def compile_world_streaming_activation(
    records: Mapping[str, Mapping[str, Any]],
    placements: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(records, Mapping) or not isinstance(placements, Mapping):
        raise WorldStreamingActivationError("streaming mode needs reviewed source graph")
    source = dict(placements)
    seal = source.pop("receipt_sha256", None)
    if seal != digest(source):
        raise WorldStreamingActivationError("streaming placement graph is unsealed")
    policies = [
        record for record in records.values()
        if isinstance(record, Mapping)
        and isinstance(record.get("document"), Mapping)
        and record["document"].get("kind") == KIND
    ]
    if len(policies) > 1:
        raise WorldStreamingActivationError("only one streaming mode may control a game")
    record = policies[0] if policies else None
    if record is not None:
        doc = _policy(record, placements)
    else:
        doc = None
    receipt = {
        "schema_version": SCHEMA,
        "enabled": doc is not None,
        "mode": "replace_static" if doc is not None else "static",
        "streaming_source_record_id": record["record_id"] if record else None,
        "streaming_source_sha256": record["source_sha256"] if record else None,
        "placement_source_receipt_sha256": seal,
        "view_radius_m": doc["view_radius_m"] if doc else None,
        "instantiate_per_frame": doc["instantiate_per_frame"] if doc else None,
        "nonduplicating_scene_switch": True,
        "godot_streaming_observed": False,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return {"receipt": receipt, "source_record": record}


def replace_static_meshes_with_streaming(
    root: str, receipt: Mapping[str, Any],
) -> str:
    if not isinstance(root, str) or not isinstance(receipt, Mapping):
        raise WorldStreamingActivationError("streaming switch needs source scene")
    if not receipt.get("enabled"):
        return root
    if (receipt.get("schema_version") != SCHEMA
            or receipt.get("mode") != "replace_static"
            or receipt.get("receipt_sha256") != digest({
                k: v for k, v in receipt.items() if k != "receipt_sha256"
            })):
        raise WorldStreamingActivationError("source streaming mode is not sealed")
    if root.count(STATIC_LINK) != 1 or root.count(INSTANCE_LINK) != 1:
        raise WorldStreamingActivationError(
            "streaming switch cannot target unknown game hierarchy"
        )
    after = (
        INSTANCE_LINK + "\nview_radius_m = "
        + str(receipt["view_radius_m"]) + ".0\n"
        + "instantiate_per_frame = "
        + str(receipt["instantiate_per_frame"])
    )
    return root.replace(STATIC_LINK, STREAM_LINK, 1).replace(
        INSTANCE_LINK, after, 1,
    )


def recover_exact_static_mesh_scene(
    active_root: str, receipt: Mapping[str, Any],
) -> str:
    if not isinstance(active_root, str) or not isinstance(receipt, Mapping):
        raise WorldStreamingActivationError("streaming archive root is invalid")
    if not receipt.get("enabled"):
        return active_root
    after = (
        INSTANCE_LINK + "\nview_radius_m = "
        + str(receipt["view_radius_m"]) + ".0\n"
        + "instantiate_per_frame = "
        + str(receipt["instantiate_per_frame"])
    )
    if active_root.count(STREAM_LINK) != 1 or active_root.count(after) != 1:
        raise WorldStreamingActivationError(
            "published streaming game scene differs from source-owned switch"
        )
    static = active_root.replace(STREAM_LINK, STATIC_LINK, 1).replace(
        after, INSTANCE_LINK, 1,
    )
    if replace_static_meshes_with_streaming(static, receipt) != active_root:
        raise WorldStreamingActivationError(
            "streaming root cannot replay exact source-owned patch"
        )
    return static


def streaming_policy_source_bytes(
    compiled: Mapping[str, Any],
) -> bytes | None:
    receipt, record = compiled["receipt"], compiled["source_record"]
    if not receipt["enabled"]:
        return None
    raw = json.dumps(
        {"record": record, "receipt": receipt},
        ensure_ascii=True, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > MAX_SOURCE_BYTES:
        raise WorldStreamingActivationError("streaming source record too large")
    return raw


def verify_streaming_policy_archive(
    archive_raw: bytes | None, receipt: Mapping[str, Any],
    placement: Mapping[str, Any], root: str,
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise WorldStreamingActivationError("streaming export lacks policy receipt")
    if not receipt.get("enabled"):
        if archive_raw is not None:
            raise WorldStreamingActivationError("static scene contains false policy source")
        expected = compile_world_streaming_activation({}, placement)
        if expected["receipt"] != dict(receipt):
            raise WorldStreamingActivationError("static source policy was altered")
        return {"enabled": False, "static_root": root}
    if type(archive_raw) is not bytes or len(archive_raw) > MAX_SOURCE_BYTES:
        raise WorldStreamingActivationError("streaming source was not published")
    try:
        policy = json.loads(archive_raw)
        if (type(policy) is not dict or set(policy) != {"record", "receipt"}
                or json.dumps(
                    policy, ensure_ascii=True, sort_keys=True,
                    allow_nan=False, separators=(",", ":"),
                ).encode("utf-8") != archive_raw):
            raise WorldStreamingActivationError("streaming policy not canonical")
        record = policy["record"]
        compiled = compile_world_streaming_activation(
            {record["record_id"]: record}, placement,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WorldStreamingActivationError(
            "published streaming activation source cannot replay"
        ) from exc
    if policy["receipt"] != dict(receipt) or compiled["receipt"] != dict(receipt):
        raise WorldStreamingActivationError("streaming runtime configuration changed")
    static = recover_exact_static_mesh_scene(root, receipt)
    return {
        "enabled": True,
        "static_root": static,
        "source_sha256": sha256(archive_raw).hexdigest(),
    }


__all__ = [
    "WorldStreamingActivationError", "compile_world_streaming_activation",
    "replace_static_meshes_with_streaming", "recover_exact_static_mesh_scene",
    "streaming_policy_source_bytes", "verify_streaming_policy_archive",
    "SOURCE_PATH", "STATIC_LINK", "STREAM_LINK",
]
