"""Trusted in-process fast checkpoint forks for original chunk-streamed game worlds.

Preparation independently authenticates the original source timeline once.
Subsequent forks simulate *only* divergent suffix transitions using a private
copy of the validated source state and exact existing game transition rules.
The resulting full game receipts are byte-for-byte canonical equals to normal
from-genesis replay.  The in-process object is NOT a serialized trust token:
imported checkpoints and produced branch records still require full replay.
"""
from __future__ import annotations

from copy import deepcopy

from .advanced_chunked_npc_world import (
    SCHEMA as GAME_SCHEMA, MAX_STEPS, PHASES, ChunkWorldError,
    _act, _hash as world_hash, _schedule, _visible,
    run_chunked_npc_world, verify_chunked_npc_world,
)
from .advanced_chunked_world_timeline import (
    BRANCH_SCHEMA, ChunkTimelineError, _hash as timeline_hash,
    verify_chunked_bookmarks, verify_chunked_continuation,
    continue_chunked_world,
)

SCHEMA = "skeleton.game_builder.trusted_fast_chunk_forks.v1"
MAX_BRANCHES = 12


def _source_check(checkpoint, cursor):
    if not verify_chunked_bookmarks(checkpoint):
        raise ChunkTimelineError("checkpoint lacks independent source replay")
    source = checkpoint["source_world"]
    end = len(source["commands"])
    if cursor is None:
        cursor = end
    if type(cursor) is not int:
        raise ChunkTimelineError("original checkpoint cursor must be an exact integer")
    points = {p["cursor"]: p for p in checkpoint["bookmarks"]}
    if cursor not in points:
        raise ChunkTimelineError("only independently verified bookmark cursors can be materialized")
    if cursor == end:
        prefix = deepcopy(source)
    else:
        prefix = run_chunked_npc_world(
            source["commands"][:cursor], source["settings"],
            scenes=source["source_scenes"], seed=source["seed"],
            options=source["options"],
        )
    attested = points[cursor]
    if (prefix["head_digest"] != attested["action_head"]
        or (cursor and prefix["trace"][-1]["after"]
            != attested["result_state_digest"])
        or prefix["commands"] != source["commands"][:cursor]
        or prefix["source_identities"] != source["source_identities"]):
        raise ChunkTimelineError("source checkpoint state disagrees with original receipt head")
    return prefix, cursor, points[cursor]


class VerifiedInProcessChunkSnapshot:
    """Integrity-sealed, in-memory-only authority; do not pickle or transport."""

    __slots__ = ("_checkpoint", "_prefix", "_seal", "_cursor", "_bookmark")

    def __init__(self, checkpoint, prefix, cursor, bookmark):
        self._checkpoint = deepcopy(checkpoint)
        self._prefix = deepcopy(prefix)
        self._seal = world_hash(self._prefix)
        self._cursor = cursor
        self._bookmark = deepcopy(bookmark)

    @property
    def cursor(self):
        return self._cursor

    @property
    def actor_count(self):
        self._check()
        return self._prefix["physical_actor_count"]

    def _check(self):
        # Protects accidental/unsafe mutation by callers holding a reference
        # to an in-process prepared snapshot; not a cryptographic signature.
        if world_hash(self._prefix) != self._seal:
            raise ChunkTimelineError("in-memory original source snapshot changed since verification")

    def fork(self, new_actions):
        """Run ONLY new actions and produce an exact canonical complete branch."""
        self._check()
        if type(new_actions) not in (tuple, list):
            raise ChunkTimelineError("bounded original action suffix must be an array")
        if len(new_actions) > MAX_STEPS - self._cursor:
            raise ChunkTimelineError("original finite game action capacity exhausted")
        prefix = self._prefix
        options = prefix["options"]
        if len(new_actions) > options["max_turns"] - self._cursor:
            raise ChunkTimelineError("original world configured turn limit exceeded")
        state = deepcopy(prefix["state"])
        frames = deepcopy(prefix["trace"])
        previous = prefix["head_digest"]
        rules = prefix["settings"]
        for step_number, command in enumerate(new_actions, start=self._cursor):
            if type(command) is not str or not 1 <= len(command) <= 32:
                raise ChunkTimelineError("unregistered or malformed original suffix action")
            before = world_hash(state)
            detailed, _ = _visible(state, options)
            try:
                events = _act(state, rules, options, command, detailed)
                movements = _schedule(state, rules, options)
            except (ChunkWorldError, ValueError, KeyError, TypeError) as exc:
                raise ChunkTimelineError("original physical suffix transition rejected") from exc
            state["last_events"] = events + (
                ["bounded_streamed_schedules_advanced"] if movements else [])
            frame = {
                "step": step_number, "command": command,
                "tick": state["tick"], "previous": previous,
                "before": before, "causal_events": events,
                "physical_moves": movements, "after": world_hash(state),
                "ordered_phases": list(PHASES),
            }
            frame["digest"] = world_hash(frame)
            previous = frame["digest"]
            frames.append(frame)
        # The canonical report shape matches the full replay engine exactly.
        report = {
            "schema": GAME_SCHEMA, "seed": prefix["seed"],
            "settings": deepcopy(prefix["settings"]),
            "source_scenes": deepcopy(prefix["source_scenes"]),
            "source_identities": deepcopy(prefix["source_identities"]),
            "options": deepcopy(prefix["options"]),
            "commands": prefix["commands"] + list(new_actions),
            "state": state, "trace": frames, "head_digest": previous,
            "physical_actor_count": len(state["actors"]),
            "streaming_is_deterministic": True,
            "offscreen_movement_was_not_fabricated": True,
            "gameplay_is_native_hardware_certified": False,
            "ai_model_weights_promoted": False,
            "source_files_mutated": False,
            "fully_simulated_offscreen_actor_count": 0,
        }
        report["digest"] = world_hash(report)
        checkpoint = deepcopy(self._checkpoint)
        body = {
            "schema": BRANCH_SCHEMA, "source_checkpoint": checkpoint,
            "cursor": self._cursor,
            "source_cursor_head": self._bookmark["action_head"],
            "appended_actions": list(new_actions),
            "discarded_future_actions": checkpoint["source_world"]["commands"][self._cursor:],
            "result": report, "result_world_digest": report["digest"],
            "resumed_from_original_source": True,
            "incremental_snapshot_restore_claimed": False,
            "source_files_modified": False,
            "ai_model_weights_promoted": False,
            "gameplay_hardware_certified": False,
        }
        body["digest"] = timeline_hash(body)
        return body


