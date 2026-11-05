"""Source-bound NPC ending coverage and playable witness audit.

The audit uses the canonical NPC planner for every authored ending. It does
not infer player outcomes from story text, invent facts or treat a bounded
search timeout as a proof of unreachable narrative content.
"""
from __future__ import annotations

from typing import Any

from .flgb_gameplay_runtime import GameplayContractError, dig, req_id
from .npc_schedule import NpcSchedule, NpcSession, _integer, play
from .npc_route_planner import NpcRoutePlanner

SCHEMA = "skeleton.npc_ending_coverage.v1"
MAX_AUDIT_ENDINGS = 64


def audit_endings(
    schedule: NpcSchedule, *, player_id: str = "player",
    max_nodes: int = 1024, max_depth: int = 24,
) -> dict[str, Any]:
    """Replay-qualify each authored ending, preserving inconclusive outcomes."""
    if not isinstance(schedule, NpcSchedule):
        raise GameplayContractError("invalid NPC coverage schedule")
    req_id(player_id, "player_id")
    _integer(max_nodes, "max_nodes", 1, 4096)
    _integer(max_depth, "max_depth", 1, 64)
    if len(schedule.endings) > MAX_AUDIT_ENDINGS:
        raise GameplayContractError("NPC ending coverage budget exceeded")
    planner = NpcRoutePlanner(schedule)
    results = []
    for ending in schedule.endings:
        route = planner.solve(
            ending.ending_id, player_id=player_id,
            max_nodes=max_nodes, max_depth=max_depth,
        )
        record = route.record()
        if record["status"] == "solved":
            replay = play(schedule, record["commands"])
            if (replay.ending != ending.ending_id
                    or replay.state_digest != record["state_digest"]
                    or NpcSession.restore(
                        schedule, record["snapshot"],
                    ).state_digest != replay.state_digest):
                raise GameplayContractError("NPC coverage witness mismatch")
        results.append({
            "ending_id": ending.ending_id,
            "priority": ending.priority,
            "required_facts": list(ending.required_facts),
            "forbidden_facts": list(ending.forbidden_facts),
            "status": record["status"],
            "reason": record["reason"],
            "expanded": record["expanded"],
            "visited": record["visited"],
            "commands": record["commands"],
            "state_digest": record["state_digest"],
            "snapshot": record["snapshot"],
        })
    counts = {
        "solved": sum(row["status"] == "solved" for row in results),
        "unreachable": sum(row["status"] == "unreachable" for row in results),
        "inconclusive": sum(row["status"] == "inconclusive" for row in results),
    }
    report = {
        "schema_version": SCHEMA,
        "schedule_digest": schedule.digest,
        "canon_digest": schedule.canon_digest,
        "player_id": player_id,
        "max_nodes": max_nodes,
        "max_depth": max_depth,
        "endings": results,
        "counts": counts,
        "coverage_complete": counts["inconclusive"] == 0,
        "all_endings_playable": counts["solved"] == len(results),
    }
    report["checksum"] = dig(report)
    return report


def verify_coverage(
    schedule: NpcSchedule, payload: Any,
) -> dict[str, Any]:
    """Recompute all ending routes and canonical snapshots from original source."""
    keys = {
        "schema_version", "schedule_digest", "canon_digest", "player_id",
        "max_nodes", "max_depth", "endings", "counts", "coverage_complete",
        "all_endings_playable", "checksum",
    }
    if type(payload) is not dict or set(payload) != keys:
        raise GameplayContractError("invalid NPC coverage report fields")
    if payload["schema_version"] != SCHEMA:
        raise GameplayContractError("unsupported NPC coverage schema")
    if payload["schedule_digest"] != schedule.digest:
        raise GameplayContractError("NPC coverage source mismatch")
    expected = audit_endings(
        schedule, player_id=payload["player_id"],
        max_nodes=payload["max_nodes"], max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise GameplayContractError("NPC coverage replay or checksum mismatch")
    return expected
