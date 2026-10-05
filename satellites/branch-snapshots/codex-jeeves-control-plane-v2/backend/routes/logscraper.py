"""
╭───────────────────────────────────────────────────────────────────────────╮
│              CODEDOCK LOGSCRAPER - Jeeves Continuous Learning             │
│                                                                           │
│  Monitors user actions and feeds insights to Jeeves for adaptive learning │
│  - Tracks learning patterns, struggles, and progress                      │
│  - Builds personalized knowledge graphs                                   │
│  - Enables predictive tutoring recommendations                            │
╰───────────────────────────────────────────────────────────────────────────╯
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import uuid
import os

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/logscraper", tags=["Logscraper - Continuous Learning"])

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
mongo_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
logs_db = mongo_client.codedock_logs
jeeves_db = mongo_client.codedock_jeeves

# ============================================================================
# DATA MODELS
# ============================================================================

class UserAction(BaseModel):
    user_id: str
    action_type: Literal[
        # Learning Actions
        'lesson_started', 'lesson_completed', 'lesson_abandoned',
        'challenge_started', 'challenge_completed', 'challenge_failed',
        'quiz_started', 'quiz_completed', 'quiz_question_answered',
        'hint_requested', 'code_executed', 'code_error',
        'topic_searched', 'feature_used', 'session_started', 'session_ended',
        # Vault Actions
        'vault_created', 'vault_updated', 'vault_deleted', 'vault_shared',
        'code_saved', 'snippet_created', 'asset_uploaded', 'asset_deleted',
        # Game Actions
        'game_created', 'game_started', 'game_completed', 'game_published',
        'game_level_completed', 'game_achievement_unlocked', 'game_shared',
        # AI Interaction Actions
        'jeeves_asked', 'jeeves_feedback_positive', 'jeeves_feedback_negative',
        'ai_code_generated', 'ai_suggestion_accepted', 'ai_suggestion_rejected',
        # Project Actions
        'project_created', 'project_exported', 'project_forked', 'project_starred'
    ]
    action_data: Dict[str, Any] = {}
    context: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class LearningPattern(BaseModel):
    user_id: str
    pattern_type: str
    pattern_data: Dict[str, Any]
    confidence: float
    detected_at: datetime = Field(default_factory=datetime.utcnow)

class JeevesInsight(BaseModel):
    insight_id: str
    user_id: str
    insight_type: Literal['struggle', 'strength', 'recommendation', 'milestone', 'pattern']
    subject: Optional[str] = None
    topic: Optional[str] = None
    description: str
    actionable: bool = True
    priority: int = 5
    created_at: datetime = Field(default_factory=datetime.utcnow)

# ============================================================================
# LOGSCRAPER CORE
# ============================================================================

@router.get("/info")
async def get_logscraper_info():
    """Get logscraper system info"""
    return {
        "name": "CodeDock Logscraper v11.6 SOTA",
        "description": "Continuous learning system for Jeeves AI Tutor - Full SOTA Implementation",
        "capabilities": [
            "Real-time action tracking",
            "Learning pattern detection",
            "Struggle identification",
            "Strength recognition",
            "Personalized recommendations",
            "Adaptive difficulty adjustment",
            "Knowledge graph building",
            "Predictive tutoring",
            "Vault activity monitoring",
            "Game completion tracking",
            "AI interaction analysis",
            "Project lifecycle tracking",
            "Cross-session learning continuity"
        ],
        "tracked_actions": {
            "learning": 16,
            "vault": 4,
            "games": 7,
            "ai_interactions": 6,
            "projects": 4,
            "total": 37
        },
        "pattern_types": 18,
        "insight_types": 8,
        "analytics_features": [
            "Time-on-task analysis",
            "Skill progression curves",
            "Learning velocity metrics",
            "Engagement scoring",
            "Retention predictions",
            "Personalized content recommendations"
        ]
    }

@router.post("/log")
async def log_user_action(action: UserAction, background_tasks: BackgroundTasks):
    """Log a user action for analysis"""
    action_doc = {
        "action_id": f"act_{uuid.uuid4().hex[:12]}",
        **action.dict(),
        "processed": False
    }
    
    await logs_db.user_actions.insert_one(action_doc)
    
    # Process in background
    background_tasks.add_task(process_action, action_doc)
    
    return {
        "logged": True,
        "action_id": action_doc["action_id"],
        "timestamp": action.timestamp.isoformat()
    }

async def process_action(action: Dict):
    """Process an action and extract insights"""
    user_id = action["user_id"]
    action_type = action["action_type"]
    action_data = action.get("action_data", {})
    
    # Update user learning profile
    await update_learning_profile(user_id, action_type, action_data)
    
    # Detect patterns
    await detect_patterns(user_id, action_type, action_data)
    
    # Generate insights if needed
    await generate_insights(user_id, action_type, action_data)
    
    # Mark as processed
    await logs_db.user_actions.update_one(
        {"action_id": action["action_id"]},
        {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
    )

async def update_learning_profile(user_id: str, action_type: str, action_data: Dict):
    """Update user's learning profile based on action"""
    profile = await jeeves_db.learning_profiles.find_one({"user_id": user_id})
    
    if not profile:
        profile = {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "topics_studied": [],
            "challenges_attempted": [],
            "quiz_history": [],
            "struggle_areas": [],
            "strength_areas": [],
            "learning_velocity": 1.0,
            "preferred_difficulty": "medium",
            "total_study_time_minutes": 0,
            "session_count": 0,
            # New SOTA fields
            "vault_stats": {
                "code_saves": 0,
                "snippets_created": 0,
                "assets_uploaded": 0
            },
            "game_stats": {
                "games_created": 0,
                "games_completed": 0,
                "games_published": 0,
                "levels_completed": 0,
                "achievements_unlocked": 0
            },
            "ai_interaction_stats": {
                "questions_asked": 0,
                "positive_feedback": 0,
                "negative_feedback": 0,
                "suggestions_accepted": 0,
                "suggestions_rejected": 0,
                "code_generated": 0
            },
            "project_stats": {
                "projects_created": 0,
                "projects_exported": 0,
                "projects_forked": 0,
                "projects_starred": 0
            },
            "engagement_score": 50,
            "skill_progression": {},
            "learning_style_detected": None
        }
        await jeeves_db.learning_profiles.insert_one(profile)
    
    update = {"$set": {"last_active": datetime.utcnow()}}
    
    # ============== LEARNING ACTIONS ==============
    if action_type == "lesson_completed":
        topic = action_data.get("topic")
        if topic:
            update["$addToSet"] = {"topics_studied": topic}
            update["$inc"] = {"total_study_time_minutes": action_data.get("duration_minutes", 5)}
    
    elif action_type == "challenge_completed":
        update["$push"] = {
            "challenges_attempted": {
                "challenge_id": action_data.get("challenge_id"),
                "passed": action_data.get("passed", False),
                "score": action_data.get("score", 0),
                "time_seconds": action_data.get("time_seconds", 0),
                "category": action_data.get("category"),
                "timestamp": datetime.utcnow()
            }
        }
        # Update strength areas if passed
        if action_data.get("passed"):
            topic = action_data.get("topic")
            if topic:
                update.setdefault("$addToSet", {})["strength_areas"] = topic
    
    elif action_type == "challenge_failed":
        topic = action_data.get("topic")
        if topic:
            update.setdefault("$addToSet", {})["struggle_areas"] = topic
    
    elif action_type == "session_started":
        update["$inc"] = {"session_count": 1}
    
    elif action_type == "quiz_completed":
        update.setdefault("$push", {})["quiz_history"] = {
            "quiz_id": action_data.get("quiz_id"),
            "category": action_data.get("category"),
            "score": action_data.get("score", 0),
            "total_questions": action_data.get("total_questions", 0),
            "correct_answers": action_data.get("correct_answers", 0),
            "timestamp": datetime.utcnow()
        }
    
    # ============== VAULT ACTIONS ==============
    elif action_type == "code_saved":
        update.setdefault("$inc", {})["vault_stats.code_saves"] = 1
    
    elif action_type == "snippet_created":
        update.setdefault("$inc", {})["vault_stats.snippets_created"] = 1
    
    elif action_type == "asset_uploaded":
        update.setdefault("$inc", {})["vault_stats.assets_uploaded"] = 1
    
    # ============== GAME ACTIONS ==============
    elif action_type == "game_created":
        update.setdefault("$inc", {})["game_stats.games_created"] = 1
    
    elif action_type == "game_completed":
        update.setdefault("$inc", {})["game_stats.games_completed"] = 1
        # Track game completion details
        await jeeves_db.game_completions.insert_one({
            "user_id": user_id,
            "game_id": action_data.get("game_id"),
            "game_type": action_data.get("game_type"),
            "completion_time_minutes": action_data.get("completion_time_minutes", 0),
            "difficulty": action_data.get("difficulty"),
            "score": action_data.get("score", 0),
            "timestamp": datetime.utcnow()
        })
    
    elif action_type == "game_published":
        update.setdefault("$inc", {})["game_stats.games_published"] = 1
    
    elif action_type == "game_level_completed":
        update.setdefault("$inc", {})["game_stats.levels_completed"] = 1
    
    elif action_type == "game_achievement_unlocked":
        update.setdefault("$inc", {})["game_stats.achievements_unlocked"] = 1
    
    # ============== AI INTERACTION ACTIONS ==============
    elif action_type == "jeeves_asked":
        update.setdefault("$inc", {})["ai_interaction_stats.questions_asked"] = 1
    
    elif action_type == "jeeves_feedback_positive":
        update.setdefault("$inc", {})["ai_interaction_stats.positive_feedback"] = 1
    
    elif action_type == "jeeves_feedback_negative":
        update.setdefault("$inc", {})["ai_interaction_stats.negative_feedback"] = 1
    
    elif action_type == "ai_suggestion_accepted":
        update.setdefault("$inc", {})["ai_interaction_stats.suggestions_accepted"] = 1
    
    elif action_type == "ai_suggestion_rejected":
        update.setdefault("$inc", {})["ai_interaction_stats.suggestions_rejected"] = 1
    
    elif action_type == "ai_code_generated":
        update.setdefault("$inc", {})["ai_interaction_stats.code_generated"] = 1
    
    # ============== PROJECT ACTIONS ==============
    elif action_type == "project_created":
        update.setdefault("$inc", {})["project_stats.projects_created"] = 1
    
    elif action_type == "project_exported":
        update.setdefault("$inc", {})["project_stats.projects_exported"] = 1
    
    elif action_type == "project_forked":
        update.setdefault("$inc", {})["project_stats.projects_forked"] = 1
    
    elif action_type == "project_starred":
        update.setdefault("$inc", {})["project_stats.projects_starred"] = 1
    
    await jeeves_db.learning_profiles.update_one(
        {"user_id": user_id},
        update
    )

