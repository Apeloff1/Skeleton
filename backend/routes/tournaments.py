"""
VI.2 Seasonal Tournaments & Arenas — single-elimination BRACKETS over playables.

A tournament auto-seeds the top N ready games into a single-elimination bracket.
Each match accumulates head-to-head votes; calling /advance resolves the current
round (winner = more votes; tie → higher seed) and builds the next round. The
final resolution crowns a champion and awards a rotating reward (a 🏅 trophy that
is also reflected on the game's leaderboard standing).

Endpoints:
  POST /api/tournaments/create            — create + auto-seed a live bracket
  GET  /api/tournaments                   — list tournaments
  GET  /api/tournaments/{tid}             — full hydrated bracket
  POST /api/tournaments/{tid}/match/{mid}/vote  — vote a match (slot 'a'|'b')
  POST /api/tournaments/{tid}/advance     — resolve current round → next round
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT
from core.anti_farm import claim_once as _claim_once

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

_GAME_LIGHT = {
    "_id": 0, "playable_id": 1, "title": 1, "genre": 1, "has_cover": 1,
    "plays": 1, "playability_score": 1, "evaluation.overall": 1, "wins": 1,
}
_VALID_SIZES = (4, 8, 16)
# Rotating reward tiers by ISO week (champion picks up the active one).
_REWARDS = [
    "🏅 Gold Cartridge Trophy",
    "👑 Champion's Crown",
    "💎 Diamond Joystick",
    "🔥 Blazing Pixel Cup",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rank_key(g: dict) -> float:
    ev = (g.get("evaluation") or {}).get("overall") or 0
    return float(ev) * 1.0 + float(g.get("playability_score") or 0) * 0.3 + float(g.get("plays") or 0) * 0.2


class CreateBody(BaseModel):
    name: str = ""
    theme: str = ""
    size: int = 8


@router.post("/create")
async def create_tournament(body: CreateBody):
    size = body.size if body.size in _VALID_SIZES else 8
    pool = await _db.playables.find(
        {"status": "ready", "html": {"$exists": True}}, _GAME_LIGHT
    ).limit(400).to_list(400)
    if len(pool) < size:
        return {"error": f"need at least {size} ready games to seed a bracket (have {len(pool)})"}
    pool.sort(key=_rank_key, reverse=True)
    seeds = pool[:size]
    # Standard seeding pairs: 1vN, 2vN-1, ... so favourites don't meet early.
    pairs = [(seeds[i], seeds[size - 1 - i]) for i in range(size // 2)]
    matches = []
    for idx, (a, b) in enumerate(pairs):
        matches.append({
            "match_id": uuid.uuid4().hex[:8],
            "a": {"playable_id": a["playable_id"], "title": a.get("title"), "seed": seeds.index(a) + 1},
            "b": {"playable_id": b["playable_id"], "title": b.get("title"), "seed": seeds.index(b) + 1},
            "votes": {"a": 0, "b": 0},
            "winner": None,
        })
    tid = uuid.uuid4().hex
    doc = {
        "tournament_id": tid,
        "name": (body.name or "").strip()[:80] or f"Bracket of {size}",
        "theme": (body.theme or "").strip()[:120],
        "size": size,
        "status": "live",            # live → complete
        "current_round": 0,
        "rounds": [matches],         # rounds[r] = list of matches
        "champion_id": None,
        "reward": _REWARDS[datetime.now(timezone.utc).isocalendar()[1] % len(_REWARDS)],
        "created_at": _now(),
    }
    await _db.tournaments.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"ok": True, "tournament": doc}


@router.get("")
async def list_tournaments(limit: int = Query(30, le=100)):
    rows = await _db.tournaments.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"tournaments": rows, "count": len(rows)}


async def _hydrate_covers(t: dict) -> dict:
    ids = set()
    for rnd in t.get("rounds", []):
        for m in rnd:
            for slot in ("a", "b"):
                if m.get(slot, {}).get("playable_id"):
                    ids.add(m[slot]["playable_id"])
    if t.get("champion_id"):
        ids.add(t["champion_id"])
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": list(ids)}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    for rnd in t.get("rounds", []):
        for m in rnd:
            for slot in ("a", "b"):
                pid = m.get(slot, {}).get("playable_id")
                if pid and pid in games:
                    m[slot]["has_cover"] = bool(games[pid].get("has_cover"))
    if t.get("champion_id") and t["champion_id"] in games:
        t["champion"] = {"playable_id": t["champion_id"],
                         "title": games[t["champion_id"]].get("title"),
                         "has_cover": bool(games[t["champion_id"]].get("has_cover"))}
    return t


@router.get("/{tid}")
async def get_tournament(tid: str):
    t = await _db.tournaments.find_one({"tournament_id": tid}, {"_id": 0})
    if not t:
        return {"error": "not found"}
    return {"tournament": await _hydrate_covers(t)}


class VoteBody(BaseModel):
    slot: str = ""  # 'a' or 'b'


@router.post("/{tid}/match/{mid}/vote")
async def vote_match(tid: str, mid: str, body: VoteBody, request: Request):
    slot = body.slot if body.slot in ("a", "b") else None
    if not slot:
        return {"error": "slot must be 'a' or 'b'"}
    # Anti-stuffing: 1 vote per match per IP (30-min TTL).
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "unknown"))
    if not _claim_once(f"vote:{ip}:{tid}:{mid}", ttl=1800):
        return {"error": "already_voted", "detail": "you've already voted on this match"}
    t = await _db.tournaments.find_one({"tournament_id": tid}, {"_id": 0})
    if not t:
        return {"error": "not found"}
    if t.get("status") != "live":
        return {"error": "tournament is complete"}
    r = t["current_round"]
    rounds = t["rounds"]
    found = None
    for m in rounds[r]:
        if m["match_id"] == mid:
            found = m
            break
    if not found:
        return {"error": "match not found in current round"}
    if found.get("winner"):
        return {"error": "match already resolved"}
    found["votes"][slot] += 1
    await _db.tournaments.update_one({"tournament_id": tid}, {"$set": {"rounds": rounds}})
    return {"ok": True, "votes": found["votes"]}


@router.post("/{tid}/advance")
async def advance_round(tid: str):
    """Resolve every match in the current round (winner = more votes; tie → better
    seed) and either build the next round or crown the champion."""
    t = await _db.tournaments.find_one({"tournament_id": tid}, {"_id": 0})
    if not t:
        return {"error": "not found"}
    if t.get("status") != "live":
        return {"error": "tournament already complete"}
    r = t["current_round"]
    rounds = t["rounds"]
    winners = []
    for m in rounds[r]:
        va, vb = m["votes"]["a"], m["votes"]["b"]
        if va == vb:
            # tie → higher seed (lower seed number) wins
            win_slot = "a" if m["a"].get("seed", 99) <= m["b"].get("seed", 99) else "b"
        else:
            win_slot = "a" if va > vb else "b"
        m["winner"] = m[win_slot]["playable_id"]
        winners.append(m[win_slot])
        # reflect a head-to-head win on the game record (best-effort)
        await _db.playables.update_one(
            {"playable_id": m[win_slot]["playable_id"]}, {"$inc": {"wins": 1}})

    if len(winners) == 1:
        champ = winners[0]["playable_id"]
        await _db.tournaments.update_one({"tournament_id": tid}, {"$set": {
            "rounds": rounds, "status": "complete", "champion_id": champ,
            "completed_at": _now()}})
        await _db.playables.update_one(
            {"playable_id": champ}, {"$inc": {"tournament_wins": 1}})
        await _db.tournament_rewards.insert_one({
            "tournament_id": tid, "playable_id": champ, "reward": t.get("reward"),
            "awarded_at": _now()})
        return {"ok": True, "status": "complete", "champion_id": champ, "reward": t.get("reward")}

    # build next round from winners (in order)
    next_matches = []
    for i in range(0, len(winners), 2):
        a, b = winners[i], winners[i + 1]
        next_matches.append({
            "match_id": uuid.uuid4().hex[:8],
            "a": {"playable_id": a["playable_id"], "title": a.get("title"), "seed": a.get("seed")},
            "b": {"playable_id": b["playable_id"], "title": b.get("title"), "seed": b.get("seed")},
            "votes": {"a": 0, "b": 0}, "winner": None,
        })
    rounds.append(next_matches)
    await _db.tournaments.update_one({"tournament_id": tid}, {"$set": {
        "rounds": rounds, "current_round": r + 1}})
    return {"ok": True, "status": "live", "round": r + 1, "matches": len(next_matches)}


# ════════════════════════ #6 AUTO-SCHEDULER + CHAMPIONS SPOTLIGHT ════════════════════════
@router.post("/ensure-weekly")
async def ensure_weekly():
    """Idempotently make sure a weekly bracket is live. Safe to call on app load or
    from a scheduler — creates one (size 8) only if none is currently live."""
    live = await _db.tournaments.find_one({"status": "live"}, {"_id": 0, "tournament_id": 1})
    if live:
        return {"ok": True, "created": False, "tournament_id": live["tournament_id"]}
    week = datetime.now(timezone.utc).isocalendar()[1]
    res = await create_tournament(CreateBody(name=f"Weekly Cup · W{week}", size=8))
    if res.get("ok"):
        return {"ok": True, "created": True, "tournament_id": res["tournament"]["tournament_id"]}
    return {"ok": False, "created": False, "error": res.get("error")}


@router.get("/champions/recent")
async def recent_champions(limit: int = Query(8, le=20)):
    """Recently crowned champions — for a 'Hall of Champions' spotlight rail."""
    rows = await _db.tournaments.find(
        {"status": "complete", "champion_id": {"$ne": None}}, {"_id": 0}
    ).sort("completed_at", -1).limit(limit).to_list(limit)
    ids = [r["champion_id"] for r in rows if r.get("champion_id")]
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    out = []
    for r in rows:
        g = games.get(r.get("champion_id")) or {}
        out.append({"tournament_id": r["tournament_id"], "name": r.get("name"),
                    "reward": r.get("reward"), "completed_at": r.get("completed_at"),
                    "champion": {"playable_id": r.get("champion_id"), "title": g.get("title"),
                                 "genre": g.get("genre"), "has_cover": bool(g.get("has_cover"))}})
    return {"champions": out, "count": len(out)}


@router.get("/rewards/ledger")
async def rewards_ledger(limit: int = Query(30, le=100)):
    """🏆 Trophy case — every reward ever awarded to a champion (this collection was
    previously written but never surfaced). Hydrated with game titles."""
    rows = await _db.tournament_rewards.find({}, {"_id": 0}).sort("awarded_at", -1).limit(limit).to_list(limit)
    ids = [r.get("playable_id") for r in rows if r.get("playable_id")]
    games = {g["playable_id"]: g for g in
             await _db.playables.find({"playable_id": {"$in": ids}}, _GAME_LIGHT).to_list(len(ids) or 1)}
    out = []
    for r in rows:
        g = games.get(r.get("playable_id")) or {}
        out.append({"reward": r.get("reward"), "awarded_at": r.get("awarded_at"),
                    "tournament_id": r.get("tournament_id"),
                    "game": {"playable_id": r.get("playable_id"), "title": g.get("title"),
                             "genre": g.get("genre"), "has_cover": bool(g.get("has_cover"))}})
    return {"rewards": out, "count": len(out)}
