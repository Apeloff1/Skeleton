"""Stalker FSM on the door graph. Patrol / chase / search / retreat."""

from __future__ import annotations

from typing import Any, Mapping

from skeleton.game.ai_policy import next_state
from skeleton.game.mechanics import AIBehaviorSpec
from skeleton.game.pathfind import PathfindError, adjacency, bfs


MAX_TICKS = 64


class StalkerError(ValueError):
    """Stalker contract violation."""


def _place(graph: Mapping[str, Any], kind: str) -> str:
    for node in graph.get("nodes") or []:
        if node.get("kind") == kind:
            return str(node["id"])
    raise StalkerError(f"missing {kind}")


def step(
    *,
    graph: Mapping[str, Any],
    stalker: str,
    player: str,
    mood: str,
    seed: int,
    tick: int,
    hp_ratio: float,
    heat_ratio: float,
) -> dict[str, Any]:
    spec = AIBehaviorSpec(
        entity_type="stalker",
        behaviors=("patrol", "chase"),
        aggression_level=0.7,
        intelligence_level=0.45,
    )
    mood = next_state(spec, seed=seed, tick=tick, hp_ratio=hp_ratio, heat_ratio=heat_ratio, current=mood if mood in {"idle", "patrol", "chase", "retreat", "extract"} else "idle")
    adj = adjacency(graph)
    if stalker not in adj or player not in adj:
        raise StalkerError("actor off graph")
    nxt = stalker
    if mood == "chase":
        try:
            path = bfs(graph, stalker, player)
            if len(path) > 1:
                nxt = path[1]
        except PathfindError:
            nxt = stalker
    elif mood == "patrol":
        options = adj[stalker] or [stalker]
        nxt = options[tick % len(options)]
    elif mood == "retreat":
        spawn = _place(graph, "spawn")
        try:
            path = bfs(graph, stalker, spawn)
            if len(path) > 1:
                nxt = path[1]
        except PathfindError:
            nxt = stalker
    contact = nxt == player
    return {
        "room": nxt,
        "mood": mood,
        "contact": contact,
        "tick": tick,
        "stored_prose": 0,
    }


def hunt(graph: Mapping[str, Any], *, seed: int, ticks: int = 16, player_path: list[str] | None = None) -> dict[str, Any]:
    if ticks < 1 or ticks > MAX_TICKS:
        raise StalkerError("ticks out of range")
    spawn = _place(graph, "spawn")
    extract = _place(graph, "extract")
    player = list(player_path or [spawn])
    while len(player) < ticks:
        player.append(player[-1])
    stalker = extract
    mood = "patrol"
    frames = []
    contacts = 0
    for tick in range(ticks):
        here = player[tick]
        frame = step(
            graph=graph,
            stalker=stalker,
            player=here,
            mood=mood,
            seed=int(seed),
            tick=tick,
            hp_ratio=0.7,
            heat_ratio=0.25,
        )
        stalker = frame["room"]
        mood = frame["mood"]
        contacts += int(frame["contact"])
        frames.append({"t": tick, "player": here, "stalker": stalker, "mood": mood, "contact": frame["contact"]})
    return {
        "kind": "stalker_hunt",
        "seed": int(seed),
        "ticks": ticks,
        "contacts": contacts,
        "final": stalker,
        "frames": frames,
        "stored_prose": 0,
    }
