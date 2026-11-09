"""Finite-state, deterministic *real controller* reachability for 2D games.

Unlike tile connectivity alone, this solver explores actual horizontal
movement, integer-tick gravity, grounded jumps and collision. No learned
policy, network request, model, source ROM or training data is used.

A search hitting its frame/state cap is INCONCLUSIVE, never passed off as
proof of an impossible game.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
from typing import Any

from .gameplay_capabilities import (
    GameplayError, _advance, _map, _point,
)

MAX_SEARCH_FRAMES = 96
MAX_STATES = 12000
_ACTIONS: tuple[dict[str, bool], ...] = (
    {"left": False, "right": False, "jump": False},
    {"left": True, "right": False, "jump": False},
    {"left": False, "right": True, "jump": False},
    {"left": False, "right": False, "jump": True},
    {"left": True, "right": False, "jump": True},
    {"left": False, "right": True, "jump": True},
)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("ascii")
    ).hexdigest()


def check_game_playability(args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict) or set(args) != {"tiles", "max_frames"}:
        raise GameplayError("playability solver requires tiles and max_frames")
    rows, spawn, goal = _map(args["tiles"])
    horizon = args["max_frames"]
    if type(horizon) is not int or not 1 <= horizon <= MAX_SEARCH_FRAMES:
        raise GameplayError("controller search horizon must be 1-96 frames")
    start = (spawn[0], spawn[1], 0)
    # Value: parent state and action index. Immutable states omit vx because
    # _advance fully recomputes horizontal movement from this frame's input.
    predecessors: dict[
        tuple[int, int, int],
        tuple[tuple[int, int, int] | None, int | None],
    ] = {start: (None, None)}
    queue = deque([(start, 0)])
    at_bound = False
    searched = 0
    if spawn == goal:
        raise GameplayError("spawn and goal must be different cells")
    while queue:
        current, depth = queue.popleft()
        if depth >= horizon:
            at_bound = True
            continue
        for action_id, control in enumerate(_ACTIONS):
            next_step = _advance(
                rows,
                {"x": current[0], "y": current[1], "vx": 0, "vy": current[2]},
                control,
                goal,
            )
            searched += 1
            resulting = next_step["avatar"]
            state = (resulting["x"], resulting["y"], resulting["vy"])
            if next_step["goal_reached"]:
                # The goal can be traversed *during* a frame; the last
                # position need not be exactly the goal tile.
                controls = [action_id]
                cursor = current
                while cursor != start:
                    parent, previous_action = predecessors[cursor]
                    if parent is None or previous_action is None:
                        raise GameplayError("invalid controller proof ancestry")
                    controls.append(previous_action)
                    cursor = parent
                controls.reverse()
                answer = [_ACTIONS[x].copy() for x in controls]
                return {
                    "schema_version": "skeleton.game.playability_check.v1",
                    "status": "playable",
                    "playable_under_integer_platformer_rules": True,
                    "controller_frames": len(answer),
                    "controller_actions": answer,
                    "controls_sha256": _hash(answer),
                    "states_explored": len(predecessors),
                    "transitions_evaluated": searched,
                    "search_frame_limit": horizon,
                    "source_map_sha256": _hash(list(rows)),
                    "model_inference_used": False,
                    "training_examples_added": 0,
                    "console_hardware_validated": False,
                }
            if state in predecessors:
                continue
            if len(predecessors) >= MAX_STATES:
                return {
                    "schema_version": "skeleton.game.playability_check.v1",
                    "status": "inconclusive_state_budget",
                    "playable_under_integer_platformer_rules": False,
                    "controller_frames": None,
                    "controller_actions": [],
                    "controls_sha256": None,
                    "states_explored": len(predecessors),
                    "transitions_evaluated": searched,
                    "search_frame_limit": horizon,
                    "source_map_sha256": _hash(list(rows)),
                    "model_inference_used": False,
                    "training_examples_added": 0,
                    "console_hardware_validated": False,
                }
            predecessors[state] = (current, action_id)
            queue.append((state, depth + 1))
    return {
        "schema_version": "skeleton.game.playability_check.v1",
        "status": (
            "inconclusive_frame_budget" if at_bound
            else "unreachable_under_current_rules"
        ),
        "playable_under_integer_platformer_rules": False,
        "controller_frames": None,
        "controller_actions": [],
        "controls_sha256": None,
        "states_explored": len(predecessors),
        "transitions_evaluated": searched,
        "search_frame_limit": horizon,
        "source_map_sha256": _hash(list(rows)),
        "model_inference_used": False,
        "training_examples_added": 0,
        "console_hardware_validated": False,
    }


__all__ = ["MAX_SEARCH_FRAMES", "MAX_STATES", "check_game_playability"]
