"""
VI.5 Live-Ops Engine — seasons, rotating events, and a battle pass.

Built on the existing engagement signals (plays / votes / generations / purchases).
A SEASON rotates every ISO-week and carries a curated set of EVENTS (e.g. Double-XP
Weekend). A visitor earns XP from actions and climbs a battle-pass track that unlocks
tiered rewards. No auth — progress is keyed by a client visitor id.

Endpoints:
  GET  /api/liveops/season           — current season + active events + battle-pass schema
  GET  /api/liveops/pass             — a visitor's battle-pass progress (xp, tier, unlocks)
  POST /api/liveops/xp               — award XP for an action; returns new tier + unlocks
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT
from core.anti_farm import allow as _allow

router = APIRouter(prefix="/api/liveops", tags=["liveops"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]

# XP awarded per action (server-authoritative; clients only name the action).
_XP = {"play": 5, "vote": 3, "react": 2, "generate": 20, "remix": 12, "purchase": 50, "share": 4}

# Battle-pass tiers: cumulative XP threshold → reward.
_TIERS = [
    {"tier": 1, "xp": 0, "reward": "🎟️ Season Pass", "free": True},
    {"tier": 2, "xp": 50, "reward": "🎨 Neon Cover Frame"},
    {"tier": 3, "xp": 120, "reward": "⚡ Double-XP Charge"},
    {"tier": 4, "xp": 220, "reward": "🏷️ Creator Badge"},
    {"tier": 5, "xp": 360, "reward": "🌈 Rainbow Trail Skin"},
    {"tier": 6, "xp": 540, "reward": "🛠️ Bonus Bugsquash Pack"},
    {"tier": 7, "xp": 760, "reward": "👑 Legendary Frame"},
    {"tier": 8, "xp": 1040, "reward": "💎 Mythic Cartridge"},
]

# Rotating season names + event pools (selected deterministically by ISO week).
_SEASONS = ["Genesis Rush", "Pixel Storm", "Neon Ascent", "Arcade Dynasty", "Quantum League"]
_EVENT_POOL = [
    {"id": "double_xp", "name": "⚡ Double-XP Weekend", "desc": "All XP gains are doubled.", "multiplier": 2},
    {"id": "arcade_spotlight", "name": "🕹️ Arcade Spotlight", "desc": "Arcade games featured all week.", "multiplier": 1},
    {"id": "remix_rally", "name": "🔱 Remix Rally", "desc": "Remixes earn bonus XP.", "multiplier": 1},
    {"id": "boss_week", "name": "👾 Boss Week", "desc": "Tough games take the stage.", "multiplier": 1},
    {"id": "creator_fest", "name": "🎉 Creator Fest", "desc": "Listings + sales celebrated.", "multiplier": 1},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _season_info() -> dict:
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    week = iso[1]
    name = _SEASONS[week % len(_SEASONS)]
    # season spans the ISO week; ends next Monday 00:00 UTC
    days_to_mon = (7 - now.isoweekday()) % 7 or 7
    ends = (now + timedelta(days=days_to_mon)).replace(hour=0, minute=0, second=0, microsecond=0)
    # 2 active events this week (deterministic rotation)
    events = [_EVENT_POOL[week % len(_EVENT_POOL)],
              _EVENT_POOL[(week + 2) % len(_EVENT_POOL)]]
    mult = max((e.get("multiplier", 1) for e in events), default=1)
    return {"season_id": f"{iso[0]}-W{week:02d}", "name": name, "week": week,
            "ends_at": ends.isoformat(), "events": events, "xp_multiplier": mult}


def _tier_for(xp: int) -> dict:
    cur = _TIERS[0]
    for t in _TIERS:
        if xp >= t["xp"]:
            cur = t
        else:
            break
    nxt = next((t for t in _TIERS if t["xp"] > xp), None)
    return {"tier": cur["tier"], "next_tier": (nxt["tier"] if nxt else None),
            "next_xp": (nxt["xp"] if nxt else None)}


def _pass_schema(xp: int) -> list:
    return [{**t, "unlocked": xp >= t["xp"]} for t in _TIERS]


@router.get("/season")
async def season():
    s = _season_info()
    return {"season": s, "battle_pass": _TIERS, "xp_table": _XP}


@router.get("/pass")
async def get_pass(visitor_id: str = Query(...)):
    doc = await _db.liveops_progress.find_one({"visitor_id": visitor_id}, {"_id": 0})
    xp = int((doc or {}).get("xp") or 0)
    s = _season_info()
    return {"visitor_id": visitor_id, "xp": xp, **_tier_for(xp),
            "season_id": s["season_id"], "tiers": _pass_schema(xp)}


class XpBody(BaseModel):
    visitor_id: str = ""
    action: str = ""


@router.post("/xp")
async def award_xp(body: XpBody):
    vid = (body.visitor_id or "").strip()[:80]
    if not vid:
        return {"error": "visitor_id required"}
    base = _XP.get(body.action)
    if base is None:
        return {"error": "unknown action", "allowed": list(_XP.keys())}
    # Anti-farm: cap XP awards per visitor (~30/min, burst 20). Excess is rejected.
    if not _allow(f"xp:{vid}", rate_per_sec=0.5, burst=20):
        return {"ok": False, "error": "rate_limited", "detail": "slow down — too many XP actions"}
    return await _grant(vid, body.action)


async def grant_xp(visitor_id: str, action: str) -> dict:
    """Server-authoritative XP grant for TRUSTED server-side events (e.g. a paid
    purchase). Bypasses the client rate-limit since it is not caller-driven."""
    vid = (visitor_id or "").strip()[:80]
    if not vid or action not in _XP:
        return {"ok": False}
    return await _grant(vid, action)


async def _grant(vid: str, action: str) -> dict:
    base = _XP[action]
    s = _season_info()
    gain = base * s["xp_multiplier"]
    doc = await _db.liveops_progress.find_one({"visitor_id": vid}, {"_id": 0})
    prev_xp = int((doc or {}).get("xp") or 0)
    prev_tier = _tier_for(prev_xp)["tier"]
    new_xp = prev_xp + gain
    await _db.liveops_progress.update_one(
        {"visitor_id": vid},
        {"$inc": {"xp": gain, f"actions.{action}": 1},
         "$set": {"updated_at": _now(), "season_id": s["season_id"]},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    new_tier = _tier_for(new_xp)["tier"]
    unlocked = [t for t in _TIERS if prev_tier < t["tier"] <= new_tier]
    return {"ok": True, "gained": gain, "xp": new_xp, "tier": new_tier,
            "tier_up": new_tier > prev_tier,
            "unlocked_rewards": [t["reward"] for t in unlocked],
            "xp_multiplier": s["xp_multiplier"]}
