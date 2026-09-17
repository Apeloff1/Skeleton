"""Labyrinth run. Weave, diffuse, lock-solve, stalk, stealth, dream, extract."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.game.diffusion import run as diffuse
from skeleton.game.dream_warp import session as dream
from skeleton.game.labyrinth import adjacency, weave
from skeleton.game.locks import solve
from skeleton.game.pathfind import bfs
from skeleton.game.stalker import hunt
from skeleton.game.stealth import detect


class LabSimError(ValueError):
    """Labyrinth sim contract violation."""


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def play(*, seed: int = 8847291, rooms: int = 8) -> dict[str, Any]:
    maze = weave(seed=int(seed), rooms=rooms)
    spawn = next(node["id"] for node in maze["nodes"] if node["kind"] == "spawn")
    extract = next(node["id"] for node in maze["nodes"] if node["kind"] == "extract")
    locks = solve(maze)
    if not locks["opened"]:
        raise LabSimError("extract locked")
    path = bfs(maze, spawn, extract)
    heat = diffuse(maze, ticks=12, inject_at=spawn)
    hunted = hunt(maze, seed=int(seed), ticks=12, player_path=path)
    last_player = path[min(len(path) - 1, 11)]
    last_stalker = hunted["final"]
    mood = hunted["frames"][-1]["mood"] if hunted["frames"] else "patrol"
    sight = detect(
        player_room=last_player,
        stalker_room=last_stalker,
        stalker_mood=mood,
        heat=heat["peak"],
        seed=int(seed),
    )
    night = dream(seed=int(seed), rooms=rooms)
    body: dict[str, Any] = {
        "kind": "lab_sim",
        "seed": int(seed),
        "rooms": rooms,
        "cycles": maze["cycles"],
        "dead_ends": len(maze["dead_ends"]),
        "bridges": len(maze["bridges"]),
        "path": path,
        "opened": locks["opened"],
        "lock_order": locks["order"],
        "peak_heat": heat["peak"],
        "tokens": heat["tokens"],
        "contacts": hunted["contacts"],
        "alert": sight["alert"],
        "dream_snapped": night["snapped"],
        "extract_count": 1,
        "warp_count": 1,
        "sota_ready": False,
        "stored_prose": 0,
    }
    body["digest"] = hashlib.sha256(_dumps(body).encode("utf-8")).hexdigest()
    body["ok"] = True
    _ = adjacency(maze)
    return body
