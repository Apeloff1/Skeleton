"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         CODEDOCK DATABASE SERVICE v12.0 - Enhanced MongoDB Integration        ║
║                                                                              ║
║  Features:                                                                   ║
║  • Connection pooling with production-optimized settings                     ║
║  • Collection references for all data types                                  ║
║  • Data migration utilities                                                  ║
║  • Synergy layer for cross-feature data access                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import MONGO_URL, DB_NAME, MONGO_POOL_CONFIG
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger("CodeDock.Database")

# Use the centralized multi-DB factory so every module shares the same client
# and every caller sees the same view of (core | content | swarm) DBs.
from core.databases import (
    client,
    core_db as db,
    content_db,
    swarm_db,
)

# ============================================================================
# CORE COLLECTIONS
# ============================================================================
files_collection = db.files
addons_collection = db.addons
preferences_collection = db.preferences
history_collection = db.history
snippets_collection = db.snippets
sessions_collection = db.sessions

# ============================================================================
# LEARNING & CURRICULUM COLLECTIONS (v12.0)
# ============================================================================
curriculum_collection = db.curriculum_modules
quiz_collection = db.quiz_bank
reading_progress_collection = db.reading_progress
learning_paths_collection = db.learning_paths

# ============================================================================
# AI & INTERACTIONS COLLECTIONS (v12.0)
# ============================================================================
ai_interactions_collection = db.ai_interactions
ai_insights_collection = db.ai_insights
jeeves_eq_profiles_collection = db.jeeves_eq_profiles
ai_toolkit_sessions_collection = db.ai_toolkit_sessions

# ============================================================================
# USER & PROGRESS COLLECTIONS (v12.0)
# ============================================================================
user_profiles_collection = db.user_profiles
achievements_collection = db.achievements
study_streaks_collection = db.study_streaks

# ============================================================================
# VAULT & EXPORTS COLLECTIONS
# ============================================================================
vault_collection = db.vault_entries
export_jobs_collection = db.export_jobs

# ============================================================================
# HEALTH & UTILITY FUNCTIONS
# ============================================================================

async def health_check() -> bool:
    """Check database connectivity"""
    try:
        await client.admin.command('ping')
        return True
    except Exception:
        return False

async def get_collection_stats() -> dict:
    """Get statistics about collections"""
    return {
        "files": await files_collection.count_documents({}),
        "addons": await addons_collection.count_documents({}),
        "snippets": await snippets_collection.count_documents({}),
        "sessions": await sessions_collection.count_documents({}),
        "curriculum_modules": await curriculum_collection.count_documents({}),
        "quiz_questions": await quiz_collection.count_documents({}),
        "ai_interactions": await ai_interactions_collection.count_documents({}),
        "user_profiles": await user_profiles_collection.count_documents({})
    }

# ============================================================================
# SYNERGY LAYER - Cross-Feature Data Access
# ============================================================================

class SynergyLayer:
    """
    Provides unified access to data across features for enhanced integration.
    Enables AI to leverage learning progress, emotional state, and user history.
    """
    
    @staticmethod
    async def get_user_context(user_id: str) -> Dict[str, Any]:
        """Get comprehensive user context for AI personalization"""
        profile = await user_profiles_collection.find_one({"user_id": user_id}) or {}
        reading_progress = await reading_progress_collection.find({"user_id": user_id}).to_list(100)
        ai_history = await ai_interactions_collection.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(10).to_list(10)
        eq_profile = await jeeves_eq_profiles_collection.find_one({"user_id": user_id}) or {}
        
        return {
            "profile": profile,
            "learning": {
                "modules_completed": len([p for p in reading_progress if p.get("completed")]),
                "current_track": profile.get("current_track"),
                "study_streak": profile.get("study_streak", 0),
                "total_study_time": sum(p.get("time_spent", 0) for p in reading_progress)
            },
            "emotional": {
                "current_state": eq_profile.get("current_emotion", "neutral"),
                "stress_level": eq_profile.get("stress_level", 0.3),
                "engagement": eq_profile.get("engagement_level", 0.7),
                "preferred_pace": eq_profile.get("learning_pace", "moderate")
            },
            "recent_interactions": [
                {"type": i.get("type"), "topic": i.get("topic")}
                for i in ai_history
            ]
        }
    
    @staticmethod
    async def log_ai_interaction(
        user_id: str,
        interaction_type: str,
        prompt: str,
        response: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """Log an AI interaction for analytics and personalization"""
        doc = {
            "user_id": user_id,
            "type": interaction_type,
            "prompt": prompt,
            "response": response[:1000],  # Truncate for storage
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {}
        }
        result = await ai_interactions_collection.insert_one(doc)
        return str(result.inserted_id)
    
    @staticmethod
    async def update_learning_progress(
        user_id: str,
        module_id: str,
        progress: float,
        time_spent: int
    ) -> None:
        """Update user's learning progress for a module"""
        await reading_progress_collection.update_one(
            {"user_id": user_id, "module_id": module_id},
            {
                "$set": {
                    "progress": progress,
                    "last_accessed": datetime.utcnow(),
                    "completed": progress >= 100
                },
                "$inc": {"time_spent": time_spent}
            },
            upsert=True
        )
        
        # Update study streak if completed
        if progress >= 100:
            await user_profiles_collection.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"modules_completed": 1, "xp": 50},
                    "$set": {"last_study_date": datetime.utcnow()}
                },
                upsert=True
            )
    
    @staticmethod
    async def get_personalized_recommendations(user_id: str) -> List[Dict]:
        """Get AI-powered content recommendations based on user context"""
        # Get user context for future personalization enhancements
        _ = await SynergyLayer.get_user_context(user_id)
        
        # Find modules user hasn't completed
        completed_modules = await reading_progress_collection.find(
            {"user_id": user_id, "completed": True}
        ).to_list(1000)
        completed_ids = {m.get("module_id") for m in completed_modules}
        
        # Get next recommended modules
        recommendations = await curriculum_collection.find(
            {"module_id": {"$nin": list(completed_ids)}}
        ).sort("difficulty", 1).limit(5).to_list(5)
        
        return recommendations
    
    @staticmethod
    async def update_emotional_state(
        user_id: str,
        emotion: str,
        intensity: float,
        source: str = "detection"
    ) -> None:
        """Update user's emotional state for adaptive learning"""
        await jeeves_eq_profiles_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "current_emotion": emotion,
                    "emotion_intensity": intensity,
                    "last_updated": datetime.utcnow(),
                    "detection_source": source
                },
                "$push": {
                    "emotion_history": {
                        "$each": [{"emotion": emotion, "intensity": intensity, "timestamp": datetime.utcnow()}],
                        "$slice": -50  # Keep last 50 entries
                    }
                }
            },
            upsert=True
        )

# Global synergy instance
synergy = SynergyLayer()

# ============================================================================
# INDEX CREATION (Run on startup)
# ============================================================================

async def create_indexes():
    """Create database indexes for optimal performance"""
    try:
        # User-related indexes
        await user_profiles_collection.create_index("user_id", unique=True)
        await reading_progress_collection.create_index([("user_id", 1), ("module_id", 1)])
        await ai_interactions_collection.create_index([("user_id", 1), ("timestamp", -1)])
        
        # Curriculum indexes
        await curriculum_collection.create_index("module_id", unique=True)
        await curriculum_collection.create_index([("track", 1), ("difficulty", 1)])
        
        # Quiz indexes
        await quiz_collection.create_index([("topic", 1), ("difficulty", 1)])
        
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
