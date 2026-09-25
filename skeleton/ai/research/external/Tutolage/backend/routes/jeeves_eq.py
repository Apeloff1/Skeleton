"""
╔══════════════════════════════════════════════════════════════════════════════╗
║       JEEVES EMOTIONAL INTELLIGENCE & PSYCHOLOGICAL LEARNING v11.7           ║
║                                                                              ║
║  Advanced AI Tutoring with Emotional Awareness & Learning Psychology         ║
║                                                                              ║
║  Features:                                                                   ║
║  • Emotional state detection from user interactions                          ║
║  • Adaptive encouragement based on frustration/confidence levels             ║
║  • Growth mindset reinforcement                                              ║
║  • Cognitive load management                                                 ║
║  • Spaced repetition optimization                                            ║
║  • Learning anxiety reduction techniques                                     ║
║  • Therapeutic techniques (Pomodoro, breaks, stress detection)               ║
║  • Motivation style profiling                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import os
import random

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(prefix="/api/jeeves-eq", tags=["Jeeves Emotional Intelligence"])

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
mongo_client = AsyncIOMotorClient(MONGO_URL)
eq_db = mongo_client.codedock_jeeves_eq

# ============================================================================
# EMOTIONAL STATE MODELS
# ============================================================================

class EmotionalState(BaseModel):
    user_id: str
    primary_emotion: Literal[
        "confident", "curious", "engaged", "neutral",
        "confused", "frustrated", "anxious", "overwhelmed", "bored", "discouraged"
    ]
    intensity: float = Field(ge=0, le=1, default=0.5)
    secondary_emotions: List[str] = []
    triggers: List[str] = []
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class LearningPsychologyProfile(BaseModel):
    user_id: str
    motivation_type: Literal["intrinsic", "extrinsic", "mixed"] = "mixed"
    motivation_drivers: List[str] = []  # achievement, mastery, social, fear_of_failure
    cognitive_style: Literal["analytical", "intuitive", "practical", "creative"] = "analytical"
    stress_tolerance: Literal["low", "medium", "high"] = "medium"
    preferred_challenge_level: float = Field(ge=0, le=1, default=0.6)  # 0=easy, 1=very hard
    learning_anxiety_level: float = Field(ge=0, le=1, default=0.3)
    perfectionism_tendency: float = Field(ge=0, le=1, default=0.5)
    growth_mindset_score: float = Field(ge=0, le=1, default=0.5)
    resilience_score: float = Field(ge=0, le=1, default=0.5)
    self_efficacy: float = Field(ge=0, le=1, default=0.5)


# ============================================================================
# EMOTIONAL DETECTION PATTERNS
# ============================================================================

EMOTIONAL_INDICATORS = {
    "frustrated": {
        "patterns": [
            "repeated_failures",
            "short_session_abandonment",
            "rapid_hint_requests",
            "same_error_multiple_times",
            "decreasing_time_between_attempts"
        ],
        "text_signals": [
            "don't understand", "doesn't work", "what's wrong",
            "confused", "stuck", "help", "??", "!!!"
        ],
        "response_style": "patient_supportive"
    },
    "confident": {
        "patterns": [
            "consecutive_successes",
            "declining_hint_usage",
            "faster_completion_times",
            "advancing_difficulty"
        ],
        "text_signals": [
            "got it", "easy", "makes sense", "let's try harder"
        ],
        "response_style": "challenging_encouraging"
    },
    "anxious": {
        "patterns": [
            "long_pauses_before_action",
            "excessive_hint_checking",
            "avoiding_difficult_topics",
            "incomplete_attempts"
        ],
        "text_signals": [
            "not sure", "might be wrong", "probably", "scared", "worried"
        ],
        "response_style": "reassuring_gentle"
    },
    "overwhelmed": {
        "patterns": [
            "rapid_topic_switching",
            "very_short_engagement",
            "avoiding_new_content",
            "regression_to_easy_material"
        ],
        "text_signals": [
            "too much", "can't", "overwhelmed", "complicated", "lost"
        ],
        "response_style": "simplifying_breaking_down"
    },
    "bored": {
        "patterns": [
            "very_fast_completions",
            "skipping_explanations",
            "avoiding_practice",
            "declining_engagement_time"
        ],
        "text_signals": [
            "boring", "already know", "too easy", "next"
        ],
        "response_style": "challenging_interesting"
    },
    "discouraged": {
        "patterns": [
            "decreasing_session_frequency",
            "shorter_sessions_over_time",
            "avoiding_previously_failed_topics",
            "negative_self_talk_in_inputs"
        ],
        "text_signals": [
            "can't do this", "too hard", "not smart", "give up", "never"
        ],
        "response_style": "empathetic_growth_focused"
    }
}

# ============================================================================
# THERAPEUTIC RESPONSE TEMPLATES
# ============================================================================

THERAPEUTIC_RESPONSES = {
    "frustrated": {
        "acknowledgment": [
            "I can see this is challenging. That's actually a sign you're pushing your boundaries - which is exactly how growth happens.",
            "Feeling stuck is frustrating, but it's part of the learning journey. Every expert programmer has been exactly where you are.",
            "I notice you've been working hard on this. Let's take a different approach together."
        ],
        "reframe": [
            "This error isn't a failure - it's information. Let's decode what it's telling us.",
            "Debugging is actually one of the most valuable skills. Each bug you solve makes you stronger.",
            "The struggle you're feeling is literally your brain forming new neural connections."
        ],
        "action": [
            "Let's break this into smaller pieces. What's the one thing that's most confusing right now?",
            "Sometimes stepping back helps. Want to try a simpler version first?",
            "I'll walk you through this step by step. No judgment, just learning."
        ]
    },
    "anxious": {
        "acknowledgment": [
            "It's completely okay to feel uncertain. Programming is complex, and every developer questions themselves.",
            "Your hesitation shows you care about getting it right. That's a strength.",
            "Remember: there's no such thing as a perfect coder. We all make mistakes daily."
        ],
        "reframe": [
            "Making mistakes in practice is free - it's how we learn without real consequences.",
            "Even senior developers Google basic things. Uncertainty is normal.",
            "Your code doesn't define your worth. It's just a work in progress, like all of us."
        ],
        "action": [
            "Let's start with something you're comfortable with and build from there.",
            "There's no timer here. Take all the time you need.",
            "Would you like me to explain my reasoning so you can see how I approach problems?"
        ]
    },
    "overwhelmed": {
        "acknowledgment": [
            "That's a lot to take in. It's okay to feel overwhelmed when learning something new.",
            "Learning to code is like learning a new language - it takes time to feel fluent.",
            "Your brain is processing a lot right now. That mental fatigue is real."
        ],
        "reframe": [
            "You don't need to learn everything at once. Let's focus on just one concept.",
            "Even a small step forward is progress. Let's find that step together.",
            "Mastery comes from many small learnings, not one giant leap."
        ],
        "action": [
            "Let's pause and identify the ONE thing that would help most right now.",
            "Would you like to take a short break? Sometimes that's the most productive thing.",
            "Let me simplify this into just the essential parts."
        ]
    },
    "discouraged": {
        "acknowledgment": [
            "It sounds like you're being hard on yourself. I want you to know that's incredibly common.",
            "Learning something difficult and feeling like you're not progressing is genuinely hard. Your feelings are valid.",
            "I hear the frustration. But can I share something? The fact that you're still here shows incredible persistence."
        ],
        "reframe": [
            "Every expert was once a beginner who didn't give up. You're on that same path.",
            "Intelligence isn't fixed - it grows with effort. This struggle is literally making you smarter.",
            "The developers you admire? They've all felt exactly like you do now. Multiple times."
        ],
        "action": [
            "Let's revisit something you've already mastered to remind yourself how far you've come.",
            "What if we set a tiny, achievable goal for today? Just one small win.",
            "I believe in you. Let me show you why by walking through how much you've actually learned."
        ]
    },
    "confident": {
        "acknowledgment": [
            "You're doing great! Your confidence is well-earned.",
            "I can tell you've been putting in the work. It shows!",
            "Excellent progress! You're building real expertise."
        ],
        "challenge": [
            "Ready for something more challenging? I think you can handle it.",
            "Let's push your skills to the next level. You're ready.",
            "How about we explore some advanced techniques?"
        ]
    },
    "bored": {
        "acknowledgment": [
            "This might be too easy for you. Let's find something more engaging.",
            "Your quick completions tell me you're ready for bigger challenges.",
            "Looks like you need something more stimulating!"
        ],
        "action": [
            "Let me find a challenge that matches your skill level better.",
            "How about we dive into some advanced topics?",
            "Want to try something that even experienced developers find tricky?"
        ]
    }
}

# ============================================================================
# COGNITIVE LOAD MANAGEMENT
# ============================================================================

COGNITIVE_LOAD_STRATEGIES = {
    "high_load_detected": {
        "indicators": [
            "introducing_many_new_concepts",
            "long_session_without_break",
            "complex_multi_step_problems",
            "high_error_rate"
        ],
        "interventions": [
            {
                "type": "chunking",
                "message": "Let's break this into smaller, digestible pieces.",
                "action": "split_problem"
            },
            {
                "type": "scaffolding",
                "message": "I'll provide some structure to guide you through this.",
                "action": "provide_template"
            },
            {
                "type": "worked_example",
                "message": "Let me show you a similar problem solved step-by-step.",
                "action": "show_example"
            },
            {
                "type": "break_suggestion",
                "message": "Your brain has been working hard. A 5-minute break could help consolidate what you've learned.",
                "action": "suggest_break"
            }
        ]
    },
    "optimal_challenge": {
        "description": "Flow state - challenge matches skill",
        "maintain_strategies": [
            "gradually_increase_difficulty",
            "provide_immediate_feedback",
            "maintain_clear_goals"
        ]
    }
}

# ============================================================================
# GROWTH MINDSET REINFORCEMENT
# ============================================================================

GROWTH_MINDSET_MESSAGES = {
    "after_failure": [
        "Mistakes are proof you're trying. Each error is a learning opportunity.",
        "The most successful programmers failed thousands of times to get where they are.",
        "Your brain is literally rewiring itself right now. This struggle is growth.",
        "Thomas Edison said 'I have not failed. I've just found 10,000 ways that won't work.'",
        "Debugging is a skill. Every bug you encounter makes you better at solving the next one."
    ],
    "after_success": [
        "Your effort and practice paid off! This success came from your hard work.",
        "Notice how your persistence led to this breakthrough?",
        "You grew your skills to solve this. That growth is permanent.",
        "This wasn't luck - this was the result of your learning journey."
    ],
    "effort_praise": [
        "I love seeing your persistence. That's the quality that leads to mastery.",
        "The effort you're putting in is building real, lasting skills.",
        "Your willingness to struggle with hard problems is exactly what separates good from great."
    ],
    "process_praise": [
        "Your problem-solving approach is getting more sophisticated.",
        "Notice how you broke that down? That's expert-level thinking.",
        "The strategy you used there shows real growth in your thinking."
    ]
}

# ============================================================================
# SPACED REPETITION OPTIMIZATION
# ============================================================================

SPACED_REPETITION_CONFIG = {
    "initial_interval_hours": 4,
    "multiplier_on_success": 2.5,
    "multiplier_on_failure": 0.5,
    "max_interval_days": 90,
    "min_interval_hours": 1,
    "emotional_adjustments": {
        "anxious": 0.8,  # Shorter intervals to build confidence
        "confident": 1.2,  # Longer intervals
        "overwhelmed": 0.6,  # Much shorter intervals
        "frustrated": 0.7
    }
}

# ============================================================================
# POMODORO & WELLNESS SYSTEM
# ============================================================================

POMODORO_CONFIG = {
    "work_duration_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "sessions_before_long_break": 4,
    "wellness_reminders": [
        {"type": "posture", "message": "Time for a posture check! Sit up straight and relax your shoulders.", "interval_minutes": 30},
        {"type": "hydration", "message": "Remember to stay hydrated! Take a sip of water.", "interval_minutes": 45},
        {"type": "eyes", "message": "Look away from the screen for 20 seconds. Your eyes will thank you!", "interval_minutes": 20},
        {"type": "stretch", "message": "Quick stretch break! Roll your wrists and stretch your arms.", "interval_minutes": 60}
    ],
    "break_activities": [
        "Take a short walk",
        "Do some light stretching",
        "Practice deep breathing",
        "Look out a window at something distant",
        "Get a healthy snack",
        "Do a quick mindfulness exercise"
    ]
}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_jeeves_eq_info():
    """Get Jeeves Emotional Intelligence system info"""
    return {
        "name": "Jeeves Emotional Intelligence v11.7 SOTA",
        "description": "Advanced AI tutoring with emotional awareness & learning psychology",
        "capabilities": [
            "Real-time emotional state detection",
            "Adaptive response based on emotional state",
            "Growth mindset reinforcement",
            "Cognitive load management",
            "Learning anxiety reduction",
            "Personalized motivation strategies",
            "Spaced repetition optimization",
            "Pomodoro technique integration",
            "Wellness reminders",
            "Therapeutic conversation patterns"
        ],
        "emotional_states_detected": list(EMOTIONAL_INDICATORS.keys()),
        "motivation_types": ["intrinsic", "extrinsic", "mixed"],
        "cognitive_styles": ["analytical", "intuitive", "practical", "creative"],
        "therapeutic_features": [
            "Frustration management",
            "Anxiety reduction",
            "Overwhelm recovery",
            "Discouragement intervention",
            "Confidence building",
            "Boredom remediation"
        ]
    }


@router.post("/detect-emotion")
async def detect_emotional_state(
    user_id: str,
    recent_actions: List[Dict[str, Any]],
    text_input: Optional[str] = None
):
    """Detect user's current emotional state from actions and text"""
    
    emotion_scores = {emotion: 0.0 for emotion in EMOTIONAL_INDICATORS.keys()}
    
    # Analyze recent actions
    action_types = [a.get("action_type", "") for a in recent_actions]
    
    for emotion, indicators in EMOTIONAL_INDICATORS.items():
        # Check action patterns
        for pattern in indicators["patterns"]:
            if pattern == "repeated_failures":
                failures = sum(1 for a in action_types if "failed" in a)
                if failures >= 3:
                    emotion_scores[emotion] += 0.3
            elif pattern == "consecutive_successes":
                successes = sum(1 for a in action_types if "completed" in a)
                if successes >= 3:
                    emotion_scores[emotion] += 0.3
            elif pattern == "rapid_hint_requests":
                hints = sum(1 for a in action_types if "hint" in a)
                if hints >= 4:
                    emotion_scores[emotion] += 0.25
        
        # Check text signals if provided
        if text_input:
            text_lower = text_input.lower()
            for signal in indicators["text_signals"]:
                if signal in text_lower:
                    emotion_scores[emotion] += 0.4
    
    # Find primary emotion
    primary_emotion = max(emotion_scores, key=emotion_scores.get)
    intensity = min(1.0, emotion_scores[primary_emotion])
    
    # Default to neutral if no strong signals
    if intensity < 0.2:
        primary_emotion = "neutral"
        intensity = 0.5
    
    # Store emotional state
    emotional_state = {
        "user_id": user_id,
        "primary_emotion": primary_emotion,
        "intensity": intensity,
        "all_scores": emotion_scores,
        "detected_at": datetime.utcnow()
    }
    
    await eq_db.emotional_states.insert_one(emotional_state)
    
    # Get appropriate response style
    response_style = EMOTIONAL_INDICATORS.get(primary_emotion, {}).get("response_style", "neutral_helpful")
    
    return {
        "user_id": user_id,
        "emotional_state": {
            "primary": primary_emotion,
            "intensity": intensity,
            "all_scores": emotion_scores
        },
        "recommended_response_style": response_style,
        "immediate_intervention_needed": primary_emotion in ["frustrated", "overwhelmed", "discouraged"] and intensity > 0.6
    }


