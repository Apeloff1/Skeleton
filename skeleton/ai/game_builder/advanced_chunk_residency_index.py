"""Source-authenticated chunk residency and exact physical NPC neighborhood index.

This is an inspectable index over an *actually replayed* original streamed game,
not a generator of new actors or a claim that offscreen people took actions.
The stored bucket table supports bounded queries without scanning every resident
in the output query. Untrusted imported indexes are reconstructed from real game
source before use; no hash alone grants execution authority.
"""
from __future__ import annotations

import json

from .advanced_chunked_npc_world import (
    CHUNK_EDGE, ChunkWorldError, _chunk, _dist, _hash,
    verify_chunked_npc_world,
)

SCHEMA = "skeleton.game_builder.original_chunk_residency_index.v1"
QUERY_SCHEMA = "skeleton.game_builder.original_chunk_residency_query.v1"
MAX_INDEX_BYTES = 4_000_000
MAX_VISIBLE = 32
MAX_MOVES = 4096


class ChunkIndexError(ChunkWorldError):
    """Cannot prove a physical body, original chunk, query or history."""


def _validate_source(report):
    if type(report) is not dict:
        raise ChunkIndexError("an original game receipt is required")
    try:
        encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_INDEX_BYTES:
            raise ChunkIndexError("source world exceeds bounded index evidence size")
        if not verify_chunked_npc_world(report):
            raise ChunkIndexError("source game did not independently replay")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise ChunkIndexError("invalid source game JSON or historical receipt") from exc
    return report


def build_original_chunk_index(report):
    game = _validate_source(report)
    state = game["state"]
    side, chunks = state["side"], state["chunks_per_side"]
    if side != chunks * CHUNK_EDGE or chunks not in (3, 5):
        raise ChunkIndexError("original source-world geometry was altered")
    people = state["actors"]
    index = {}
    occupied = set()
    # All chunks are present, including empty chunks: queries never invent
    # unloaded or missing geometry simply because there are no residents.
    for cy in range(chunks):
        for cx in range(chunks):
            index[f"{cx}:{cy}"] = []
    for actor in people:
        cell = actor["position"]
        if (type(cell) is not int or not 0 <= cell < side * side
            or cell in occupied or cell in state["obstacles"]
            or cell == state["player"]):
            raise ChunkIndexError("actor placement violates single-body physical map")
        occupied.add(cell)
        cx, cy = _chunk(cell, side)
        index[f"{cx}:{cy}"].append({
            "actor_id": actor["id"], "source_index": actor["index"],
            "position": cell, "origin": actor["origin_kind"],
            "detailed_ticks": actor["detailed_ticks"],
            "deferred_ticks": actor["deferred_ticks"],
            "eligible_deferred_ticks": actor["eligible_deferred_ticks"],
        })
    for bucket in index.values():
        bucket.sort(key=lambda a: a["source_index"])
    all_ids = [a["actor_id"] for bucket in index.values() for a in bucket]
    if len(all_ids) != len(set(all_ids)) or len(all_ids) != len(people):
        raise ChunkIndexError("source body identity duplicated or missing")

    transfers = []
    movement_total = 0
    detailed_total = 0
    deferred_total = 0
    tick_details = []
    for frame in game["trace"]:
        proof = frame["lod_fidelity"]
        if (proof["actually_detailed"] + proof["deferred"] != len(people)
            or proof["actually_detailed"] != len(proof["selected_actor_ids"])
            or proof["phantom_updates"] != 0):
            raise ChunkIndexError("source LOD work record is inconsistent")
        detailed_total += proof["actually_detailed"]
        deferred_total += proof["deferred"]
        tick_details.append({
            "tick": frame["tick"], "source_head": frame["digest"],
            "detailed": proof["actually_detailed"],
            "deferred": proof["deferred"],
            "selected_actor_ids": list(proof["selected_actor_ids"]),
        })
        for move in frame["physical_moves"]:
            movement_total += 1
            if movement_total > MAX_MOVES:
                raise ChunkIndexError("original source movement journal too large")
            start = move["from_chunk"]
            finish = move["to_chunk"]
            if start != finish:
                transfers.append({
                    "tick": frame["tick"], "actor_id": move["actor"],
                    "from_chunk": list(start), "to_chunk": list(finish),
                    "from_cell": move["from"], "to_cell": move["to"],
                    "source_frame": frame["digest"],
                })
    if (detailed_total != state["scheduler"]["detailed_updates"]
        or deferred_total != state["scheduler"]["deferred_actor_turns"]
        or movement_total != state["scheduler"]["physical_moves"]):
        raise ChunkIndexError("source actor work and movement did not conserve")
    body = {
        "schema": SCHEMA, "source_game": game,
        "source_game_digest": game["digest"],
        "source_head": game["head_digest"],
        "tick": state["tick"], "side": side,
        "chunks_per_side": chunks, "player_position": state["player"],
        "physical_actor_count": len(people),
        "buckets": index,
        "chunk_transfers": transfers,
        "physical_movements_total": movement_total,
        "detailed_updates_total": detailed_total,
        "deferred_actor_turns_total": deferred_total,
        "per_turn_lod_receipts": tick_details,
        "all_original_bodies_indexed": True,
        "phantom_offscreen_progress": False,
        "indexed_query_uses_only_candidate_chunk_buckets": True,
        "constant_time_persistence_claimed": False,
        "native_engine_certified": False, "model_weights_promoted": False,
        "source_files_modified": False,
    }
    return {**body, "digest": _hash(body)}


