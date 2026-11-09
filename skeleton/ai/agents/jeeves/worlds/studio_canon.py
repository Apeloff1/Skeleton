"""Bounded cross-plane canon proof for testimony and propagated NPC rumors."""
from __future__ import annotations

from collections import deque
from typing import Any

from .rumors import _advance, _check_contradictions, validate_rumors
from .testimony import _reveals, _conflict, validate_testimony
from .world_canon import CanonError, digest, prove

SCHEMA = "jeeves.world.studio_cross_canon.v1"


def prove_studio_cross_canon(world: Any, cast: Any,
                             testimony: Any, rumors: Any) -> dict[str, Any]:
    """Reject any reachable NPC claim that contradicts their informed rumor state.

    Branch-exclusive claims remain valid. All state and path exploration is
    bounded; unknown or over-budget states fail closed rather than certify.
    """
    prove(world)
    validate_testimony(testimony, world, cast)
    validate_rumors(rumors, world, cast)
    statements = testimony["statements"]
    rumors_list = rumors["rumors"]
    edges: dict[str, list[dict[str, Any]]] = {}
    for choice in world["choices"]:
        edges.setdefault(choice["from"], []).append(choice)
    for group in edges.values():
        group.sort(key=lambda item: item["id"])
    endings = {item["scene"] for item in world["endings"]}
    initial = (world["start"], frozenset(),
               tuple(frozenset() for _ in rumors_list), 0)
    queue = deque([(initial, ())])
    visited = {initial}
    ending_witnesses: dict[str, list[str]] = {}
    while queue:
        (scene, flags, informed, mask), trace = queue.popleft()
        beliefs: dict[tuple[str, str], str] = {}
        for rumor, actors in zip(rumors_list, informed):
            for actor in actors:
                beliefs[(actor, rumor["claim"])] = rumor["stance"]
        for index, statement in enumerate(statements):
            if not mask & (1 << index):
                continue
            key = (statement["actor"], statement["claim"])
            if key in beliefs and beliefs[key] != statement["stance"]:
                raise CanonError("studio_cross_plane_contradiction",
                                 statement["id"])
        if scene in endings:
            ending_witnesses.setdefault(scene, list(trace))
            continue
        enabled = [choice for choice in edges.get(scene, ())
                   if set(choice["requires"]) <= flags]
        if not enabled:
            raise CanonError("studio_cross_plane_dead_end")
        if len(trace) >= 128:
            raise CanonError("studio_cross_plane_step_budget")
        for choice in enabled:
            known, _ = _advance(rumors, informed, choice["id"])
            _check_contradictions(rumors, known)
            new_mask = mask | _reveals(statements, choice["id"])
            if _conflict(statements, new_mask):
                raise CanonError("studio_cross_plane_testimony_conflict")
            state = (choice["to"], flags | frozenset(choice["grants"]),
                     known, new_mask)
            if state in visited:
                continue
            if len(visited) >= 4096:
                raise CanonError("studio_cross_plane_state_budget")
            visited.add(state)
            queue.append((state, trace + (choice["id"],)))
    if endings - set(ending_witnesses):
        raise CanonError("studio_cross_plane_unreachable_ending")
    return {"schema": SCHEMA, "world_digest": digest(world),
            "testimony_digest": digest(testimony), "rumors_digest": digest(rumors),
            "states_explored": len(visited),
            "ending_witnesses": {key: ending_witnesses[key]
                                 for key in sorted(ending_witnesses)},
            "cross_plane_contradictions": 0}
