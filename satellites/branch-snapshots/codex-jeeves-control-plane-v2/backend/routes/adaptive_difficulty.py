"""
╔══════════════════════════════════════════════════════════════════════════╗
║  ADAPTIVE DIFFICULTY ENGINE — Optimal Learning Zone Detection          ║
║  Analyzes accuracy per domain, auto-adjusts question difficulty        ║
║  Keeps learner in flow state: not too easy, not too hard               ║
║  Based on Vygotsky's Zone of Proximal Development                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Query
from typing import Optional
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

load_dotenv()

router = APIRouter(prefix="/api/adaptive", tags=["adaptive-difficulty"])

MONGO_URL = os.environ.get("MONGO_URL")
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get('DB_NAME', 'codedock')]
PROJ = {"_id": 0}

# Difficulty levels ordered
DIFF_ORDER = ["beginner", "intermediate", "advanced", "expert", "master"]
DIFF_INDEX = {d: i for i, d in enumerate(DIFF_ORDER)}

# Thresholds for adjustment
PROMOTE_THRESHOLD = 0.80  # 80%+ accuracy → harder
DEMOTE_THRESHOLD = 0.40   # <40% accuracy → easier
MIN_ANSWERS = 5           # Need at least 5 answers to adjust


@router.post("/record")
async def record_answer(
    user_id: str = Query("default_user"),
    domain: str = Query(...),
    difficulty: str = Query(...),
    correct: bool = Query(...),
):
    """Record a quiz answer for adaptive difficulty tracking."""
    now = datetime.now(timezone.utc)
    key = f"{user_id}_{domain}"

    await _db.adaptive_history.insert_one({
        "user_id": user_id,
        "domain": domain,
        "difficulty": difficulty,
        "correct": correct,
        "answered_at": now.isoformat(),
    })

    # Update running stats per domain
    await _db.adaptive_stats.update_one(
        {"user_id": user_id, "domain": domain},
        {
            "$inc": {
                "total_answers": 1,
                "correct_answers": 1 if correct else 0,
                f"answers_{difficulty}": 1,
                f"correct_{difficulty}": 1 if correct else 0,
            },
            "$set": {"last_answer": now.isoformat()},
            "$setOnInsert": {"user_id": user_id, "domain": domain, "current_level": "intermediate"},
        },
        upsert=True,
    )

    # Check if we should adjust difficulty
    stats = await _db.adaptive_stats.find_one({"user_id": user_id, "domain": domain}, PROJ)
    current_level = stats.get("current_level", "intermediate")
    current_idx = DIFF_INDEX.get(current_level, 1)

    # Get accuracy at current level
    answers_at_level = stats.get(f"answers_{current_level}", 0)
    correct_at_level = stats.get(f"correct_{current_level}", 0)

    adjustment = None
    if answers_at_level >= MIN_ANSWERS:
        accuracy = correct_at_level / answers_at_level
        if accuracy >= PROMOTE_THRESHOLD and current_idx < len(DIFF_ORDER) - 1:
            new_level = DIFF_ORDER[current_idx + 1]
            adjustment = "promoted"
            await _db.adaptive_stats.update_one(
                {"user_id": user_id, "domain": domain},
                {"$set": {"current_level": new_level}}
            )
            current_level = new_level
        elif accuracy < DEMOTE_THRESHOLD and current_idx > 0:
            new_level = DIFF_ORDER[current_idx - 1]
            adjustment = "demoted"
            await _db.adaptive_stats.update_one(
                {"user_id": user_id, "domain": domain},
                {"$set": {"current_level": new_level}}
            )
            current_level = new_level

    return {
        "recorded": True,
        "domain": domain,
        "current_level": current_level,
        "adjustment": adjustment,
        "accuracy_at_level": round(correct_at_level / max(answers_at_level, 1) * 100, 1),
        "answers_at_level": answers_at_level,
    }


@router.get("/level/{user_id}")
async def get_adaptive_levels(user_id: str):
    """Get current adaptive difficulty levels for all domains."""
    stats = await _db.adaptive_stats.find({"user_id": user_id}, PROJ).to_list(50)
    levels = {}
    for s in stats:
        domain = s.get("domain", "")
        total = s.get("total_answers", 0)
        correct = s.get("correct_answers", 0)
        levels[domain] = {
            "current_level": s.get("current_level", "intermediate"),
            "total_answers": total,
            "correct_answers": correct,
            "overall_accuracy": round(correct / max(total, 1) * 100, 1),
            "per_difficulty": {
                d: {
                    "answers": s.get(f"answers_{d}", 0),
                    "correct": s.get(f"correct_{d}", 0),
                    "accuracy": round(s.get(f"correct_{d}", 0) / max(s.get(f"answers_{d}", 1), 1) * 100, 1),
                }
                for d in DIFF_ORDER
            },
        }
    return {"user_id": user_id, "levels": levels, "total_domains": len(levels)}


@router.get("/quiz/{user_id}")
async def get_adaptive_quiz(
    user_id: str,
    domain: Optional[str] = None,
    count: int = Query(10, le=50),
):
    """Get quizzes at the user's adaptive difficulty level per domain."""
    if domain:
        stat = await _db.adaptive_stats.find_one({"user_id": user_id, "domain": domain}, PROJ)
        level = stat.get("current_level", "intermediate") if stat else "intermediate"
        pipeline = [
            {"$match": {"domain": domain, "difficulty": level}},
            {"$sample": {"size": count}},
            {"$project": {"_id": 0, "correct_answer": 0, "explanation": 0}},
        ]
    else:
        # Mixed domains at respective levels
        stats = await _db.adaptive_stats.find({"user_id": user_id}, PROJ).to_list(50)
        domain_levels = {s["domain"]: s.get("current_level", "intermediate") for s in stats}

        if domain_levels:
            or_conditions = [{"domain": d, "difficulty": l} for d, l in domain_levels.items()]
            pipeline = [
                {"$match": {"$or": or_conditions}},
                {"$sample": {"size": count}},
                {"$project": {"_id": 0, "correct_answer": 0, "explanation": 0}},
            ]
        else:
            pipeline = [
                {"$match": {"difficulty": "intermediate"}},
                {"$sample": {"size": count}},
                {"$project": {"_id": 0, "correct_answer": 0, "explanation": 0}},
            ]

    quizzes = await _db.interactive_quizzes.aggregate(pipeline).to_list(count)
    return {"quizzes": quizzes, "count": len(quizzes), "adaptive": True}


