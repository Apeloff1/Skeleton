"""Source-verified historical spatial playback for original streamed NPC games.

Reconstructs selected real world ticks from the original source and action
ledger. No generated interpolation, NPC teleport, guessed eyewitness or
fictional offscreen progress is used. Historical pages are derived from the
same tested physical chunk-residency index as the current-world inspector.
"""
from __future__ import annotations

from .advanced_chunk_residency_index import (
    ChunkIndexError, _validate_source, _query_authenticated,
    _query, build_original_chunk_index,
)
from .advanced_chunked_npc_world import run_chunked_npc_world, _hash

SCHEMA = "skeleton.game_builder.original_npc_historical_spatial_lens.v1"
MAX_EPOCHS = 12


def _turns(values, total):
    if type(values) not in (list, tuple) or not 1 <= len(values) <= MAX_EPOCHS:
        raise ChunkIndexError("select one to twelve actual original game turns")
    result = []
    previous = -1
    for t in values:
        if type(t) is not int or not 0 <= t <= total or t <= previous:
            raise ChunkIndexError("original history epochs must be unique increasing real turns")
        result.append(t)
        previous = t
    return result


def _original_head(game, turn):
    if turn:
        return game["trace"][turn - 1]["digest"]
    if game["trace"]:
        return game["trace"][0]["previous"]
    return game["head_digest"]


def _all_positions(game):
    return {actor["id"]: actor["position"] for actor in game["state"]["actors"]}


def analyze_original_spatial_epochs(source_game, turns, *, query=None):
    source_game = _validate_source(source_game)
    total = len(source_game["commands"])
    epochs = _turns(turns, total)
    spec = _query(query, source_game["state"]["chunks_per_side"])
    timeline = []
    last_positions = None
    previous_epoch = 0
    executed_prefix_work = 0
    for turn in epochs:
        if turn == total:
            replay = source_game
        else:
            replay = run_chunked_npc_world(
                source_game["commands"][:turn], source_game["settings"],
                scenes=source_game["source_scenes"],
                seed=source_game["seed"], options=source_game["options"],
            )
            executed_prefix_work += turn
        expected_head = _original_head(source_game, turn)
        if (replay["head_digest"] != expected_head
            or replay["source_identities"] != source_game["source_identities"]
            or replay["commands"] != source_game["commands"][:turn]
            or replay["state"]["tick"] != turn):
            raise ChunkIndexError("historical world diverged from actual original action-chain head")
        indexed = build_original_chunk_index(replay)
        page = _query_authenticated(indexed, spec)
        occupants = {
            chunk: len(members) for chunk, members in indexed["buckets"].items()
        }
        if sum(occupants.values()) != indexed["physical_actor_count"]:
            raise ChunkIndexError("historical original chunk population is not conserved")
        actor_positions = _all_positions(replay)
        if last_positions is None:
            changed = []
        else:
            changed = [
                actor for actor in sorted(actor_positions)
                if actor_positions[actor] != last_positions[actor]
            ]
            moving_ids = {
                step["actor"]
                for frame in source_game["trace"][previous_epoch:turn]
                for step in frame["physical_moves"]
            }
            if not set(changed).issubset(moving_ids):
                raise ChunkIndexError("unattested physical NPC displacement occurred")
        moved_steps = sum(
            len(frame["physical_moves"])
            for frame in source_game["trace"][previous_epoch:turn]
        )
        timeline.append({
            "turn": turn,
            "actual_source_head": indexed["source_head"],
            "original_world_digest": indexed["source_game_digest"],
            "physical_actor_count": indexed["physical_actor_count"],
            "player_position": replay["state"]["player"],
            "chunk_occupancy": occupants,
            "all_unique_original_actor_positions": actor_positions,
            "changed_body_ids_since_previous_epoch": changed,
            "real_one_tile_moves_in_interval": moved_steps,
            "detailed_update_count": indexed["detailed_updates_total"],
            "deferred_actor_turns": indexed["deferred_actor_turns_total"],
            "loaded_chunks": [list(c) for c in replay["state"]["loaded_chunks"]],
            "query": {
                "candidate_chunk_keys": page["candidate_chunk_keys"],
                "candidate_actor_entries_examined": page["candidate_actor_entries_examined"],
                "matching_actors": page["matching_actors"],
                "returned_count": page["returned_count"],
                "next_offset": page["next_offset"],
                "residents": page["residents"],
            },
        })
        last_positions = actor_positions
        previous_epoch = turn
    body = {
        "schema": SCHEMA,
        "source_game": source_game,
        "source_game_digest": source_game["digest"],
        "queried_original_turns": epochs,
        "bounded_spatial_query": spec,
        "historical_epoch_count": len(timeline),
        "epochs": timeline,
        "extra_prefix_transitions_replayed_during_index_build": executed_prefix_work,
        "source_transitions_are_real_not_interpolated": True,
        "full_origin_source_replay_verified": True,
        "model_weights_promoted": False,
        "original_game_files_changed": False,
        "native_engine_certified": False,
    }
    return {**body, "digest": _hash(body)}


def verify_original_spatial_epochs(record):
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise ChunkIndexError("exact original spatial timeline source schema required")
    try:
        expected = analyze_original_spatial_epochs(
            record["source_game"], record["queried_original_turns"],
            query=record["bounded_spatial_query"],
        )
    except (KeyError, IndexError, TypeError, ValueError, RecursionError) as exc:
        raise ChunkIndexError("invalid source game or spatial timeline record") from exc
    if expected != record:
        raise ChunkIndexError("historical NPC positions, world movement or index evidence forged")
    return True


__all__ = [
    "SCHEMA", "MAX_EPOCHS", "analyze_original_spatial_epochs",
    "verify_original_spatial_epochs",
]