async def detect_patterns(user_id: str, action_type: str, action_data: Dict):
    """Detect learning patterns from user actions"""
    # Get recent actions
    recent_actions = await logs_db.user_actions.find(
        {"user_id": user_id},
        sort=[("timestamp", -1)],
        limit=100
    ).to_list(100)
    
    if len(recent_actions) < 5:
        return
    
    patterns_detected = []
    
    # Pattern: Repeated failures in same topic
    failures = [a for a in recent_actions if a["action_type"] == "challenge_failed"]
    if len(failures) >= 3:
        topics = [f.get("action_data", {}).get("topic") for f in failures[:10]]
        from collections import Counter
        topic_counts = Counter(topics)
        for topic, count in topic_counts.items():
            if topic and count >= 3:
                patterns_detected.append({
                    "pattern_type": "repeated_struggle",
                    "topic": topic,
                    "count": count,
                    "confidence": min(0.9, 0.5 + count * 0.1)
                })
    
    # Pattern: Quick completions (high skill)
    completions = [a for a in recent_actions if a["action_type"] == "challenge_completed"]
    fast_completions = [c for c in completions if c.get("action_data", {}).get("time_seconds", 999) < 60]
    if len(fast_completions) >= 3:
        patterns_detected.append({
            "pattern_type": "fast_learner",
            "count": len(fast_completions),
            "confidence": 0.8
        })
    
    # Pattern: Hint dependency
    hints = [a for a in recent_actions if a["action_type"] == "hint_requested"]
    if len(hints) >= 5:
        patterns_detected.append({
            "pattern_type": "hint_dependent",
            "count": len(hints),
            "confidence": 0.7
        })
    
    # Pattern: Game enthusiast
    game_actions = [a for a in recent_actions if a["action_type"].startswith("game_")]
    if len(game_actions) >= 10:
        patterns_detected.append({
            "pattern_type": "game_enthusiast",
            "count": len(game_actions),
            "confidence": 0.85
        })
    
    # Pattern: Prolific creator (many games/projects created)
    creations = [a for a in recent_actions if a["action_type"] in ["game_created", "project_created"]]
    if len(creations) >= 5:
        patterns_detected.append({
            "pattern_type": "prolific_creator",
            "count": len(creations),
            "confidence": 0.9
        })
    
    # Pattern: Active vault user
    vault_actions = [a for a in recent_actions if a["action_type"] in ["code_saved", "snippet_created", "asset_uploaded"]]
    if len(vault_actions) >= 10:
        patterns_detected.append({
            "pattern_type": "vault_power_user",
            "count": len(vault_actions),
            "confidence": 0.75
        })
    
    # Pattern: AI collaborator (high AI interaction)
    ai_actions = [a for a in recent_actions if a["action_type"].startswith("jeeves_") or a["action_type"].startswith("ai_")]
    if len(ai_actions) >= 15:
        patterns_detected.append({
            "pattern_type": "ai_collaborator",
            "count": len(ai_actions),
            "confidence": 0.8
        })
    
    # Pattern: Night owl (learns late)
    late_actions = [a for a in recent_actions if a.get("timestamp") and a["timestamp"].hour >= 22 or a["timestamp"].hour <= 4]
    if len(late_actions) >= 10:
        patterns_detected.append({
            "pattern_type": "night_owl",
            "count": len(late_actions),
            "confidence": 0.7
        })
    
    # Pattern: Early bird (learns early)
    early_actions = [a for a in recent_actions if a.get("timestamp") and 5 <= a["timestamp"].hour <= 8]
    if len(early_actions) >= 10:
        patterns_detected.append({
            "pattern_type": "early_bird",
            "count": len(early_actions),
            "confidence": 0.7
        })
    
    # Pattern: Consistent learner (daily activity)
    action_dates = set()
    for a in recent_actions:
        if a.get("timestamp"):
            action_dates.add(a["timestamp"].date())
    if len(action_dates) >= 7:
        patterns_detected.append({
            "pattern_type": "consistent_learner",
            "days_active": len(action_dates),
            "confidence": min(0.95, 0.5 + len(action_dates) * 0.05)
        })
    
    # Pattern: Quiz master (high quiz scores)
    quiz_results = [a for a in recent_actions if a["action_type"] == "quiz_completed"]
    if len(quiz_results) >= 5:
        avg_score = sum(q.get("action_data", {}).get("score", 0) for q in quiz_results) / len(quiz_results)
        if avg_score >= 80:
            patterns_detected.append({
                "pattern_type": "quiz_master",
                "average_score": avg_score,
                "confidence": 0.85
            })
    
    # Pattern: Error recovery (failed then succeeded)
    for i, action in enumerate(recent_actions[:-1]):
        if action["action_type"] == "challenge_failed":
            challenge_id = action.get("action_data", {}).get("challenge_id")
            # Check if later succeeded
            for later_action in recent_actions[i+1:]:
                if (later_action["action_type"] == "challenge_completed" and 
                    later_action.get("action_data", {}).get("challenge_id") == challenge_id and
                    later_action.get("action_data", {}).get("passed")):
                    patterns_detected.append({
                        "pattern_type": "perseverant_learner",
                        "challenge_id": challenge_id,
                        "confidence": 0.9
                    })
                    break
    
    # Store patterns
    for pattern in patterns_detected:
        await jeeves_db.patterns.update_one(
            {"user_id": user_id, "pattern_type": pattern["pattern_type"]},
            {
                "$set": {
                    "user_id": user_id,
                    **pattern,
                    "detected_at": datetime.utcnow()
                }
            },
            upsert=True
        )

