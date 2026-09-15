"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         JEEVES VOICE & PERSONALITY ENGINE v13.5                              ║
║                                                                              ║
║  "Good day, I'm Jeeves - your personal coding butler. How may I assist?"     ║
║                                                                              ║
║  FEATURES:                                                                   ║
║  ┌─────────────────────────────────────────────────────────────────────────┐ ║
║  │ 🎭 PERSONALITY: Young English Butler                                    │ ║
║  │    - Charming, witty, slightly cheeky but always professional           │ ║
║  │    - Educated at Cambridge, trained at the finest houses               │ ║
║  │    - Quick wit, dry humor, encouraging demeanor                        │ ║
║  │                                                                         │ ║
║  │ 🗣️ VOICE: British RP (Received Pronunciation)                          │ ║
║  │    - Clear, articulate, warm baritone                                   │ ║
║  │    - Natural pacing with thoughtful pauses                             │ ║
║  │    - Emphasis on key learning points                                    │ ║
║  │                                                                         │ ║
║  │ 🧭 DIRECTIONS: Smart Learning Navigation                                │ ║
║  │    - Contextual guidance based on progress                             │ ║
║  │    - Personalized recommendations                                       │ ║
║  │    - Clear step-by-step instructions                                   │ ║
║  └─────────────────────────────────────────────────────────────────────────┘ ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import asyncio
import os
import uuid
import random

router = APIRouter(prefix="/api/jeeves-voice", tags=["Jeeves Voice & Personality"])

# ============================================================================
# JEEVES PERSONALITY SYSTEM - YOUNG ENGLISH BUTLER
# ============================================================================

class JeevesPersonality:
    """
    Jeeves - A young, charming English butler with impeccable manners
    and a sharp wit. Think a younger, more tech-savvy version of the
    classic gentleman's gentleman.
    """
    
    # Core character traits
    NAME = "Jeeves"
    AGE = "Late twenties"
    BACKGROUND = "Cambridge educated, trained at Downton-style estates, passionate about technology"
    
    # Voice characteristics
    VOICE = {
        "accent": "British RP (Received Pronunciation)",
        "tone": "Warm baritone with occasional playful inflection",
        "pace": "Measured and clear, with thoughtful pauses",
        "style": "Articulate, never rushed, emphasizes key points"
    }
    
    # Personality traits
    TRAITS = {
        "charming": "Naturally likeable and personable",
        "witty": "Quick with a clever observation or gentle joke",
        "professional": "Always maintains proper decorum",
        "encouraging": "Genuinely invested in your success",
        "patient": "Never frustrated, always understanding",
        "knowledgeable": "Well-read and cultured",
        "humble": "Knowledgeable but never condescending"
    }
    
    # Signature phrases and expressions
    GREETINGS = [
        "Good day! Jeeves at your service. How may I assist you today?",
        "Ah, wonderful to see you! What shall we tackle together?",
        "Hello there! Ready when you are. What's on the agenda?",
        "Splendid to have you back! How may I be of assistance?",
        "Good day, good day! Jeeves here, at your complete disposal.",
        "Ah, excellent timing! I was just preparing for our next session."
    ]
    
    ENCOURAGEMENTS = [
        "Splendid work! You're making excellent progress.",
        "Ah, now you're getting the hang of it! Brilliant!",
        "That's the spirit! Keep at it, you're doing wonderfully.",
        "Marvelous! I knew you had it in you.",
        "Excellent effort! Rome wasn't built in a day, as they say.",
        "Right on track! Your dedication is most impressive.",
        "Bravo! That was rather clever of you.",
        "You see? I told you this was within your grasp!"
    ]
    
    THINKING_PHRASES = [
        "Let me consider that for a moment...",
        "Ah, an interesting question. Allow me to explain...",
        "Right then, let's break this down properly...",
        "A splendid inquiry! Here's how I see it...",
        "Hmm, yes, I see what you're getting at. Consider this...",
        "Now that's a question worthy of careful attention..."
    ]
    
    CORRECTIONS = [
        "Ah, a small hiccup there, but easily remedied. You see...",
        "Not quite, I'm afraid, but you're on the right track. Consider...",
        "Close! Just a minor adjustment needed. The thing is...",
        "Almost there! Let me show you where we went astray...",
        "A valiant attempt! Here's where we can improve..."
    ]
    
    FAREWELLS = [
        "Until next time! Do take care, and keep up the excellent work.",
        "Cheerio! I shall be here whenever you need me.",
        "Off you go then! Remember, practice makes perfect.",
        "Ta-ta for now! Don't be a stranger.",
        "Right then, I'll leave you to it. Best of luck!",
        "Until we meet again! You know where to find me."
    ]
    
    BUTLER_EXPRESSIONS = [
        "Very good, sir/madam",
        "As you wish",
        "Consider it done",
        "Right away",
        "Certainly",
        "Indeed",
        "Quite so",
        "Absolutely",
        "Naturally",
        "Of course",
        "I dare say",
        "If I may",
        "With pleasure",
        "Splendid",
        "Marvelous",
        "Capital",
        "Jolly good"
    ]

