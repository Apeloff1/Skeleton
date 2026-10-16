"""Chained, resumable Director playthrough evidence over bounded action segments.

This module deliberately reuses the canonical DirectorWorld and director_step.
There is no cumulative project step or recording cap: each submitted segment
has a bounded size, but state and exact digest links survive every boundary.
A journal validates action legality and recorded checkpoints; it does not
certify a graphical engine, native installation or real user playthrough.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any

from .quest_scene_engine import (
    MAX_EVENTS, DirectorAction, DirectorState, DirectorWorld,
    director_initial, director_step,
)

SCHEMA = "skeleton.game_builder.director_segment_chain.v1"
_HEX = re.compile(r"^[0-9a-f]{64}$")


class DirectorSegmentError(ValueError):
    """A segment is malformed, out of order, or diverges from Director state."""


def _hash(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class SegmentedDirectorTrace:
    final: DirectorState
    digest: str
    action_count: int
    segment_receipts: tuple[dict[str, Any], ...]


def replay_director_segments(
    world: DirectorWorld, segments: Any,
) -> SegmentedDirectorTrace:
    """Verify every consecutive signed checkpoint from the real genesis.

    Each segment is an independent resource-bounded replay slice with
    exactly actions, start_digest and end_digest. The caller may append
    further segments without resetting quest progress, choices, inventory
    or world state. Checkpoints are *recomputed* rather than blindly trusted.
    """
    if not isinstance(world, DirectorWorld):
        raise DirectorSegmentError("original typed DirectorWorld required")
    if not isinstance(segments, list) or not segments:
        raise DirectorSegmentError("at least one nonempty action segment required")
    state = director_initial(world)
    receipts: list[dict[str, Any]] = []
    previous = _hash({"schema": SCHEMA, "world": world.digest, "genesis": state.digest})
    total_actions = 0
    for number, segment in enumerate(segments, 1):
        if not isinstance(segment, dict) or set(segment) != {
            "actions", "start_digest", "end_digest"
        }:
            raise DirectorSegmentError("segment needs actions and exact start/end checkpoints")
        start_digest, end_digest = segment["start_digest"], segment["end_digest"]
        if not isinstance(start_digest, str) or not _HEX.fullmatch(start_digest):
            raise DirectorSegmentError("invalid segment start checkpoint hash")
        if not isinstance(end_digest, str) or not _HEX.fullmatch(end_digest):
            raise DirectorSegmentError("invalid segment end checkpoint hash")
        if start_digest != state.digest:
            raise DirectorSegmentError("missing or out-of-order Director state checkpoint")
        raw = segment["actions"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_EVENTS:
            raise DirectorSegmentError("segment exceeds bounded per-slice action budget")
        actions: list[DirectorAction] = []
        for entry in raw:
            if not isinstance(entry, dict) or set(entry) != {"kind", "key", "scene"}:
                raise DirectorSegmentError("segment contains non-Director player action")
            actions.append(DirectorAction(**entry))
        beginning = state
        for action in actions:
            state = director_step(world, state, action)
        if state.digest != end_digest:
            raise DirectorSegmentError("Director replay diverged from recorded end checkpoint")
        # Deterministic second pass from the independently held starting
        # state: no saved packet can install/replace an untrusted DirectorState.
        verification = beginning
        for action in actions:
            verification = director_step(world, verification, action)
        if verification != state:
            raise DirectorSegmentError("Director segment is not deterministic")
        action_hash = _hash([action.payload() for action in actions])
        record = {
            "segment": number,
            "start_digest": start_digest,
            "end_digest": end_digest,
            "action_count": len(actions),
            "actions_sha256": action_hash,
            "completed_quests": len(state.complete),
            "executed_quest_stages": len(state.results),
            "previous_receipt_sha256": previous,
        }
        record["receipt_sha256"] = _hash({
            "schema": SCHEMA, "world": world.digest, **record,
        })
        previous = record["receipt_sha256"]
        receipts.append(record)
        total_actions += len(actions)
    return SegmentedDirectorTrace(
        final=state, digest=previous, action_count=total_actions,
        segment_receipts=tuple(receipts),
    )