async def generate_insights(user_id: str, action_type: str, action_data: Dict):
    """Generate actionable insights for Jeeves"""
    insights = []
    
    # Get user profile
    profile = await jeeves_db.learning_profiles.find_one({"user_id": user_id})
    if not profile:
        return
    
    # Insight: Struggle detection
    struggle_areas = profile.get("struggle_areas", [])
    if len(struggle_areas) > 0 and action_type == "challenge_failed":
        topic = action_data.get("topic")
        if topic in struggle_areas:
            insights.append({
                "insight_type": "struggle",
                "subject": action_data.get("category"),
                "topic": topic,
                "description": f"User consistently struggles with {topic}. Consider simpler exercises or foundational review.",
                "priority": 8
            })
    
    # Insight: Milestone reached
    challenges = profile.get("challenges_attempted", [])
    passed = [c for c in challenges if c.get("passed")]
    if len(passed) in [10, 25, 50, 100]:
        insights.append({
            "insight_type": "milestone",
            "description": f"User completed {len(passed)} challenges! Consider congratulating and suggesting advanced topics.",
            "priority": 5
        })
    
    # Store insights
    for insight in insights:
        await jeeves_db.insights.insert_one({
            "insight_id": f"ins_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            **insight,
            "created_at": datetime.utcnow(),
            "acted_upon": False
        })

