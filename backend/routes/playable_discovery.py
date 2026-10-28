"""
Engagement & Discovery rails for the playable marketplace — split out of the
(large) routes/playable.py for maintainability. Shares the same /api/playable
prefix and reuses core helpers (_db, _champ_rank, _log_event) from routes.playable.

IMPORTANT (route ordering): this router MUST be registered BEFORE routes.playable
so its literal GET paths (/trending, /daily, /arena, /spotlight, /most-loved,
/theme-of-week) win over playable's catch-all GET /{pid}.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Request

from core.anti_farm import rate_ok
from routes.playable import _db, _champ_rank, _log_event

router = APIRouter(prefix="/api/playable", tags=["playable-discovery"])


@router.post("/{pid}/play")
async def record_play(pid: str):
    """▶ Increment a game's all-time play counter and log a Trending event.
    Called by the client when a game is opened/loaded."""
    res = await _db.playables.update_one({"playable_id": pid}, {"$inc": {"plays": 1}})
    if res.matched_count == 0:
        return {"error": "not found"}
    await _log_event(pid, "play")
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "plays": 1})
    return {"playable_id": pid, "plays": (doc or {}).get("plays", 0)}


@router.get("/trending")
async def trending(limit: int = Query(20, le=50), hours: int = Query(24, le=168)):
    """🔥 TRENDING — games with the most momentum (plays + votes + reacts) in the
    last `hours` window, velocity-ranked rather than by all-time score."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    pipeline = [
        {"$match": {"ts": {"$gte": since}}},
        {"$group": {
            "_id": "$playable_id",
            "plays": {"$sum": {"$cond": [{"$eq": ["$kind", "play"]}, 1, 0]}},
            "votes": {"$sum": {"$cond": [{"$eq": ["$kind", "vote"]}, 1, 0]}},
            "reacts": {"$sum": {"$cond": [{"$eq": ["$kind", "react"]}, 1, 0]}},
        }},
    ]
    try:
        agg = await _db.playable_events.aggregate(pipeline).to_list(400)
    except Exception:
        agg = []
    scored = []
    for a in agg:
        vel = (a.get("plays", 0) or 0) + (a.get("votes", 0) or 0) * 2 + (a.get("reacts", 0) or 0)
        if vel > 0:
            scored.append((a["_id"], vel, a.get("plays", 0), a.get("votes", 0), a.get("reacts", 0)))
    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[:limit]
    ids = [s[0] for s in scored]
    metas = {}
    if ids:
        cur = await _db.playables.find(
            {"playable_id": {"$in": ids}, "status": "ready"},
            {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
        ).to_list(len(ids))
        metas = {d["playable_id"]: d for d in cur}
    out, rank = [], 0
    for pid, vel, plays_w, votes_w, reacts_w in scored:
        d = metas.get(pid)
        if not d:
            continue
        rank += 1
        ev = d.get("evaluation") or {}
        out.append({
            "rank": rank, "playable_id": pid, "title": d.get("title"),
            "genre": d.get("genre"), "derive_mode": d.get("derive_mode"),
            "velocity": vel, "plays_window": plays_w, "votes_window": votes_w,
            "reacts_window": reacts_w,
            "plays": d.get("plays", 0) or 0, "has_cover": bool(d.get("has_cover")),
            "overall": ev.get("overall"), "intricacy": d.get("intricacy"),
            "difficulty": ev.get("difficulty"), "length": ev.get("length"),
        })
    return {"trending": out, "count": len(out), "window_hours": hours}


_DAILY_THEMES = [
    "a one-thumb endless runner that speeds up the longer you survive",
    "a calming zen puzzle about arranging falling shapes",
    "a fast arcade dodge-em-up with escalating bullet patterns",
    "a cozy match-and-merge game with gentle progression",
    "a precision tap-timing rhythm game",
    "a single-screen tower-defense with one tower you upgrade",
    "a physics flinging game where you launch an object at targets",
    "a memory/recall game with growing sequences",
    "a snake-like grow-and-survive game with a twist mechanic",
    "a flappy-style ascent through a hazard gauntlet",
    "a brick-breaker reinvented with a special power-up",
    "a stealth one-screen maze where you avoid roaming guards",
    "a reaction game: tap only the correct colour as fast as you can",
    "a tiny roguelike: one room, escalating waves, pick-an-upgrade",
]


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _daily_theme_for(d) -> str:
    return _DAILY_THEMES[d.toordinal() % len(_DAILY_THEMES)]


@router.get("/daily")
async def daily_challenge(limit: int = Query(20, le=50)):
    """📅 DAILY CHALLENGE — one rotating themed brief per day plus a mini
    leaderboard of the games entered into today's challenge."""
    today = datetime.now(timezone.utc).date()
    theme = _daily_theme_for(today)
    prompt = (f"Today's Daily Challenge: build {theme}. Make it a complete, polished, "
              "single-screen mobile-touch HTML5 game.")
    docs = await _db.playables.find(
        {"status": "ready", "moderation_status": {"$ne": "hidden"}, "daily_date": today.isoformat()},
        {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
    ).to_list(200)
    ranked = sorted(docs, key=_champ_rank, reverse=True)[:limit]
    entries = []
    for i, d in enumerate(ranked):
        ev = d.get("evaluation") or {}
        entries.append({
            "rank": i + 1, "playable_id": d.get("playable_id"), "title": d.get("title"),
            "genre": d.get("genre"), "overall": ev.get("overall"),
            "difficulty": ev.get("difficulty"), "length": ev.get("length"),
            "plays": d.get("plays", 0) or 0, "has_cover": bool(d.get("has_cover")),
            "score": round(_champ_rank(d), 1),
        })
    return {"date": today.isoformat(), "theme": theme, "prompt": prompt,
            "entries": entries, "count": len(entries)}


@router.post("/{pid}/daily/enter")
async def daily_enter(pid: str):
    """Enter an existing game into TODAY's Daily Challenge board."""
    today = _today_iso()
    res = await _db.playables.update_one(
        {"playable_id": pid}, {"$set": {"daily_date": today}})
    if res.matched_count == 0:
        return {"error": "not found"}
    return {"playable_id": pid, "daily_date": today, "entered": True}


_ARENA_THEMES = [
    "a roguelike", "a tower-defense", "a bullet-hell shooter", "a puzzle-platformer",
    "a survival crafting micro-game", "a racing/time-trial game", "a tycoon/management sim",
    "a rhythm game", "a stealth game", "a metroidvania-style explorer",
    "a deckbuilder", "a physics sandbox", "a boss-rush brawler",
]
# Regex patterns (aligned 1:1 with _ARENA_THEMES) used to match the week's theme
# against a game's genre/title for the "Theme of the Week" rail.
_ARENA_PATTERNS = [
    "rogue", "tower[ -]?defen", "bullet|shoot", "puzzle|platform",
    "surviv|craft", "rac(e|ing)|time.?trial", "tycoon|manage",
    "rhythm|music", "stealth", "metroid|explor",
    "deck|card", "physics|sandbox", "boss|brawl|beat.?em",
]


@router.get("/arena")
async def weekly_arena():
    """🏟️ WEEKLY ARENA — a themed challenge for the current ISO week. Pair with
    GET /leaderboard?period=week for the live board."""
    now = datetime.now(timezone.utc)
    ws = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    iso_week = now.isocalendar()[1]
    theme = _ARENA_THEMES[iso_week % len(_ARENA_THEMES)]
    prompt = (f"This week's Arena: build {theme}. Compete on the weekly board for "
              "Champion of the Week.")
    count = await _db.playables.count_documents(
        {"status": "ready", "moderation_status": {"$ne": "hidden"}, "created_at": {"$gte": ws.isoformat()}})
    next_mon = ws + timedelta(days=7)
    return {"week_start": ws.date().isoformat(), "theme": theme, "prompt": prompt,
            "entries_this_week": count, "resets_at": next_mon.isoformat()}


# ── Emoji reactions (lightweight anonymous community signal) ──
_REACTIONS = ["🔥", "❤️", "😂", "😮", "👍"]


@router.post("/{pid}/react")
async def react(pid: str, body: dict, request: Request):
    """React to a game with one of a fixed emoji set. Anonymous, additive counts.
    Body: {"emoji": "🔥"}."""
    emoji = str((body or {}).get("emoji", "")).strip()
    if emoji not in _REACTIONS:
        return {"error": "invalid emoji", "allowed": _REACTIONS}
    if not rate_ok(request, "react", rate_per_sec=2.0, burst=15):
        return {"error": "rate_limited"}
    res = await _db.playables.update_one(
        {"playable_id": pid}, {"$inc": {f"reactions.{emoji}": 1}})
    if res.matched_count == 0:
        return {"error": "not found"}
    await _log_event(pid, "react")
    doc = await _db.playables.find_one({"playable_id": pid}, {"_id": 0, "reactions": 1})
    return {"playable_id": pid, "reactions": (doc or {}).get("reactions", {})}


@router.get("/spotlight")
async def spotlight():
    """🌟 SPOTLIGHT — a single featured game, rotated daily (deterministic) from the
    current top-scoring ready games. Powers the /top hero banner."""
    docs = await _db.playables.find(
        {"status": "ready", "moderation_status": {"$ne": "hidden"}},
        {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
    ).sort("created_at", -1).limit(400).to_list(400)
    if not docs:
        return {"spotlight": None}
    top = sorted(docs, key=_champ_rank, reverse=True)[:25]
    if not top:
        return {"spotlight": None}
    pick = top[datetime.now(timezone.utc).date().toordinal() % len(top)]
    ev = pick.get("evaluation") or {}
    return {"spotlight": {
        "playable_id": pick.get("playable_id"), "title": pick.get("title"),
        "genre": pick.get("genre"), "overall": ev.get("overall"),
        "difficulty": ev.get("difficulty"), "length": ev.get("length"),
        "plays": pick.get("plays", 0) or 0, "has_cover": bool(pick.get("has_cover")),
        "intricacy": pick.get("intricacy"),
    }, "date": datetime.now(timezone.utc).date().isoformat()}


@router.get("/most-loved")
async def most_loved(limit: int = Query(12, le=30)):
    """❤️ MOST LOVED — ready games ranked by total emoji reactions (desc).
    Only games with at least one reaction are returned. Powers the /top rail."""
    docs = await _db.playables.find(
        {"status": "ready", "moderation_status": {"$ne": "hidden"}, "reactions": {"$exists": True}},
        {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
    ).limit(500).to_list(500)
    scored = []
    for d in docs:
        total = sum((d.get("reactions") or {}).values())
        if total > 0:
            scored.append((total, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for total, d in scored[:limit]:
        ev = d.get("evaluation") or {}
        out.append({
            "playable_id": d.get("playable_id"), "title": d.get("title"),
            "genre": d.get("genre"), "overall": ev.get("overall"),
            "difficulty": ev.get("difficulty"), "length": ev.get("length"),
            "plays": d.get("plays", 0) or 0, "has_cover": bool(d.get("has_cover")),
            "reactions_total": total, "reactions": d.get("reactions") or {},
        })
    return {"most_loved": out, "count": len(out)}


@router.get("/theme-of-week")
async def theme_of_week(limit: int = Query(12, le=30)):
    """🗓️ THEME OF THE WEEK (Live-Ops) — the current ISO-week arena theme plus a
    curated rail of ready games whose genre/title match that theme, top-ranked."""
    now = datetime.now(timezone.utc)
    iso_week = now.isocalendar()[1]
    idx = iso_week % len(_ARENA_THEMES)
    theme = _ARENA_THEMES[idx]
    pattern = _ARENA_PATTERNS[idx]
    rx = {"$regex": pattern, "$options": "i"}
    docs = await _db.playables.find(
        {"status": "ready", "moderation_status": {"$ne": "hidden"}, "$or": [{"genre": rx}, {"title": rx}]},
        {"_id": 0, "html": 0, "cover_b64": 0, "repair_trail": 0, "sanitized": 0}
    ).limit(300).to_list(300)
    ranked = sorted(docs, key=_champ_rank, reverse=True)[:limit]
    out = []
    for d in ranked:
        ev = d.get("evaluation") or {}
        out.append({
            "playable_id": d.get("playable_id"), "title": d.get("title"),
            "genre": d.get("genre"), "overall": ev.get("overall"),
            "difficulty": ev.get("difficulty"), "length": ev.get("length"),
            "plays": d.get("plays", 0) or 0, "has_cover": bool(d.get("has_cover")),
        })
    prompt = (f"This week's theme: build {theme}. Match the vibe to climb the "
              "Theme of the Week rail.")
    return {"theme": theme, "prompt": prompt, "week": iso_week,
            "games": out, "count": len(out)}


@router.get("/surprise")
async def surprise(genre: str = Query("", max_length=60), min_overall: int = Query(60, le=100)):
    """🎲 SURPRISE ME — a random high-quality ready game, optionally biased toward a
    `genre` (e.g. the visitor's favourite). Falls back gracefully if the filtered
    pool is empty so it always returns something playable."""
    light = {"_id": 0, "playable_id": 1, "title": 1, "genre": 1, "has_cover": 1,
             "plays": 1, "evaluation.overall": 1, "evaluation.difficulty": 1}
    base = {"status": "ready", "moderation_status": {"$ne": "hidden"}}
    pools = []
    if genre.strip():
        rx = {"$regex": re.escape(genre.strip()), "$options": "i"}
        pools.append({**base, "genre": rx, "evaluation.overall": {"$gte": min_overall}})
        pools.append({**base, "genre": rx})
    pools.append({**base, "evaluation.overall": {"$gte": min_overall}})
    pools.append(base)
    docs = []
    for q in pools:
        docs = await _db.playables.find(q, light).limit(300).to_list(300)
        if docs:
            break
    if not docs:
        return {"surprise": None}
    pick = random.choice(docs)
    ev = pick.get("evaluation") or {}
    return {"surprise": {
        "playable_id": pick.get("playable_id"), "title": pick.get("title"),
        "genre": pick.get("genre"), "overall": ev.get("overall"),
        "difficulty": ev.get("difficulty"), "plays": pick.get("plays", 0) or 0,
        "has_cover": bool(pick.get("has_cover")),
    }}
