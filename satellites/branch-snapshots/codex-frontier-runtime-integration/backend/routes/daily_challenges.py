"""
╔══════════════════════════════════════════════════════════════════════════╗
║  DAILY CHALLENGES + WEEKLY STREAK + LEARNING SCIENCE ENGINE            ║
║  Enforced learning with scientifically-backed techniques               ║
║  Active recall, spaced repetition, interleaving, retrieval practice    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query
from typing import Optional
import os, hashlib
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

load_dotenv()

router = APIRouter(prefix="/api/daily", tags=["daily-challenges"])

MONGO_URL = os.environ.get("MONGO_URL")
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}


def _today_key():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _week_key():
    now = datetime.now(timezone.utc)
    return f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"


@router.get("/challenge")
async def get_daily_challenge(user_id: str = Query("default_user")):
    """Get today's daily challenge — 10 curated questions spanning all domains.
    Uses interleaving (mixing domains) for better learning."""
    today = _today_key()
    # Check if already generated for today
    existing = await _db.daily_challenges.find_one({"date": today}, PROJ)
    if existing:
        # Check user's progress on this challenge
        progress = await _db.daily_progress.find_one({"user_id": user_id, "date": today}, PROJ)
        return {
            "challenge": existing,
            "user_progress": progress,
            "already_started": progress is not None,
        }

    # Generate new daily challenge using interleaving (mix domains)
    seed = int(hashlib.md5(today.encode()).hexdigest()[:8], 16)
    pipeline = [
        {"$sample": {"size": 10}},
        {"$project": {"_id": 0, "correct_answer": 0, "explanation": 0}},
    ]
    quizzes = await _db.interactive_quizzes.aggregate(pipeline).to_list(10)

    challenge = {
        "date": today,
        "title": f"Daily Challenge — {today}",
        "quizzes": quizzes,
        "total_questions": len(quizzes),
        "domains_covered": list(set(q.get("domain", "") for q in quizzes)),
        "max_points": sum(q.get("points", 20) for q in quizzes),
        "learning_technique": "interleaving",
        "technique_description": "Questions from mixed domains improve long-term retention through interleaved practice.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # ★ FIX 2026-02: previously inserted with explicit `"_id": None` which
    # collides on the unique _id_ index. Let Mongo auto-generate the _id, and
    # upsert by date so re-runs are idempotent.
    await _db.daily_challenges.update_one(
        {"date": today},
        {"$setOnInsert": challenge},
        upsert=True,
    )
    # Remove _id before returning
    challenge.pop("_id", None)
    return {"challenge": challenge, "user_progress": None, "already_started": False}


@router.post("/challenge/submit")
async def submit_daily_challenge(
    user_id: str = Query("default_user"),
    score: int = Query(...),
    correct: int = Query(...),
    total: int = Query(10),
):
    """Submit daily challenge results. Updates streak."""
    today = _today_key()
    now = datetime.now(timezone.utc)

    # ★ Anti-cheat (2026-06): clamp client-supplied score/correct/total to
    # physically-possible bounds + rate-limit replay farming before they
    # touch streaks / leaderboards / XP.
    from routes.anticheat import validate_challenge_score, check_rate_limit, log_violation
    allowed, _cnt, retry_after = await check_rate_limit(user_id, "daily_submit", 20, 60)
    if not allowed:
        await log_violation(user_id, "daily_submit", ["rate_limited"], {"score": score})
        return {"error": "rate_limited", "flagged": True, "retry_after_seconds": retry_after,
                "message": "Too many submissions — slow down."}
    clean, flags = validate_challenge_score(score, correct, total)
    if flags:
        await log_violation(user_id, "daily_submit", flags,
                            {"requested": {"score": score, "correct": correct, "total": total}, "clean": clean})
    score, correct, total = clean["score"], clean["correct"], clean["total"]

    # Save progress
    progress = {
        "user_id": user_id,
        "date": today,
        "score": score,
        "correct": correct,
        "total": total,
        "accuracy": clean["accuracy"],
        "completed_at": now.isoformat(),
    }
    await _db.daily_progress.update_one(
        {"user_id": user_id, "date": today},
        {"$set": progress},
        upsert=True,
    )

    # Update streak
    streak_doc = await _db.learning_streaks.find_one({"user_id": user_id}, PROJ)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    if streak_doc:
        last_date = streak_doc.get("last_activity_date", "")
        if last_date == yesterday:
            # Consecutive day — extend streak
            new_streak = streak_doc.get("current_streak", 0) + 1
        elif last_date == today:
            # Already logged today
            new_streak = streak_doc.get("current_streak", 1)
        else:
            # Streak broken
            new_streak = 1
        best = max(streak_doc.get("best_streak", 0), new_streak)
        total_days = streak_doc.get("total_days", 0) + (1 if last_date != today else 0)
    else:
        new_streak = 1
        best = 1
        total_days = 1

    # Determine streak tier
    if new_streak >= 365:
        tier = "legendary"
    elif new_streak >= 100:
        tier = "diamond"
    elif new_streak >= 30:
        tier = "platinum"
    elif new_streak >= 14:
        tier = "gold"
    elif new_streak >= 7:
        tier = "silver"
    elif new_streak >= 3:
        tier = "bronze"
    else:
        tier = "starter"

    week = _week_key()
    week_data = streak_doc.get("weekly_data", {}) if streak_doc else {}
    if week not in week_data:
        week_data[week] = {"days": 0, "total_score": 0, "total_correct": 0}
    week_data[week]["days"] = week_data[week].get("days", 0) + (1 if (not streak_doc or streak_doc.get("last_activity_date") != today) else 0)
    week_data[week]["total_score"] = week_data[week].get("total_score", 0) + score
    week_data[week]["total_correct"] = week_data[week].get("total_correct", 0) + correct

    streak_update = {
        "user_id": user_id,
        "current_streak": new_streak,
        "best_streak": best,
        "total_days": total_days,
        "last_activity_date": today,
        "streak_tier": tier,
        "weekly_data": week_data,
        "updated_at": now.isoformat(),
    }
    await _db.learning_streaks.update_one(
        {"user_id": user_id},
        {"$set": streak_update},
        upsert=True,
    )

    # XP auto-award for daily challenge
    is_perfect = correct == total
    xp_amt = 75 if is_perfect else 25
    try:
        from routes.xp_helper import award_xp
        await award_xp(user_id, "daily_perfect" if is_perfect else "daily_challenge", "daily_challenges", xp_amt)
        if new_streak > 1:
            await award_xp(user_id, "streak_day", "streaks", 10)
    except: pass

    return {
        "score": score,
        "accuracy": progress["accuracy"],
        "streak": new_streak,
        "best_streak": best,
        "tier": tier,
        "total_days": total_days,
        "xp_awarded": xp_amt,
    }


@router.get("/streak/{user_id}")
async def get_streak(user_id: str):
    """Get user's learning streak data."""
    streak = await _db.learning_streaks.find_one({"user_id": user_id}, PROJ)
    if not streak:
        return {
            "user_id": user_id,
            "current_streak": 0,
            "best_streak": 0,
            "total_days": 0,
            "streak_tier": "starter",
            "weekly_data": {},
        }
    return streak


