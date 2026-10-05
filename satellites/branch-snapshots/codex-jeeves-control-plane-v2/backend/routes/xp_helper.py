"""Shared XP award helper — called from any route to award gamification XP."""
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from datetime import datetime, timezone
from dotenv import load_dotenv
import os

load_dotenv()

_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]

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

async def award_xp(user_id: str, activity: str, domain: str = None, amount: int = None):
    """Fire-and-forget XP award. Never raises."""
    try:
        xp = amount if amount else XP_TABLE.get(activity, 5)
        now = datetime.now(timezone.utc).isoformat()
        update = {
            "$inc": {"total_xp": xp, "activities_count": 1},
            "$set": {"last_active": now},
            "$setOnInsert": {"created_at": now},
        }
        if domain:
            update["$inc"][f"domain_xp.{domain}"] = xp
        await _db.user_gamification.update_one({"user_id": user_id}, update, upsert=True)
    except:
        pass