@router.get("/insights/{user_id}")
async def get_user_insights(user_id: str, limit: int = 10):
    """Get insights for a user"""
    insights = await jeeves_db.insights.find(
        {"user_id": user_id, "acted_upon": False},
        sort=[("priority", -1), ("created_at", -1)],
        limit=limit
    ).to_list(limit)
    
    return {
        "user_id": user_id,
        "insights": [
            {
                "insight_id": i.get("insight_id"),
                "type": i.get("insight_type"),
                "subject": i.get("subject"),
                "topic": i.get("topic"),
                "description": i.get("description"),
                "priority": i.get("priority")
            }
            for i in insights
        ],
        "total": len(insights)
    }

@router.get("/profile/{user_id}")
async def get_learning_profile(user_id: str):
    """Get comprehensive learning profile for Jeeves"""
    profile = await jeeves_db.learning_profiles.find_one({"user_id": user_id})
    patterns = await jeeves_db.patterns.find({"user_id": user_id}).to_list(20)
    insights = await jeeves_db.insights.find(
        {"user_id": user_id, "acted_upon": False},
        limit=5
    ).to_list(5)
    
    if not profile:
        return {"user_id": user_id, "profile": None, "patterns": [], "insights": []}
    
    return {
        "user_id": user_id,
        "profile": {
            "topics_studied": profile.get("topics_studied", []),
            "struggle_areas": profile.get("struggle_areas", []),
            "strength_areas": profile.get("strength_areas", []),
            "learning_velocity": profile.get("learning_velocity", 1.0),
            "preferred_difficulty": profile.get("preferred_difficulty", "medium"),
            "total_study_time_minutes": profile.get("total_study_time_minutes", 0),
            "session_count": profile.get("session_count", 0),
            "challenges_completed": len([c for c in profile.get("challenges_attempted", []) if c.get("passed")])
        },
        "patterns": [
            {
                "type": p.get("pattern_type"),
                "confidence": p.get("confidence"),
                "topic": p.get("topic")
            }
            for p in patterns
        ],
        "pending_insights": len(insights),
        "recommendations": await generate_recommendations(profile, patterns)
    }

