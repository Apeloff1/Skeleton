"""Human-owned tactical turns with deterministic offline opponent actions.

Only the authored hero may be controlled by the caller. Opponent actions are
derived from the canonical arena policy, not from untrusted input. This
function requires a terminal arena before committing an expedition fight.
"""
from __future__ import annotations

from typing import Any

from skeleton.game.gameplay.arena_policy import _decide
from skeleton.game.gameplay.tactical_arena import (
    _active, _advance, new_arena, verify_arena,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def run_player_tactics(
    source: Any, hero_id: str, hero_actions: Any,
) -> dict[str, Any]:
    session = new_arena(source)
    if type(hero_id) is not str or hero_id not in {
        actor["id"] for actor in session["source"]["actors"]
    }:
        raise CombatSessionError("unknown tactical hero")
    if type(hero_actions) is not list or len(hero_actions) > session["source"]["turn_limit"]:
        raise CombatSessionError("invalid tactical hero action budget")
    index = 0
    while session["state"]["phase"] == "active":
        actor_id, _ = _active(session["source"], session["state"])
        if actor_id == hero_id:
            if index >= len(hero_actions):
                raise CombatSessionError("tactical hero action script incomplete")
            action = hero_actions[index]
            if type(action) is not dict or action.get("actor_id") != hero_id:
                raise CombatSessionError("tactical action cannot control opponent")
            index += 1
        else:
            action = _decide(session)
        session = _advance(session, action)
    if index != len(hero_actions):
        raise CombatSessionError("unused tactical hero actions after terminal")
    return verify_arena(session)