@router.post("/therapeutic-response")
async def get_therapeutic_response(
    user_id: str,
    emotional_state: str,
    context: Optional[str] = None,
    intensity: float = 0.5
):
    """Get an emotionally intelligent therapeutic response"""
    
    if emotional_state not in THERAPEUTIC_RESPONSES:
        emotional_state = "neutral"
    
    responses = THERAPEUTIC_RESPONSES.get(emotional_state, {})
    
    # Build response based on intensity
    response_parts = []
    
    if intensity > 0.5:
        # Strong emotion - acknowledge first
        if "acknowledgment" in responses:
            response_parts.append(random.choice(responses["acknowledgment"]))
    
    # Add reframe
    if "reframe" in responses:
        response_parts.append(random.choice(responses["reframe"]))
    
    # Add action suggestion
    if "action" in responses:
        response_parts.append(random.choice(responses["action"]))
    elif "challenge" in responses:
        response_parts.append(random.choice(responses["challenge"]))
    
    combined_response = " ".join(response_parts)
    
    # For intense negative emotions, use AI for more personalized response
    if intensity > 0.7 and emotional_state in ["frustrated", "overwhelmed", "discouraged"]:
        try:
            chat = LlmChat(api_key=EMERGENT_LLM_KEY)
            ai_prompt = f"""You are Jeeves, an emotionally intelligent AI tutor. The user is feeling {emotional_state} (intensity: {intensity}).
            
Context: {context or 'Learning programming'}

Generate a warm, empathetic, and helpful response that:
1. Validates their feelings without being patronizing
2. Gently reframes the situation positively
3. Offers a concrete, small next step
4. Reinforces growth mindset

Keep it conversational, warm, and under 100 words. Don't use phrases like "I understand" - show understanding through action."""

            ai_response = await chat.send_async([UserMessage(content=ai_prompt)])
            combined_response = ai_response.text
        except Exception:
            pass
    
    # Log therapeutic interaction
    await eq_db.therapeutic_interactions.insert_one({
        "user_id": user_id,
        "emotional_state": emotional_state,
        "intensity": intensity,
        "response_given": combined_response,
        "timestamp": datetime.utcnow()
    })
    
    return {
        "response": combined_response,
        "emotional_state": emotional_state,
        "intensity": intensity,
        "response_type": "therapeutic",
        "follow_up_recommended": intensity > 0.6
    }