def verify_original_chunk_index(document):
    if type(document) is not dict or document.get("schema") != SCHEMA:
        raise ChunkIndexError("exact source-verified original chunk-index schema required")
    try:
        expected = build_original_chunk_index(document["source_game"])
    except (KeyError, TypeError, IndexError, ValueError, RecursionError) as exc:
        raise ChunkIndexError("malformed original spatial source record") from exc
    if expected != document:
        raise ChunkIndexError("chunk location, actor, source frame or LOD proof forged")
    return True


def _query(query, chunks):
    if query is None:
        query = {}
    if type(query) is not dict or set(query) - {
        "center_chunk", "radius", "mode", "actor_id", "offset", "limit",
    }:
        raise ChunkIndexError("only bounded original chunk-query controls permitted")
    result = {
        "center_chunk": [chunks//2, chunks//2],
        "radius": 1, "mode": "all", "actor_id": None,
        "offset": 0, "limit": 16,
        **query,
    }
    center = result["center_chunk"]
    if (type(center) is not list or len(center) != 2
        or any(type(x) is not int or not 0 <= x < chunks for x in center)):
        raise ChunkIndexError("exact existing original chunk coordinates required")
    if type(result["radius"]) is not int or result["radius"] not in (0, 1):
        raise ChunkIndexError("bounded radius 0/1 only")
    if type(result["mode"]) is not str or result["mode"] not in (
        "all", "detailed_this_turn", "deferred_this_turn",
    ):
        raise ChunkIndexError("unsupported real NPC activity mode")
    if (type(result["offset"]) is not int or not 0 <= result["offset"] <= 128
        or type(result["limit"]) is not int or not 1 <= result["limit"] <= MAX_VISIBLE):
        raise ChunkIndexError("bounded index page controls required")
    identifier = result["actor_id"]
    if identifier is not None and (
        type(identifier) is not str or len(identifier) != len("original_chunk_npc:000")
        or not identifier.startswith("original_chunk_npc:")
        or not identifier[-3:].isascii() or not identifier[-3:].isdigit()
    ):
        raise ChunkIndexError("optional actor filter must be exact original ID")
    return result


def _query_authenticated(index, query):
    q = _query(query, index["chunks_per_side"])
    side = index["side"]
    state = index["source_game"]["state"]
    selected = set(state["detailed_actor_ids"])
    cx, cy = q["center_chunk"]
    area = []
    for yy in range(max(0, cy-q["radius"]),
                    min(index["chunks_per_side"], cy+q["radius"]+1)):
        for xx in range(max(0, cx-q["radius"]),
                        min(index["chunks_per_side"], cx+q["radius"]+1)):
            area.append([xx, yy])
    candidates = []
    for x, y in area:
        candidates.extend(index["buckets"][f"{x}:{y}"])
    gathered = []
    for actor in candidates:
        identity = actor["actor_id"]
        if q["actor_id"] is not None and identity != q["actor_id"]:
            continue
        # The genesis state has not executed a scheduling tick. No actor
        # can truthfully be classified as served or deferred *this turn*.
        if q["mode"] != "all" and state["tick"] == 0:
            continue
        is_detail = identity in selected
        if q["mode"] == "detailed_this_turn" and not is_detail:
            continue
        if q["mode"] == "deferred_this_turn" and is_detail:
            continue
        gathered.append({
            **actor, "actually_detailed_this_turn": is_detail,
            "distance_from_player": _dist(actor["position"],
                                          state["player"], side),
            "source_head": index["source_head"],
        })
    gathered.sort(key=lambda a: (a["distance_from_player"], a["source_index"]))
    page = gathered[q["offset"]:q["offset"]+q["limit"]]
    body = {
        "schema": QUERY_SCHEMA, "source_index": index,
        "source_index_digest": index["digest"], "query": q,
        "candidate_chunk_keys": [f"{x}:{y}" for x, y in area],
        "candidate_actor_entries_examined": len(candidates),
        "physical_actor_population": index["physical_actor_count"],
        "matching_actors": len(gathered),
        "residents": page, "returned_count": len(page),
        "next_offset": (
            q["offset"]+len(page)
            if q["offset"]+len(page) < len(gathered) else None
        ),
        "original_source_fully_authenticated": True,
        "query_does_not_move_npcs_or_mint_witnesses": True,
        "hardware_speed_benchmark_claimed": False,
        "model_weights_promoted": False,
    }
    return {**body, "digest": _hash(body)}


def query_original_chunk_index(index, *, query=None):
    verify_original_chunk_index(index)
    return _query_authenticated(index, query)


def verify_original_chunk_query(document):
    if type(document) is not dict or document.get("schema") != QUERY_SCHEMA:
        raise ChunkIndexError("exact source-verified chunk query record required")
    try:
        expected = query_original_chunk_index(
            document["source_index"], query=document["query"],
        )
    except (KeyError, TypeError, IndexError, ValueError, RecursionError) as exc:
        raise ChunkIndexError("malformed or unverified original chunk query") from exc
    if expected != document:
        raise ChunkIndexError("actor spatial query or actual NPC state was forged")
    return True


__all__ = [
    "SCHEMA", "QUERY_SCHEMA", "ChunkIndexError", "MAX_VISIBLE",
    "build_original_chunk_index", "verify_original_chunk_index",
    "query_original_chunk_index", "verify_original_chunk_query",
]
