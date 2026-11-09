"""Bounded long-form controller replay with receipt-linked 64-frame segments.

The underlying integer physics and goal detection are delegated to the
verified platformer_replay primitive. Results are deterministic source-game
evidence, NOT native emulator/hardware certification or AI training.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .gameplay_capabilities import GameplayError, MAX_FRAMES, platformer_replay

MAX_LONG_REPLAY_FRAMES = 16_384
MAX_START_FRAME = 2_147_483_647
_HASH = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def replay_long_controller(arguments: dict[str, Any]) -> dict[str, Any]:
    """Replay 1–16,384 controller frames in segments and chain their receipts.

    The caller may continue a long run with the returned final_avatar,
    frames_simulated (as start_frame), and receipt_digest. Cross-invocation
    continuity must be checked by whoever stores those receipts; this API
    cannot certify a claimed past game state merely from a supplied digest.
    """
    required = {"tiles", "avatar", "controls"}
    allowed = required | {"start_frame", "previous_receipt_digest"}
    if not isinstance(arguments, dict) or not required <= set(arguments) or set(arguments) - allowed:
        raise GameplayError("long replay requires tiles, avatar, controls and optional chain metadata")
    tiles, avatar, controls = (arguments[key] for key in ("tiles", "avatar", "controls"))
    if not isinstance(controls, list) or not 1 <= len(controls) <= MAX_LONG_REPLAY_FRAMES:
        raise GameplayError("long replay requires 1–16384 controller frames")
    start_frame = arguments.get("start_frame", 0)
    if type(start_frame) is not int or not 0 <= start_frame <= MAX_START_FRAME - len(controls):
        raise GameplayError("long replay start frame is invalid or unbounded")
    previous = arguments.get("previous_receipt_digest")
    if not (previous is None or isinstance(previous, str) and _HASH.fullmatch(previous)):
        raise GameplayError("previous replay receipt must be a lowercase SHA-256 digest")
    if start_frame > 0 and previous is None:
        raise GameplayError("continuation requires a previous receipt")
    if start_frame == 0 and previous is not None:
        raise GameplayError("new replay must not claim a previous receipt")

    # Run the first real segment before hashing or allocating receipts.
    # This validates map dimensions, avatar state and controller shape using
    # the same engine that will execute the rest of the replay.
    validated_first = platformer_replay({
        "tiles": tiles, "avatar": avatar, "controls": controls[:MAX_FRAMES],
    })
    initial_avatar = dict(avatar)
    source_digest = _digest(tiles)
    chain = _digest({
        "schema": "skeleton.gameplay.long_replay.v1",
        "tiles_digest": source_digest,
        "initial_avatar": initial_avatar,
        "start_frame": start_frame,
        "previous_receipt_digest": previous,
    })
    segments: list[dict[str, Any]] = []
    goal_first_reached_frame: int | None = None
    current_avatar = avatar
    for index, offset in enumerate(range(0, len(controls), MAX_FRAMES)):
        batch = controls[offset:offset + MAX_FRAMES]
        result = validated_first if index == 0 else platformer_replay({
            "tiles": tiles, "avatar": current_avatar, "controls": batch,
        })
        global_start = start_frame + offset
        if goal_first_reached_frame is None and result["goal_first_reached_frame"] is not None:
            goal_first_reached_frame = global_start + result["goal_first_reached_frame"]
        previous_chain = chain
        chain = _digest({
            "previous": previous_chain,
            "segment_index": index,
            "start_frame": global_start,
            "end_frame": global_start + len(batch),
            "controls_digest": _digest(batch),
            "initial_avatar": current_avatar,
            "final_avatar": result["final_avatar"],
            "trace_digest": result["trace_sha256"],
            "goal_first_reached_local_frame": result["goal_first_reached_frame"],
        })
        segments.append({
            "segment_index": index,
            "start_frame": global_start,
            "end_frame": global_start + len(batch),
            "frames": len(batch),
            "controls_digest": _digest(batch),
            "trace_sha256": result["trace_sha256"],
            "previous_receipt_digest": previous_chain,
            "receipt_digest": chain,
        })
        current_avatar = result["final_avatar"]
    return {
        "schema_version": "skeleton.gameplay.long_replay.v1",
        "start_frame": start_frame,
        "frames_simulated": len(controls),
        "end_frame": start_frame + len(controls),
        "segment_count": len(segments),
        "initial_avatar": initial_avatar,
        "final_avatar": current_avatar,
        "goal_first_reached_frame": goal_first_reached_frame,
        "source_map_sha256": source_digest,
        "previous_receipt_digest": previous,
        "receipt_digest": chain,
        "segments": segments,
        "trained_model_used": False,
        "training_examples_added": 0,
        "native_emulator_certified": False,
    }


__all__ = ["MAX_LONG_REPLAY_FRAMES", "replay_long_controller"]