@router.get("/psychology-profile/{user_id}")
async def get_psychology_profile(user_id: str):
    """Get or create user's learning psychology profile"""
    
    profile = await eq_db.psychology_profiles.find_one({"user_id": user_id})
    
    if not profile:
        # Create default profile
        profile = {
            "user_id": user_id,
            "motivation_type": "mixed",
            "motivation_drivers": ["mastery", "achievement"],
            "cognitive_style": "analytical",
            "stress_tolerance": "medium",
            "preferred_challenge_level": 0.6,
            "learning_anxiety_level": 0.3,
            "perfectionism_tendency": 0.5,
            "growth_mindset_score": 0.5,
            "resilience_score": 0.5,
            "self_efficacy": 0.5,
            "created_at": datetime.utcnow(),
            "last_updated": datetime.utcnow()
        }
        await eq_db.psychology_profiles.insert_one(profile)
    
    # Get recent emotional history
    recent_emotions = await eq_db.emotional_states.find(
        {"user_id": user_id}
    ).sort("detected_at", -1).limit(20).to_list(20)
    
    # Calculate emotional trends
    emotion_counts = {}
    for e in recent_emotions:
        em = e.get("primary_emotion", "neutral")
        emotion_counts[em] = emotion_counts.get(em, 0) + 1
    
    return {
        "user_id": user_id,
        "profile": {
            "motivation_type": profile.get("motivation_type"),
            "motivation_drivers": profile.get("motivation_drivers"),
            "cognitive_style": profile.get("cognitive_style"),
            "stress_tolerance": profile.get("stress_tolerance"),
            "preferred_challenge_level": profile.get("preferred_challenge_level"),
            "learning_anxiety_level": profile.get("learning_anxiety_level"),
            "perfectionism_tendency": profile.get("perfectionism_tendency"),
            "growth_mindset_score": profile.get("growth_mindset_score"),
            "resilience_score": profile.get("resilience_score"),
            "self_efficacy": profile.get("self_efficacy")
        },
        "emotional_trends": emotion_counts,
        "recommendations": generate_psychology_recommendations(profile, emotion_counts)
    }


