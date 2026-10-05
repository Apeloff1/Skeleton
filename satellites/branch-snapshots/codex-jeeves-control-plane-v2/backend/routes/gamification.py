"""Gamification Engine — XP, Levels, Skill Trees, Leaderboard, Streaks"""
from fastapi import APIRouter, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone
import os, math

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/gamification", tags=["gamification"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}

# XP per activity type
XP_TABLE = {
    "quiz_correct": 10, "quiz_wrong": 2, "quiz_perfect": 50,
    "book_chapter": 15, "book_complete": 100,
    "bugfix_studied": 5, "workaround_studied": 8,
    "playground_run": 10, "playground_clean": 15,
    "srs_review": 3, "srs_correct": 5,
    "pomodoro_complete": 20, "pomodoro_hour": 50,
    "daily_challenge": 25, "daily_perfect": 75,
    "streak_day": 10, "streak_week": 100, "streak_month": 500,
    "study_path_step": 15, "study_path_complete": 500,
    "achievement_earned": 25, "first_time_bonus": 50,
    "language_started": 20, "language_mastered": 200,
}

def _level_from_xp(xp):
    """XP to level: level = floor(sqrt(xp / 50))"""
    if xp <= 0: return 1
    return max(1, int(math.sqrt(xp / 50)) + 1)

def _xp_for_level(level):
    """XP required for a given level"""
    return (level - 1) ** 2 * 50

def _rank_from_level(level):
    if level >= 100: return "Transcendent"
    if level >= 80: return "Grandmaster"
    if level >= 60: return "Master"
    if level >= 45: return "Expert"
    if level >= 30: return "Adept"
    if level >= 20: return "Journeyman"
    if level >= 10: return "Apprentice"
    if level >= 5: return "Initiate"
    return "Novice"


@router.post("/xp/award")
async def award_xp(user_id: str = Query("default_user"), activity: str = Query(...), amount: Optional[int] = None, domain: Optional[str] = None):
    """Award XP for an activity. Auto-calculates from XP_TABLE if amount not given.

    ★ Anti-cheat (2026-06): client-supplied `amount` is clamped to a
    server-authoritative ceiling and the user is rate-limited to block
    unlimited-XP tampering + rapid grind farming. Adjustments are audited."""
    from routes.anticheat import validate_xp_award, check_rate_limit, log_violation

    # 1) Rate limit — block grind/replay farming (default 60 awards / 60s).
    allowed, count, retry_after = await check_rate_limit(user_id, "xp_award", 60, 60)
    if not allowed:
        await log_violation(user_id, "xp_award", ["rate_limited"], {"activity": activity, "count": count})
        return {"error": "rate_limited", "flagged": True, "retry_after_seconds": retry_after,
                "message": "Too many XP awards — slow down."}

    # 2) Value clamp — never trust the client's number.
    xp, flags = validate_xp_award(activity, amount, XP_TABLE)
    if flags:
        await log_violation(user_id, "xp_award", flags, {"activity": activity, "requested": amount, "granted": xp})
    now = datetime.now(timezone.utc).isoformat()

    # Update user profile
    await _db.user_gamification.update_one(
        {"user_id": user_id},
        {"$inc": {"total_xp": xp, "activities_count": 1},
         "$set": {"last_active": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True
    )

    # Update domain-specific XP
    if domain:
        await _db.user_gamification.update_one(
            {"user_id": user_id},
            {"$inc": {f"domain_xp.{domain}": xp}}
        )

    # Log activity
    await _db.xp_log.insert_one({
        "user_id": user_id, "activity": activity, "xp": xp,
        "domain": domain, "timestamp": now
    })

    # Get updated profile
    profile = await _db.user_gamification.find_one({"user_id": user_id}, PROJ)
    total_xp = profile.get("total_xp", 0)
    level = _level_from_xp(total_xp)
    next_level_xp = _xp_for_level(level + 1)

    return {
        "xp_awarded": xp, "activity": activity,
        "total_xp": total_xp, "level": level,
        "rank": _rank_from_level(level),
        "next_level_xp": next_level_xp,
        "xp_to_next": max(0, next_level_xp - total_xp),
        "progress_pct": round(min(100, (total_xp - _xp_for_level(level)) / max(1, next_level_xp - _xp_for_level(level)) * 100), 1),
    }


@router.get("/profile/{user_id}")
async def get_gamification_profile(user_id: str):
    """Get full gamification profile with level, rank, skill tree, streaks."""
    profile = await _db.user_gamification.find_one({"user_id": user_id}, PROJ)
    if not profile:
        return {"user_id": user_id, "total_xp": 0, "level": 1, "rank": "Novice", "domain_xp": {}, "skill_tree": [], "activities_count": 0}

    total_xp = profile.get("total_xp", 0)
    level = _level_from_xp(total_xp)
    domain_xp = profile.get("domain_xp", {})

    # Build skill tree from domain XP
    skill_tree = []
    for domain, dxp in sorted(domain_xp.items(), key=lambda x: -x[1]):
        dlevel = _level_from_xp(dxp)
        skill_tree.append({
            "domain": domain,
            "xp": dxp,
            "level": dlevel,
            "rank": _rank_from_level(dlevel),
            "mastery_pct": round(min(100, dxp / max(1, _xp_for_level(dlevel + 1)) * 100), 1),
        })

    return {
        "user_id": user_id,
        "total_xp": total_xp,
        "level": level,
        "rank": _rank_from_level(level),
        "next_level_xp": _xp_for_level(level + 1),
        "xp_to_next": max(0, _xp_for_level(level + 1) - total_xp),
        "progress_pct": round(min(100, (total_xp - _xp_for_level(level)) / max(1, _xp_for_level(level + 1) - _xp_for_level(level)) * 100), 1),
        "activities_count": profile.get("activities_count", 0),
        "skill_tree": skill_tree,
        "last_active": profile.get("last_active"),
        "created_at": profile.get("created_at"),
        "domain_count": len(domain_xp),
    }


@router.get("/leaderboard")
async def get_gamification_leaderboard(limit: int = Query(20, le=100)):
    """Global XP leaderboard."""
    users = await _db.user_gamification.find({}, PROJ).sort("total_xp", -1).limit(limit).to_list(limit)
    board = []
    for i, u in enumerate(users):
        xp = u.get("total_xp", 0)
        level = _level_from_xp(xp)
        board.append({
            "rank": i + 1,
            "user_id": u["user_id"],
            "total_xp": xp,
            "level": level,
            "title": _rank_from_level(level),
            "activities": u.get("activities_count", 0),
        })
    return {"leaderboard": board, "total_players": len(board)}


@router.get("/xp-table")
async def get_xp_table():
    """Get the full XP reward table."""
    return {"xp_table": XP_TABLE, "ranks": [
        {"min_level": 1, "name": "Novice"}, {"min_level": 5, "name": "Initiate"},
        {"min_level": 10, "name": "Apprentice"}, {"min_level": 20, "name": "Journeyman"},
        {"min_level": 30, "name": "Adept"}, {"min_level": 45, "name": "Expert"},
        {"min_level": 60, "name": "Master"}, {"min_level": 80, "name": "Grandmaster"},
        {"min_level": 100, "name": "Transcendent"},
    ]}


@router.get("/activity-log/{user_id}")
async def get_activity_log(user_id: str, limit: int = Query(50, le=200)):
    """Get recent XP activity log."""
    logs = await _db.xp_log.find({"user_id": user_id}, PROJ).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"activities": logs, "count": len(logs)}
