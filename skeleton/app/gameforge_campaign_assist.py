"""Bounded completion search from an independently replayed campaign checkpoint.

Searches each required conversation using the existing authored dialogue owner,
then routes through the generated world graph. No guessed grants or automatic
progress. Exhaustion is not impossibility. Returned plans are re-executed by
the campaign owner before being reported as completion witnesses.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from skeleton.app.gameforge_campaign import (
    MAX_CAMPAIGN_ACTIONS, _admit, _gate_open, append_actions, digest, verify_session,
)
from skeleton.app.gameforge_quest_bridge import _route, _steps
from skeleton.app.original_quest_cli import _encode, _integer, _require
from skeleton.game.gameplay.dialogue_graph import replay as dialogue_replay
from skeleton.gameforge.errors import GameForgeError

SCHEMA = "skeleton.gameforge.campaign.assistance.v1"
MAX_EXPANSIONS = 4096


def _state_key(save: dict) -> tuple:
    s = save["state"]
    # Steps matter: an otherwise identical state may reach the owner's limit.
    return (s["node_id"], tuple(s["flags"]), tuple(s["quests"]), s["reputation"],
            s["step"], s["phase"])


def _find_ending(authored: dict, prior: dict, grants: set[str], budget: int) -> tuple[str, list, int]:
    if prior["state"]["phase"] == "ended":
        return ("found" if grants <= set(prior["state"]["quests"]) else "unreachable", [], 0)
    if prior["terminal"]:
        return "unreachable", [], 0
    nodes = {node["id"]: node for node in authored["nodes"]}
    queue = deque([[]])
    seen = {_state_key(prior)}
    used = 0
    while queue:
        if used >= budget:
            return "budget_exhausted", [], used
        suffix = queue.popleft()
        saved = dialogue_replay(authored, [*prior["choices"], *suffix])
        used += 1
        state = saved["state"]
        if saved["terminal"]:
            if state["phase"] == "ended" and grants <= set(state["quests"]):
                return "found", suffix, used
            continue
        for choice in sorted(nodes[state["node_id"]]["choices"], key=lambda item: item["id"]):
            if not set(choice["requires"]) <= set(state["flags"]):
                continue
            try:
                following = dialogue_replay(authored, [*saved["choices"], choice["id"]])
            except ValueError:
                continue
            key = _state_key(following)
            if key not in seen:
                # Bound enqueued candidate states, even on wide graphs.
                if len(seen) >= budget + 1:
                    return "budget_exhausted", [], used
                seen.add(key)
                queue.append([*suffix, choice["id"]])
    return "unreachable", [], used


def plan_completion(source: Any, checkpoint: Any, *, max_expansions: int = 1024) -> dict:
    """Read-only completion witness or a narrowly scoped blocker explanation."""
    budget = _integer(max_expansions, 1, MAX_EXPANSIONS)
    _require(verify_session(source, checkpoint), "independent checkpoint replay mismatch")
    base, conversations, gates = _admit(source)
    state = checkpoint["state"]
    world = base["world"]
    statuses = state["quest"]["state"]["quest_snapshot"]["states"]
    outstanding = [step for step in _steps(base["quest_receipt"]["artifact"])
                   if statuses[step["id"]] != "completed"]
    grants_by_npc: dict[str, set[str]] = {}
    for step in outstanding:
        gate = gates.get(step["id"])
        if gate is not None and not _gate_open(gate, state["dialogues"]):
            npc, grant = gate
            grants_by_npc.setdefault(npc, set()).add(grant)
    actions: list[dict] = []
    spent = 0
    location = state["location"]
    result = "already_completed" if not outstanding else "completion_witness"
    blocker = None

    def move(destination: str) -> None:
        nonlocal location
        actions.extend({"type": "move", "to": key}
                       for key in _route(world["edges"], location, destination)[1:])
        location = destination

    visited: set[str] = set()
    for step in outstanding:
        gate = gates.get(step["id"])
        if gate is not None and gate[0] in grants_by_npc and gate[0] not in visited:
            npc = gate[0]
            required = grants_by_npc[npc]
            found, choices, used = _find_ending(conversations[npc]["source"],
                                              state["dialogues"][npc], required, budget - spent)
            spent += used
            if found != "found":
                result = "dialogue_unreachable" if found == "unreachable" else "budget_exhausted"
                blocker = {"npc": npc, "objective": step["id"],
                           "required_grants": sorted(required), "search": found}
                break
            move(world["npcs"][npc])
            actions.extend({"type": "dialogue", "npc": npc, "choice": choice} for choice in choices)
            visited.add(npc)
        move(step["location"])
        actions.append({"type": "resolve", "objective": step["id"], "npc": step["npc"]})
        if len(checkpoint["actions"]) + len(actions) > MAX_CAMPAIGN_ACTIONS:
            result = "action_budget_exhausted"
            blocker = {"objective": step["id"]}
            break

    final = None
    if result == "completion_witness":
        final = append_actions(source, checkpoint, actions)
        _require(final["state"]["status"] == "completed", "completion witness not accepted by owner")
    elif result == "already_completed":
        final = checkpoint
    else:
        # A partial hypothetical path is never presented as a completion witness.
        actions = []
    body = {"schema": SCHEMA, "source_digest": digest(source),
            "checkpoint_digest": checkpoint["session_digest"], "status": result,
            "search_budget": budget, "expanded": spent, "blocker": blocker,
            "additional": actions, "next_action": actions[0] if actions else None,
            "completion_digest": final["session_digest"] if final is not None else None,
            "native_qualified": False, "release_qualified": False}
    receipt = {**body, "assistance_digest": digest(body)}
    _encode({"request": source, "checkpoint": checkpoint, "assistance": receipt})
    return receipt


def verify_assistance(source: Any, checkpoint: Any, assistance: Any) -> bool:
    try:
        return _encode(assistance) == _encode(plan_completion(
            source, checkpoint, max_expansions=assistance["search_budget"]))
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