async def generate_recommendations(profile: Dict, patterns: List) -> List[Dict]:
    """Generate personalized recommendations"""
    recommendations = []
    
    struggle_areas = profile.get("struggle_areas", [])
    if struggle_areas:
        recommendations.append({
            "type": "review",
            "title": "Review Fundamentals",
            "description": f"Consider reviewing: {', '.join(struggle_areas[:3])}",
            "priority": "high"
        })
    
    study_time = profile.get("total_study_time_minutes", 0)
    if study_time < 60:
        recommendations.append({
            "type": "engagement",
            "title": "Build Consistency",
            "description": "Try to study for at least 15 minutes daily to build momentum",
            "priority": "medium"
        })
    
    # Check for fast learner pattern
    fast_learner = any(p.get("pattern_type") == "fast_learner" for p in patterns)
    if fast_learner:
        recommendations.append({
            "type": "advancement",
            "title": "Ready for Advanced Content",
            "description": "Your quick completion times suggest you're ready for harder challenges!",
            "priority": "high"
        })
    
    return recommendations

@router.post("/scrape-session")
async def scrape_session(user_id: str):
    """Run a full scrape session to update Jeeves knowledge about a user"""
    # Get all user actions from last 7 days
    week_ago = datetime.utcnow() - timedelta(days=7)
    actions = await logs_db.user_actions.find(
        {"user_id": user_id, "timestamp": {"$gte": week_ago}}
    ).to_list(1000)
    
    # Aggregate statistics
    stats = {
        "total_actions": len(actions),
        "period_start": week_ago.isoformat(),
        "period_end": datetime.utcnow().isoformat(),
        
        # Learning stats
        "lessons_completed": len([a for a in actions if a["action_type"] == "lesson_completed"]),
        "challenges_attempted": len([a for a in actions if a["action_type"] in ["challenge_completed", "challenge_failed"]]),
        "challenges_passed": len([a for a in actions if a["action_type"] == "challenge_completed" and a.get("action_data", {}).get("passed")]),
        "quizzes_taken": len([a for a in actions if a["action_type"] == "quiz_completed"]),
        "hints_used": len([a for a in actions if a["action_type"] == "hint_requested"]),
        "errors_encountered": len([a for a in actions if a["action_type"] == "code_error"]),
        
        # Vault stats
        "vault_activity": {
            "code_saves": len([a for a in actions if a["action_type"] == "code_saved"]),
            "snippets_created": len([a for a in actions if a["action_type"] == "snippet_created"]),
            "assets_uploaded": len([a for a in actions if a["action_type"] == "asset_uploaded"]),
            "total_vault_actions": len([a for a in actions if a["action_type"] in ["code_saved", "snippet_created", "asset_uploaded", "vault_created", "vault_updated"]])
        },
        
        # Game stats
        "game_activity": {
            "games_created": len([a for a in actions if a["action_type"] == "game_created"]),
            "games_completed": len([a for a in actions if a["action_type"] == "game_completed"]),
            "games_published": len([a for a in actions if a["action_type"] == "game_published"]),
            "levels_completed": len([a for a in actions if a["action_type"] == "game_level_completed"]),
            "achievements_unlocked": len([a for a in actions if a["action_type"] == "game_achievement_unlocked"]),
            "total_game_actions": len([a for a in actions if a["action_type"].startswith("game_")])
        },
        
        # AI interaction stats
        "ai_interaction": {
            "questions_asked": len([a for a in actions if a["action_type"] == "jeeves_asked"]),
            "positive_feedback": len([a for a in actions if a["action_type"] == "jeeves_feedback_positive"]),
            "negative_feedback": len([a for a in actions if a["action_type"] == "jeeves_feedback_negative"]),
            "suggestions_accepted": len([a for a in actions if a["action_type"] == "ai_suggestion_accepted"]),
            "suggestions_rejected": len([a for a in actions if a["action_type"] == "ai_suggestion_rejected"]),
            "code_generated": len([a for a in actions if a["action_type"] == "ai_code_generated"])
        },
        
        # Project stats
        "project_activity": {
            "projects_created": len([a for a in actions if a["action_type"] == "project_created"]),
            "projects_exported": len([a for a in actions if a["action_type"] == "project_exported"]),
            "projects_forked": len([a for a in actions if a["action_type"] == "project_forked"])
        }
    }
    
    # Calculate success rate
    if stats["challenges_attempted"] > 0:
        stats["success_rate"] = stats["challenges_passed"] / stats["challenges_attempted"]
    else:
        stats["success_rate"] = 0
    
    # Calculate engagement score
    engagement_factors = [
        stats["lessons_completed"] * 2,
        stats["challenges_passed"] * 3,
        stats["quizzes_taken"] * 2,
        stats["vault_activity"]["total_vault_actions"],
        stats["game_activity"]["total_game_actions"] * 2,
        stats["ai_interaction"]["questions_asked"]
    ]
    stats["engagement_score"] = min(100, sum(engagement_factors))
    
    # Calculate learning velocity (actions per day)
    unique_days = set()
    for a in actions:
        if a.get("timestamp"):
            unique_days.add(a["timestamp"].date())
    stats["active_days"] = len(unique_days)
    stats["learning_velocity"] = round(len(actions) / max(1, len(unique_days)), 2)
    
    # Detect dominant learning style
    if stats["game_activity"]["total_game_actions"] > 20:
        stats["detected_learning_style"] = "kinesthetic"
    elif stats["quizzes_taken"] > 10:
        stats["detected_learning_style"] = "reading/writing"
    elif stats["ai_interaction"]["questions_asked"] > 15:
        stats["detected_learning_style"] = "auditory"
    else:
        stats["detected_learning_style"] = "visual"
    
    # Store scrape results
    await jeeves_db.scrape_results.insert_one({
        "user_id": user_id,
        "scraped_at": datetime.utcnow(),
        "period_days": 7,
        "stats": stats
    })
    
    # Update learning profile with computed metrics
    await jeeves_db.learning_profiles.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "engagement_score": stats["engagement_score"],
                "learning_velocity": stats["learning_velocity"],
                "learning_style_detected": stats["detected_learning_style"],
                "last_scraped": datetime.utcnow()
            }
        }
    )
    
    return {
        "user_id": user_id,
        "scraped": True,
        "actions_processed": len(actions),
        "stats": stats,
        "jeeves_updated": True,
        "insights_generated": await generate_scrape_insights(user_id, stats)
    }


