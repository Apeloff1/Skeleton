"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     IMMERSIVE TUTORING ENGINE v14.0 - ADAPTIVE LEARNING CURVE SYSTEM         ║
║                                                                              ║
║  "Learning should feel like an adventure, not a chore." - Jeeves             ║
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ IMMERSIVE EXPERIENCE COMPONENTS:                                        │ ║
║  │                                                                         │ ║
║  │ 🎮 Gamification Layer                                                   │ ║
║  │    • XP & Leveling System                                              │ ║
║  │    • Achievement Badges                                                 │ ║
║  │    • Daily Quests & Challenges                                         │ ║
║  │    • Streak Rewards                                                     │ ║
║  │                                                                         │ ║
║  │ 📈 Learning Curve Engine                                               │ ║
║  │    • Zone of Proximal Development (ZPD) Tracking                       │ ║
║  │    • Scaffolding System                                                 │ ║
║  │    • Difficulty Calibration                                             │ ║
║  │    • Mastery-Based Progression                                          │ ║
║  │                                                                         │ ║
║  │ 🧠 Cognitive Load Management                                           │ ║
║  │    • Chunking Optimizer                                                 │ ║
║  │    • Interleaving Strategy                                              │ ║
║  │    • Spaced Repetition                                                  │ ║
║  │    • Active Recall Triggers                                             │ ║
║  │                                                                         │ ║
║  │ 💬 Interactive Dialogue System                                         │ ║
║  │    • Socratic Method Implementation                                     │ ║
║  │    • Guided Discovery                                                   │ ║
║  │    • Reflective Prompts                                                 │ ║
║  │    • Error Analysis & Correction                                        │ ║
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

router = APIRouter(prefix="/api/immersive-tutor", tags=["Immersive Tutoring Engine"])

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class DifficultyZone(str, Enum):
    COMFORT = "comfort"           # Too easy - risk of boredom
    GROWTH = "growth"             # Optimal - Zone of Proximal Development
    STRETCH = "stretch"           # Challenging - needs support
    PANIC = "panic"               # Too hard - risk of frustration

class LearningPhase(str, Enum):
    INTRODUCTION = "introduction"  # First exposure
    ACQUISITION = "acquisition"    # Building understanding
    PRACTICE = "practice"          # Reinforcement
    APPLICATION = "application"    # Real-world use
    MASTERY = "mastery"           # Teaching others

class ScaffoldType(str, Enum):
    HINT = "hint"
    EXAMPLE = "example"
    ANALOGY = "analogy"
    BREAKDOWN = "breakdown"
    VISUAL = "visual"
    STEP_BY_STEP = "step_by_step"
    PEER_COMPARISON = "peer_comparison"
    WORKED_EXAMPLE = "worked_example"

# XP requirements for each level (exponential growth)
LEVEL_XP_REQUIREMENTS = [0] + [int(100 * (1.5 ** i)) for i in range(100)]

# Achievement definitions
ACHIEVEMENTS = {
    "first_lesson": {"name": "First Steps", "description": "Complete your first lesson", "xp": 50, "icon": "🌱"},
    "streak_3": {"name": "Getting Consistent", "description": "3-day learning streak", "xp": 100, "icon": "🔥"},
    "streak_7": {"name": "Week Warrior", "description": "7-day learning streak", "xp": 250, "icon": "⚡"},
    "streak_30": {"name": "Monthly Master", "description": "30-day learning streak", "xp": 1000, "icon": "💎"},
    "mastery_first": {"name": "First Mastery", "description": "Master your first topic", "xp": 500, "icon": "🏆"},
    "challenge_complete": {"name": "Challenge Accepted", "description": "Complete a daily challenge", "xp": 75, "icon": "🎯"},
    "perfect_quiz": {"name": "Perfect Score", "description": "100% on a quiz", "xp": 150, "icon": "⭐"},
    "night_owl": {"name": "Night Owl", "description": "Study after midnight", "xp": 50, "icon": "🦉"},
    "early_bird": {"name": "Early Bird", "description": "Study before 7am", "xp": 50, "icon": "🐦"},
    "speed_demon": {"name": "Speed Demon", "description": "Complete lesson in half the expected time", "xp": 100, "icon": "🚀"},
    "deep_diver": {"name": "Deep Diver", "description": "Spend 2+ hours in a single session", "xp": 200, "icon": "🤿"},
    "comeback_kid": {"name": "Comeback Kid", "description": "Return after 7+ days away", "xp": 100, "icon": "🔄"},
    "helper": {"name": "Helping Hand", "description": "Share knowledge with the community", "xp": 150, "icon": "🤝"},
    "explorer": {"name": "Explorer", "description": "Try 5 different topics", "xp": 200, "icon": "🗺️"},
    "completionist": {"name": "Completionist", "description": "Complete all lessons in a module", "xp": 500, "icon": "✅"},
}

