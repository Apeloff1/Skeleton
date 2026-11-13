"""Source-bound deterministic ghost races for Lantern Quay time trials.

A ghost is a verified recorded game, not an NPC injected into the live world.
Two replay-derived movement timelines can be compared without altering player
collision, resource, crafting, or ending rules.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest,
    initial_state, normalize_action, step, verify_bundle,
)
from .harbor_crafting_time_trials import (
    time_trial_report, validate_course,
)

SCHEMA = "skeleton.game.harbor.ghost-race.v1"
MAX_RACE_BYTES = MAX_BUNDLE_BYTES * 5
FIELDS = {
    "schema", "course", "course_digest", "player", "ghost",
    "source_digest", "player_visits", "ghost_visits",
    "checkpoint_deltas", "timeline", "finish_delta",
    "leader", "race_digest",
}


def _positions(bundle: dict[str, Any]) -> list[list[int]]:
    """Execute canonical moves, including the tick-zero position."""
    world = bundle["source"]
    state = initial_state(world)
    positions = [list(state["pos"])]
    for event in bundle["events"]:
        state = step(world, state, normalize_action(event["action"]))
        positions.append(list(state["pos"]))
    if state != bundle["state"]:
        raise HarborError("ghost position replay mismatch")
    return positions


def ghost_race(
    player: Any, ghost: Any, course: Any, *,
    expected_player_terminal_digest: str | None = None,
) -> dict[str, Any]:
    """Compare one real player save against a completed verified ghost run."""
    verify_bundle(player)
    verify_bundle(ghost)
    if player["source_digest"] != ghost["source_digest"]:
        raise HarborError("ghost source mismatch")
    if (
        expected_player_terminal_digest is not None
        and expected_player_terminal_digest != player["terminal_digest"]
    ):
        raise HarborError("stale ghost race player checkpoint")
    authored = validate_course(course, player["source"])
    player_report = time_trial_report(player, authored)
    ghost_report = time_trial_report(ghost, authored, require_finish=True)
    player_visits = player_report["visits"]
    ghost_visits = ghost_report["visits"]
    ghost_by_id = {entry["id"]: entry["tick"] for entry in ghost_visits}
    player_by_id = {entry["id"]: entry["tick"] for entry in player_visits}
    deltas = [
        {
            "id": checkpoint["id"],
            "player_tick": player_by_id.get(checkpoint["id"]),
            "ghost_tick": ghost_by_id[checkpoint["id"]],
            "delta": (
                player_by_id[checkpoint["id"]] - ghost_by_id[checkpoint["id"]]
                if checkpoint["id"] in player_by_id else None
            ),
        }
        for checkpoint in authored["checkpoints"]
    ]
    player_positions = _positions(player)
    ghost_positions = _positions(ghost)
    timeline = []
    for tick in range(max(len(player_positions), len(ghost_positions))):
        timeline.append({
            "tick": tick,
            "player_pos": deepcopy(player_positions[min(tick, len(player_positions) - 1)]),
            "ghost_pos": deepcopy(ghost_positions[min(tick, len(ghost_positions) - 1)]),
        })
    finish_delta = None
    leader = "ghost"
    if player_report["status"] == "finished":
        finish_delta = player_report["finish_tick"] - ghost_report["finish_tick"]
        leader = "player" if finish_delta < 0 else "tied" if finish_delta == 0 else "ghost"
    race = {
        "schema": SCHEMA,
        "course": authored,
        "course_digest": digest(authored),
        "player": deepcopy(player),
        "ghost": deepcopy(ghost),
        "source_digest": player["source_digest"],
        "player_visits": deepcopy(player_visits),
        "ghost_visits": deepcopy(ghost_visits),
        "checkpoint_deltas": deltas,
        "timeline": timeline,
        "finish_delta": finish_delta,
        "leader": leader,
    }
    race["race_digest"] = digest(race)
    if len(canonical(race)) > MAX_RACE_BYTES:
        raise HarborError("ghost race exceeds byte limit")
    return race


def verify_ghost_race(race: Any) -> dict[str, Any]:
    """Replay both independent source-bound saves, not just the race hash."""
    _keys(race, FIELDS, "ghost race")
    if race["schema"] != SCHEMA or len(canonical(race)) > MAX_RACE_BYTES:
        raise HarborError("unsupported or oversized ghost race")
    if race["race_digest"] != digest({
        key: value for key, value in race.items() if key != "race_digest"
    }):
        raise HarborError("ghost race digest mismatch")
    rebuilt = ghost_race(race["player"], race["ghost"], race["course"])
    if rebuilt != race:
        raise HarborError("ghost race replay mismatch")
    return {
        "leader": rebuilt["leader"],
        "finish_delta": rebuilt["finish_delta"],
        "checkpoint_deltas": deepcopy(rebuilt["checkpoint_deltas"]),
        "player_terminal_digest": rebuilt["player"]["terminal_digest"],
        "ghost_terminal_digest": rebuilt["ghost"]["terminal_digest"],
    }