def prepare_verified_chunk_snapshot(checkpoint, *, cursor=None):
    """Expensive full verification is mandatory once per trusted preparation."""
    prefix, selected, bookmark = _source_check(checkpoint, cursor)
    return VerifiedInProcessChunkSnapshot(checkpoint, prefix, selected, bookmark)


def run_fast_chunk_branches(checkpoint, branches, *, cursor=None):
    """Batch divergent original stories with one shared full source verification."""
    if type(branches) not in (tuple, list) or not 1 <= len(branches) <= MAX_BRANCHES:
        raise ChunkTimelineError("one to twelve bounded original branches required")
    parsed = []
    names = set()
    for row in branches:
        if type(row) is not dict or set(row) != {"name", "actions"}:
            raise ChunkTimelineError("source branch must have exact name and actions")
        name, actions = row["name"], row["actions"]
        if (type(name) is not str or not 1 <= len(name) <= 32
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in name)
            or name in names):
            raise ChunkTimelineError("duplicate or unbounded original branch identity")
        names.add(name)
        if type(actions) not in (list, tuple) or len(actions) > MAX_STEPS:
            raise ChunkTimelineError("unbounded original branch actions")
        parsed.append((name, actions))
    source = prepare_verified_chunk_snapshot(checkpoint, cursor=cursor)
    results = []
    for name, actions in parsed:
        branch = source.fork(actions)
        world = branch["result"]["state"]
        results.append({
            "name": name, "cursor": source.cursor,
            "appended_actions": list(actions),
            "result_digest": branch["result_world_digest"],
            "result_head": branch["result"]["head_digest"],
            "state": {
                "tick": world["tick"], "player": world["player"],
                "physical_actor_count": len(world["actors"]),
                "detailed_updates": world["scheduler"]["detailed_updates"],
                "deferred_actor_turns": world["scheduler"]["deferred_actor_turns"],
                "physical_moves": world["scheduler"]["physical_moves"],
                "quests_resolved": world["completed"],
                "ending": world["finished"], "supplies": world["inventory"]["supplies"],
            },
        })
    body = {
        "schema": SCHEMA,
        "source_checkpoint": deepcopy(checkpoint),
        "source_cursor": source.cursor,
        "original_prefix_authentications": 1,
        "suffix_transitions_executed": sum(len(actions) for _name, actions in parsed),
        "prefix_transitions_reexecuted_during_branch_forks": 0,
        "full_replay_used_during_preparation": True,
        "native_speed_certified": False,
        "trust_scope": "single_validated_in_process_instance_only",
        "core_model_weights_promoted": False,
        "results": results,
    }
    body["digest"] = timeline_hash(body)
    return body


def verify_fast_chunk_branches(record):
    """Untrusted multi-branch receipt gets *full* verification, no fast trust."""
    if type(record) is not dict or record.get("schema") != SCHEMA:
        raise ChunkTimelineError("exact source-authenticated fork batch required")
    try:
        branches = [
            {"name": row["name"], "actions": row["appended_actions"]}
            for row in record["results"]
        ]
        expected = run_fast_chunk_branches(
            record["source_checkpoint"], branches,
            cursor=record["source_cursor"],
        )
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ChunkTimelineError("malformed original source branch batch") from exc
    if record != expected:
        raise ChunkTimelineError("source branch, final state, clock or ledger was forged")
    for row in record["results"]:
        historical = continue_chunked_world(
            record["source_checkpoint"],row["appended_actions"],
            cursor=record["source_cursor"],
        )
        if (not verify_chunked_continuation(historical)
            or not verify_chunked_npc_world(historical["result"])
            or historical["result_world_digest"] != row["result_digest"]
            or historical["result"]["head_digest"] != row["result_head"]):
            raise ChunkTimelineError("original branch full replay did not converge")
    return True


__all__ = [
    "SCHEMA", "MAX_BRANCHES", "VerifiedInProcessChunkSnapshot",
    "prepare_verified_chunk_snapshot", "run_fast_chunk_branches",
    "verify_fast_chunk_branches",
]
