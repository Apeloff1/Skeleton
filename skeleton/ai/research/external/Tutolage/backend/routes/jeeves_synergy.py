"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         JEEVES SYNERGY ENGINE v14.5 - UNIFIED IMMERSIVE TUTORING             ║
║                                                                              ║
║  "Good day! Allow me to orchestrate your complete learning journey."         ║
║                                                                              ║
║  FULL SYNERGY INTEGRATION:                                                   ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ 🧠 JEEVES + HYPERION (20x Knowledge Base)                               │ ║
║  │    • 2000+ concepts across 6 domains                                    │ ║
║  │    • Self-learning algorithms                                           │ ║
║  │    • Development matrices (SAM, CLO, PTA, LSA, KRP)                     │ ║
║  │                                                                         │ ║
║  │ 🎮 JEEVES + IMMERSIVE TUTOR                                             │ ║
║  │    • Gamification (XP, Levels, Achievements)                           │ ║
║  │    • Zone of Proximal Development tracking                             │ ║
║  │    • Scaffolding system                                                 │ ║
║  │    • Socratic dialogue                                                  │ ║
║  │                                                                         │ ║
║  │ 💬 JEEVES + VOICE/PERSONALITY                                          │ ║
║  │    • Young English Butler persona                                       │ ║
║  │    • Contextual directions                                              │ ║
║  │    • Emotional adaptation                                               │ ║
║  │                                                                         │ ║
║  │ 📈 JEEVES + SYNERGY                                                    │ ║
║  │    • Session tracking                                                   │ ║
║  │    • Cross-feature analytics                                            │ ║
║  │    • Personalized recommendations                                       │ ║
║  │                                                                         │ ║
║  │ 📚 JEEVES + LEARNING ENGINE                                            │ ║
║  │    • Multi-layer redundant learning                                     │ ║
║  │    • 1320+ hours across 10 domains                                      │ ║
║  │    • 6 learning pathways                                                │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
║                                                                              ║
║  MANAGED LEARNING CURVE:                                                     ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ Stage 1: ONBOARDING (0-5 hrs)                                          │ ║
║  │   • Gentle introduction, heavy scaffolding                              │ ║
║  │   • Build confidence with quick wins                                    │ ║
║  │                                                                         │ ║
║  │ Stage 2: FOUNDATION (5-50 hrs)                                         │ ║
║  │   • Core concepts, moderate scaffolding                                │ ║
║  │   • Pattern recognition development                                     │ ║
║  │                                                                         │ ║
║  │ Stage 3: GROWTH (50-200 hrs)                                           │ ║
║  │   • Advanced topics, light scaffolding                                 │ ║
║  │   • Challenge-based learning                                            │ ║
║  │                                                                         │ ║
║  │ Stage 4: MASTERY (200+ hrs)                                            │ ║
║  │   • Expert level, minimal scaffolding                                  │ ║
║  │   • Teaching others, real-world projects                               │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timedelta
from enum import Enum
import uuid
import random
import math

router = APIRouter(prefix="/api/jeeves-synergy", tags=["Jeeves Synergy Engine v14.5"])

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class LearningStage(str, Enum):
    ONBOARDING = "onboarding"
    FOUNDATION = "foundation"
    GROWTH = "growth"
    MASTERY = "mastery"

class InteractionMode(str, Enum):
    TEACH = "teach"
    PRACTICE = "practice"
    CHALLENGE = "challenge"
    REVIEW = "review"
    EXPLORE = "explore"
    REFLECT = "reflect"

class ResponseStyle(str, Enum):
    ENCOURAGING = "encouraging"
    CHALLENGING = "challenging"
    SUPPORTIVE = "supportive"
    CELEBRATORY = "celebratory"
    ANALYTICAL = "analytical"
    PLAYFUL = "playful"

