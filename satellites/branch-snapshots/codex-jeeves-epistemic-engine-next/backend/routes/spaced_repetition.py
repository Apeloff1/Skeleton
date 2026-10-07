"""
╔══════════════════════════════════════════════════════════════════════════╗
║  SPACED REPETITION ENGINE — SM-2 ALGORITHM (Anki-Style)                ║
║  Tracks every quiz answer, schedules optimal review intervals           ║
║  Scientifically proven memory retention through active recall           ║
╚══════════════════════════════════════════════════════════════════════════╝

SM-2 Algorithm:
- Quality 0-5 rating per answer (0=blackout, 5=perfect)
- EF (Easiness Factor) starts at 2.5, min 1.3
- Interval: 1d → 6d → prev*EF
- After incorrect: reset to 1d
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

router = APIRouter(prefix="/api/srs", tags=["spaced-repetition"])

MONGO_URL = os.environ.get("MONGO_URL")
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}


def _sm2(quality: int, repetitions: int, ef: float, interval: int):
    """SM-2 algorithm — returns (new_repetitions, new_ef, new_interval)."""
    if quality < 3:
        return 0, max(1.3, ef), 1
    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = round(interval * ef)
    new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)
    return repetitions + 1, new_ef, new_interval


@router.post("/review")
async def submit_review(
    user_id: str = Query("default_user"),
    quiz_id: str = Query(...),
    quality: int = Query(..., ge=0, le=5),
):
    """Submit a review for a quiz card. Quality: 0=blackout, 1=wrong, 2=hard, 3=ok, 4=good, 5=perfect."""
    now = datetime.now(timezone.utc)
    existing = await _db.srs_cards.find_one({"user_id": user_id, "quiz_id": quiz_id}, PROJ)

    if existing:
        reps = existing.get("repetitions", 0)
        ef = existing.get("easiness_factor", 2.5)
        interval = existing.get("interval_days", 1)
    else:
        reps, ef, interval = 0, 2.5, 1

    new_reps, new_ef, new_interval = _sm2(quality, reps, ef, interval)
    next_review = now + timedelta(days=new_interval)

    doc = {
        "user_id": user_id,
        "quiz_id": quiz_id,
        "quality": quality,
        "repetitions": new_reps,
        "easiness_factor": round(new_ef, 2),
        "interval_days": new_interval,
        "next_review": next_review.isoformat(),
        "last_reviewed": now.isoformat(),
        "total_reviews": (existing.get("total_reviews", 0) if existing else 0) + 1,
        "correct_count": (existing.get("correct_count", 0) if existing else 0) + (1 if quality >= 3 else 0),
        "streak": (existing.get("streak", 0) if existing else 0) + 1 if quality >= 3 else 0,
    }

    await _db.srs_cards.update_one(
        {"user_id": user_id, "quiz_id": quiz_id},
        {"$set": doc},
        upsert=True,
    )

    # XP auto-award for SRS review
    srs_xp = 5 if quality >= 3 else 3
    try:
        from routes.xp_helper import award_xp
        await award_xp(user_id, "srs_correct" if quality >= 3 else "srs_review", "srs", srs_xp)
    except: pass

    return {
        "quiz_id": quiz_id,
        "quality": quality,
        "new_interval_days": new_interval,
        "next_review": next_review.isoformat(),
        "easiness_factor": round(new_ef, 2),
        "repetitions": new_reps,
        "streak": doc["streak"],
        "xp_awarded": srs_xp,
    }


@router.get("/due")
async def get_due_cards(
    user_id: str = Query("default_user"),
    limit: int = Query(20, le=100),
    domain: Optional[str] = None,
):
    """Get cards due for review right now (Anki-style study session)."""
    now = datetime.now(timezone.utc).isoformat()
    query = {"user_id": user_id, "next_review": {"$lte": now}}
    cards = await _db.srs_cards.find(query, PROJ).sort("next_review", 1).limit(limit).to_list(limit)

    # For each card, fetch the actual quiz question
    quiz_ids = [c["quiz_id"] for c in cards]
    quizzes = {}
    if quiz_ids:
        quiz_docs = await _db.interactive_quizzes.find(
            {"id": {"$in": quiz_ids}},
            {"_id": 0, "correct_answer": 0, "explanation": 0}
        ).to_list(len(quiz_ids))
        quizzes = {q["id"]: q for q in quiz_docs}

    enriched = []
    for card in cards:
        quiz = quizzes.get(card["quiz_id"], {})
        enriched.append({**card, "quiz": quiz})

    # If filtered by domain, filter enriched cards
    if domain:
        enriched = [c for c in enriched if c.get("quiz", {}).get("domain") == domain]

    return {"cards": enriched[:limit], "total_due": len(enriched)}


@router.get("/new")
async def get_new_cards(
    user_id: str = Query("default_user"),
    domain: Optional[str] = None,
    count: int = Query(10, le=50),
):
    """Get new quiz cards the user hasn't seen yet (for learning new material)."""
    # Get all quiz IDs this user has already reviewed
    reviewed = await _db.srs_cards.find({"user_id": user_id}, {"_id": 0, "quiz_id": 1}).to_list(50000)
    reviewed_ids = {r["quiz_id"] for r in reviewed}

    query = {}
    if domain:
        query["domain"] = domain

    pipeline = [{"$match": query}, {"$sample": {"size": count * 3}}, {"$project": {"_id": 0, "correct_answer": 0, "explanation": 0}}]
    candidates = await _db.interactive_quizzes.aggregate(pipeline).to_list(count * 3)

    new_cards = [c for c in candidates if c["id"] not in reviewed_ids][:count]
    return {"cards": new_cards, "count": len(new_cards)}