def generate_psychology_recommendations(profile: Dict, emotion_trends: Dict) -> List[Dict]:
    """Generate personalized recommendations based on psychology profile"""
    recommendations = []
    
    # High anxiety
    if profile.get("learning_anxiety_level", 0) > 0.6:
        recommendations.append({
            "type": "anxiety_management",
            "title": "Reduce Learning Anxiety",
            "suggestions": [
                "Start with familiar topics to build confidence",
                "Use smaller, achievable goals",
                "Practice self-compassion when making mistakes",
                "Try the Pomodoro technique to manage overwhelm"
            ]
        })
    
    # Low growth mindset
    if profile.get("growth_mindset_score", 0) < 0.4:
        recommendations.append({
            "type": "mindset_development",
            "title": "Develop Growth Mindset",
            "suggestions": [
                "Reframe 'I can't' to 'I can't YET'",
                "Celebrate effort, not just results",
                "View challenges as opportunities",
                "Learn about neuroplasticity - your brain can grow!"
            ]
        })
    
    # High perfectionism
    if profile.get("perfectionism_tendency", 0) > 0.7:
        recommendations.append({
            "type": "perfectionism_management",
            "title": "Manage Perfectionism",
            "suggestions": [
                "Aim for 'good enough' on practice exercises",
                "Set time limits to prevent over-polishing",
                "Remember: professional code is rarely perfect",
                "Value progress over perfection"
            ]
        })
    
    # Frequent frustration
    if emotion_trends.get("frustrated", 0) > 5:
        recommendations.append({
            "type": "frustration_management",
            "title": "Better Handle Frustration",
            "suggestions": [
                "Take breaks when stuck for more than 15 minutes",
                "Use rubber duck debugging",
                "Ask for hints earlier - it's not cheating",
                "Remember: frustration means you're challenging yourself"
            ]
        })
    
    return recommendations


