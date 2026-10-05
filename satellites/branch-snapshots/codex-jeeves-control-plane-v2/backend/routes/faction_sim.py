"""
🏛️ FACTION & SOCIAL SIMULATION — Segment III.4 (deterministic, seedable, no LLM).

Generates N factions with traits (aggression / ambition / wealth / openness), then runs a
turn-based social simulation: a reputation/relationship matrix that evolves from trait
compatibility + random diplomatic events, an economy (resources grow via wealth & trade,
shrink during wars), dynamic ALLIANCES (when mutual relationship crosses +threshold) and
WARS (when it crosses -threshold), territory shifts, and a chronological world-event log.

Same seed ⇒ byte-identical history (deterministic). Pure-python, fast (~ms for 8 factions /
40 turns). Optional grounding from a worldforge world's POIs as faction homelands.
"""
from __future__ import annotations

import os
import math
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/factions", tags=["factions"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

_ARCHETYPES = [
    ("Empire", "🏛️", "expansionist"), ("Republic", "⚖️", "diplomatic"),
    ("Clans", "🪓", "warlike"), ("Guild", "⚒️", "mercantile"),
    ("Order", "✝️", "zealous"), ("Collective", "⚙️", "industrious"),
    ("Nomads", "🐎", "opportunist"), ("Dynasty", "👑", "traditionalist"),
    ("Syndicate", "🎭", "scheming"), ("Federation", "🤝", "cooperative"),
    ("Horde", "💀", "raiding"), ("Theocracy", "🔯", "doctrinaire"),
]
_PREFIX = ["Iron", "Crimson", "Azure", "Golden", "Shadow", "Verdant", "Storm", "Sun",
           "Frost", "Ember", "Silver", "Obsidian", "Jade", "Ashen", "Dawn", "Dusk"]

ALLY_T = 55      # relationship >= → alliance
WAR_T = -50      # relationship <= → war


def _mk_factions(rnd: random.Random, n: int, homelands: list[str] | None) -> list[dict]:
    arche = _ARCHETYPES[:]
    rnd.shuffle(arche)
    facs = []
    for i in range(n):
        kind, icon, ethos = arche[i % len(arche)]
        name = f"{rnd.choice(_PREFIX)} {kind}"
        facs.append({
            "id": i, "name": name, "icon": icon, "ethos": ethos,
            "aggression": round(rnd.uniform(0.1, 0.95), 2),
            "ambition": round(rnd.uniform(0.1, 0.95), 2),
            "wealth": round(rnd.uniform(0.2, 0.9), 2),
            "openness": round(rnd.uniform(0.1, 0.95), 2),
            "resources": rnd.randint(80, 140),
            "territory": rnd.randint(3, 8),
            "power": 0.0,
            "homeland": (homelands[i] if homelands and i < len(homelands) else None),
            "allies": [], "wars": [],
        })
    return facs


def _power(f: dict) -> float:
    return round(f["resources"] * 0.5 + f["territory"] * 8 + f["aggression"] * 20, 1)


