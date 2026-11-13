"""Offline, deterministic tactical opponents for canonical source-bound combat.

Rules are reproducible, not an AI provider, and cannot mutate game state.
Every action is validated by the canonical combat engine before execution.
"""
from __future__ import annotations
from typing import Any
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _active_actor, verify_session,
)

POLICY_VERSION = "skeleton.combat_tactics.v1"


def _decide_verified(session: dict[str, Any]) -> dict[str, str]:
    """Choose a legal action from a canonical engine-produced snapshot."""
    spec, state = session["scenario"], session["state"]
    if state["phase"] != "active":
        raise CombatSessionError("cannot choose action for terminal combat")
    actor_id, _ = _active_actor(spec, state)
    stats = {actor["id"]: actor for actor in spec["actors"]}
    actor = stats[actor_id]
    status = state["actors"][actor_id]
    enemies = [
        enemy for enemy in spec["actors"]
        if enemy["team"] != actor["team"]
        and state["actors"][enemy["id"]]["hp"] > 0
    ]
    if not enemies:
        raise CombatSessionError("active combat has no opposing actors")
    candidates: list[tuple[bool, int, int, str]] = []
    for enemy in enemies:
        target = state["actors"][enemy["id"]]
        damage = max(1, actor["attack"] - enemy["defense"])
        if target["guard"]:
            damage = max(1, damage // 2)
        remaining = max(0, target["hp"] - damage)
        candidates.append((remaining == 0, damage, remaining, enemy["id"]))
    candidates.sort(key=lambda x: (-int(x[0]), -x[1], x[2], x[3]))
    lethal, _, _, target_id = candidates[0]
    if lethal:
        return {"kind": "attack", "actor_id": actor_id, "target_id": target_id}
    threshold = max(2, actor["max_hp"] // 3)
    if status["hp"] <= threshold and not status["guard"]:
        return {"kind": "guard", "actor_id": actor_id}
    if status["hp"] <= threshold and status["guard"] and status["hp"] < actor["max_hp"]:
        return {"kind": "rest", "actor_id": actor_id}
    return {"kind": "attack", "actor_id": actor_id, "target_id": target_id}


def choose_action(session: Any) -> dict[str, str]:
    """Replay-verify all previous turns before choosing a tactical action."""
    return _decide_verified(verify_session(session))


def policy_receipt(session: Any, action: Any) -> dict[str, str]:
    """Checksum source, preceding state, policy and action; not a signature."""
    verified = verify_session(session)
    expected = _decide_verified(verified)
    if type(action) is not dict or action != expected:
        raise CombatSessionError("action does not match tactical policy")
    record = {
        "policy": POLICY_VERSION,
        "source_digest": verified["source_digest"],
        "state_digest": verified["state_digest"],
        "action_digest": dig(expected),
    }
    return {**record, "receipt": dig(record)}


def run_autoplay(scenario: Any) -> dict[str, Any]:
    """Run all teams offline under the source's bounded turn budget."""
    from skeleton.game.gameplay.turn_combat import _advance, new_session
    session = new_session(scenario)
    while session["state"]["phase"] == "active":
        session = _advance(session, _decide_verified(session))
    return verify_session(session)
