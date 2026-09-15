"""Hyperscale Leaderboard System — 10 boards, time ranges, tier system"""
from fastapi import APIRouter, Query
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timezone, timedelta
import os, random

load_dotenv(Path(__file__).parent.parent / '.env')

router = APIRouter(prefix="/api/leaderboards", tags=["leaderboards"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}

BOARDS = [
    {"id": "xp_champions", "name": "XP Champions", "icon": "star", "color": "#F59E0B", "description": "Overall XP ranking across all activities", "metric": "total_xp"},
    {"id": "rosetta_masters", "name": "Rosetta Masters", "icon": "trophy", "color": "#8B5CF6", "description": "Top Rosetta Challenge scorers", "metric": "challenge_score"},
    {"id": "code_warriors", "name": "Code Warriors", "icon": "code-slash", "color": "#22C55E", "description": "Most code executed in playground", "metric": "executions"},
    {"id": "quiz_champions", "name": "Quiz Champions", "icon": "school", "color": "#3B82F6", "description": "Highest quiz scores", "metric": "quiz_score"},
    {"id": "streak_kings", "name": "Streak Kings", "icon": "flame", "color": "#EF4444", "description": "Longest active learning streaks", "metric": "streak_days"},
    {"id": "polyglots", "name": "Language Polyglots", "icon": "globe", "color": "#06B6D4", "description": "Most programming languages practiced", "metric": "languages_count"},
    {"id": "achievement_hunters", "name": "Achievement Hunters", "icon": "medal", "color": "#EC4899", "description": "Most achievements unlocked", "metric": "achievements"},
    {"id": "daily_heroes", "name": "Daily Heroes", "icon": "calendar", "color": "#F97316", "description": "Daily challenge performance", "metric": "daily_score"},
    {"id": "speed_coders", "name": "Speed Coders", "icon": "flash", "color": "#A855F7", "description": "Fastest code execution times", "metric": "avg_time_ms"},
    {"id": "bug_crushers", "name": "Bug Crushers", "icon": "bug", "color": "#10B981", "description": "Most bugs fixed in bugfix challenges", "metric": "bugs_fixed"},
]

TIERS = [
    {"name": "Grandmaster", "min_xp": 50000, "color": "#F59E0B", "icon": "diamond"},
    {"name": "Master", "min_xp": 25000, "color": "#8B5CF6", "icon": "star"},
    {"name": "Expert", "min_xp": 10000, "color": "#3B82F6", "icon": "shield-checkmark"},
    {"name": "Advanced", "min_xp": 5000, "color": "#22C55E", "icon": "trending-up"},
    {"name": "Intermediate", "min_xp": 1000, "color": "#94A3B8", "icon": "school"},
    {"name": "Beginner", "min_xp": 0, "color": "#64748B", "icon": "person"},
]


def _get_tier(xp: int) -> dict:
    for t in TIERS:
        if xp >= t["min_xp"]:
            return t
    return TIERS[-1]


@router.get("/boards")
async def list_boards():
    """List all available leaderboard categories."""
    boards_with_counts = []
    for b in BOARDS:
        count = await _db.leaderboard_entries.count_documents({"board": b["id"]})
        boards_with_counts.append({**b, "total_entries": count})
    return {"boards": boards_with_counts, "total": len(BOARDS), "tiers": TIERS}


@router.get("/board/{board_id}")
async def get_board(
    board_id: str,
    time_range: str = Query("all_time", pattern="^(daily|weekly|monthly|all_time)$"),
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
):
    """Get leaderboard entries for a specific board."""
    board = next((b for b in BOARDS if b["id"] == board_id), None)
    if not board:
        return {"error": "Board not found", "available": [b["id"] for b in BOARDS]}

    query = {"board": board_id}
    if time_range != "all_time":
        now = datetime.now(timezone.utc)
        if time_range == "daily":
            query["last_active"] = {"$gte": (now - timedelta(days=1)).isoformat()}
        elif time_range == "weekly":
            query["last_active"] = {"$gte": (now - timedelta(days=7)).isoformat()}
        elif time_range == "monthly":
            query["last_active"] = {"$gte": (now - timedelta(days=30)).isoformat()}

    sort_field = board["metric"]
    sort_dir = 1 if board_id == "speed_coders" else -1  # Lower is better for speed

    entries = await _db.leaderboard_entries.find(query, PROJ).sort(sort_field, sort_dir).skip(skip).limit(limit).to_list(limit)
    total = await _db.leaderboard_entries.count_documents(query)

    # Add rank numbers
    for i, e in enumerate(entries):
        e["rank"] = skip + i + 1
        e["tier"] = _get_tier(e.get("total_xp", 0))

    return {
        "board": board,
        "entries": entries,
        "total": total,
        "time_range": time_range,
    }


@router.get("/user/{user_id}")
async def get_user_rankings(user_id: str):
    """Get a user's rank across all boards."""
    rankings = []
    for b in BOARDS:
        entry = await _db.leaderboard_entries.find_one(
            {"board": b["id"], "user_id": user_id}, PROJ
        )
        if entry:
            sort_field = b["metric"]
            sort_dir = 1 if b["id"] == "speed_coders" else -1
            rank = await _db.leaderboard_entries.count_documents({
                "board": b["id"],
                sort_field: {"$gt" if sort_dir == -1 else "$lt": entry.get(sort_field, 0)}
            }) + 1
            entry["rank"] = rank
            entry["tier"] = _get_tier(entry.get("total_xp", 0))
            rankings.append({"board": b, "entry": entry})
    return {"user_id": user_id, "rankings": rankings, "boards_ranked": len(rankings)}


@router.get("/stats")
async def leaderboard_stats():
    """Global leaderboard stats."""
    total_entries = await _db.leaderboard_entries.count_documents({})
    unique_users = len(await _db.leaderboard_entries.distinct("user_id"))
    top_xp_entry = await _db.leaderboard_entries.find_one(
        {"board": "xp_champions"}, PROJ, sort=[("total_xp", -1)]
    )
    return {
        "total_entries": total_entries,
        "unique_users": unique_users,
        "total_boards": len(BOARDS),
        "top_player": top_xp_entry.get("username", "Unknown") if top_xp_entry else None,
        "top_xp": top_xp_entry.get("total_xp", 0) if top_xp_entry else 0,
    }