# Learning curve parameters
LEARNING_CURVE_STAGES = {
    LearningStage.ONBOARDING: {
        "hours_range": (0, 5),
        "scaffolding_level": "heavy",
        "difficulty_cap": 0.3,
        "xp_multiplier": 1.5,
        "focus": "confidence_building",
        "jeeves_style": "nurturing",
        "goals": [
            "Complete first successful program",
            "Understand basic syntax",
            "Experience the joy of coding",
            "Build initial momentum"
        ]
    },
    LearningStage.FOUNDATION: {
        "hours_range": (5, 50),
        "scaffolding_level": "moderate",
        "difficulty_cap": 0.5,
        "xp_multiplier": 1.2,
        "focus": "core_concepts",
        "jeeves_style": "instructive",
        "goals": [
            "Master fundamental concepts",
            "Develop problem-solving patterns",
            "Build coding vocabulary",
            "Establish learning habits"
        ]
    },
    LearningStage.GROWTH: {
        "hours_range": (50, 200),
        "scaffolding_level": "light",
        "difficulty_cap": 0.8,
        "xp_multiplier": 1.0,
        "focus": "advanced_application",
        "jeeves_style": "mentoring",
        "goals": [
            "Apply concepts to real problems",
            "Handle complexity",
            "Develop intuition",
            "Build substantial projects"
        ]
    },
    LearningStage.MASTERY: {
        "hours_range": (200, 999999),
        "scaffolding_level": "minimal",
        "difficulty_cap": 1.0,
        "xp_multiplier": 0.8,
        "focus": "expertise",
        "jeeves_style": "collaborative",
        "goals": [
            "Achieve expert proficiency",
            "Teach and mentor others",
            "Innovate and create",
            "Contribute to community"
        ]
    }
}

# Jeeves personality expressions for each stage
JEEVES_STAGE_EXPRESSIONS = {
    LearningStage.ONBOARDING: [
        "Welcome aboard! I'm absolutely delighted to begin this journey with you.",
        "Splendid start! Every master was once a beginner, you know.",
        "No need to rush - we'll take this one step at a time, together.",
        "Excellent first effort! I knew you had potential.",
        "Don't worry about perfection - learning is a process, not a destination."
    ],
    LearningStage.FOUNDATION: [
        "You're building a solid foundation - this will serve you well!",
        "Ah, now you're starting to see the patterns. Capital!",
        "Each concept you master opens doors to new possibilities.",
        "Your persistence is most admirable. Keep at it!",
        "I can see the gears turning - you're developing real intuition."
    ],
    LearningStage.GROWTH: [
        "Now we're getting to the good stuff! Ready for a challenge?",
        "You're no longer a beginner - time to push those boundaries.",
        "Impressive growth! Let's see what you're really capable of.",
        "This is where coding becomes truly exciting - real problems, real solutions.",
        "You've earned the right to tackle more complex challenges."
    ],
    LearningStage.MASTERY: [
        "You've achieved remarkable proficiency. I'm genuinely impressed.",
        "At this level, you're not just learning - you're creating.",
        "Perhaps you'd like to mentor others? Your knowledge is valuable.",
        "The student becomes the master - a proud moment indeed!",
        "You've earned expert status. Now, let's push the boundaries of what's possible."
    ]
}

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class SynergySessionRequest(BaseModel):
    user_id: str
    total_learning_hours: float = 0
    current_topic: str = "programming"
    emotional_state: str = "neutral"
    recent_performance: List[float] = []
    preferred_mode: Optional[InteractionMode] = None

class InteractionRequest(BaseModel):
    user_id: str
    interaction_type: str
    content: str
    topic: str = "programming"
    difficulty: float = 0.5
    emotional_state: str = "neutral"

class LearningCurveRequest(BaseModel):
    user_id: str
    total_hours: float
    domains_explored: List[str] = []
    achievements_earned: int = 0
    streak_days: int = 0
    mastery_scores: Dict[str, float] = {}

class AdaptiveContentRequest(BaseModel):
    user_id: str
    current_stage: str
    topic: str
    time_available_minutes: int = 30
    energy_level: str = "normal"  # low, normal, high

# ============================================================================
# SYNERGY ENGINE
# ============================================================================

