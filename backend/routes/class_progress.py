"""
Class Progress & Repeat System with Achievements
Version: 1.0.0 | Track class completions, repeat classes, and earn achievements
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/class-progress", tags=["class-progress"])

# MongoDB setup
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
db = client[os.environ.get('DB_NAME', 'test_database')]

# Collections
class_progress_collection = db.class_progress
achievements_collection = db.user_achievements

# =============================================================================
# DATA MODELS
# =============================================================================

class ClassCompletion(BaseModel):
    user_id: str = "default_user"
    class_id: str
    class_name: str
    language_id: Optional[str] = None
    category: str = "general"  # language, academy, camera, etc.
    score: Optional[float] = None
    notes: Optional[str] = None

class ClassProgressResponse(BaseModel):
    class_id: str
    class_name: str
    completion_count: int
    first_completed: Optional[str] = None
    last_completed: Optional[str] = None
    best_score: Optional[float] = None
    achievements_earned: List[Dict[str, Any]] = []

# =============================================================================
# ACHIEVEMENT DEFINITIONS
# =============================================================================

ACHIEVEMENTS = {
    "first_class": {
        "id": "first_class",
        "name": "First Steps",
        "description": "Complete your very first class",
        "icon": "school",
        "color": "#3B82F6",
        "xp": 50,
        "rarity": "common",
        "trigger": {"type": "total_completions", "count": 1}
    },
    "repeat_learner": {
        "id": "repeat_learner",
        "name": "Repeat Learner",
        "description": "Complete any class twice — practice makes perfect!",
        "icon": "refresh",
        "color": "#8B5CF6",
        "xp": 100,
        "rarity": "uncommon",
        "trigger": {"type": "class_repeat", "count": 2}
    },
    "triple_master": {
        "id": "triple_master",
        "name": "Triple Master",
        "description": "Complete the same class 3 times — true mastery!",
        "icon": "trophy",
        "color": "#F59E0B",
        "xp": 250,
        "rarity": "rare",
        "trigger": {"type": "class_repeat", "count": 3}
    },
    "five_timer": {
        "id": "five_timer",
        "name": "Dedicated Scholar",
        "description": "Complete the same class 5 times — unstoppable!",
        "icon": "star",
        "color": "#EC4899",
        "xp": 500,
        "rarity": "epic",
        "trigger": {"type": "class_repeat", "count": 5}
    },
    "ten_timer": {
        "id": "ten_timer",
        "name": "Legendary Learner",
        "description": "Complete the same class 10 times — legendary dedication!",
        "icon": "diamond",
        "color": "#EF4444",
        "xp": 1000,
        "rarity": "legendary",
        "trigger": {"type": "class_repeat", "count": 10}
    },
    "polyglot_5": {
        "id": "polyglot_5",
        "name": "Polyglot",
        "description": "Complete classes in 5 different programming languages",
        "icon": "globe",
        "color": "#10B981",
        "xp": 300,
        "rarity": "rare",
        "trigger": {"type": "unique_languages", "count": 5}
    },
    "polyglot_10": {
        "id": "polyglot_10",
        "name": "Master Polyglot",
        "description": "Complete classes in 10 different programming languages",
        "icon": "earth",
        "color": "#6366F1",
        "xp": 750,
        "rarity": "epic",
        "trigger": {"type": "unique_languages", "count": 10}
    },
    "streak_7": {
        "id": "streak_7",
        "name": "Week Warrior",
        "description": "Complete classes 7 days in a row",
        "icon": "flame",
        "color": "#F97316",
        "xp": 200,
        "rarity": "uncommon",
        "trigger": {"type": "streak", "count": 7}
    },
    "total_10": {
        "id": "total_10",
        "name": "Devoted Student",
        "description": "Complete 10 total classes across all subjects",
        "icon": "ribbon",
        "color": "#14B8A6",
        "xp": 150,
        "rarity": "uncommon",
        "trigger": {"type": "total_completions", "count": 10}
    },
    "total_50": {
        "id": "total_50",
        "name": "Scholar Elite",
        "description": "Complete 50 total classes — you're in the top tier!",
        "icon": "medal",
        "color": "#A855F7",
        "xp": 1000,
        "rarity": "legendary",
        "trigger": {"type": "total_completions", "count": 50}
    },
    "perfectionist": {
        "id": "perfectionist",
        "name": "Perfectionist",
        "description": "Score 100% on any class",
        "icon": "checkmark-done-circle",
        "color": "#22C55E",
        "xp": 200,
        "rarity": "rare",
        "trigger": {"type": "perfect_score", "count": 1}
    },
    "improver": {
        "id": "improver",
        "name": "Constant Improver",
        "description": "Improve your score on a repeated class",
        "icon": "trending-up",
        "color": "#06B6D4",
        "xp": 150,
        "rarity": "uncommon",
        "trigger": {"type": "score_improved", "count": 1}
    },
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def check_and_award_achievements(user_id: str, class_id: str, completion_count: int, score: Optional[float] = None) -> List[Dict]:
    """Check if user earned any new achievements after a class completion"""
    newly_earned = []
    
    # Get existing achievements
    existing = await achievements_collection.find({"user_id": user_id}).to_list(100)
    existing_ids = {a["achievement_id"] for a in existing}
    
    # Get total completions
    total_completions = await class_progress_collection.count_documents({"user_id": user_id})
    
    # Get unique languages
    unique_languages = await class_progress_collection.distinct("language_id", {"user_id": user_id, "language_id": {"$ne": None}})
    
    # Check repeat achievements (class_repeat type)
    repeat_achievements = [
        ("repeat_learner", 2),
        ("triple_master", 3),
        ("five_timer", 5),
        ("ten_timer", 10),
    ]
    for ach_id, required_count in repeat_achievements:
        if ach_id not in existing_ids and completion_count >= required_count:
            newly_earned.append(await award_achievement(user_id, ach_id, class_id))
    
    # Check total completion achievements
    total_achievements = [
        ("first_class", 1),
        ("total_10", 10),
        ("total_50", 50),
    ]
    for ach_id, required_count in total_achievements:
        if ach_id not in existing_ids and total_completions >= required_count:
            newly_earned.append(await award_achievement(user_id, ach_id, class_id))
    
    # Check polyglot achievements
    polyglot_achievements = [
        ("polyglot_5", 5),
        ("polyglot_10", 10),
    ]
    for ach_id, required_count in polyglot_achievements:
        if ach_id not in existing_ids and len(unique_languages) >= required_count:
            newly_earned.append(await award_achievement(user_id, ach_id, class_id))
    
    # Check perfect score
    if score is not None and score >= 100 and "perfectionist" not in existing_ids:
        newly_earned.append(await award_achievement(user_id, "perfectionist", class_id))
    
    # Check score improvement
    if score is not None and completion_count > 1 and "improver" not in existing_ids:
        prev_completions = await class_progress_collection.find(
            {"user_id": user_id, "class_id": class_id, "score": {"$ne": None}}
        ).sort("completed_at", -1).limit(2).to_list(2)
        if len(prev_completions) >= 2:
            prev_completions = [clean_doc(c) for c in prev_completions]
            if prev_completions[0].get("score", 0) > prev_completions[1].get("score", 0):
                newly_earned.append(await award_achievement(user_id, "improver", class_id))
    
    return [a for a in newly_earned if a is not None]


def clean_doc(doc: dict) -> dict:
    """Remove MongoDB _id from document for JSON serialization"""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def award_achievement(user_id: str, achievement_id: str, trigger_class_id: str) -> Optional[Dict]:
    """Award an achievement to a user"""
    if achievement_id not in ACHIEVEMENTS:
        return None
    
    ach = ACHIEVEMENTS[achievement_id]
    doc = {
        "user_id": user_id,
        "achievement_id": achievement_id,
        "name": ach["name"],
        "description": ach["description"],
        "icon": ach["icon"],
        "color": ach["color"],
        "xp": ach["xp"],
        "rarity": ach["rarity"],
        "trigger_class_id": trigger_class_id,
        "earned_at": datetime.utcnow().isoformat()
    }
    
    await achievements_collection.insert_one(doc.copy())
    return doc


# =============================================================================
# API ROUTES
# =============================================================================

@router.post("/complete")
async def complete_class(completion: ClassCompletion):
    """Record a class completion and check for achievements"""
    # Store the completion
    doc = {
        "user_id": completion.user_id,
        "class_id": completion.class_id,
        "class_name": completion.class_name,
        "language_id": completion.language_id,
        "category": completion.category,
        "score": completion.score,
        "notes": completion.notes,
        "completed_at": datetime.utcnow().isoformat()
    }
    await class_progress_collection.insert_one(doc.copy())
    
    # Count completions for this class
    completion_count = await class_progress_collection.count_documents({
        "user_id": completion.user_id,
        "class_id": completion.class_id
    })
    
    # Check and award achievements
    new_achievements = await check_and_award_achievements(
        completion.user_id, completion.class_id, completion_count, completion.score
    )
    
    return {
        "status": "completed",
        "class_id": completion.class_id,
        "class_name": completion.class_name,
        "completion_count": completion_count,
        "is_repeat": completion_count > 1,
        "new_achievements": new_achievements,
        "message": f"Class completed {completion_count} time{'s' if completion_count > 1 else ''}!" + 
                   (f" You earned {len(new_achievements)} new achievement{'s' if len(new_achievements) > 1 else ''}!" if new_achievements else "")
    }


@router.get("/class/{class_id}")
async def get_class_progress(class_id: str, user_id: str = "default_user"):
    """Get progress for a specific class"""
    completions = await class_progress_collection.find(
        {"user_id": user_id, "class_id": class_id}
    ).sort("completed_at", 1).to_list(100)
    
    if not completions:
        return {
            "class_id": class_id,
            "completion_count": 0,
            "completions": [],
            "can_repeat": True,
            "next_repeat_achievement": "Complete this class to earn 'First Steps'!"
        }
    
    scores = [c.get("score") for c in completions if c.get("score") is not None]
    completion_count = len(completions)
    
    # Determine next repeat achievement
    next_ach = None
    for threshold, ach_id in [(2, "repeat_learner"), (3, "triple_master"), (5, "five_timer"), (10, "ten_timer")]:
        if completion_count < threshold:
            next_ach = f"Complete {threshold - completion_count} more time{'s' if threshold - completion_count > 1 else ''} to earn '{ACHIEVEMENTS[ach_id]['name']}'!"
            break
    
    return {
        "class_id": class_id,
        "class_name": completions[0].get("class_name", class_id),
        "completion_count": completion_count,
        "first_completed": completions[0].get("completed_at"),
        "last_completed": completions[-1].get("completed_at"),
        "best_score": max(scores) if scores else None,
        "average_score": sum(scores) / len(scores) if scores else None,
        "scores_history": scores,
        "can_repeat": True,
        "next_repeat_achievement": next_ach or "You've earned all repeat achievements for this class!",
        "completions": [
            {
                "completed_at": c.get("completed_at"),
                "score": c.get("score"),
                "notes": c.get("notes")
            }
            for c in completions
        ]
    }


@router.get("/user/{user_id}/overview")
async def get_user_progress_overview(user_id: str):
    """Get overall learning progress for a user"""
    total_completions = await class_progress_collection.count_documents({"user_id": user_id})
    unique_classes = await class_progress_collection.distinct("class_id", {"user_id": user_id})
    unique_languages = await class_progress_collection.distinct("language_id", {"user_id": user_id, "language_id": {"$ne": None}})
    achievements = await achievements_collection.find({"user_id": user_id}).to_list(100)
    
    # Get repeat stats
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$class_id", "count": {"$sum": 1}, "name": {"$first": "$class_name"}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}}
    ]
    repeated_classes = await class_progress_collection.aggregate(pipeline).to_list(50)
    
    total_xp = sum(a.get("xp", 0) for a in achievements)
    
    return {
        "user_id": user_id,
        "total_completions": total_completions,
        "unique_classes": len(unique_classes),
        "unique_languages": len(unique_languages),
        "languages_studied": unique_languages,
        "total_xp": total_xp,
        "level": total_xp // 500 + 1,
        "achievements_count": len(achievements),
        "repeated_classes": [
            {"class_id": r["_id"], "class_name": r.get("name", r["_id"]), "times_completed": r["count"]}
            for r in repeated_classes
        ],
        "most_repeated": repeated_classes[0] if repeated_classes else None
    }


@router.get("/user/{user_id}/achievements")
async def get_user_achievements(user_id: str):
    """Get all achievements for a user"""
    earned = await achievements_collection.find({"user_id": user_id}).to_list(100)
    earned_ids = {a["achievement_id"] for a in earned}
    
    all_achievements = []
    for ach_id, ach in ACHIEVEMENTS.items():
        earned_data = next((e for e in earned if e["achievement_id"] == ach_id), None)
        all_achievements.append({
            "id": ach_id,
            "name": ach["name"],
            "description": ach["description"],
            "icon": ach["icon"],
            "color": ach["color"],
            "xp": ach["xp"],
            "rarity": ach["rarity"],
            "earned": ach_id in earned_ids,
            "earned_at": earned_data.get("earned_at") if earned_data else None,
            "trigger_class_id": earned_data.get("trigger_class_id") if earned_data else None
        })
    
    return {
        "achievements": all_achievements,
        "earned_count": len(earned_ids),
        "total_count": len(ACHIEVEMENTS),
        "total_xp": sum(a.get("xp", 0) for a in earned),
        "completion_percentage": round(len(earned_ids) / len(ACHIEVEMENTS) * 100, 1)
    }


@router.get("/achievements/all")
async def get_all_achievements():
    """Get list of all available achievements"""
    return {
        "achievements": [
            {
                "id": ach_id,
                "name": ach["name"],
                "description": ach["description"],
                "icon": ach["icon"],
                "color": ach["color"],
                "xp": ach["xp"],
                "rarity": ach["rarity"]
            }
            for ach_id, ach in ACHIEVEMENTS.items()
        ],
        "total": len(ACHIEVEMENTS),
        "total_xp_available": sum(a["xp"] for a in ACHIEVEMENTS.values())
    }


@router.get("/leaderboard")
async def get_leaderboard(limit: int = 20):
    """Get the class repeat leaderboard"""
    pipeline = [
        {"$group": {
            "_id": "$user_id",
            "total_completions": {"$sum": 1},
            "unique_classes": {"$addToSet": "$class_id"},
            "unique_languages": {"$addToSet": "$language_id"}
        }},
        {"$addFields": {
            "unique_class_count": {"$size": "$unique_classes"},
            "unique_language_count": {"$size": {
                "$filter": {"input": "$unique_languages", "as": "l", "cond": {"$ne": ["$$l", None]}}
            }}
        }},
        {"$sort": {"total_completions": -1}},
        {"$limit": limit}
    ]
    
    leaders = await class_progress_collection.aggregate(pipeline).to_list(limit)
    
    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "user_id": l["_id"],
                "total_completions": l["total_completions"],
                "unique_classes": l.get("unique_class_count", 0),
                "unique_languages": l.get("unique_language_count", 0)
            }
            for i, l in enumerate(leaders)
        ]
    }


@router.delete("/user/{user_id}/reset")
async def reset_user_progress(user_id: str):
    """Reset all progress for a user (admin/debug)"""
    prog_result = await class_progress_collection.delete_many({"user_id": user_id})
    ach_result = await achievements_collection.delete_many({"user_id": user_id})
    
    return {
        "status": "reset",
        "user_id": user_id,
        "completions_deleted": prog_result.deleted_count,
        "achievements_deleted": ach_result.deleted_count
    }