@router.get("/streak/{user_id}/weekly")
async def get_weekly_stats(user_id: str):
    """Get weekly learning stats."""
    streak = await _db.learning_streaks.find_one({"user_id": user_id}, PROJ)
    week = _week_key()
    weekly = (streak or {}).get("weekly_data", {}).get(week, {"days": 0, "total_score": 0, "total_correct": 0})
    return {
        "user_id": user_id,
        "week": week,
        "days_active": weekly.get("days", 0),
        "total_score": weekly.get("total_score", 0),
        "total_correct": weekly.get("total_correct", 0),
        "goal_days": 7,
        "goal_met": weekly.get("days", 0) >= 7,
    }


@router.get("/history/{user_id}")
async def get_daily_history(user_id: str, limit: int = Query(30, le=90)):
    """Get user's daily challenge history."""
    history = await _db.daily_progress.find(
        {"user_id": user_id}, PROJ
    ).sort("date", -1).limit(limit).to_list(limit)
    return {"history": history, "total": len(history)}


@router.get("/leaderboard/daily")
async def get_daily_leaderboard():
    """Get today's daily challenge leaderboard."""
    today = _today_key()
    leaders = await _db.daily_progress.find(
        {"date": today}, PROJ
    ).sort("score", -1).limit(20).to_list(20)
    return {"date": today, "leaderboard": leaders}


