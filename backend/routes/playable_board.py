"""
Public marketplace BOARD endpoints — leaderboard, Hall of Champions, Staff Picks —
split out of routes/playable.py for maintainability. Shares the /api/playable prefix
and reuses _db and _champ_rank from routes.playable.

IMPORTANT (route ordering): register this router BEFORE routes.playable so its literal
GET paths (/leaderboard, /champions, /staff-picks) win over playable's /{pid}.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from routes.playable import _db, _champ_rank

router = APIRouter(prefix="/api/playable", tags=["playable-board"])


@router.get("/leaderboard")
async def leaderboard(limit: int = Query(20, le=100), period: str = Query("all"),
                      q: str = Query("", max_length=80), sort: str = Query("score"),
                      assets: str = Query("")):
    """★ TOP GAMES — rank ready playables by a blended score: vote win-rate (with
    a confidence prior), judge overall, intricacy, popularity and reactions.
    period='week' restricts to the current ISO week; q = title/genre search;
    sort = score (default) | plays | newest | remixed; assets='complete' shows only
    fully art-skinned games."""
    query = {"status": "ready", "moderation_status": {"$ne": "hidden"}}
    if assets == "complete":
        query["asset_status"] = "complete"
    if period == "week":
        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        query["created_at"] = {"$gte": week_start.isoformat()}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"title": rx}, {"genre": rx}]
    docs = await _db.playables.find(
        query,
        {"_id": 0, "html": 0, "repair_trail": 0, "missing_checks": 0, "sanitized": 0, "cover_b64": 0}
    ).sort("created_at", -1).limit(400).to_list(400)

    def _rank(d):
        wins = d.get("wins", 0) or 0
        matches = d.get("matches", 0) or 0
        win_rate = (wins + 2) / (matches + 4) if matches else 0.5
        ev = (d.get("evaluation") or {}).get("overall", 0) or 0
        intr = d.get("intricacy", 0) or 0
        popularity = min((d.get("plays", 0) or 0) / 50.0, 1.0) * 8
        loved = min(sum((d.get("reactions") or {}).values()) / 30.0, 1.0) * 6
        return win_rate * 55 + (ev / 100) * 35 + (intr / 7) * 10 + popularity + loved

    _SORTERS = {
        "plays": lambda d: d.get("plays", 0) or 0,
        "newest": lambda d: d.get("created_at", ""),
        "remixed": lambda d: d.get("remix_count", 0) or 0,
        "score": _rank,
    }
    keyfn = _SORTERS.get(sort, _rank)
    ranked = sorted(docs, key=keyfn, reverse=True)[:limit]
    out = []
    for i, d in enumerate(ranked):
        out.append({
            "rank": i + 1,
            "playable_id": d.get("playable_id"),
            "title": d.get("title"),
            "genre": d.get("genre"),
            "depth": d.get("depth"),
            "derive_mode": d.get("derive_mode"),
            "imported": d.get("imported", False),
            "playability_score": d.get("playability_score"),
            "intricacy": d.get("intricacy"),
            "overall": (d.get("evaluation") or {}).get("overall"),
            "verdict": (d.get("evaluation") or {}).get("verdict"),
            "wins": d.get("wins", 0) or 0,
            "matches": d.get("matches", 0) or 0,
            "plays": d.get("plays", 0) or 0,
            "remix_count": d.get("remix_count", 0) or 0,
            "champion_weeks": d.get("champion_weeks", 0) or 0,
            "reactions_total": sum((d.get("reactions") or {}).values()),
            "staff_pick": bool(d.get("staff_pick")),
            "difficulty": (d.get("evaluation") or {}).get("difficulty"),
            "length": (d.get("evaluation") or {}).get("length"),
            "score": round(_rank(d), 1),
            "has_cover": bool(d.get("has_cover")),
            "asset_status": d.get("asset_status"),
        })
    return {"leaderboard": out, "count": len(out)}


async def _record_champion(week_offset: int = 0):
    """Snapshot a given ISO-week's #1 into the `champions` collection (keyed by
    Monday date). week_offset=0 = current week, -1 = previous week. Re-upserting
    keeps the current leader fresh; once a week rolls over its last snapshot
    becomes the permanent champion of record."""
    try:
        now = datetime.now(timezone.utc)
        ws = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        ws = ws + timedelta(weeks=week_offset)
        we = ws + timedelta(days=7)
        docs = await _db.playables.find(
            {"status": "ready", "moderation_status": {"$ne": "hidden"}, "created_at": {"$gte": ws.isoformat(), "$lt": we.isoformat()}},
            {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
        ).sort("created_at", -1).limit(400).to_list(400)
        if not docs:
            return
        top = max(docs, key=_champ_rank)
        existing = await _db.champions.find_one({"week_start": ws.date().isoformat()}, {"_id": 0, "awarded": 1})
        # 🏆 Rotating reward: when finalizing a COMPLETED past week (offset<0), award
        # the winning game a permanent trophy exactly once (idempotent via `awarded`).
        if week_offset < 0 and not (existing or {}).get("awarded"):
            try:
                await _db.playables.update_one(
                    {"playable_id": top.get("playable_id")},
                    {"$inc": {"champion_weeks": 1}})
            except Exception:
                pass
        await _db.champions.update_one(
            {"week_start": ws.date().isoformat()},
            {"$set": {
                "week_start": ws.date().isoformat(),
                "playable_id": top.get("playable_id"),
                "title": top.get("title"),
                "genre": top.get("genre"),
                "derive_mode": top.get("derive_mode"),
                "overall": (top.get("evaluation") or {}).get("overall"),
                "score": round(_champ_rank(top), 1),
                "wins": top.get("wins", 0) or 0,
                "matches": top.get("matches", 0) or 0,
                "plays": top.get("plays", 0) or 0,
                "has_cover": bool(top.get("has_cover")),
                "updated_at": now.isoformat(),
                **({"awarded": True} if week_offset < 0 else {}),
            }}, upsert=True)
    except Exception:
        pass


@router.get("/champions")
async def champions(limit: int = Query(26, le=52)):
    """🏛️ Hall of Champions — each ISO week's #1 game, newest first.
    Auto-archives both the current week's leader and (on rollover) the just-
    completed previous week's permanent champion."""
    await _record_champion(0)    # current week (live leader)
    await _record_champion(-1)   # previous week (finalize on rollover)
    now = datetime.now(timezone.utc)
    cur = (now - timedelta(days=now.weekday())).date().isoformat()
    docs = await _db.champions.find({}, {"_id": 0}).sort("week_start", -1).limit(limit).to_list(limit)
    for d in docs:
        d["is_current"] = d.get("week_start") == cur
    return {"champions": docs, "count": len(docs)}