@router.get("/recommendation/{user_id}")
async def get_learning_recommendation(user_id: str):
    """Get personalized learning recommendations based on adaptive data."""
    stats = await _db.adaptive_stats.find({"user_id": user_id}, PROJ).to_list(50)

    weak_domains = []
    strong_domains = []
    for s in stats:
        accuracy = s.get("correct_answers", 0) / max(s.get("total_answers", 1), 1)
        domain = s.get("domain", "")
        level = s.get("current_level", "intermediate")
        if accuracy < 0.5:
            weak_domains.append({"domain": domain, "accuracy": round(accuracy * 100, 1), "level": level, "recommendation": f"Focus more on {domain.replace('_', ' ')} — review fundamentals"})
        elif accuracy > 0.8:
            strong_domains.append({"domain": domain, "accuracy": round(accuracy * 100, 1), "level": level, "recommendation": f"Great at {domain.replace('_', ' ')}! Ready for {DIFF_ORDER[min(DIFF_INDEX.get(level, 1) + 1, 4)]}"})

    return {
        "user_id": user_id,
        "weak_domains": weak_domains,
        "strong_domains": strong_domains,
        "total_domains_tracked": len(stats),
        "overall_recommendation": "Focus on weak domains first, then advance strong ones" if weak_domains else "All domains strong — keep pushing to master level!",
    }


@router.get("/history/{user_id}")
async def get_adaptive_history(user_id: str, limit: int = Query(50, le=200)):
    """Recent answer timeline + per-day accuracy. Surfaces the adaptive_history event
    log (previously written but never read back)."""
    rows = await _db.adaptive_history.find(
        {"user_id": user_id}, PROJ).sort("answered_at", -1).limit(limit).to_list(limit)
    by_day: dict = {}
    for r in rows:
        day = (r.get("answered_at") or "")[:10]
        d = by_day.setdefault(day, {"total": 0, "correct": 0})
        d["total"] += 1
        d["correct"] += 1 if r.get("correct") else 0
    daily = [{"day": k, "total": v["total"], "correct": v["correct"],
              "accuracy": round(100 * v["correct"] / max(1, v["total"]), 1)}
             for k, v in sorted(by_day.items(), reverse=True)]
    total = len(rows)
    correct = sum(1 for r in rows if r.get("correct"))
    return {"user_id": user_id, "events": rows, "count": total,
            "accuracy": round(100 * correct / max(1, total), 1), "daily": daily}