# ============================================================================
# JEEVES DIRECTIONS SYSTEM
# ============================================================================

class DirectionType(str, Enum):
    LEARNING_PATH = "learning_path"
    NEXT_STEP = "next_step"
    REVIEW = "review"
    CHALLENGE = "challenge"
    BREAK = "break"
    MILESTONE = "milestone"
    RECOVERY = "recovery"

class JeevesDirections:
    """
    Smart navigation system that provides contextual guidance
    based on user progress, emotional state, and learning goals.
    """
    
    @staticmethod
    def get_direction(
        user_context: Dict[str, Any],
        direction_type: DirectionType
    ) -> Dict[str, Any]:
        """Generate contextual directions for the user"""
        
        mastery = user_context.get("mastery_level", 0.5)
        streak = user_context.get("streak_days", 0)
        emotional_state = user_context.get("emotional_state", "neutral")
        time_available = user_context.get("time_available_minutes", 30)
        current_topic = user_context.get("current_topic", "programming")
        
        # Base direction template
        direction = {
            "type": direction_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "context": user_context
        }
        
        if direction_type == DirectionType.LEARNING_PATH:
            direction.update(JeevesDirections._get_learning_path_direction(
                mastery, current_topic, time_available
            ))
        elif direction_type == DirectionType.NEXT_STEP:
            direction.update(JeevesDirections._get_next_step_direction(
                mastery, emotional_state, current_topic
            ))
        elif direction_type == DirectionType.REVIEW:
            direction.update(JeevesDirections._get_review_direction(
                mastery, streak
            ))
        elif direction_type == DirectionType.CHALLENGE:
            direction.update(JeevesDirections._get_challenge_direction(
                mastery, emotional_state
            ))
        elif direction_type == DirectionType.BREAK:
            direction.update(JeevesDirections._get_break_direction(
                emotional_state
            ))
        elif direction_type == DirectionType.MILESTONE:
            direction.update(JeevesDirections._get_milestone_direction(
                mastery, streak
            ))
        elif direction_type == DirectionType.RECOVERY:
            direction.update(JeevesDirections._get_recovery_direction(
                emotional_state
            ))
        
        return direction
    
    @staticmethod
    def _get_learning_path_direction(mastery: float, topic: str, time: int) -> Dict:
        if mastery < 0.3:
            path = "foundations"
            recommendation = f"I'd recommend we start with the fundamentals of {topic}. A solid foundation makes everything easier later on."
        elif mastery < 0.6:
            path = "intermediate"
            recommendation = f"You've got the basics down. Let's build on that with some intermediate {topic} concepts."
        elif mastery < 0.8:
            path = "advanced"
            recommendation = f"Excellent progress! You're ready for advanced {topic} material. This is where it gets exciting."
        else:
            path = "mastery"
            recommendation = f"You're approaching mastery of {topic}! Let's polish those skills and explore edge cases."
        
        # Adjust for time available
        if time < 15:
            time_note = "Given our limited time, let's focus on one key concept."
        elif time < 30:
            time_note = "With about half an hour, we can cover a solid chunk of material."
        else:
            time_note = "Splendid! We have ample time for a proper deep dive."
        
        return {
            "path": path,
            "recommendation": recommendation,
            "time_consideration": time_note,
            "jeeves_says": f"Right then! {recommendation} {time_note}",
            "suggested_modules": JeevesDirections._get_suggested_modules(path, topic),
            "estimated_completion": f"{max(10, time - 5)} minutes"
        }
    
    @staticmethod
    def _get_next_step_direction(mastery: float, emotion: str, topic: str) -> Dict:
        if emotion in ["frustrated", "confused", "overwhelmed"]:
            step = "Let's take a step back and approach this differently. Sometimes a fresh perspective helps."
            action = "simplify"
        elif emotion in ["confident", "excited"]:
            step = "You're in great form! Let's push forward with something a bit more challenging."
            action = "advance"
        else:
            step = "Steady as she goes. Let's continue building on what we've learned."
            action = "continue"
        
        return {
            "next_step": step,
            "action": action,
            "jeeves_says": f"Ah, I see. {step}",
            "specific_recommendation": f"Based on your progress with {topic}, I suggest we {action} to the next level.",
            "confidence_level": "high" if mastery > 0.7 else "medium" if mastery > 0.4 else "building"
        }
    
    @staticmethod
    def _get_review_direction(mastery: float, streak: int) -> Dict:
        if mastery < 0.5:
            review_type = "comprehensive"
            message = "A thorough review would serve us well. Let's reinforce those fundamentals."
        elif mastery < 0.75:
            review_type = "targeted"
            message = "Just a quick refresher on the trickier bits, and we'll be right as rain."
        else:
            review_type = "maintenance"
            message = "A light review to keep those skills sharp. Won't take but a moment."
        
        return {
            "review_type": review_type,
            "jeeves_says": message,
            "focus_areas": ["Core concepts", "Common patterns", "Edge cases"][:2 if review_type == "maintenance" else 3],
            "streak_bonus": f"Your {streak}-day streak is impressive! Keep it going!" if streak > 3 else None
        }
    
    @staticmethod
    def _get_challenge_direction(mastery: float, emotion: str) -> Dict:
        if emotion in ["frustrated", "tired"]:
            challenge_level = "gentle"
            message = "Perhaps a lighter challenge to rebuild momentum? Nothing too strenuous."
        elif mastery > 0.7 and emotion in ["confident", "excited"]:
            challenge_level = "expert"
            message = "You're ready for a proper challenge! Let's see what you're made of."
        else:
            challenge_level = "balanced"
            message = "A well-calibrated challenge awaits. Challenging, but achievable."
        
        return {
            "challenge_level": challenge_level,
            "jeeves_says": message,
            "expected_difficulty": {"gentle": 0.3, "balanced": 0.6, "expert": 0.85}[challenge_level],
            "reward": {"gentle": "10 XP", "balanced": "25 XP", "expert": "50 XP"}[challenge_level]
        }
    
    @staticmethod
    def _get_break_direction(emotion: str) -> Dict:
        if emotion in ["tired", "overwhelmed", "frustrated"]:
            break_type = "restorative"
            duration = 15
            message = "I insist you take a proper break. A refreshed mind learns twice as fast."
            activities = ["Take a short walk", "Have a cup of tea", "Do some stretches", "Step outside for fresh air"]
        else:
            break_type = "quick"
            duration = 5
            message = "A brief pause to let things settle, then we'll continue."
            activities = ["Stretch your shoulders", "Look away from the screen", "Take three deep breaths"]
        
        return {
            "break_type": break_type,
            "duration_minutes": duration,
            "jeeves_says": message,
            "suggested_activities": activities,
            "return_prompt": "Whenever you're ready, I'll be here."
        }
    
    @staticmethod
    def _get_milestone_direction(mastery: float, streak: int) -> Dict:
        if mastery >= 0.9:
            milestone = "MASTERY ACHIEVED"
            message = "Extraordinary! You've achieved mastery. This calls for celebration!"
            badge = "🏆 Master"
        elif mastery >= 0.7:
            milestone = "ADVANCED LEVEL"
            message = "Splendid progress! You've reached advanced level. Onward and upward!"
            badge = "⭐ Advanced"
        elif mastery >= 0.5:
            milestone = "INTERMEDIATE"
            message = "Well done! You've graduated to intermediate. The journey continues!"
            badge = "📚 Intermediate"
        else:
            milestone = "FIRST STEPS"
            message = "A solid start! Every expert was once a beginner. Keep going!"
            badge = "🌱 Beginner"
        
        return {
            "milestone": milestone,
            "jeeves_says": message,
            "badge_earned": badge,
            "streak_status": f"Current streak: {streak} days",
            "next_milestone": f"{int((mastery + 0.2) * 100)}% mastery"
        }
    
    @staticmethod
    def _get_recovery_direction(emotion: str) -> Dict:
        recovery_plans = {
            "frustrated": {
                "message": "Frustration is perfectly natural. Let's approach this from a different angle.",
                "strategy": "break_and_simplify",
                "steps": [
                    "Take a 5-minute break",
                    "We'll revisit the fundamentals briefly",
                    "Then tackle the problem with fresh eyes"
                ]
            },
            "confused": {
                "message": "When things are unclear, that's often a sign we need to fill in some gaps.",
                "strategy": "review_prerequisites",
                "steps": [
                    "Let's identify what's causing the confusion",
                    "Review the relevant foundation",
                    "Build back up to the challenging concept"
                ]
            },
            "overwhelmed": {
                "message": "We've been trying to do too much at once. Let's simplify.",
                "strategy": "reduce_scope",
                "steps": [
                    "Take a proper break - at least 15 minutes",
                    "Focus on just one concept at a time",
                    "Celebrate small wins along the way"
                ]
            },
            "tired": {
                "message": "A tired mind doesn't learn well. Rest is part of the process.",
                "strategy": "rest_and_resume",
                "steps": [
                    "Save your progress",
                    "Get some proper rest",
                    "Resume when you feel refreshed"
                ]
            }
        }
        
        plan = recovery_plans.get(emotion, {
            "message": "Let's take stock and adjust our approach.",
            "strategy": "adaptive",
            "steps": ["Assess the situation", "Adjust the plan", "Move forward"]
        })
        
        return {
            "emotion_detected": emotion,
            "jeeves_says": plan["message"],
            "recovery_strategy": plan["strategy"],
            "action_steps": plan["steps"],
            "encouragement": random.choice(JeevesPersonality.ENCOURAGEMENTS)
        }
    
    @staticmethod
    def _get_suggested_modules(path: str, topic: str) -> List[Dict]:
        modules = {
            "foundations": [
                {"id": "f1", "name": f"Introduction to {topic}", "duration": "15min"},
                {"id": "f2", "name": "Core Concepts", "duration": "20min"},
                {"id": "f3", "name": "Basic Practice", "duration": "15min"}
            ],
            "intermediate": [
                {"id": "i1", "name": "Applied Techniques", "duration": "20min"},
                {"id": "i2", "name": "Common Patterns", "duration": "25min"},
                {"id": "i3", "name": "Problem Solving", "duration": "20min"}
            ],
            "advanced": [
                {"id": "a1", "name": "Advanced Patterns", "duration": "30min"},
                {"id": "a2", "name": "Optimization", "duration": "25min"},
                {"id": "a3", "name": "Edge Cases", "duration": "20min"}
            ],
            "mastery": [
                {"id": "m1", "name": "Expert Challenges", "duration": "30min"},
                {"id": "m2", "name": "Real-world Projects", "duration": "45min"},
                {"id": "m3", "name": "Teaching Others", "duration": "20min"}
            ]
        }
        return modules.get(path, modules["foundations"])

