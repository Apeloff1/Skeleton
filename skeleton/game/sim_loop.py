"""Integrated NEXUS loop. Path, heat, craft, quests, stalker, combat, extract."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.game.combat_resolve import resolve as combat
from skeleton.game.economy_sim import run as econ
from skeleton.game.heat_model import run as heat_run
from skeleton.game.pathfind import extract_route
from skeleton.game.quest_engine import nexus_book, run as quests
from skeleton.game.stalker import hunt
from skeleton.game.world_graph import place


class SimLoopError(ValueError):
    """Integrated sim contract violation."""


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def play(*, seed: int = 8847291) -> dict[str, Any]:
    graph = place(seed=int(seed), rooms=5)
    route = extract_route(graph)
    heat = heat_run(["heat", "heat", "heat", "wait", "heat", "extract", "sleep", "dream"])
    economy = econ(
        [
            {"verb": "scavenge"},
            {"verb": "scavenge"},
            {"verb": "trade", "give": "scrap", "take": "parts"},
            {"verb": "craft", "target": "coil"},
        ],
        heat=heat["final_heat"],
    )
    quest = quests(nexus_book(), ["heat", "heat", "heat", "extract", "craft", "bait"])
    hunted = hunt(graph, seed=int(seed), ticks=12, player_path=list(route["path"]))
    fight = combat(seed=int(seed), rounds=6)
    body: dict[str, Any] = {
        "kind": "sim_loop",
        "seed": int(seed),
        "route": route["path"],
        "route_cost": route["cost"],
        "warp_count": route["warp_count"],
        "heat": heat["final_heat"],
        "tokens": heat["tokens"],
        "bag": economy["bag"],
        "quests_done": quest["done"],
        "contacts": hunted["contacts"],
        "combat_winner": fight["winner"],
        "extracted": route["extract_count"],
        "sota_ready": False,
        "stored_prose": 0,
    }
    body["digest"] = hashlib.sha256(_dumps(body).encode("utf-8")).hexdigest()
    body["ok"] = True
    return body
