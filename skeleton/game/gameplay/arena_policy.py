"""Deterministic bounded offline opponents for the canonical tactical arena."""
from __future__ import annotations
from typing import Any

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import (
    _active, _advance, legal_targets,
    new_arena, verify_arena,
)

POLICY = "skeleton.arena_policy.v1"


def _decide(session: dict[str, Any]) -> dict[str, str]:
    source, state = session["source"], session["state"]
    if state["phase"] != "active":
        raise CombatSessionError("arena already terminal")
    actor_id, _ = _active(source, state)
    stats = {a["id"]: a for a in source["actors"]}
    actor = stats[actor_id]
    targets = legal_targets(source, state, actor_id)
    if targets:
        scored = []
        for target_id in targets:
            target = state["actors"][target_id]
            damage = max(1, actor["attack"] - stats[target_id]["defense"])
            if target["guard"]:
                damage = max(1, damage // 2)
            scored.append((
                -int(damage >= target["hp"]), -damage, target["hp"] - damage,
                target_id,
            ))
        target_id = min(scored)[3]
        return {"kind": "attack", "actor_id": actor_id, "target_id": target_id}
    opponents = [
        other for other in source["actors"]
        if other["team"] != actor["team"]
        and state["actors"][other["id"]]["hp"] > 0
    ]
    if not opponents:
        raise CombatSessionError("arena has no live opponent")
    from skeleton.game.gameplay.arena_routes import _route_verified
    route = _route_verified(session)
    if route:
        return {"kind": "move", "actor_id": actor_id, "direction": route[0]}
    status = state["actors"][actor_id]
    if status["hp"] < actor["max_hp"] and status["guard"]:
        return {"kind": "rest", "actor_id": actor_id}
    return {"kind": "guard", "actor_id": actor_id}


def choose_action(payload: Any) -> dict[str, str]:
    return _decide(verify_arena(payload))


def run_autoplay(source: Any, *, resume: Any = None) -> dict[str, Any]:
    session = new_arena(source) if resume is None else verify_arena(resume)
    if resume is not None and new_arena(source)["source_digest"] != session["source_digest"]:
        raise CombatSessionError("arena autoplay source mismatch")
    while session["state"]["phase"] == "active":
        session = _advance(session, _decide(session))
    return verify_arena(session)
