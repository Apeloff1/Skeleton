"""Bounded player-reachable league action guidance by actual canonical transitions.

No guessed movement or unearned craft/trade hint is advertised as legal.
Every candidate is replayed against the exact current league checkpoint.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    DIRECTIONS, HarborError, _keys, canonical, digest,
)
from .harbor_crafting_convoy_league import (
    MAX_SAVE_BYTES, league_status, resume_league, verify_league,
)

SCHEMA = "skeleton.game.harbor.convoy-league-guidance.v1"
MAX_GUIDANCE_BYTES = MAX_SAVE_BYTES + 65536
FIELDS = {"schema", "save", "legal", "next_round", "guidance_digest"}
MAX_CANDIDATES = 64


def _candidates(save: dict[str, Any]) -> list[dict[str, str]]:
    world = save["source"]
    candidates: list[dict[str, str]] = [
        {"op": "escort"}, {"op": "strike"}, {"op": "guard"},
        {"op": "gather"}, {"op": "wait"},
    ]
    candidates.extend(
        {"op": "move", "direction": direction}
        for direction in sorted(DIRECTIONS)
    )
    candidates.extend(
        {"op": "craft", "recipe": recipe["id"]}
        for recipe in world["recipes"]
    )
    candidates.extend(
        {"op": "trade", "item": item}
        for item in sorted(world["npc"]["stock"])
    )
    if len(candidates) > MAX_CANDIDATES:
        raise HarborError("league guidance candidate budget exceeded")
    return candidates


def build_league_guidance(save: Any) -> dict[str, Any]:
    verify_league(save)
    status = league_status(save)
    legal = []
    if not status["complete"] and not status["failed"]:
        for action in _candidates(save):
            try:
                result = resume_league(
                    save, [action], expected_digest=save["save_digest"],
                )
            except HarborError:
                continue
            legal.append({
                "action": action, "next_save_digest": result["save_digest"],
                "round": status["next_round"],
                "complete": result["complete"], "failed": result["failed"],
                "score": result["score"],
            })
    guidance = {
        "schema": SCHEMA, "save": deepcopy(save), "legal": legal,
        "next_round": status["next_round"],
    }
    guidance["guidance_digest"] = digest(guidance)
    if len(canonical(guidance)) > MAX_GUIDANCE_BYTES:
        raise HarborError("league guidance exceeds byte budget")
    return guidance


def verify_league_guidance(guidance: Any) -> dict[str, Any]:
    _keys(guidance, FIELDS, "league guidance")
    if guidance["schema"] != SCHEMA or len(canonical(guidance)) > MAX_GUIDANCE_BYTES:
        raise HarborError("unsupported or oversized league guidance")
    if guidance["guidance_digest"] != digest({
        key: value for key, value in guidance.items() if key != "guidance_digest"
    }):
        raise HarborError("league guidance digest mismatch")
    rebuilt = build_league_guidance(guidance["save"])
    if rebuilt != guidance:
        raise HarborError("league guidance replay mismatch")
    return {
        "verified": True, "legal_count": len(rebuilt["legal"]),
        "next_round": rebuilt["next_round"],
        "guidance_digest": rebuilt["guidance_digest"],
    }