# ============================================================================
# LEARNING CURVE ENGINE
# ============================================================================

class LearningCurveEngine:
    """
    Manages the learning curve to keep users in their Zone of Proximal Development.
    Uses Vygotsky's ZPD theory combined with modern adaptive learning algorithms.
    """
    
    @staticmethod
    def calculate_zpd(
        current_mastery: float,
        recent_performance: List[float],
        time_on_task: int,
        errors_made: int,
        hints_used: int
    ) -> Dict[str, Any]:
        """
        Calculate the user's Zone of Proximal Development.
        Returns optimal difficulty range and current zone.
        """
        if not recent_performance:
            recent_performance = [0.5]
        
        avg_performance = sum(recent_performance[-10:]) / min(len(recent_performance), 10)
        performance_variance = sum((p - avg_performance) ** 2 for p in recent_performance[-10:]) / max(len(recent_performance[-10:]), 1)
        
        # Calculate struggle indicators
        struggle_score = 0
        if avg_performance < 0.6:
            struggle_score += 0.3
        if errors_made > 5:
            struggle_score += 0.2
        if hints_used > 3:
            struggle_score += 0.2
        if time_on_task > 1800:  # More than 30 minutes
            struggle_score += 0.1
        
        # Determine current zone
        if avg_performance > 0.9 and struggle_score < 0.1:
            zone = DifficultyZone.COMFORT
            recommendation = "increase_difficulty"
        elif 0.7 <= avg_performance <= 0.9 and struggle_score < 0.3:
            zone = DifficultyZone.GROWTH
            recommendation = "maintain"
        elif 0.5 <= avg_performance < 0.7 or struggle_score < 0.5:
            zone = DifficultyZone.STRETCH
            recommendation = "add_scaffolding"
        else:
            zone = DifficultyZone.PANIC
            recommendation = "reduce_difficulty"
        
        # Calculate optimal difficulty range
        optimal_min = max(0.1, current_mastery - 0.1)
        optimal_max = min(1.0, current_mastery + 0.2)
        
        return {
            "current_zone": zone.value,
            "average_performance": round(avg_performance, 2),
            "performance_consistency": round(1 - min(performance_variance, 1), 2),
            "struggle_score": round(struggle_score, 2),
            "optimal_difficulty_range": {
                "min": round(optimal_min, 2),
                "max": round(optimal_max, 2),
                "sweet_spot": round((optimal_min + optimal_max) / 2, 2)
            },
            "recommendation": recommendation,
            "zpd_analysis": {
                "can_do_alone": f"Tasks up to {int(current_mastery * 100)}% difficulty",
                "can_do_with_help": f"Tasks {int(optimal_min * 100)}%-{int(optimal_max * 100)}% difficulty",
                "too_difficult": f"Tasks above {int(optimal_max * 100)}% difficulty"
            }
        }
    
    @staticmethod
    def generate_scaffolding(
        current_difficulty: float,
        user_performance: float,
        topic: str,
        error_patterns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Generate appropriate scaffolding based on user performance and errors.
        """
        scaffolds = []
        
        # Determine scaffolding intensity
        if user_performance < 0.4:
            intensity = "heavy"
            scaffold_count = 4
        elif user_performance < 0.6:
            intensity = "medium"
            scaffold_count = 3
        elif user_performance < 0.8:
            intensity = "light"
            scaffold_count = 2
        else:
            intensity = "minimal"
            scaffold_count = 1
        
        # Generate scaffolds based on error patterns
        if "conceptual" in error_patterns:
            scaffolds.append({
                "type": ScaffoldType.ANALOGY.value,
                "content": f"Think of {topic} like building with LEGO blocks. Each concept connects to others.",
                "when_to_show": "before_attempt",
                "priority": 1
            })
        
        if "procedural" in error_patterns:
            scaffolds.append({
                "type": ScaffoldType.STEP_BY_STEP.value,
                "content": f"Let's break this down step by step...",
                "steps": [
                    "Identify the inputs",
                    "Determine the expected output",
                    "Choose the right approach",
                    "Implement step by step",
                    "Test and verify"
                ],
                "when_to_show": "on_first_error",
                "priority": 2
            })
        
        if "application" in error_patterns:
            scaffolds.append({
                "type": ScaffoldType.WORKED_EXAMPLE.value,
                "content": "Here's a similar problem solved step by step...",
                "when_to_show": "after_second_error",
                "priority": 3
            })
        
        # Always include hints
        scaffolds.append({
            "type": ScaffoldType.HINT.value,
            "hints": [
                {"level": 1, "text": "Consider what data type would be most appropriate here."},
                {"level": 2, "text": "Remember, this pattern is similar to what we covered in the basics."},
                {"level": 3, "text": f"The key insight for {topic} is..."}
            ],
            "when_to_show": "on_request",
            "priority": 4
        })
        
        return {
            "scaffolding_intensity": intensity,
            "scaffolds": scaffolds[:scaffold_count],
            "total_available": len(scaffolds),
            "fading_strategy": "Scaffolds will be gradually removed as you improve"
        }
    
    @staticmethod
    def calculate_progression(
        completed_lessons: List[Dict],
        current_level: int,
        total_xp: int
    ) -> Dict[str, Any]:
        """
        Calculate learning progression and next milestones.
        """
        # Calculate current level progress
        current_level_xp = LEVEL_XP_REQUIREMENTS[current_level]
        next_level_xp = LEVEL_XP_REQUIREMENTS[min(current_level + 1, 99)]
        xp_in_current_level = total_xp - current_level_xp
        xp_needed = next_level_xp - current_level_xp
        level_progress = xp_in_current_level / max(xp_needed, 1)
        
        # Calculate completion stats
        total_lessons = len(completed_lessons)
        mastered_lessons = len([l for l in completed_lessons if l.get("mastery", 0) >= 0.9])
        
        # Determine learning velocity
        if completed_lessons:
            recent_lessons = completed_lessons[-7:]
            avg_time_per_lesson = sum(l.get("time_spent", 0) for l in recent_lessons) / len(recent_lessons)
            velocity = len(recent_lessons) / 7  # Lessons per day
        else:
            avg_time_per_lesson = 0
            velocity = 0
        
        return {
            "current_level": current_level,
            "total_xp": total_xp,
            "level_progress": round(level_progress, 2),
            "xp_to_next_level": max(0, next_level_xp - total_xp),
            "stats": {
                "total_lessons_completed": total_lessons,
                "lessons_mastered": mastered_lessons,
                "mastery_rate": round(mastered_lessons / max(total_lessons, 1), 2),
                "avg_time_per_lesson_minutes": round(avg_time_per_lesson / 60, 1),
                "learning_velocity": round(velocity, 2)
            },
            "next_milestones": [
                {"name": f"Level {current_level + 1}", "xp_needed": next_level_xp - total_xp},
                {"name": f"Complete 10 lessons", "lessons_needed": max(0, 10 - total_lessons)},
                {"name": f"Master 5 topics", "topics_needed": max(0, 5 - mastered_lessons)}
            ]
        }

# ============================================================================
# IMMERSIVE EXPERIENCE ENGINE
# ============================================================================

class ImmersiveExperienceEngine:
    """
    Creates engaging, game-like learning experiences while maintaining
    educational rigor.
    """
    
    @staticmethod
    def generate_daily_quest(
        user_level: int,
        recent_topics: List[str],
        streak_days: int
    ) -> Dict[str, Any]:
        """
        Generate personalized daily quests based on user progress.
        """
        quest_templates = [
            {
                "type": "practice",
                "title": "Practice Makes Perfect",
                "description": "Complete {count} practice problems",
                "target": {"count": min(5 + user_level // 5, 15)},
                "xp_reward": 50 + (user_level * 5),
                "time_limit_hours": 24
            },
            {
                "type": "streak",
                "title": "Keep the Fire Burning",
                "description": "Maintain your learning streak",
                "target": {"days": 1},
                "xp_reward": 25 * (1 + streak_days // 7),
                "time_limit_hours": 24
            },
            {
                "type": "mastery",
                "title": "Aim for Excellence",
                "description": "Achieve 90%+ on a quiz",
                "target": {"score": 90},
                "xp_reward": 100,
                "time_limit_hours": 24
            },
            {
                "type": "exploration",
                "title": "Curious Mind",
                "description": "Try a new topic you haven't explored",
                "target": {"new_topics": 1},
                "xp_reward": 75,
                "time_limit_hours": 24
            },
            {
                "type": "review",
                "title": "Memory Lane",
                "description": "Review {count} previously learned concepts",
                "target": {"count": 3},
                "xp_reward": 40,
                "time_limit_hours": 24
            },
            {
                "type": "time",
                "title": "Dedicated Learner",
                "description": "Spend {minutes} minutes learning",
                "target": {"minutes": 30},
                "xp_reward": 60,
                "time_limit_hours": 24
            }
        ]
        
        # Select 3 quests for the day
        selected_quests = random.sample(quest_templates, min(3, len(quest_templates)))
        
        # Add a bonus challenge based on streak
        if streak_days >= 7:
            selected_quests.append({
                "type": "bonus",
                "title": "🔥 Streak Bonus Challenge",
                "description": "Complete all daily quests for bonus XP",
                "target": {"complete_all": True},
                "xp_reward": 150,
                "time_limit_hours": 24,
                "is_bonus": True
            })
        
        return {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "quests": selected_quests,
            "total_possible_xp": sum(q["xp_reward"] for q in selected_quests),
            "streak_multiplier": 1 + (streak_days * 0.05),  # 5% bonus per streak day
            "refresh_in_hours": 24 - datetime.utcnow().hour
        }
    
    @staticmethod
    def generate_challenge(
        difficulty: float,
        topic: str,
        time_limit_minutes: int = 10
    ) -> Dict[str, Any]:
        """
        Generate a timed challenge for the user.
        """
        challenge_types = ["speed_round", "accuracy_challenge", "endurance_test", "boss_battle"]
        challenge_type = random.choice(challenge_types)
        
        challenges = {
            "speed_round": {
                "name": "⚡ Speed Round",
                "description": "Answer as many questions as you can!",
                "rules": [
                    f"You have {time_limit_minutes} minutes",
                    "Each correct answer: +10 XP",
                    "Each wrong answer: -5 seconds",
                    "Bonus for speed!"
                ],
                "xp_multiplier": 1.5
            },
            "accuracy_challenge": {
                "name": "🎯 Precision Strike",
                "description": "Accuracy is everything. Don't make mistakes!",
                "rules": [
                    "Get 10 questions right in a row",
                    "One mistake = start over",
                    "Huge XP reward for completion"
                ],
                "xp_multiplier": 2.0
            },
            "endurance_test": {
                "name": "🏃 Endurance Test",
                "description": "How long can you go without a break?",
                "rules": [
                    "Questions keep coming",
                    "Difficulty increases over time",
                    "See how far you can get!"
                ],
                "xp_multiplier": 1.75
            },
            "boss_battle": {
                "name": "👹 Boss Battle",
                "description": "Face the ultimate challenge!",
                "rules": [
                    "5 difficult questions",
                    "No hints allowed",
                    "Defeat the boss for massive XP!"
                ],
                "xp_multiplier": 3.0
            }
        }
        
        selected = challenges[challenge_type]
        
        return {
            "id": str(uuid.uuid4()),
            "type": challenge_type,
            "name": selected["name"],
            "description": selected["description"],
            "topic": topic,
            "difficulty": difficulty,
            "time_limit_minutes": time_limit_minutes,
            "rules": selected["rules"],
            "rewards": {
                "base_xp": int(100 * difficulty),
                "multiplier": selected["xp_multiplier"],
                "max_xp": int(100 * difficulty * selected["xp_multiplier"])
            },
            "started_at": None,
            "status": "available"
        }
    
    @staticmethod
    def calculate_streak_rewards(streak_days: int) -> Dict[str, Any]:
        """
        Calculate rewards based on current streak.
        """
        milestones = [
            {"days": 3, "reward": "streak_3", "xp_bonus": 100},
            {"days": 7, "reward": "streak_7", "xp_bonus": 250},
            {"days": 14, "reward": "2x XP Day", "xp_bonus": 500},
            {"days": 30, "reward": "streak_30", "xp_bonus": 1000},
            {"days": 60, "reward": "Legendary Learner", "xp_bonus": 2500},
            {"days": 100, "reward": "Century Club", "xp_bonus": 5000}
        ]
        
        # Find current milestone and next milestone
        current_milestone = None
        next_milestone = None
        
        for milestone in milestones:
            if streak_days >= milestone["days"]:
                current_milestone = milestone
            elif next_milestone is None:
                next_milestone = milestone
        
        # Calculate daily streak bonus
        daily_bonus = min(streak_days * 5, 100)  # Max 100 bonus XP per day
        
        return {
            "current_streak": streak_days,
            "daily_xp_bonus": daily_bonus,
            "multiplier": 1 + (streak_days * 0.02),  # 2% per day, max 200%
            "current_milestone": current_milestone,
            "next_milestone": next_milestone,
            "days_to_next": next_milestone["days"] - streak_days if next_milestone else None,
            "streak_message": ImmersiveExperienceEngine._get_streak_message(streak_days)
        }
    
    @staticmethod
    def _get_streak_message(days: int) -> str:
        if days == 0:
            return "Start your streak today!"
        elif days == 1:
            return "Great start! Keep it going tomorrow."
        elif days < 7:
            return f"{days} days strong! You're building a habit."
        elif days < 14:
            return f"A full week+! You're on fire! 🔥"
        elif days < 30:
            return f"{days} days! You're becoming unstoppable!"
        elif days < 60:
            return f"A month+! You're a dedicated learner! 💪"
        else:
            return f"{days} days! You're a legend! 🏆"

# ============================================================================
# INTERACTIVE DIALOGUE SYSTEM
# ============================================================================

class SocraticDialogueEngine:
    """
    Implements the Socratic method for deeper understanding.
    Guides users to discover answers through questioning.
    """
    
    QUESTION_TEMPLATES = {
        "clarification": [
            "What do you mean by {concept}?",
            "Can you explain that in your own words?",
            "What's another way to think about this?",
            "How would you explain this to a friend?"
        ],
        "assumption": [
            "What are you assuming here?",
            "Is that always true?",
            "What if {assumption} wasn't the case?",
            "Why do you think that's the right approach?"
        ],
        "evidence": [
            "What evidence supports that?",
            "How do you know that works?",
            "Can you give me an example?",
            "What would prove you wrong?"
        ],
        "implication": [
            "What follows from that?",
            "If that's true, what else must be true?",
            "What are the consequences of this approach?",
            "How does this connect to what we learned before?"
        ],
        "perspective": [
            "What would someone who disagrees say?",
            "Is there another way to look at this?",
            "What are the trade-offs?",
            "Why might someone choose a different approach?"
        ]
    }
    
    @staticmethod
    def generate_dialogue(
        topic: str,
        user_answer: str,
        is_correct: bool,
        confidence_level: float
    ) -> Dict[str, Any]:
        """
        Generate Socratic dialogue based on user's answer.
        """
        if is_correct and confidence_level > 0.8:
            # User is confident and correct - push deeper
            question_type = random.choice(["implication", "perspective"])
            follow_up = "Excellent! Let's go deeper..."
        elif is_correct and confidence_level <= 0.8:
            # Correct but uncertain - reinforce understanding
            question_type = random.choice(["clarification", "evidence"])
            follow_up = "You're on the right track. Let's solidify this..."
        elif not is_correct and confidence_level > 0.8:
            # Wrong but confident - challenge assumptions
            question_type = "assumption"
            follow_up = "Interesting thinking, but let's examine that assumption..."
        else:
            # Wrong and uncertain - guide to discovery
            question_type = random.choice(["clarification", "evidence"])
            follow_up = "Let's work through this together..."
        
        questions = SocraticDialogueEngine.QUESTION_TEMPLATES[question_type]
        selected_question = random.choice(questions).format(
            concept=topic,
            assumption="your initial assumption"
        )
        
        return {
            "dialogue_type": question_type,
            "follow_up": follow_up,
            "question": selected_question,
            "guidance_level": "light" if is_correct else "supportive",
            "jeeves_tone": "encouraging" if confidence_level < 0.5 else "challenging",
            "next_steps": [
                "Think about the question",
                "Consider what you know",
                "Try to explain your reasoning"
            ]
        }
    
    @staticmethod
    def generate_reflection_prompt(
        lesson_topic: str,
        performance: float,
        time_spent: int,
        errors: List[str]
    ) -> Dict[str, Any]:
        """
        Generate reflection prompts after a lesson.
        """
        prompts = []
        
        # Core reflection
        prompts.append({
            "type": "understanding",
            "question": f"In your own words, what's the most important thing you learned about {lesson_topic}?",
            "purpose": "Consolidate understanding through articulation"
        })
        
        # Performance-based reflection
        if performance < 0.6:
            prompts.append({
                "type": "struggle",
                "question": "What part felt most challenging? What made it difficult?",
                "purpose": "Identify obstacles for targeted improvement"
            })
        elif performance > 0.9:
            prompts.append({
                "type": "extension",
                "question": "How might you apply this in a real project?",
                "purpose": "Connect learning to practical application"
            })
        
        # Error-based reflection
        if errors:
            prompts.append({
                "type": "error_analysis",
                "question": f"Looking at your mistakes, what pattern do you notice?",
                "purpose": "Develop metacognitive awareness"
            })
        
        # Connection reflection
        prompts.append({
            "type": "connection",
            "question": "How does this connect to something you already knew?",
            "purpose": "Build knowledge networks"
        })
        
        return {
            "topic": lesson_topic,
            "performance": performance,
            "prompts": prompts,
            "jeeves_intro": "Splendid effort! Before we move on, let's take a moment to reflect...",
            "estimated_time_minutes": 3
        }

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class LearningSessionRequest(BaseModel):
    user_id: str
    topic: str
    current_mastery: float = 0.5
    recent_performance: List[float] = []
    time_on_task_seconds: int = 0
    errors_made: int = 0
    hints_used: int = 0

class ChallengeRequest(BaseModel):
    user_id: str
    topic: str
    preferred_difficulty: float = 0.5
    time_limit_minutes: int = 10

class DialogueRequest(BaseModel):
    user_id: str
    topic: str
    user_answer: str
    is_correct: bool
    confidence_level: float = 0.5

class ProgressRequest(BaseModel):
    user_id: str
    completed_lessons: List[Dict[str, Any]] = []
    current_level: int = 1
    total_xp: int = 0

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/zpd/analyze")
async def analyze_zpd(request: LearningSessionRequest):
    """Analyze user's Zone of Proximal Development"""
    return LearningCurveEngine.calculate_zpd(
        request.current_mastery,
        request.recent_performance,
        request.time_on_task_seconds,
        request.errors_made,
        request.hints_used
    )

@router.post("/scaffolding/generate")
async def generate_scaffolding(
    topic: str,
    current_difficulty: float = 0.5,
    user_performance: float = 0.5,
    error_patterns: List[str] = ["conceptual"]
):
    """Generate appropriate scaffolding for the user"""
    return LearningCurveEngine.generate_scaffolding(
        current_difficulty,
        user_performance,
        topic,
        error_patterns
    )

@router.post("/progression/calculate")
async def calculate_progression(request: ProgressRequest):
    """Calculate learning progression and milestones"""
    return LearningCurveEngine.calculate_progression(
        request.completed_lessons,
        request.current_level,
        request.total_xp
    )

@router.post("/quest/daily")
async def get_daily_quest(
    user_level: int = 1,
    recent_topics: List[str] = [],
    streak_days: int = 0
):
    """Generate daily quests for the user"""
    return ImmersiveExperienceEngine.generate_daily_quest(
        user_level,
        recent_topics,
        streak_days
    )

@router.post("/challenge/generate")
async def generate_challenge(request: ChallengeRequest):
    """Generate a timed challenge"""
    return ImmersiveExperienceEngine.generate_challenge(
        request.preferred_difficulty,
        request.topic,
        request.time_limit_minutes
    )

@router.get("/streak/rewards")
async def get_streak_rewards(streak_days: int = 0):
    """Calculate streak rewards and bonuses"""
    return ImmersiveExperienceEngine.calculate_streak_rewards(streak_days)

@router.post("/dialogue/socratic")
async def generate_socratic_dialogue(request: DialogueRequest):
    """Generate Socratic dialogue based on user's answer"""
    return SocraticDialogueEngine.generate_dialogue(
        request.topic,
        request.user_answer,
        request.is_correct,
        request.confidence_level
    )

@router.post("/reflection/prompt")
async def generate_reflection(
    lesson_topic: str,
    performance: float = 0.7,
    time_spent_seconds: int = 600,
    errors: List[str] = []
):
    """Generate reflection prompts after a lesson"""
    return SocraticDialogueEngine.generate_reflection_prompt(
        lesson_topic,
        performance,
        time_spent_seconds,
        errors
    )

@router.get("/achievements/list")
async def list_achievements():
    """Get all available achievements"""
    return {
        "achievements": [
            {
                "id": aid,
                "name": ach["name"],
                "description": ach["description"],
                "xp_reward": ach["xp"],
                "icon": ach["icon"]
            }
            for aid, ach in ACHIEVEMENTS.items()
        ],
        "total_achievements": len(ACHIEVEMENTS),
        "total_possible_xp": sum(a["xp"] for a in ACHIEVEMENTS.values())
    }

@router.get("/levels/info")
async def get_level_info():
    """Get leveling system information"""
    return {
        "max_level": 100,
        "xp_formula": "100 * (1.5 ^ level)",
        "sample_levels": [
            {"level": i, "xp_required": LEVEL_XP_REQUIREMENTS[i]}
            for i in [1, 5, 10, 20, 50, 100]
            if i < len(LEVEL_XP_REQUIREMENTS)
        ],
        "level_perks": {
            5: "Unlock daily challenges",
            10: "Unlock advanced topics",
            20: "Unlock mentor mode",
            50: "Unlock custom challenges",
            100: "Unlock everything + special badge"
        }
    }

@router.get("/immersion/overview")
async def get_immersion_overview():
    """Get overview of the immersive tutoring system"""
    return {
        "system": "Immersive Tutoring Engine v14.0",
        "components": {
            "learning_curve": {
                "name": "Learning Curve Engine",
                "features": ["ZPD Tracking", "Scaffolding System", "Difficulty Calibration", "Mastery Progression"]
            },
            "gamification": {
                "name": "Gamification Layer", 
                "features": ["XP & Leveling", "Achievements", "Daily Quests", "Streak Rewards", "Challenges"]
            },
            "cognitive": {
                "name": "Cognitive Load Management",
                "features": ["Chunking", "Interleaving", "Spaced Repetition", "Active Recall"]
            },
            "dialogue": {
                "name": "Interactive Dialogue",
                "features": ["Socratic Method", "Guided Discovery", "Reflection Prompts", "Error Analysis"]
            }
        },
        "philosophy": "Learning should feel like an adventure, not a chore.",
        "jeeves_says": "Together, we shall make your learning journey both effective and enjoyable. Shall we begin?"
    }
