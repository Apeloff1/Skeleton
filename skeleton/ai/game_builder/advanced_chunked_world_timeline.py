"""Original chunked NPC bookmarks, timeline forks and verifiable resume.

Bookmarks store real event-chain positions, never unverified GPU/LLM state.
Resume and branching independently reconstruct original authored world actions
from the genesis source, so the authority never trusts supplied actor snapshots.
The implementation explicitly makes NO claim of constant-time restoration:
this is a correctness-first, bounded, source-verified savegame prototype.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_chunked_npc_world import (
    SCHEMA as GAME_SCHEMA, ChunkWorldError,
    run_chunked_npc_world, verify_chunked_npc_world,
)

SCHEMA = "skeleton.game_builder.original_streaming_bookmarks.v1"
BRANCH_SCHEMA = "skeleton.game_builder.original_streaming_branch.v1"
MAX_BOOKMARKS = 17


class ChunkTimelineError(ChunkWorldError):
    """A source checkpoint, fork or continuation is invalid or forged."""


def _hash(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ChunkTimelineError("noncanonical original timeline evidence") from exc
    if len(raw) > 500_000:
        raise ChunkTimelineError("original timeline receipt exceeds 500 kB source budget")
    return sha256(raw).hexdigest()


def _as_game(receipt):
    if type(receipt) is not dict or receipt.get("schema") != GAME_SCHEMA:
        raise ChunkTimelineError("source-verified chunked world required")
    try:
        if not verify_chunked_npc_world(receipt):
            raise ChunkTimelineError("original game source did not independently replay")
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise ChunkTimelineError("original world source or state was forged") from exc
    return receipt


def make_chunked_bookmarks(receipt, *, interval=8):
    source = _as_game(receipt)
    if type(interval) is not int or not 8 <= interval <= 64:
        raise ChunkTimelineError("bookmark interval must be 8..64 original turns")
    trace = source["trace"]
    count = len(source["commands"])
    cursors = sorted({0, count, *(range(interval, count+1, interval))})
    if len(cursors) > MAX_BOOKMARKS:
        raise ChunkTimelineError("bounded source timeline exceeds 17 bookmarks")
    if trace:
        genesis = trace[0]["previous"]
        first_state = trace[0]["before"]
    else:
        genesis = source["head_digest"]
        first_state = None
    bookmarks = []
    for cursor in cursors:
        if cursor == 0:
            digest, state_digest = genesis, first_state
        else:
            row = trace[cursor-1]
            digest = row["digest"]
            state_digest = row["after"]
        bookmarks.append({
            "cursor":cursor,"action_head":digest,
            "result_state_digest":state_digest,
            "source_actors":source["physical_actor_count"],
            "parent_world_digest":source["digest"],
            "kind":"actual_replayed_original_world_cursor",
        })
    body = {
        "schema":SCHEMA, "source_world":source,
        "interval":interval,"bookmarks":bookmarks,
        "source_world_digest":source["digest"],
        "source_actor_count":source["physical_actor_count"],
        "actual_end_cursor":count,
        "bookmarks_are_source_verified":True,
        "model_weights_promoted":False,
        "source_project_mutated":False,
        "native_restore_speed_certified":False,
    }
    return {**body,"digest":_hash(body)}


def verify_chunked_bookmarks(record):
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise ChunkTimelineError("exact chunked timeline receipt schema required")
    try:
        expected = make_chunked_bookmarks(
            record["source_world"], interval=record["interval"]
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise ChunkTimelineError("missing original timeline source or interval") from exc
    if expected != record:
        raise ChunkTimelineError("original bookmarks, source heads or world history modified")
    return True


def continue_chunked_world(checkpoint, additional_actions, *, cursor=None):
    """Proof-preserving continuation or explicit alternative-history fork."""
    if not verify_chunked_bookmarks(checkpoint):
        raise ChunkTimelineError("checkpoint proof could not be verified")
    if type(additional_actions) not in (list, tuple):
        raise ChunkTimelineError("continuation must contain bounded original actions")
    if type(cursor) is not int and cursor is not None:
        raise ChunkTimelineError("alternative-history cursor must be an exact integer")
    base = checkpoint["source_world"]
    start = len(base["commands"]) if cursor is None else cursor
    indexed = {point["cursor"]:point for point in checkpoint["bookmarks"]}
    if start not in indexed:
        raise ChunkTimelineError("fork must start at a source-verified timeline bookmark")
    if len(additional_actions)>128-start:
        raise ChunkTimelineError("continuation exceeds finite world action budget")
    if any(type(action) is not str or not 1 <= len(action) <= 32
           for action in additional_actions):
        raise ChunkTimelineError("original continuation contains unsupported command form")
    original_prefix = base["commands"][:start]
    if start:
        phase = base["trace"][start-1]
        if (indexed[start]["action_head"] != phase["digest"] or
            indexed[start]["result_state_digest"] != phase["after"]):
            raise ChunkTimelineError("fork source head does not match original action ledger")
    new_commands = original_prefix + list(additional_actions)
    try:
        result = run_chunked_npc_world(
            new_commands,base["settings"],
            scenes=base["source_scenes"],seed=base["seed"],
            options=base["options"],
        )
    except (ChunkWorldError, ValueError, TypeError, KeyError) as exc:
        raise ChunkTimelineError("original continuation rejected illegal physical action") from exc
    if not verify_chunked_npc_world(result):
        raise ChunkTimelineError("continued authored world could not independently replay")
    body = {
        "schema":BRANCH_SCHEMA,"source_checkpoint":checkpoint,
        "cursor":start,"source_cursor_head":indexed[start]["action_head"],
        "appended_actions":list(additional_actions),
        "discarded_future_actions":base["commands"][start:],
        "result":result,
        "result_world_digest":result["digest"],
        "resumed_from_original_source":True,
        "incremental_snapshot_restore_claimed":False,
        "source_files_modified":False,
        "ai_model_weights_promoted":False,
        "gameplay_hardware_certified":False,
    }
    return {**body,"digest":_hash(body)}


def verify_chunked_continuation(record):
    if type(record) is not dict or record.get("schema") != BRANCH_SCHEMA:
        raise ChunkTimelineError("exact original streamed timeline branch schema required")
    try:
        expected = continue_chunked_world(
            record["source_checkpoint"],
            record["appended_actions"],cursor=record["cursor"],
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise ChunkTimelineError("source fork fields missing or invalid") from exc
    if expected != record:
        raise ChunkTimelineError("saved source branch, state or actor history forged")
    return True


__all__ = [
    "SCHEMA","BRANCH_SCHEMA","ChunkTimelineError",
    "make_chunked_bookmarks","verify_chunked_bookmarks",
    "continue_chunked_world","verify_chunked_continuation",
]
