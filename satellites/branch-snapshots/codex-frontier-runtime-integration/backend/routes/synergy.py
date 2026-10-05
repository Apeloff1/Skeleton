"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CODEDOCK SYNERGY INTEGRATION v12.0 - Cross-Feature API               ║
║                                                                              ║
║  Unified API endpoints that leverage data across all features:               ║
║  • AI-aware learning recommendations                                         ║
║  • Emotional state-adaptive content delivery                                 ║
║  • Cross-module progress tracking                                            ║
║  • Unified analytics and insights                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from services.database import (
    synergy, user_profiles_collection, reading_progress_collection,
    ai_interactions_collection, jeeves_eq_profiles_collection,
    curriculum_collection, quiz_collection
)

router = APIRouter(prefix="/api/synergy", tags=["Synergy Integration"])

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class UserContextRequest(BaseModel):
    user_id: str
    include_recommendations: bool = True
    include_insights: bool = True

class LearningSessionStart(BaseModel):
    user_id: str
    module_id: str
    session_type: str = "reading"  # reading, quiz, practice

class LearningSessionUpdate(BaseModel):
    user_id: str
    module_id: str
    progress: float
    time_spent_seconds: int
    emotional_state: Optional[str] = None

class AIInteractionLog(BaseModel):
    user_id: str
    interaction_type: str  # code_generation, explanation, debugging, tutoring
    prompt: str
    response: str
    context_module: Optional[str] = None
    satisfaction_rating: Optional[int] = None

class DashboardRequest(BaseModel):
    user_id: str
    time_range_days: int = 7

# ============================================================================
# UNIFIED USER CONTEXT ENDPOINT
# ============================================================================

@router.post("/context")
async def get_unified_context(request: UserContextRequest):
    """
    Get comprehensive user context combining:
    - Learning progress across all tracks
    - Emotional state and preferences
    - Recent AI interactions
    - Personalized recommendations
    """
    context = await synergy.get_user_context(request.user_id)
    
    response = {
        "user_id": request.user_id,
        "timestamp": datetime.utcnow().isoformat(),
        "context": context
    }
    
    if request.include_recommendations:
        recommendations = await synergy.get_personalized_recommendations(request.user_id)
        response["recommendations"] = recommendations
    
    if request.include_insights:
        # Calculate insights
        total_interactions = await ai_interactions_collection.count_documents(
            {"user_id": request.user_id}
        )
        this_week = datetime.utcnow() - timedelta(days=7)
        week_interactions = await ai_interactions_collection.count_documents(
            {"user_id": request.user_id, "timestamp": {"$gte": this_week}}
        )
        
        response["insights"] = {
            "total_ai_interactions": total_interactions,
            "interactions_this_week": week_interactions,
            "learning_velocity": context["learning"]["modules_completed"] / max(1, context["learning"]["total_study_time"] / 60),
            "engagement_trend": "increasing" if week_interactions > total_interactions / 4 else "stable"
        }
    
    return response

# ============================================================================
# LEARNING SESSION MANAGEMENT
# ============================================================================

@router.post("/session/start")
async def start_learning_session(session: LearningSessionStart):
    """Start a tracked learning session with emotional context"""
    # Get current emotional state
    eq_profile = await jeeves_eq_profiles_collection.find_one(
        {"user_id": session.user_id}
    ) or {}
    
    current_emotion = eq_profile.get("current_emotion", "neutral")
    stress_level = eq_profile.get("stress_level", 0.3)
    
    # Adapt content based on emotional state
    adaptations = []
    if stress_level > 0.7:
        adaptations.append("simplified_explanations")
        adaptations.append("more_breaks_suggested")
    if current_emotion in ["frustrated", "confused"]:
        adaptations.append("extra_examples")
        adaptations.append("encouragement_messages")
    
    # Log session start
    await ai_interactions_collection.insert_one({
        "user_id": session.user_id,
        "type": "session_start",
        "module_id": session.module_id,
        "session_type": session.session_type,
        "emotional_context": {
            "emotion": current_emotion,
            "stress_level": stress_level
        },
        "adaptations": adaptations,
        "timestamp": datetime.utcnow()
    })
    
    return {
        "session_started": True,
        "module_id": session.module_id,
        "emotional_context": {
            "detected_emotion": current_emotion,
            "stress_level": stress_level
        },
        "content_adaptations": adaptations,
        "recommended_session_length": 25 if stress_level < 0.5 else 15,  # Pomodoro timing
        "tips": get_emotional_tips(current_emotion)
    }

@router.post("/session/update")
async def update_learning_session(update: LearningSessionUpdate):
    """Update learning progress and optionally update emotional state"""
    await synergy.update_learning_progress(
        update.user_id,
        update.module_id,
        update.progress,
        update.time_spent_seconds // 60
    )
    
    if update.emotional_state:
        await synergy.update_emotional_state(
            update.user_id,
            update.emotional_state,
            0.7,  # Default intensity
            "self_report"
        )
    
    # Check for achievements
    achievements = await check_achievements(update.user_id)
    
    return {
        "progress_updated": True,
        "current_progress": update.progress,
        "new_achievements": achievements,
        "xp_earned": 10 if update.progress < 100 else 50
    }

# ============================================================================
# AI INTERACTION LOGGING WITH CONTEXT
# ============================================================================