@router.post("/growth-mindset-message")
async def get_growth_mindset_message(
    context: Literal["after_failure", "after_success", "effort_praise", "process_praise"],
    user_id: Optional[str] = None
):
    """Get a growth mindset reinforcement message"""
    
    messages = GROWTH_MINDSET_MESSAGES.get(context, GROWTH_MINDSET_MESSAGES["effort_praise"])
    message = random.choice(messages)
    
    return {
        "message": message,
        "context": context,
        "purpose": "growth_mindset_reinforcement"
    }


@router.post("/cognitive-load-check")
async def check_cognitive_load(
    user_id: str,
    session_duration_minutes: int,
    new_concepts_introduced: int,
    error_count: int,
    last_break_minutes_ago: int
):
    """Check if cognitive load is too high and suggest interventions"""
    
    load_score = 0
    
    # Session duration factor
    if session_duration_minutes > 60:
        load_score += 0.3
    elif session_duration_minutes > 90:
        load_score += 0.5
    
    # New concepts factor
    if new_concepts_introduced > 3:
        load_score += 0.3
    elif new_concepts_introduced > 5:
        load_score += 0.5
    
    # Error rate factor
    if error_count > 5:
        load_score += 0.2
    elif error_count > 10:
        load_score += 0.4
    
    # Break factor
    if last_break_minutes_ago > 45:
        load_score += 0.3
    elif last_break_minutes_ago > 90:
        load_score += 0.5
    
    load_level = "low" if load_score < 0.4 else "medium" if load_score < 0.7 else "high"
    
    interventions = []
    if load_level == "high":
        interventions = COGNITIVE_LOAD_STRATEGIES["high_load_detected"]["interventions"]
    
    return {
        "cognitive_load_level": load_level,
        "load_score": min(1.0, load_score),
        "factors": {
            "session_duration": session_duration_minutes,
            "new_concepts": new_concepts_introduced,
            "errors": error_count,
            "minutes_since_break": last_break_minutes_ago
        },
        "recommended_interventions": interventions,
        "break_recommended": last_break_minutes_ago > 45 or load_score > 0.6
    }