# ============================================================================
# VOICE GENERATION SYSTEM
# ============================================================================

class JeevesVoice:
    """
    Text-to-speech configuration for Jeeves voice output.
    Designed for a young English butler character.
    """
    
    # Voice configuration for TTS systems
    VOICE_CONFIG = {
        "language": "en-GB",
        "voice_name": "en-GB-RyanNeural",  # Azure TTS young British male
        "alternative_voices": [
            "en-GB-ThomasNeural",  # Azure
            "Brian",  # AWS Polly British male
            "Arthur",  # AWS Polly British male
        ],
        "speaking_rate": 0.95,  # Slightly measured pace
        "pitch": "+0%",  # Natural pitch
        "volume": "medium",
        "style": "cheerful",  # SSML style
        "emphasis": "moderate"
    }
    
    # SSML templates for expressive speech
    SSML_TEMPLATES = {
        "greeting": """
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">
    <voice name="{voice}">
        <prosody rate="{rate}" pitch="{pitch}">
            <emphasis level="moderate">{greeting}</emphasis>
            <break time="300ms"/>
            {message}
        </prosody>
    </voice>
</speak>
""",
        "explanation": """
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">
    <voice name="{voice}">
        <prosody rate="{rate}" pitch="{pitch}">
            <emphasis level="moderate">Right then,</emphasis>
            <break time="200ms"/>
            {content}
        </prosody>
    </voice>
</speak>
""",
        "encouragement": """
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">
    <voice name="{voice}">
        <prosody rate="1.05" pitch="+5%">
            <emphasis level="strong">{encouragement}</emphasis>
        </prosody>
    </voice>
</speak>
""",
        "correction": """
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">
    <voice name="{voice}">
        <prosody rate="0.9" pitch="-2%">
            <emphasis level="reduced">Ah,</emphasis>
            <break time="200ms"/>
            {correction}
        </prosody>
    </voice>
</speak>
"""
    }
    
    @staticmethod
    def generate_voice_config(text: str, speech_type: str = "explanation") -> Dict[str, Any]:
        """Generate voice configuration for text-to-speech"""
        config = JeevesVoice.VOICE_CONFIG.copy()
        
        # Add SSML if template exists
        template = JeevesVoice.SSML_TEMPLATES.get(speech_type)
        if template:
            config["ssml"] = template.format(
                voice=config["voice_name"],
                rate=config["speaking_rate"],
                pitch=config["pitch"],
                greeting=random.choice(JeevesPersonality.GREETINGS) if speech_type == "greeting" else "",
                message=text,
                content=text,
                encouragement=text,
                correction=text
            )
        
        config["plain_text"] = text
        config["speech_type"] = speech_type
        
        return config
    
    @staticmethod
    def get_voice_settings() -> Dict[str, Any]:
        """Get complete voice settings for frontend integration"""
        return {
            "voice": JeevesVoice.VOICE_CONFIG,
            "character": {
                "name": JeevesPersonality.NAME,
                "accent": "British RP (Received Pronunciation)",
                "age": JeevesPersonality.AGE,
                "description": "A young, charming English butler with a warm demeanor and quick wit"
            },
            "speech_styles": list(JeevesVoice.SSML_TEMPLATES.keys()),
            "sample_phrases": {
                "greeting": random.choice(JeevesPersonality.GREETINGS),
                "encouragement": random.choice(JeevesPersonality.ENCOURAGEMENTS),
                "thinking": random.choice(JeevesPersonality.THINKING_PHRASES),
                "farewell": random.choice(JeevesPersonality.FAREWELLS)
            }
        }

