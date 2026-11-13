"""Original, fully authored NPC cast and waypoint patrol source for Godot 4.

An NPC only exists if an approved project source record explicitly supplies
its ID, first real world waypoint, and optional waypoint patrol. This module
does not fabricate NPCs, invent AI autonomy, or infer spatial positions from
unrelated Forge map layers. The native Expedition engine already loads the
emitted cast JSON and advances declared routes through its NPC marker plane.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any

from skeleton.jeeves.game_frontier_expedition import ExpeditionWorld

from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.authored_npc_cast.v1"
ENGINE_SCHEMA = "skeleton.game.original_npc_cast.v1"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
FIELDS = frozenset({
    "kind", "npc_id", "home_waypoint_id", "patrol_waypoint_ids",
})
MAX_CAST = 64
MAX_PATROL = 256


class OriginalNpcCastError(ValueError):
    """Original authored NPC identity or gameplay placement cannot compile."""


def compile_original_npc_cast(
    records: Mapping[str, Mapping[str, Any]], world: ExpeditionWorld,
    *, world_source_record_id: str,
) -> dict[str, Any] | None:
    if not isinstance(world, ExpeditionWorld):
        raise OriginalNpcCastError("real typed authored ExpeditionWorld required")
    if not isinstance(records, Mapping):
        raise OriginalNpcCastError("canonical original project source required")
    nodes = world.by_id
    cast: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    ids: set[str] = set()
    for record_id, record in sorted(records.items()):
        doc = record.get("document")
        if not isinstance(doc, Mapping) or doc.get("kind") != "npc_spawn":
            continue
        if (record.get("record_id") != record_id
                or record.get("facet") not in ("npc", "cast", "scene_forge")
                or set(doc) != FIELDS):
            raise OriginalNpcCastError("NPC spawn requires exact reviewed gameplay source")
        identity = doc["npc_id"]
        if (type(identity) is not str or ID.fullmatch(identity) is None
                or identity in ids):
            raise OriginalNpcCastError("original character identity is duplicated or unsafe")
        ids.add(identity)
        home = doc["home_waypoint_id"]
        patrol = doc["patrol_waypoint_ids"]
        if (type(home) is not str or home not in nodes
                or type(patrol) is not list or len(patrol) > MAX_PATROL
                or any(type(step) is not str or step not in nodes for step in patrol)):
            raise OriginalNpcCastError(
                "NPC home and patrol must reference real authored world waypoint IDs"
            )
        parents = record.get("depends_on")
        if (type(parents) is not list
                or world_source_record_id not in parents):
            raise OriginalNpcCastError(
                "NPC must depend on the exact original source of its world topology"
            )
        source_digest = record.get("source_sha256")
        revision = record.get("revision")
        if (type(revision) is not int or revision < 1
                or source_digest != digest([
                    record_id, record["facet"], revision, doc, parents,
                ])):
            raise OriginalNpcCastError("NPC spawn changed after its original source revision")
        cast.append({
            "design": {"npc_id": identity, "home": home},
            "proof": {
                "steps": [{"new": location} for location in patrol],
                "patrol_is_authored_not_autonomous_ai": True,
            },
        })
        sources.append({
            "record_id": record_id, "source_sha256": source_digest,
            "npc_id": identity, "home_waypoint_id": home,
            "patrol_waypoint_ids": list(patrol),
        })
        if len(cast) > MAX_CAST:
            raise OriginalNpcCastError("original world NPC cast exceeds native density budget")
    if not cast:
        return None
    body = {
        "schema": ENGINE_SCHEMA,
        "world_digest": world.digest,
        "cast": cast,
    }
    data = json.dumps(
        body, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )
    proof = {
        "schema_version": SCHEMA,
        "project_id": world.project_id,
        "world_digest": world.digest,
        "world_source_record_id": world_source_record_id,
        "npc_source_records": sources,
        "npc_count": len(cast),
        "authored_patrol_steps": sum(
            len(entry["proof"]["steps"]) for entry in cast
        ),
        "native_cast_json_sha256": sha256(data.encode("utf-8")).hexdigest(),
        "native_engine_npc_process_executed": False,
        "npc_autonomous_intelligence_claimed": False,
    }
    proof["receipt_sha256"] = digest(proof)
    return {"content": data, "receipt": proof}


def verify_original_npc_cast(
    content: str, proof: Mapping[str, Any], *,
    world_digest: str,
) -> dict[str, Any]:
    if type(content) is not str or len(content.encode("utf-8")) > 2_000_000:
        raise OriginalNpcCastError("native NPC cast requires bounded JSON text")
    if (not isinstance(proof, Mapping)
            or proof.get("world_digest") != world_digest
            or proof.get("native_cast_json_sha256")
            != sha256(content.encode("utf-8")).hexdigest()):
        raise OriginalNpcCastError("NPC cast bytes or original world hash differ")
    payload = dict(proof)
    signature = payload.pop("receipt_sha256", None)
    if signature != digest(payload):
        raise OriginalNpcCastError("native NPC cast receipt lineage differs")
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise OriginalNpcCastError("NPC native cast source is invalid JSON") from exc
    if (type(parsed) is not dict or parsed.get("schema") != ENGINE_SCHEMA
            or parsed.get("world_digest") != world_digest
            or not isinstance(parsed.get("cast"), list)):
        raise OriginalNpcCastError("native NPC cast belongs to a different original world")
    cast = parsed["cast"]
    source = proof.get("npc_source_records")
    if (len(cast) != proof.get("npc_count") or len(cast) > MAX_CAST
            or type(source) is not list or len(source) != len(cast)):
        raise OriginalNpcCastError("NPC source count does not match authored cast")
    reconstructed = []
    for entry in source:
        if not isinstance(entry, dict):
            raise OriginalNpcCastError("original NPC source record is not typed")
        patrol = entry.get("patrol_waypoint_ids")
        if (type(patrol) is not list or len(patrol) > MAX_PATROL
                or not all(type(point) is str for point in patrol)):
            raise OriginalNpcCastError("native patrol source does not match reviewed steps")
        reconstructed.append({
            "design": {
                "npc_id": entry["npc_id"],
                "home": entry["home_waypoint_id"],
            },
            "proof": {
                "steps": [{"new": point} for point in patrol],
                "patrol_is_authored_not_autonomous_ai": True,
            },
        })
    if cast != reconstructed:
        raise OriginalNpcCastError("authored NPCs or patrol path differ from source receipts")
    check = {
        "schema_version": "skeleton.jeeves.original_npc_cast_disk_check.v1",
        "world_digest": world_digest,
        "cast_sha256": sha256(content.encode("utf-8")).hexdigest(),
        "npc_count": len(cast),
        "all_character_source_receipts_replayed": True,
        "actual_npc_engine_movement_observed": False,
    }
    check["receipt_sha256"] = digest(check)
    return check


__all__ = [
    "OriginalNpcCastError", "compile_original_npc_cast",
    "verify_original_npc_cast",
]