@router.get("/pomodoro/status/{user_id}")
async def get_pomodoro_status(user_id: str):
    """Get user's Pomodoro session status"""
    
    session = await eq_db.pomodoro_sessions.find_one(
        {"user_id": user_id, "active": True}
    )
    
    if not session:
        return {
            "active_session": False,
            "message": "No active Pomodoro session. Start one to boost your focus!",
            "config": POMODORO_CONFIG
        }
    
    elapsed = (datetime.utcnow() - session["started_at"]).seconds // 60
    remaining = session["duration_minutes"] - elapsed
    
    return {
        "active_session": True,
        "session_type": session["session_type"],
        "elapsed_minutes": elapsed,
        "remaining_minutes": max(0, remaining),
        "sessions_completed_today": session.get("sessions_today", 0),
        "session_complete": remaining <= 0
    }


@router.post("/pomodoro/start")
async def start_pomodoro(user_id: str, session_type: Literal["work", "short_break", "long_break"] = "work"):
    """Start a Pomodoro session"""
    
    # End any active session
    await eq_db.pomodoro_sessions.update_many(
        {"user_id": user_id, "active": True},
        {"$set": {"active": False, "ended_at": datetime.utcnow()}}
    )
    
    durations = {
        "work": POMODORO_CONFIG["work_duration_minutes"],
        "short_break": POMODORO_CONFIG["short_break_minutes"],
        "long_break": POMODORO_CONFIG["long_break_minutes"]
    }
    
    session = {
        "user_id": user_id,
        "session_type": session_type,
        "duration_minutes": durations[session_type],
        "started_at": datetime.utcnow(),
        "active": True
    }
    
    await eq_db.pomodoro_sessions.insert_one(session)
    
    messages = {
        "work": "Focus time started! 25 minutes of concentrated learning ahead. You've got this!",
        "short_break": "Short break time! Step away from the screen, stretch, and breathe.",
        "long_break": "Great work! You've earned a longer break. Rest well to consolidate your learning."
    }
    
    return {
        "started": True,
        "session_type": session_type,
        "duration_minutes": durations[session_type],
        "message": messages[session_type],
        "wellness_tip": random.choice(POMODORO_CONFIG["break_activities"]) if "break" in session_type else None
    }