class JeevesSynergyEngine:
    """
    The unified orchestrator that connects all learning systems through Jeeves.
    """
    
    @staticmethod
    def determine_learning_stage(total_hours: float) -> LearningStage:
        """Determine the user's current learning stage based on hours invested."""
        if total_hours < 5:
            return LearningStage.ONBOARDING
        elif total_hours < 50:
            return LearningStage.FOUNDATION
        elif total_hours < 200:
            return LearningStage.GROWTH
        else:
            return LearningStage.MASTERY
    
    @staticmethod
    def calculate_optimal_difficulty(
        stage: LearningStage,
        recent_performance: List[float],
        emotional_state: str
    ) -> Dict[str, Any]:
        """Calculate optimal difficulty based on stage, performance, and emotional state."""
        stage_config = LEARNING_CURVE_STAGES[stage]
        difficulty_cap = stage_config["difficulty_cap"]
        
        # Base difficulty from recent performance
        if recent_performance:
            avg_performance = sum(recent_performance[-10:]) / min(len(recent_performance), 10)
            
            # Zone of Proximal Development: 70-85% success rate is optimal
            if avg_performance > 0.85:
                base_difficulty = min(avg_performance + 0.1, difficulty_cap)
            elif avg_performance < 0.70:
                base_difficulty = max(avg_performance - 0.1, 0.1)
            else:
                base_difficulty = avg_performance
        else:
            # New learner - start at stage-appropriate difficulty
            base_difficulty = difficulty_cap * 0.3
        
        # Emotional state adjustment
        emotional_adjustments = {
            "frustrated": -0.15,
            "confused": -0.10,
            "tired": -0.15,
            "overwhelmed": -0.20,
            "anxious": -0.10,
            "confident": 0.05,
            "excited": 0.10,
            "focused": 0.05,
            "neutral": 0
        }
        
        adjustment = emotional_adjustments.get(emotional_state, 0)
        final_difficulty = max(0.1, min(difficulty_cap, base_difficulty + adjustment))
        
        return {
            "optimal_difficulty": round(final_difficulty, 2),
            "difficulty_cap": difficulty_cap,
            "stage": stage.value,
            "adjustment_applied": round(adjustment, 2),
            "reason": f"Based on {stage.value} stage limits and {emotional_state} emotional state",
            "scaffolding_recommendation": stage_config["scaffolding_level"]
        }
    
    @staticmethod
    def generate_stage_guidance(stage: LearningStage) -> Dict[str, Any]:
        """Generate Jeeves guidance specific to the learning stage."""
        config = LEARNING_CURVE_STAGES[stage]
        expressions = JEEVES_STAGE_EXPRESSIONS[stage]
        
        return {
            "stage": stage.value,
            "jeeves_greeting": random.choice(expressions),
            "focus_area": config["focus"],
            "scaffolding_level": config["scaffolding_level"],
            "xp_multiplier": config["xp_multiplier"],
            "goals": config["goals"],
            "jeeves_style": config["jeeves_style"],
            "tips": JeevesSynergyEngine._get_stage_tips(stage),
            "recommended_session_length": JeevesSynergyEngine._get_recommended_session_length(stage)
        }
    
    @staticmethod
    def _get_stage_tips(stage: LearningStage) -> List[str]:
        """Get tips specific to the learning stage."""
        tips = {
            LearningStage.ONBOARDING: [
                "Focus on understanding, not memorizing",
                "Make mistakes - they're learning opportunities!",
                "Celebrate small wins",
                "Don't compare yourself to others"
            ],
            LearningStage.FOUNDATION: [
                "Practice regularly - consistency beats intensity",
                "Start building your own small projects",
                "Ask 'why' more often than 'how'",
                "Connect new concepts to ones you know"
            ],
            LearningStage.GROWTH: [
                "Challenge yourself with harder problems",
                "Read other people's code",
                "Contribute to open source projects",
                "Teach what you learn to reinforce it"
            ],
            LearningStage.MASTERY: [
                "Share your knowledge - teaching deepens understanding",
                "Tackle unsolved problems",
                "Develop your unique coding style",
                "Mentor newcomers to the craft"
            ]
        }
        return tips[stage]
    
    @staticmethod
    def _get_recommended_session_length(stage: LearningStage) -> Dict[str, int]:
        """Get recommended session lengths based on stage."""
        recommendations = {
            LearningStage.ONBOARDING: {"min": 15, "optimal": 20, "max": 30},
            LearningStage.FOUNDATION: {"min": 20, "optimal": 30, "max": 45},
            LearningStage.GROWTH: {"min": 30, "optimal": 45, "max": 90},
            LearningStage.MASTERY: {"min": 30, "optimal": 60, "max": 120}
        }
        return recommendations[stage]
    
    @staticmethod
    def create_adaptive_session(
        stage: LearningStage,
        topic: str,
        time_available: int,
        energy_level: str
    ) -> Dict[str, Any]:
        """Create an adaptive learning session based on all factors."""
        config = LEARNING_CURVE_STAGES[stage]
        
        # Adjust for energy level
        energy_adjustments = {
            "low": {"difficulty_mod": -0.15, "pace": "gentle", "breaks": True},
            "normal": {"difficulty_mod": 0, "pace": "steady", "breaks": False},
            "high": {"difficulty_mod": 0.1, "pace": "intensive", "breaks": False}
        }
        energy = energy_adjustments.get(energy_level, energy_adjustments["normal"])
        
        # Calculate content blocks based on time
        if time_available < 20:
            blocks = 1
            structure = "quick_review"
        elif time_available < 45:
            blocks = 2
            structure = "learn_and_practice"
        elif time_available < 90:
            blocks = 3
            structure = "full_session"
        else:
            blocks = 4
            structure = "deep_dive"
        
        session = {
            "session_id": str(uuid.uuid4()),
            "stage": stage.value,
            "topic": topic,
            "duration_minutes": time_available,
            "structure": structure,
            "pace": energy["pace"],
            "include_breaks": energy["breaks"],
            "blocks": []
        }
        
        # Generate session blocks
        block_types = {
            "quick_review": ["review"],
            "learn_and_practice": ["learn", "practice"],
            "full_session": ["learn", "practice", "challenge"],
            "deep_dive": ["learn", "practice", "challenge", "reflect"]
        }
        
        for i, block_type in enumerate(block_types[structure]):
            block_duration = time_available // len(block_types[structure])
            session["blocks"].append({
                "order": i + 1,
                "type": block_type,
                "duration_minutes": block_duration,
                "difficulty": round(config["difficulty_cap"] * (0.6 + 0.1 * i) + energy["difficulty_mod"], 2),
                "scaffolding": config["scaffolding_level"]
            })
        
        # Add Jeeves commentary
        session["jeeves_intro"] = random.choice(JEEVES_STAGE_EXPRESSIONS[stage])
        session["jeeves_plan"] = f"For today's {structure.replace('_', ' ')} session on {topic}, we'll be working through {blocks} focused blocks. {energy['pace'].title()} pace, as befits your current energy."
        
        return session
    
    @staticmethod
    def analyze_synergy_metrics(
        user_id: str,
        total_hours: float,
        domains_explored: List[str],
        achievements_earned: int,
        streak_days: int,
        mastery_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """Comprehensive analysis of user's learning synergy."""
        stage = JeevesSynergyEngine.determine_learning_stage(total_hours)
        config = LEARNING_CURVE_STAGES[stage]
        
        # Calculate overall mastery
        if mastery_scores:
            avg_mastery = sum(mastery_scores.values()) / len(mastery_scores)
            highest_mastery = max(mastery_scores.items(), key=lambda x: x[1])
            lowest_mastery = min(mastery_scores.items(), key=lambda x: x[1])
        else:
            avg_mastery = 0
            highest_mastery = ("none", 0)
            lowest_mastery = ("none", 0)
        
        # Calculate engagement score
        engagement_factors = [
            min(streak_days / 30, 1) * 0.3,  # Consistency (30%)
            min(len(domains_explored) / 10, 1) * 0.25,  # Breadth (25%)
            min(achievements_earned / 20, 1) * 0.25,  # Achievements (25%)
            min(avg_mastery, 1) * 0.2  # Mastery (20%)
        ]
        engagement_score = sum(engagement_factors)
        
        # Calculate learning velocity
        expected_hours_for_stage = {
            LearningStage.ONBOARDING: 5,
            LearningStage.FOUNDATION: 50,
            LearningStage.GROWTH: 200,
            LearningStage.MASTERY: 500
        }
        expected = expected_hours_for_stage[stage]
        progress_in_stage = min(total_hours / expected, 1)
        
        # Generate insights
        insights = []
        if streak_days >= 7:
            insights.append({"type": "positive", "message": f"Impressive {streak_days}-day streak! Consistency is key."})
        if streak_days == 0:
            insights.append({"type": "neutral", "message": "Start a learning streak to build momentum!"})
        if avg_mastery > 0.7:
            insights.append({"type": "positive", "message": "Strong mastery across topics. Consider advanced challenges."})
        if len(domains_explored) == 1:
            insights.append({"type": "suggestion", "message": "Explore other domains to become a well-rounded developer."})
        if lowest_mastery[1] < 0.4:
            insights.append({"type": "focus", "message": f"'{lowest_mastery[0]}' needs attention. Would you like targeted practice?"})
        
        return {
            "user_id": user_id,
            "current_stage": stage.value,
            "stage_progress": round(progress_in_stage * 100, 1),
            "hours_to_next_stage": max(0, expected - total_hours),
            "total_learning_hours": total_hours,
            "metrics": {
                "engagement_score": round(engagement_score, 2),
                "average_mastery": round(avg_mastery, 2),
                "domains_explored": len(domains_explored),
                "streak_days": streak_days,
                "achievements_earned": achievements_earned
            },
            "strengths": {
                "strongest_domain": highest_mastery[0],
                "mastery_level": round(highest_mastery[1], 2)
            },
            "growth_areas": {
                "domain_needing_focus": lowest_mastery[0],
                "current_level": round(lowest_mastery[1], 2)
            },
            "insights": insights,
            "jeeves_says": JeevesSynergyEngine._generate_synergy_message(stage, engagement_score, streak_days)
        }
    
    @staticmethod
    def _generate_synergy_message(stage: LearningStage, engagement: float, streak: int) -> str:
        """Generate Jeeves' personalized synergy message."""
        if engagement > 0.8:
            return f"Outstanding progress! Your dedication in the {stage.value} phase is exemplary. You're truly making the most of this learning journey."
        elif engagement > 0.5:
            return f"Solid effort in your {stage.value} phase. A few more consistent sessions, and you'll see remarkable improvement."
        elif streak > 0:
            return f"You've got a {streak}-day streak going - that's the spirit! Keep building momentum in your {stage.value} phase."
        else:
            return f"Welcome back! Every master was once a beginner. Let's pick up where we left off in the {stage.value} phase."

# ============================================================================
# IMMERSIVE RESPONSE GENERATOR
# ============================================================================

class ImmersiveResponder:
    """
    Generates immersive, contextual responses from Jeeves
    that adapt to the user's journey.
    """
    
    @staticmethod
    def generate_response(
        content: str,
        stage: LearningStage,
        response_style: ResponseStyle,
        include_guidance: bool = True
    ) -> Dict[str, Any]:
        """Generate a fully immersive Jeeves response."""
        
        # Style-specific prefixes
        style_prefixes = {
            ResponseStyle.ENCOURAGING: [
                "Splendid! ", "Marvelous work! ", "That's the spirit! ",
                "Excellent progress! ", "You're doing brilliantly! "
            ],
            ResponseStyle.CHALLENGING: [
                "Ready for something more demanding? ", "Let's push those limits. ",
                "Here's a worthy challenge: ", "Think you can handle this? "
            ],
            ResponseStyle.SUPPORTIVE: [
                "No worries at all. ", "Let's work through this together. ",
                "I'm here to help. ", "We'll figure this out. "
            ],
            ResponseStyle.CELEBRATORY: [
                "Bravo! 🎉 ", "Outstanding achievement! ", "Cause for celebration! ",
                "You've outdone yourself! "
            ],
            ResponseStyle.ANALYTICAL: [
                "Let's examine this closely. ", "Analyzing the situation: ",
                "Here's what the data shows: ", "Upon careful consideration: "
            ],
            ResponseStyle.PLAYFUL: [
                "Ah, here's an interesting one! ", "Ready for some fun? ",
                "Let's make this enjoyable: ", "Time for a bit of coding adventure! "
            ]
        }
        
        prefix = random.choice(style_prefixes.get(response_style, style_prefixes[ResponseStyle.ENCOURAGING]))
        
        response = {
            "jeeves_response": f"{prefix}{content}",
            "style": response_style.value,
            "stage": stage.value,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if include_guidance:
            response["stage_context"] = LEARNING_CURVE_STAGES[stage]["focus"]
            response["next_suggestion"] = JeevesSynergyEngine._get_stage_tips(stage)[0]
        
        return response
    
    @staticmethod
    def generate_transition_message(from_stage: LearningStage, to_stage: LearningStage) -> Dict[str, Any]:
        """Generate a message for when the user transitions between stages."""
        
        transitions = {
            (LearningStage.ONBOARDING, LearningStage.FOUNDATION): {
                "celebration": "🎉 Congratulations! You've completed your onboarding!",
                "message": "You've taken your first steps and built a foundation. Now the real adventure begins - we'll deepen your understanding and expand your capabilities.",
                "unlocks": ["Intermediate challenges", "Project mode", "Code review features"]
            },
            (LearningStage.FOUNDATION, LearningStage.GROWTH): {
                "celebration": "🚀 You've leveled up to Growth Phase!",
                "message": "Your fundamentals are solid. It's time to apply what you've learned to real challenges and build substantial projects.",
                "unlocks": ["Advanced challenges", "Real-world projects", "Algorithm deep-dives"]
            },
            (LearningStage.GROWTH, LearningStage.MASTERY): {
                "celebration": "👑 Welcome to Mastery! You've achieved expert status!",
                "message": "You've proven yourself a capable developer. Now you join the ranks of those who create, innovate, and teach others.",
                "unlocks": ["Expert challenges", "Mentorship mode", "Community contributions"]
            }
        }
        
        transition_key = (from_stage, to_stage)
        if transition_key in transitions:
            transition = transitions[transition_key]
            return {
                "transition_type": f"{from_stage.value}_to_{to_stage.value}",
                "celebration": transition["celebration"],
                "jeeves_message": transition["message"],
                "newly_unlocked": transition["unlocks"],
                "previous_stage": from_stage.value,
                "new_stage": to_stage.value,
                "xp_bonus": 1000 * (list(LearningStage).index(to_stage) + 1)
            }
        
        return {"transition_type": "none", "message": "Continue your current journey"}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_synergy_overview():
    """Get overview of the Jeeves Synergy Engine"""
    return {
        "system": "Jeeves Synergy Engine v14.5",
        "description": "Unified immersive tutoring with full system integration",
        "integrations": [
            {"system": "Jeeves Hyperion", "features": "2000+ concepts, self-learning algorithms"},
            {"system": "Immersive Tutor", "features": "Gamification, ZPD tracking, scaffolding"},
            {"system": "Jeeves Voice", "features": "Young English butler personality"},
            {"system": "Synergy API", "features": "Session tracking, cross-feature analytics"},
            {"system": "Learning Engine", "features": "Multi-layer redundant learning"}
        ],
        "learning_stages": [
            {"stage": "onboarding", "hours": "0-5", "focus": "confidence_building"},
            {"stage": "foundation", "hours": "5-50", "focus": "core_concepts"},
            {"stage": "growth", "hours": "50-200", "focus": "advanced_application"},
            {"stage": "mastery", "hours": "200+", "focus": "expertise"}
        ],
        "features": [
            "Managed learning curve",
            "Emotional state adaptation",
            "Contextual scaffolding",
            "Stage-appropriate challenges",
            "Personalized Jeeves guidance"
        ],
        "jeeves_says": "Good day! I'm Jeeves, your dedicated learning companion. Together, we shall navigate the wonderful world of coding - at precisely the right pace for you."
    }

@router.post("/session/create")
async def create_synergy_session(request: SynergySessionRequest):
    """Create a new synergy-aware learning session"""
    stage = JeevesSynergyEngine.determine_learning_stage(request.total_learning_hours)
    
    # Calculate optimal difficulty
    difficulty_config = JeevesSynergyEngine.calculate_optimal_difficulty(
        stage, request.recent_performance, request.emotional_state
    )
    
    # Get stage guidance
    guidance = JeevesSynergyEngine.generate_stage_guidance(stage)
    
    return {
        "session_id": str(uuid.uuid4()),
        "user_id": request.user_id,
        "stage": stage.value,
        "difficulty": difficulty_config,
        "guidance": guidance,
        "recommended_mode": request.preferred_mode.value if request.preferred_mode else "learn",
        "topic": request.current_topic,
        "emotional_adaptation": {
            "detected_state": request.emotional_state,
            "response_style": "supportive" if request.emotional_state in ["frustrated", "confused", "tired"] else "encouraging"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/adaptive-content")
async def get_adaptive_content(request: AdaptiveContentRequest):
    """Get adaptive content tailored to user's current state"""
    try:
        stage = LearningStage(request.current_stage)
    except ValueError:
        stage = LearningStage.FOUNDATION
    
    session = JeevesSynergyEngine.create_adaptive_session(
        stage,
        request.topic,
        request.time_available_minutes,
        request.energy_level
    )
    
    return session

@router.post("/analyze")
async def analyze_learning_synergy(request: LearningCurveRequest):
    """Comprehensive analysis of learning progress and synergy"""
    return JeevesSynergyEngine.analyze_synergy_metrics(
        request.user_id,
        request.total_hours,
        request.domains_explored,
        request.achievements_earned,
        request.streak_days,
        request.mastery_scores
    )

@router.get("/stage/{hours}")
async def get_stage_for_hours(hours: float):
    """Get learning stage and guidance for given hours"""
    stage = JeevesSynergyEngine.determine_learning_stage(hours)
    return {
        "hours": hours,
        "stage": stage.value,
        "guidance": JeevesSynergyEngine.generate_stage_guidance(stage)
    }

@router.post("/respond")
async def get_jeeves_response(
    content: str,
    stage: str = "foundation",
    style: str = "encouraging"
):
    """Generate an immersive Jeeves response"""
    try:
        stage_enum = LearningStage(stage)
    except ValueError:
        stage_enum = LearningStage.FOUNDATION
    
    try:
        style_enum = ResponseStyle(style)
    except ValueError:
        style_enum = ResponseStyle.ENCOURAGING
    
    return ImmersiveResponder.generate_response(content, stage_enum, style_enum)

@router.get("/transition/{from_stage}/{to_stage}")
async def get_transition_message(from_stage: str, to_stage: str):
    """Get celebration message for stage transition"""
    try:
        from_enum = LearningStage(from_stage)
        to_enum = LearningStage(to_stage)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid stage names")
    
    return ImmersiveResponder.generate_transition_message(from_enum, to_enum)

@router.get("/stages/all")
async def get_all_stages():
    """Get detailed information about all learning stages"""
    return {
        "stages": [
            {
                "id": stage.value,
                "name": stage.value.title(),
                "config": LEARNING_CURVE_STAGES[stage],
                "expressions_sample": JEEVES_STAGE_EXPRESSIONS[stage][:2]
            }
            for stage in LearningStage
        ],
        "total_stages": len(LearningStage),
        "progression": "onboarding → foundation → growth → mastery"
    }

@router.post("/optimal-difficulty")
async def get_optimal_difficulty(
    stage: str,
    recent_performance: List[float] = [],
    emotional_state: str = "neutral"
):
    """Calculate optimal difficulty for current conditions"""
    try:
        stage_enum = LearningStage(stage)
    except ValueError:
        stage_enum = LearningStage.FOUNDATION
    
    return JeevesSynergyEngine.calculate_optimal_difficulty(
        stage_enum, recent_performance, emotional_state
    )
