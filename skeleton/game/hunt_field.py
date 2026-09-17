"""Multi-agent hunt on campus graph. Influence flow + extract once."""

from __future__ import annotations

from typing import Any

from skeleton.game.floors import weave_campus
from skeleton.game.influence import card as influence_card
from skeleton.game.pathfind import bfs
from skeleton.game.seal_card import seal


class HuntError(ValueError):
    pass


ROLES = ("scout", "chaser", "blocker", "sentry")


def _spawn_hunters(graph: dict[str, Any], n: int = 8) -> list[dict[str, Any]]:
    rooms = [node["id"] for node in graph["nodes"] if node["kind"] in {"empty", "heat", "lock"}]
    if not rooms:
        raise HuntError("rooms")
    out = []
    for i in range(n):
        out.append({
            "id": f"h{i}",
            "role": ROLES[i % len(ROLES)],
            "room": rooms[i % len(rooms)],
            "alert": 0,
            "seen": 0,
        })
    return out


def _step_hunter(hunter: dict[str, Any], arrows: dict[str, str | None], player: str, t: int) -> dict[str, Any]:
    nxt = dict(hunter)
    role = nxt["role"]
    if role == "scout":
        step = arrows.get(nxt["room"])
        if step:
            nxt["room"] = step
        nxt["alert"] = max(0, int(nxt["alert"]) - 1)
    elif role == "chaser":
        if nxt["room"] == player:
            nxt["alert"] = min(8, int(nxt["alert"]) + 2)
            nxt["seen"] += 1
        else:
            step = arrows.get(nxt["room"])
            if step:
                nxt["room"] = step
    elif role == "blocker":
        if t % 3 == 0 and arrows.get(nxt["room"]):
            nxt["room"] = arrows[nxt["room"]]
        nxt["alert"] = int(nxt["room"] == player)
    else:
        nxt["alert"] = int(nxt["room"] == player) * 3
        nxt["seen"] += int(nxt["room"] == player)
    return nxt


def play(*, seed: int = 8847291, ticks: int = 16, hunters: int = 8) -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise HuntError("ticks")
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    spawn = next(n["id"] for n in campus["nodes"] if n["kind"] == "spawn")
    extract = next(n["id"] for n in campus["nodes"] if n["kind"] == "extract")
    path = bfs(campus, spawn, extract)
    field = influence_card(campus, extract)
    arrows = field["flow"]
    pack = _spawn_hunters(campus, hunters)
    contacts = 0
    player = spawn
    for t in range(ticks):
        player = path[min(t, len(path) - 1)]
        pack = [_step_hunter(h, arrows, player, t) for h in pack]
        contacts += sum(1 for h in pack if h["room"] == player)
    extracted = 1 if player == extract else 0
    return seal({
        "kind": "hunt_field",
        "seed": int(seed),
        "ticks": ticks,
        "hunters": len(pack),
        "contacts": contacts,
        "seen": sum(int(h["seen"]) for h in pack),
        "player": player,
        "extract": extract,
        "extract_count": extracted,
        "warp_count": extracted,
        "sota_ready": False,
        "stored_prose": 0,
    })