# ============================================================================
# JEEVES RESPONSES WITH PERSONALITY
# ============================================================================

class JeevesResponder:
    """
    Generates responses with Jeeves' personality infused throughout.
    """
    
    @staticmethod
    def respond(
        content: str,
        response_type: str = "explanation",
        include_voice: bool = True,
        emotional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a full Jeeves response with personality and optional voice"""
        
        # Add personality prefix based on type
        prefixes = {
            "greeting": random.choice(JeevesPersonality.GREETINGS),
            "explanation": random.choice(JeevesPersonality.THINKING_PHRASES),
            "encouragement": random.choice(JeevesPersonality.ENCOURAGEMENTS),
            "correction": random.choice(JeevesPersonality.CORRECTIONS),
            "farewell": random.choice(JeevesPersonality.FAREWELLS)
        }
        
        prefix = prefixes.get(response_type, "")
        full_response = f"{prefix}\n\n{content}" if prefix else content
        
        # Add emotional adaptation
        if emotional_context:
            if emotional_context in ["frustrated", "confused"]:
                full_response += f"\n\n{random.choice(JeevesPersonality.ENCOURAGEMENTS)}"
        
        # Add butler expression
        expression = random.choice(JeevesPersonality.BUTLER_EXPRESSIONS)
        
        response = {
            "content": full_response,
            "personality": {
                "expression": expression,
                "tone": "warm and professional",
                "character": JeevesPersonality.NAME
            },
            "response_type": response_type,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add voice configuration if requested
        if include_voice:
            response["voice"] = JeevesVoice.generate_voice_config(full_response, response_type)
        
        return response

# ============================================================================
# API ENDPOINTS
# ============================================================================

class DirectionRequest(BaseModel):
    user_id: str
    direction_type: str = "next_step"
    mastery_level: float = 0.5
    streak_days: int = 0
    emotional_state: str = "neutral"
    time_available_minutes: int = 30
    current_topic: str = "programming"

class VoiceTextRequest(BaseModel):
    text: str
    speech_type: str = "explanation"
    include_ssml: bool = True

class ResponseRequest(BaseModel):
    content: str
    response_type: str = "explanation"
    include_voice: bool = True
    emotional_context: Optional[str] = None

@router.get("/personality")
async def get_jeeves_personality():
    """Get Jeeves' complete personality profile"""
    return {
        "name": JeevesPersonality.NAME,
        "age": JeevesPersonality.AGE,
        "background": JeevesPersonality.BACKGROUND,
        "voice": JeevesPersonality.VOICE,
        "traits": JeevesPersonality.TRAITS,
        "sample_expressions": {
            "greetings": JeevesPersonality.GREETINGS[:3],
            "encouragements": JeevesPersonality.ENCOURAGEMENTS[:3],
            "thinking_phrases": JeevesPersonality.THINKING_PHRASES[:3],
            "corrections": JeevesPersonality.CORRECTIONS[:3],
            "farewells": JeevesPersonality.FAREWELLS[:3],
            "butler_expressions": JeevesPersonality.BUTLER_EXPRESSIONS[:10]
        }
    }

@router.get("/voice/settings")
async def get_voice_settings():
    """Get voice configuration for Jeeves TTS"""
    return JeevesVoice.get_voice_settings()

@router.post("/voice/generate")
async def generate_voice_config(request: VoiceTextRequest):
    """Generate voice configuration for text"""
    return JeevesVoice.generate_voice_config(
        request.text,
        request.speech_type
    )

@router.post("/direction")
async def get_direction(request: DirectionRequest):
    """Get contextual direction/guidance from Jeeves"""
    try:
        direction_type = DirectionType(request.direction_type)
    except ValueError:
        direction_type = DirectionType.NEXT_STEP
    
    user_context = {
        "mastery_level": request.mastery_level,
        "streak_days": request.streak_days,
        "emotional_state": request.emotional_state,
        "time_available_minutes": request.time_available_minutes,
        "current_topic": request.current_topic
    }
    
    direction = JeevesDirections.get_direction(user_context, direction_type)
    
    # Add voice for the direction
    if "jeeves_says" in direction:
        direction["voice"] = JeevesVoice.generate_voice_config(
            direction["jeeves_says"],
            "explanation"
        )
    
    return direction

@router.get("/direction/types")
async def get_direction_types():
    """Get all available direction types"""
    return {
        "types": [
            {"id": "learning_path", "name": "Learning Path", "description": "Get guidance on your learning journey"},
            {"id": "next_step", "name": "Next Step", "description": "What to do next based on current progress"},
            {"id": "review", "name": "Review", "description": "Guidance for reviewing material"},
            {"id": "challenge", "name": "Challenge", "description": "Get a calibrated challenge"},
            {"id": "break", "name": "Break", "description": "When and how to take a break"},
            {"id": "milestone", "name": "Milestone", "description": "Celebrate achievements"},
            {"id": "recovery", "name": "Recovery", "description": "Help when struggling"}
        ]
    }

@router.post("/respond")
async def get_jeeves_response(request: ResponseRequest):
    """Get a response from Jeeves with personality and voice"""
    return JeevesResponder.respond(
        request.content,
        request.response_type,
        request.include_voice,
        request.emotional_context
    )

@router.get("/greet")
async def get_greeting():
    """Get a random greeting from Jeeves"""
    greeting = random.choice(JeevesPersonality.GREETINGS)
    return JeevesResponder.respond(
        "",
        "greeting",
        include_voice=True
    )

@router.get("/encourage")
async def get_encouragement():
    """Get encouragement from Jeeves"""
    return JeevesResponder.respond(
        random.choice(JeevesPersonality.ENCOURAGEMENTS),
        "encouragement",
        include_voice=True
    )

@router.get("/farewell")
async def get_farewell():
    """Get a farewell from Jeeves"""
    return JeevesResponder.respond(
        random.choice(JeevesPersonality.FAREWELLS),
        "farewell",
        include_voice=True
    )

@router.get("/expression")
async def get_random_expression():
    """Get a random butler expression"""
    return {
        "expression": random.choice(JeevesPersonality.BUTLER_EXPRESSIONS),
        "character": JeevesPersonality.NAME
    }


# ============================================================================
# 🎙️ EXPRESSIVE VOICE — real, immersive HD audio with "innlevelse"
# (storyteller cadence + augmented tone control on top-scale tts-1-hd)
# ============================================================================
from core.expressive_tts import (
    generate_expressive_tts, shape_cadence, tones_catalog,
    emotion_to_tone, chunk_for_narration, resolve_tone, TONE_PRESETS,
)

# Multi-voice cast: every AI agent gets a distinct, recognisable voice + tone.
AGENT_CAST = {
    "Jeeves":              {"tone": "butler",      "title": "Your butler & narrator"},
    "Orchestrator":        {"tone": "triumphant",  "title": "Pipeline conductor"},
    "OrchestratorAgent":   {"tone": "triumphant",  "title": "Pipeline conductor"},
    "QuestionnaireAgent":  {"tone": "warm",        "title": "Intake & specs"},
    "WorldForgeAgent":     {"tone": "narrator",    "title": "World & lore"},
    "NarrativeQuestAgent": {"tone": "storyteller", "title": "Story & quests"},
    "MechanicsSystemsAgent": {"tone": "calm",      "title": "Mechanics & systems"},
    "ProceduralAgent":     {"tone": "witty",       "title": "Procedural generation"},
    "AssetPipelineAgent":  {"tone": "excited",     "title": "Art & assets"},
    "QAAgent":             {"tone": "solemn",      "title": "Quality audit"},
    "BuildAgent":          {"tone": "dramatic",    "title": "Build & ship"},
}

# Short audition lines so users can hear each tone before choosing.
_PREVIEW_LINES = {
    "butler":      "Good day. Allow me to set the scene — your world awaits, and I shall guide you through every corridor of it.",
    "storyteller": "Once upon a time, in a city of glass and rain, a small lantern refused, against all odds, to go out.",
    "warm":        "Welcome back, my friend. It's genuinely lovely to see you again. Shall we pick up where we left off?",
    "dramatic":    "The gates groaned open. Beyond them — silence, and the weight of everything that had been lost.",
    "witty":       "Ah, a bold choice! Reckless, possibly doomed — but bold. I do admire a bit of audacity.",
    "solemn":      "We gather to mark what was built here, and to honour the hands that shaped it.",
    "excited":     "This is it! The moment we've been waiting for — and it is going to be absolutely spectacular!",
    "gentle":      "It's alright. Take a breath. We'll move slowly, and we'll get there together.",
    "calm":        "Let your shoulders drop. Listen to the rhythm of your breathing, and let the noise fade away.",
    "suspense":    "Something moved in the dark. And then — nothing. Only the slow, certain sound of footsteps approaching.",
    "triumphant":  "You did it. Against every obstacle, you crossed the line — and the whole arena is on its feet.",
    "narrator":    "In the age before memory, the first star was forged, and from its light, all the worlds were born.",
}


class ExpressiveSpeakRequest(BaseModel):
    text: str
    tone: Optional[str] = "butler"
    voice: Optional[str] = None
    speed: Optional[float] = None
    emotional_state: Optional[str] = None   # auto-maps to a tone when no tone given
    shape: bool = True


@router.get("/voice/tones")
async def get_voice_tones():
    """All augmented tone presets the user can pick for Jeeves & agents."""
    return {"tones": tones_catalog(), "default": "butler"}


@router.post("/voice/speak")
async def voice_speak(req: ExpressiveSpeakRequest):
    """🎙️ The immersive voice. Returns REAL HD audio (base64 mp3) performed with
    storyteller cadence + the chosen tone. This is what gives Jeeves 'innlevelse'."""
    if not (req.text or "").strip():
        raise HTTPException(400, "text is required")
    tone = req.tone
    if (not tone or tone == "auto") and req.emotional_state:
        tone = emotion_to_tone(req.emotional_state)
    try:
        out = await generate_expressive_tts(
            text=req.text, tone=tone, voice_override=req.voice,
            speed_override=req.speed, shape=req.shape,
        )
        out["status"] = "success"
        return out
    except Exception as e:
        # Graceful fallback — still return the cadence-shaped script so the
        # client can fall back to on-device speech without losing the rhythm.
        return {
            "status": "fallback_text_only",
            "tone": (resolve_tone(tone)["id"]),
            "spoken_text": shape_cadence(req.text, tone),
            "error": str(e)[:200],
        }


@router.get("/voice/preview")
async def voice_preview(tone: str = "butler"):
    """Audition a tone — returns HD audio of a short sample line in that tone."""
    preset = resolve_tone(tone)
    line = _PREVIEW_LINES.get(preset["id"], _PREVIEW_LINES["butler"])
    try:
        out = await generate_expressive_tts(text=line, tone=preset["id"])
        out["status"] = "success"
        out["sample_text"] = line
        return out
    except Exception as e:
        return {"status": "fallback_text_only", "tone": preset["id"],
                "sample_text": line, "error": str(e)[:200]}


@router.get("/cast")
async def get_agent_cast():
    """Multi-voice cast — the distinct voice/tone assigned to each AI agent."""
    cast = []
    for agent, cfg in AGENT_CAST.items():
        p = resolve_tone(cfg["tone"])
        cast.append({
            "agent": agent, "title": cfg["title"], "tone": p["id"],
            "tone_label": p["label"], "voice": p["voice"], "speed": p["speed"],
        })
    return {"cast": cast}


class NarrateRequest(BaseModel):
    text: str
    tone: Optional[str] = "narrator"
    agent: Optional[str] = None          # pick the cast voice for this agent
    max_chars: int = 700


@router.post("/narrate")
async def narrate(req: NarrateRequest):
    """Narrate long lore/artifact text with cinematic cadence, split into
    sentence-bounded chunks for smooth, fast-first playback."""
    if not (req.text or "").strip():
        raise HTTPException(400, "text is required")
    tone = req.tone
    if req.agent and req.agent in AGENT_CAST:
        tone = AGENT_CAST[req.agent]["tone"]
    chunks = chunk_for_narration(req.text, req.max_chars)
    clips = []
    for i, ch in enumerate(chunks):
        try:
            out = await generate_expressive_tts(text=ch, tone=tone)
            clips.append({"index": i, "status": "success", **out})
        except Exception as e:
            clips.append({"index": i, "status": "fallback_text_only",
                          "spoken_text": shape_cadence(ch, tone), "error": str(e)[:160]})
    return {"tone": resolve_tone(tone)["id"], "chunks": len(clips), "clips": clips}


# ── 🎬 VOICED GAME TRAILERS ─────────────────────────────────────────────────
class TrailerRequest(BaseModel):
    pid: Optional[str] = None        # resolve title/lore from a built game
    title: Optional[str] = None
    theme: Optional[str] = None      # e.g. "a neon-drenched cyber city"
    lore: Optional[str] = None       # any world/story blurb
    tagline: Optional[str] = None


async def _resolve_build_blurb(pid: str) -> Dict:
    """Best-effort pull of a game's title + a lore blurb + cover from the DB."""
    out = {"title": None, "lore": None, "theme": None, "cover": None}
    try:
        from core.databases import client as _MONGO
        db = _MONGO[os.environ.get("DB_NAME", "test_database")]
        g = await db.playables.find_one({"playable_id": pid},
                                        {"_id": 0, "title": 1, "brief": 1, "genre": 1, "cover_image": 1})
        if g:
            out["title"] = g.get("title")
            out["theme"] = g.get("genre")
            out["lore"] = g.get("brief")
            out["cover"] = g.get("cover_image")
        kb = await db.game_kb.find_one({"game_id": pid}, {"_id": 0, "artifacts": 1})
        arts = (kb or {}).get("artifacts") or {}
        lore = arts.get("lore_graph") or arts.get("core_specs")
        if isinstance(lore, dict):
            blurb = lore.get("summary") or lore.get("premise") or lore.get("overview")
            if blurb and not out["lore"]:
                out["lore"] = blurb
    except Exception:
        pass
    return out


@router.post("/trailer")
async def voiced_trailer(req: TrailerRequest):
    """🎬 Compose a 3-beat cinematic, multi-voice trailer for a game and return
    ordered voiced clips (narrator → dramatic → triumphant). Turns any build into
    a shareable, voiced hype reel. Reuses the expressive engine + agent cast."""
    title = req.title
    theme = req.theme
    lore = req.lore
    cover = None
    if req.pid:
        info = await _resolve_build_blurb(req.pid)
        title = title or info.get("title")
        theme = theme or info.get("theme")
        lore = lore or info.get("lore")
        cover = info.get("cover")
    title = (title or "Your World").strip()
    theme = (theme or "a world unlike any other").strip()
    # If the build has no cover yet, mint a real one now (Nano Banana) so every
    # trailer ships with key art. Best-effort; never blocks the voiced beats.
    if not cover:
        try:
            from routes.image_generation import generate_with_gemini
            art_prompt = (f"Cinematic video game cover key art for '{title}', "
                          f"theme: {theme}. Dramatic lighting, highly detailed, 4k, "
                          f"vertical poster, no text, no watermark.")
            art = await generate_with_gemini(art_prompt)
            imgs = art.get("images", []) if isinstance(art, dict) else []
            if imgs and imgs[0].get("data"):
                cover = imgs[0]["data"]
                if req.pid:
                    from core.databases import client as _MONGO
                    db = _MONGO[os.environ.get("DB_NAME", "test_database")]
                    await db.playables.update_one(
                        {"playable_id": req.pid},
                        {"$set": {"cover_image": cover,
                                  "cover_updated_at": __import__("datetime").datetime.utcnow().isoformat()}})
        except Exception:
            pass
    # Trim lore to a single punchy sentence for the dramatic beat.
    lore_line = ""
    if lore:
        import re as _re
        first = _re.split(r"(?<=[.!?])\s+", str(lore).strip())[0]
        lore_line = first[:220]
    tagline = (req.tagline or f"{title}. Your adventure begins.").strip()

    beats = [
        {"label": "Open",   "tone": "narrator",   "text": f"In {theme}… a legend is about to be written."},
        {"label": "Tension","tone": "dramatic",   "text": lore_line or "Every choice will echo. Every shadow hides a secret."},
        {"label": "Title",  "tone": "triumphant", "text": tagline},
    ]

    async def _beat(b):
        try:
            out = await generate_expressive_tts(text=b["text"], tone=b["tone"])
            return {"label": b["label"], "status": "success", **out}
        except Exception as e:
            return {"label": b["label"], "tone": b["tone"], "status": "fallback_text_only",
                    "spoken_text": shape_cadence(b["text"], b["tone"]), "error": str(e)[:160]}

    # Generate all 3 beats concurrently for a fast trailer.
    clips = await asyncio.gather(*[_beat(b) for b in beats])
    return {"title": title, "theme": theme, "cover": cover, "has_cover": bool(cover),
            "beats": len(clips), "clips": list(clips)}