@router.get("/staff-picks")
async def staff_picks(limit: int = Query(10, le=30)):
    """⭐ STAFF PICKS — a hand-curated rail of standout games (newest pick first)."""
    docs = await _db.playables.find(
        {"status": "ready", "moderation_status": {"$ne": "hidden"}, "staff_pick": True},
        {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
    ).sort("staff_pick_at", -1).limit(limit).to_list(limit)
    out = []
    for d in docs:
        ev = d.get("evaluation") or {}
        out.append({
            "playable_id": d.get("playable_id"), "title": d.get("title"),
            "genre": d.get("genre"), "overall": ev.get("overall"),
            "difficulty": ev.get("difficulty"), "length": ev.get("length"),
            "plays": d.get("plays", 0) or 0, "remix_count": d.get("remix_count", 0) or 0,
            "has_cover": bool(d.get("has_cover")),
        })
    return {"staff_picks": out, "count": len(out)}


class StaffPickBody(BaseModel):
    pick: bool = True


@router.post("/{pid}/staff-pick")
async def set_staff_pick(pid: str, body: StaffPickBody):
    """Toggle a game's Staff Pick status (curator action; open in dev)."""
    upd = {"staff_pick": bool(body.pick)}
    if body.pick:
        upd["staff_pick_at"] = datetime.now(timezone.utc).isoformat()
    res = await _db.playables.update_one({"playable_id": pid}, {"$set": upd})
    if res.matched_count == 0:
        return {"error": "not found"}
    return {"playable_id": pid, "staff_pick": bool(body.pick)}