@router.post("/ai/log")
async def log_ai_interaction(interaction: AIInteractionLog):
    """Log AI interaction with full context for analytics"""
    interaction_id = await synergy.log_ai_interaction(
        interaction.user_id,
        interaction.interaction_type,
        interaction.prompt,
        interaction.response,
        {
            "context_module": interaction.context_module,
            "satisfaction": interaction.satisfaction_rating
        }
    )
    
    # Update interaction patterns
    await update_interaction_patterns(interaction.user_id, interaction.interaction_type)
    
    return {
        "logged": True,
        "interaction_id": interaction_id,
        "pattern_updated": True
    }

# ============================================================================
# UNIFIED DASHBOARD
# ============================================================================

@router.post("/dashboard")
async def get_unified_dashboard(request: DashboardRequest):
    """Get unified dashboard data combining all features"""
    time_start = datetime.utcnow() - timedelta(days=request.time_range_days)
    
    # Aggregate learning data
    learning_progress = await reading_progress_collection.find(
        {"user_id": request.user_id}
    ).to_list(1000)
    
    # Aggregate AI interactions
    ai_interactions = await ai_interactions_collection.find(
        {"user_id": request.user_id, "timestamp": {"$gte": time_start}}
    ).to_list(1000)
    
    # Get emotional history
    eq_profile = await jeeves_eq_profiles_collection.find_one(
        {"user_id": request.user_id}
    ) or {}
    
    # Calculate metrics
    total_study_time = sum(p.get("time_spent", 0) for p in learning_progress)
    completed_modules = len([p for p in learning_progress if p.get("completed")])
    
    # Interaction breakdown
    interaction_types = {}
    for i in ai_interactions:
        t = i.get("type", "other")
        interaction_types[t] = interaction_types.get(t, 0) + 1
    
    return {
        "user_id": request.user_id,
        "period": f"Last {request.time_range_days} days",
        "learning": {
            "total_study_minutes": total_study_time,
            "modules_completed": completed_modules,
            "current_streak": await get_study_streak(request.user_id),
            "xp_earned": completed_modules * 50 + total_study_time
        },
        "ai_usage": {
            "total_interactions": len(ai_interactions),
            "by_type": interaction_types,
            "avg_per_day": len(ai_interactions) / max(1, request.time_range_days)
        },
        "emotional_wellness": {
            "current_state": eq_profile.get("current_emotion", "neutral"),
            "avg_stress_level": eq_profile.get("stress_level", 0.3),
            "pomodoro_sessions": eq_profile.get("pomodoro_completed", 0)
        },
        "recommendations": await synergy.get_personalized_recommendations(request.user_id)
    }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_emotional_tips(emotion: str) -> List[str]:
    """Get tips based on emotional state"""
    tips = {
        "frustrated": [
            "Take a 5-minute break - you've got this!",
            "Try breaking the problem into smaller steps",
            "It's okay to ask for help or revisit fundamentals"
        ],
        "confused": [
            "Re-read the key concepts section",
            "Try the interactive examples",
            "The AI tutor can explain this differently"
        ],
        "confident": [
            "Great momentum! Consider tackling a challenge",
            "You might enjoy the advanced track",
            "Share your knowledge - teaching reinforces learning"
        ],
        "tired": [
            "Consider saving progress and taking a break",
            "A short walk can boost focus",
            "Review mode might be easier than new content"
        ],
        "neutral": [
            "Ready to learn? Let's dive in!",
            "Set a small goal for this session",
            "Remember: consistency beats intensity"
        ]
    }
    return tips.get(emotion, tips["neutral"])

async def check_achievements(user_id: str) -> List[Dict]:
    """Check and award new achievements"""
    profile = await user_profiles_collection.find_one({"user_id": user_id}) or {}
    existing = set(profile.get("achievements", []))
    new_achievements = []
    
    modules_completed = profile.get("modules_completed", 0)
    
    # Check achievement conditions
    if modules_completed >= 1 and "first_module" not in existing:
        new_achievements.append({"id": "first_module", "name": "First Steps", "xp": 100})
    if modules_completed >= 10 and "ten_modules" not in existing:
        new_achievements.append({"id": "ten_modules", "name": "Dedicated Learner", "xp": 500})
    if modules_completed >= 50 and "fifty_modules" not in existing:
        new_achievements.append({"id": "fifty_modules", "name": "Knowledge Seeker", "xp": 2000})
    
    # Update profile with new achievements
    if new_achievements:
        await user_profiles_collection.update_one(
            {"user_id": user_id},
            {
                "$addToSet": {"achievements": {"$each": [a["id"] for a in new_achievements]}},
                "$inc": {"xp": sum(a["xp"] for a in new_achievements)}
            }
        )
    
    return new_achievements

async def get_study_streak(user_id: str) -> int:
    """Calculate current study streak"""
    profile = await user_profiles_collection.find_one({"user_id": user_id}) or {}
    last_study = profile.get("last_study_date")
    
    if not last_study:
        return 0
    
    # Check if studied yesterday or today
    today = datetime.utcnow().date()
    last_date = last_study.date() if isinstance(last_study, datetime) else last_study
    
    diff = (today - last_date).days
    if diff > 1:
        return 0
    
    return profile.get("study_streak", 0)

async def update_interaction_patterns(user_id: str, interaction_type: str):
    """Update user's AI interaction patterns for personalization"""
    await user_profiles_collection.update_one(
        {"user_id": user_id},
        {
            "$inc": {f"interaction_patterns.{interaction_type}": 1},
            "$set": {"last_interaction": datetime.utcnow()}
        },
        upsert=True
    )