@router.get("/wellness-reminder")
async def get_wellness_reminder():
    """Get a random wellness reminder"""
    reminder = random.choice(POMODORO_CONFIG["wellness_reminders"])
    return {
        "type": reminder["type"],
        "message": reminder["message"],
        "importance": "Your wellbeing matters for effective learning!"
    }


@router.post("/update-psychology-profile")
async def update_psychology_profile(
    user_id: str,
    updates: Dict[str, Any]
):
    """Update user's psychology profile based on observed behavior"""
    
    allowed_fields = [
        "motivation_type", "motivation_drivers", "cognitive_style",
        "stress_tolerance", "preferred_challenge_level", "learning_anxiety_level",
        "perfectionism_tendency", "growth_mindset_score", "resilience_score", "self_efficacy"
    ]
    
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    filtered_updates["last_updated"] = datetime.utcnow()
    
    await eq_db.psychology_profiles.update_one(
        {"user_id": user_id},
        {"$set": filtered_updates},
        upsert=True
    )
    
    return {
        "updated": True,
        "fields_updated": list(filtered_updates.keys())
    }


@router.get("/spaced-repetition/schedule/{user_id}")
async def get_spaced_repetition_schedule(user_id: str):
    """Get personalized spaced repetition schedule"""
    
    # Get user's emotional profile for adjustments
    _profile = await eq_db.psychology_profiles.find_one({"user_id": user_id})
    recent_emotion = await eq_db.emotional_states.find_one(
        {"user_id": user_id},
        sort=[("detected_at", -1)]
    )
    
    # Get items due for review
    now = datetime.utcnow()
    due_items = await eq_db.spaced_repetition.find(
        {"user_id": user_id, "next_review": {"$lte": now}}
    ).to_list(50)
    
    # Adjust based on emotional state
    emotional_adjustment = 1.0
    if recent_emotion:
        emotion = recent_emotion.get("primary_emotion", "neutral")
        emotional_adjustment = SPACED_REPETITION_CONFIG["emotional_adjustments"].get(emotion, 1.0)
    
    return {
        "user_id": user_id,
        "items_due_for_review": len(due_items),
        "emotional_adjustment": emotional_adjustment,
        "items": [
            {
                "item_id": item["item_id"],
                "concept": item["concept"],
                "last_reviewed": item.get("last_review"),
                "current_interval_days": item.get("interval", 1),
                "repetitions": item.get("repetitions", 0)
            }
            for item in due_items[:10]
        ],
        "recommendation": "Review items in short sessions for better retention" if len(due_items) > 5 else "You're up to date!"
    }