@router.get("/leaderboard/streaks")
async def get_streak_leaderboard():
    """Get the streak leaderboard — longest current streaks."""
    leaders = await _db.learning_streaks.find(
        {}, PROJ
    ).sort("current_streak", -1).limit(20).to_list(20)
    return {"leaderboard": leaders}


@router.get("/learning-tips")
async def get_learning_tips():
    """Get science-backed learning tips — 2026+ learning enhancement."""
    return {"tips": [
        {"id": "spaced_repetition", "title": "Spaced Repetition (SM-2)", "description": "Review material at increasing intervals. Our Anki-style system automatically schedules optimal review times based on your performance.", "science": "Ebbinghaus forgetting curve (1885), Pimsleur graduated intervals, SuperMemo SM-2 algorithm", "status": "active"},
        {"id": "interleaving", "title": "Interleaved Practice", "description": "Mix different topics instead of studying one thing at a time. Daily Challenges use interleaving to mix domains.", "science": "Rohrer & Taylor (2007) — interleaving improves discriminative contrast and long-term retention", "status": "active"},
        {"id": "active_recall", "title": "Active Recall", "description": "Test yourself rather than passively re-reading. Our quiz system forces active retrieval from memory.", "science": "Karpicke & Roediger (2008) — testing effect produces 50%+ better retention than restudying", "status": "active"},
        {"id": "elaborative_interrogation", "title": "Elaborative Interrogation", "description": "Ask 'why?' and 'how?' about every concept. Our quiz explanations trigger deeper processing.", "science": "Pressley et al. (1987) — asking why generates stronger memory traces", "status": "active"},
        {"id": "dual_coding", "title": "Dual Coding", "description": "Combine visual and verbal information. Our knowledge databases pair text with conceptual frameworks.", "science": "Paivio (1986) — dual coding theory shows visual+verbal encoding doubles retention", "status": "active"},
        {"id": "desirable_difficulty", "title": "Desirable Difficulty", "description": "Embrace productive struggle. Our difficulty-rated quizzes ensure you're always challenged at the right level.", "science": "Bjork (1994) — conditions that create difficulty for the learner often enhance long-term retention", "status": "active"},
        {"id": "retrieval_practice", "title": "Retrieval Practice", "description": "The act of retrieving information strengthens memory. Every quiz attempt is a retrieval practice session.", "science": "Roediger & Butler (2011) — retrieval practice is more effective than elaborative studying", "status": "active"},
        {"id": "spacing_effect", "title": "Spacing Effect", "description": "Distribute learning over time rather than cramming. Study paths spread material across weeks/months.", "science": "Cepeda et al. (2006) — distributed practice yields 10-30% better retention than massed practice", "status": "active"},
        {"id": "generation_effect", "title": "Generation Effect", "description": "Generating answers is more effective than recognition. Open-ended exercises in books create generation opportunities.", "science": "Slamecka & Graf (1978) — self-generated information is remembered better", "status": "active"},
        {"id": "metacognition", "title": "Metacognitive Monitoring", "description": "Track your own learning. Progress tracking, accuracy stats, and SRS feedback loops enable self-monitoring.", "science": "Dunlosky & Rawson (2012) — metacognitive monitoring improves study strategy selection", "status": "active"},
    ]}
