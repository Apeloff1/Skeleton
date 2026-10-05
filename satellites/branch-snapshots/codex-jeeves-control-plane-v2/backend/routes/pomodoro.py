"""
╔══════════════════════════════════════════════════════════════════════════╗
║  POMODORO STUDY ENGINE — Scientifically Optimized Study Sessions        ║
║  25min focus + 5min break + SRS integration + path progression         ║
║  Based on Cirillo Technique + Deliberate Practice research             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query
from typing import Optional
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

load_dotenv()

router = APIRouter(prefix="/api/pomodoro", tags=["pomodoro"])

MONGO_URL = os.environ.get("MONGO_URL")
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}


@router.post("/start")
async def start_session(
    user_id: str = Query("default_user"),
    focus_minutes: int = Query(25, ge=5, le=90),
    break_minutes: int = Query(5, ge=1, le=30),
    study_type: str = Query("free"),
    study_ref: Optional[str] = None,
):
    """Start a Pomodoro study session."""
    now = datetime.now(timezone.utc)
    session = {
        "user_id": user_id,
        "status": "active",
        "focus_minutes": focus_minutes,
        "break_minutes": break_minutes,
        "study_type": study_type,
        "study_ref": study_ref,
        "started_at": now.isoformat(),
        "focus_end": (now + timedelta(minutes=focus_minutes)).isoformat(),
        "session_end": (now + timedelta(minutes=focus_minutes + break_minutes)).isoformat(),
        "completed": False,
    }
    result = await _db.pomodoro_sessions.insert_one(session)
    session.pop("_id", None)
    session["session_id"] = str(result.inserted_id)
    return session


@router.post("/complete")
async def complete_session(
    user_id: str = Query("default_user"),
    focus_minutes: int = Query(25),
    study_type: str = Query("free"),
    notes: Optional[str] = None,
):
    """Mark a Pomodoro session as completed. Tracks total focus time."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    # Update daily stats
    await _db.pomodoro_stats.update_one(
        {"user_id": user_id, "date": today},
        {
            "$inc": {"sessions_completed": 1, "total_focus_minutes": focus_minutes},
            "$set": {"last_session": now.isoformat()},
            "$setOnInsert": {"user_id": user_id, "date": today},
        },
        upsert=True,
    )

    # Update lifetime stats
    await _db.pomodoro_lifetime.update_one(
        {"user_id": user_id},
        {
            "$inc": {"total_sessions": 1, "total_focus_minutes": focus_minutes},
            "$set": {"last_session": now.isoformat()},
            "$setOnInsert": {"user_id": user_id},
        },
        upsert=True,
    )

    return {
        "status": "completed",
        "focus_minutes": focus_minutes,
        "study_type": study_type,
        "completed_at": now.isoformat(),
    }


@router.get("/stats/{user_id}")
async def get_pomodoro_stats(user_id: str):
    """Get Pomodoro stats — today + lifetime."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = await _db.pomodoro_stats.find_one({"user_id": user_id, "date": today}, PROJ)
    lifetime = await _db.pomodoro_lifetime.find_one({"user_id": user_id}, PROJ)

    return {
        "user_id": user_id,
        "today": {
            "sessions": (daily or {}).get("sessions_completed", 0),
            "focus_minutes": (daily or {}).get("total_focus_minutes", 0),
            "focus_hours": round((daily or {}).get("total_focus_minutes", 0) / 60, 1),
        },
        "lifetime": {
            "total_sessions": (lifetime or {}).get("total_sessions", 0),
            "total_focus_minutes": (lifetime or {}).get("total_focus_minutes", 0),
            "total_focus_hours": round((lifetime or {}).get("total_focus_minutes", 0) / 60, 1),
        },
    }


@router.get("/schedule")
async def get_study_schedule(
    user_id: str = Query("default_user"),
    sessions_target: int = Query(4, ge=1, le=12),
):
    """Generate an optimal study schedule combining Pomodoro + SRS review queue."""
    # Get due SRS cards
    now = datetime.now(timezone.utc).isoformat()
    due_count = await _db.srs_cards.count_documents({"user_id": user_id, "next_review": {"$lte": now}})

    # Get daily challenge status
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_done = await _db.daily_progress.find_one({"user_id": user_id, "date": today})

    schedule = []
    for i in range(sessions_target):
        if i == 0 and due_count > 0:
            schedule.append({
                "session": i + 1,
                "type": "srs_review",
                "title": f"SRS Review ({min(due_count, 20)} cards due)",
                "focus_minutes": 25,
                "break_minutes": 5,
                "description": "Review due flashcards using spaced repetition for maximum retention.",
            })
        elif i == 1 and not daily_done:
            schedule.append({
                "session": i + 1,
                "type": "daily_challenge",
                "title": "Daily Challenge",
                "focus_minutes": 15,
                "break_minutes": 5,
                "description": "Complete today's 10-question interleaved challenge.",
            })
        elif i % 3 == 0:
            schedule.append({
                "session": i + 1,
                "type": "deep_study",
                "title": "Deep Study (Book/Knowledge DB)",
                "focus_minutes": 25,
                "break_minutes": 5,
                "description": "Focus on a single chapter or knowledge domain for deep understanding.",
            })
        elif i % 3 == 1:
            schedule.append({
                "session": i + 1,
                "type": "practice",
                "title": "Active Practice (Quizzes)",
                "focus_minutes": 25,
                "break_minutes": 5,
                "description": "Active recall through quiz practice — retrieval strengthens memory.",
            })
        else:
            schedule.append({
                "session": i + 1,
                "type": "project",
                "title": "Project Work",
                "focus_minutes": 25,
                "break_minutes": 5 if (i + 1) % 4 != 0 else 15,
                "description": "Apply knowledge through hands-on project work. Long break after 4th session.",
            })

    total_focus = sum(s["focus_minutes"] for s in schedule)
    total_break = sum(s["break_minutes"] for s in schedule)

    return {
        "schedule": schedule,
        "total_sessions": len(schedule),
        "total_focus_minutes": total_focus,
        "total_break_minutes": total_break,
        "total_time_minutes": total_focus + total_break,
        "srs_cards_due": due_count,
        "daily_challenge_done": daily_done is not None,
    }


@router.get("/leaderboard")
async def get_pomodoro_leaderboard():
    """Leaderboard by total focus hours."""
    pipeline = [
        {"$group": {"_id": "$user_id", "total_minutes": {"$sum": "$total_focus_minutes"}}},
        {"$sort": {"total_minutes": -1}},
        {"$limit": 20},
        {"$project": {"_id": 0, "user_id": "$_id", "total_minutes": 1, "total_hours": {"$round": [{"$divide": ["$total_minutes", 60]}, 1]}}},
    ]
    leaders = await _db.pomodoro_stats.aggregate(pipeline).to_list(20)
    return {"leaderboard": leaders}