def simulate(seed: int, n: int, turns: int, homelands: list[str] | None = None) -> dict:
    rnd = random.Random(seed & 0xFFFFFFFF)
    n = max(3, min(n, 12))
    turns = max(5, min(turns, 120))
    facs = _mk_factions(rnd, n, homelands)
    # relationship matrix seeded by trait compatibility
    rel = [[0] * n for _ in range(n)]
    for a in range(n):
        for b in range(a + 1, n):
            compat = 100 * (1 - abs(facs[a]["openness"] - facs[b]["openness"]))
            rivalry = 60 * (facs[a]["ambition"] * facs[b]["ambition"])
            v = int(compat - rivalry + rnd.uniform(-25, 25))
            v = max(-100, min(100, v))
            rel[a][b] = rel[b][a] = v

    events = []
    series = []

    def log(turn, kind, text):
        events.append({"turn": turn, "kind": kind, "text": text})

    for t in range(1, turns + 1):
        # economy: wealth grows resources; allies trade bonus; wars drain
        for f in facs:
            grow = f["wealth"] * 6 - 2
            f["resources"] += grow + len(f["allies"]) * 1.5 - len(f["wars"]) * 4
            f["resources"] = max(0, round(f["resources"], 1))
        # diplomatic drift between a random subset of pairs
        for _ in range(max(2, n)):
            a, b = rnd.randrange(n), rnd.randrange(n)
            if a == b:
                continue
            drift = (facs[a]["openness"] + facs[b]["openness"] - 1) * 8
            drift += rnd.uniform(-12, 12) - facs[a]["aggression"] * 6
            rel[a][b] = rel[b][a] = max(-100, min(100, int(rel[a][b] + drift)))
            pair = tuple(sorted((a, b)))
            # alliance formation
            if rel[a][b] >= ALLY_T and b not in facs[a]["allies"]:
                facs[a]["allies"].append(b); facs[b]["allies"].append(a)
                if b in facs[a]["wars"]:
                    facs[a]["wars"].remove(b); facs[b]["wars"].remove(a)
                log(t, "alliance", f"{facs[a]['name']} and {facs[b]['name']} forge an alliance.")
            # war declaration
            elif rel[a][b] <= WAR_T and b not in facs[a]["wars"]:
                facs[a]["wars"].append(b); facs[b]["wars"].append(a)
                if b in facs[a]["allies"]:
                    facs[a]["allies"].remove(b); facs[b]["allies"].remove(a)
                log(t, "war", f"⚔️ {facs[a]['name']} declares war on {facs[b]['name']}.")
        # resolve wars: stronger faction seizes territory
        for f in facs:
            for e in list(f["wars"]):
                if e <= f["id"]:
                    continue
                opp = facs[e]
                if _power(f) > _power(opp) and opp["territory"] > 1 and rnd.random() < 0.35:
                    opp["territory"] -= 1; f["territory"] += 1
                    log(t, "conquest", f"{f['name']} seizes territory from {opp['name']}.")
                    rel[f["id"]][e] = rel[e][f["id"]] = max(-100, rel[f["id"]][e] - 8)
        # collapse: a faction with no territory/resources is absorbed
        for f in facs:
            if f["territory"] <= 0 and f.get("alive", True) is not False:
                f["alive"] = False
                log(t, "collapse", f"💀 {f['name']} collapses and is absorbed.")
        alive = [f for f in facs if f.get("alive", True) is not False]
        series.append({"turn": t, "alive": len(alive),
                       "alliances": sum(len(f["allies"]) for f in facs) // 2,
                       "wars": sum(len(f["wars"]) for f in facs) // 2})

    for f in facs:
        f["power"] = _power(f)
        f["alive"] = f.get("alive", True) is not False
    ranking = sorted(facs, key=lambda x: (x["alive"], x["power"]), reverse=True)
    dominant = ranking[0]
    return {
        "seed": seed, "factions": facs, "n": n, "turns": turns,
        "relationships": rel, "events": events[-80:], "series": series,
        "summary": {
            "dominant": dominant["name"], "dominant_icon": dominant["icon"],
            "dominant_power": dominant["power"],
            "survivors": sum(1 for f in facs if f["alive"]),
            "total_wars": sum(1 for e in events if e["kind"] == "war"),
            "total_alliances": sum(1 for e in events if e["kind"] == "alliance"),
            "collapses": sum(1 for e in events if e["kind"] == "collapse"),
        },
    }


class FactionBody(BaseModel):
    seed: int = 1337
    factions: int = 6
    turns: int = 40
    world_id: str | None = None   # optional worldforge world → POIs as homelands


@router.get("/options")
async def options():
    return {"archetypes": [{"kind": k, "icon": i, "ethos": e} for k, i, e in _ARCHETYPES],
            "ally_threshold": ALLY_T, "war_threshold": WAR_T,
            "limits": {"factions": [3, 12], "turns": [5, 120]}}


@router.post("/simulate")
async def simulate_post(body: FactionBody):
    homelands = None
    if body.world_id:
        w = await _db.worldforge_worlds.find_one({"world_id": body.world_id}, {"_id": 0, "pois": 1})
        pois = (w or {}).get("pois") or []
        homelands = [p.get("name") for p in pois if p.get("name")][: body.factions] or None
    return simulate(body.seed, body.factions, body.turns, homelands)


@router.get("/simulate")
async def simulate_get(seed: int = Query(1337), factions: int = Query(6, ge=3, le=12),
                       turns: int = Query(40, ge=5, le=120)):
    return simulate(seed, factions, turns)