@router.get("/stats/{user_id}")
async def get_srs_stats(user_id: str):
    """Get spaced repetition stats for a user."""
    now = datetime.now(timezone.utc).isoformat()
    total = await _db.srs_cards.count_documents({"user_id": user_id})
    due = await _db.srs_cards.count_documents({"user_id": user_id, "next_review": {"$lte": now}})
    learning = await _db.srs_cards.count_documents({"user_id": user_id, "repetitions": {"$lte": 1}})
    mature = await _db.srs_cards.count_documents({"user_id": user_id, "interval_days": {"$gte": 21}})

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": None,
            "total_reviews": {"$sum": "$total_reviews"},
            "total_correct": {"$sum": "$correct_count"},
            "avg_ef": {"$avg": "$easiness_factor"},
            "max_streak": {"$max": "$streak"},
        }},
    ]
    agg = await _db.srs_cards.aggregate(pipeline).to_list(1)
    stats = agg[0] if agg else {}

    return {
        "user_id": user_id,
        "total_cards": total,
        "due_now": due,
        "learning": learning,
        "mature": mature,
        "young": total - learning - mature,
        "total_reviews": stats.get("total_reviews", 0),
        "total_correct": stats.get("total_correct", 0),
        "retention_rate": round(stats.get("total_correct", 0) / max(stats.get("total_reviews", 1), 1) * 100, 1),
        "avg_easiness": round(stats.get("avg_ef", 2.5), 2),
        "max_streak": stats.get("max_streak", 0),
    }


@router.get("/forecast/{user_id}")
async def get_review_forecast(user_id: str, days: int = Query(7, le=30)):
    """Forecast how many reviews are due each day for the next N days."""
    now = datetime.now(timezone.utc)
    forecast = []
    for d in range(days):
        day_start = (now + timedelta(days=d)).replace(hour=0, minute=0, second=0).isoformat()
        day_end = (now + timedelta(days=d + 1)).replace(hour=0, minute=0, second=0).isoformat()
        count = await _db.srs_cards.count_documents({
            "user_id": user_id,
            "next_review": {"$gte": day_start, "$lt": day_end},
        })
        forecast.append({"day": d, "date": day_start[:10], "due_count": count})
    return {"forecast": forecast, "user_id": user_id}