async def generate_scrape_insights(user_id: str, stats: Dict) -> List[Dict]:
    """Generate insights from scrape session data"""
    insights = []
    
    # High performer insight
    if stats["success_rate"] > 0.8:
        insights.append({
            "type": "strength",
            "title": "High Achiever",
            "description": f"Excellent {stats['success_rate']*100:.0f}% success rate on challenges!",
            "recommendation": "Consider advancing to harder difficulty levels"
        })
    
    # Struggling insight
    if stats["success_rate"] < 0.4 and stats["challenges_attempted"] > 5:
        insights.append({
            "type": "struggle",
            "title": "Needs Support",
            "description": f"Only {stats['success_rate']*100:.0f}% success rate",
            "recommendation": "Review fundamentals and try easier challenges first"
        })
    
    # Game creator insight
    if stats["game_activity"]["games_created"] > 3:
        insights.append({
            "type": "achievement",
            "title": "Prolific Creator",
            "description": f"Created {stats['game_activity']['games_created']} games this week!",
            "recommendation": "Consider publishing your best game to share with others"
        })
    
    # Vault power user insight
    if stats["vault_activity"]["total_vault_actions"] > 20:
        insights.append({
            "type": "pattern",
            "title": "Organized Developer",
            "description": "Excellent use of the vault for code organization",
            "recommendation": "Consider sharing your snippets with the community"
        })
    
    # AI collaboration insight
    ai_ratio = stats["ai_interaction"]["suggestions_accepted"] / max(1, stats["ai_interaction"]["suggestions_accepted"] + stats["ai_interaction"]["suggestions_rejected"])
    if ai_ratio > 0.7 and stats["ai_interaction"]["suggestions_accepted"] > 5:
        insights.append({
            "type": "pattern",
            "title": "AI Collaborator",
            "description": f"Strong AI partnership with {ai_ratio*100:.0f}% suggestion acceptance",
            "recommendation": "Continue leveraging AI while building independent problem-solving skills"
        })
    
    # Store insights
    for insight in insights:
        await jeeves_db.insights.insert_one({
            "insight_id": f"ins_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "insight_type": insight["type"],
            "description": f"{insight['title']}: {insight['description']}",
            "recommendation": insight["recommendation"],
            "created_at": datetime.utcnow(),
            "acted_upon": False,
            "source": "scrape_session"
        })
    
    return insights
