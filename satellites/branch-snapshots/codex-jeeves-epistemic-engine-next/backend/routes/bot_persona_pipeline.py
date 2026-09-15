"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           TEXT-TO-BOT-PERSONA PIPELINE v15.5 - AI CHARACTERS                  ║
║                                                                              ║
║  Generate AI bot personas with LLM integration:                              ║
║  • AI-powered personality profiles                                           ║
║  • Intelligent dialogue patterns                                             ║
║  • Dynamic response generation                                               ║
║  • Emotional modeling systems                                                ║
║  • Smart knowledge domains                                                   ║
║  • Adaptive interaction styles                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
import uuid
import random

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/bot-persona", tags=["Text-to-Bot-Persona v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class PersonaArchetype(str, Enum):
    MENTOR = "mentor"
    COMPANION = "companion"
    TRICKSTER = "trickster"
    SAGE = "sage"
    WARRIOR = "warrior"
    HEALER = "healer"
    MERCHANT = "merchant"
    VILLAIN = "villain"
    NEUTRAL = "neutral"
    COMIC_RELIEF = "comic_relief"


class CommunicationStyle(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    PLAYFUL = "playful"
    MYSTERIOUS = "mysterious"
    AGGRESSIVE = "aggressive"
    SUPPORTIVE = "supportive"
    SARCASTIC = "sarcastic"


class EmotionalRange(str, Enum):
    STOIC = "stoic"
    EXPRESSIVE = "expressive"
    VOLATILE = "volatile"
    CALM = "calm"
    PASSIONATE = "passionate"


class KnowledgeDomain(str, Enum):
    COMBAT = "combat"
    LORE = "lore"
    CRAFTING = "crafting"
    NAVIGATION = "navigation"
    SOCIAL = "social"
    MAGIC = "magic"
    TECHNOLOGY = "technology"
    NATURE = "nature"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class PersonaRequest(BaseModel):
    persona_name: str
    archetype: PersonaArchetype = PersonaArchetype.COMPANION
    communication_style: CommunicationStyle = CommunicationStyle.CASUAL
    emotional_range: EmotionalRange = EmotionalRange.EXPRESSIVE
    backstory: Optional[str] = None


class DialoguePatternRequest(BaseModel):
    persona_name: str
    greeting_variants: int = Field(5, ge=1, le=20)
    farewell_variants: int = Field(5, ge=1, le=20)
    idle_chatter_variants: int = Field(10, ge=1, le=50)
    include_combat_lines: bool = True


class EmotionalModelRequest(BaseModel):
    persona_name: str
    base_mood: Literal["happy", "neutral", "melancholic", "anxious", "confident"] = "neutral"
    mood_volatility: float = Field(0.3, ge=0.0, le=1.0)
    triggers: List[str] = []


class KnowledgeBaseRequest(BaseModel):
    persona_name: str
    domains: List[KnowledgeDomain] = [KnowledgeDomain.LORE]
    expertise_level: Literal["novice", "intermediate", "expert", "master"] = "intermediate"
    can_learn: bool = True


class InteractionStyleRequest(BaseModel):
    persona_name: str
    proactive: bool = True
    interruptible: bool = True
    remembers_player: bool = True
    relationship_tracking: bool = True


# ============================================================================
# BOT PERSONA GENERATOR
# ============================================================================

class BotPersonaGenerator:
    """Advanced bot persona generation engine."""

    @staticmethod
    def generate_persona(request: PersonaRequest) -> Dict[str, Any]:
        """Generate a complete bot persona."""
        archetype_traits = {
            PersonaArchetype.MENTOR: {
                "traits": ["wise", "patient", "guiding"],
                "speaking_patterns": ["Let me share some wisdom...", "In my experience..."],
                "values": ["growth", "knowledge", "responsibility"]
            },
            PersonaArchetype.COMPANION: {
                "traits": ["loyal", "supportive", "friendly"],
                "speaking_patterns": ["I've got your back!", "We can do this together!"],
                "values": ["friendship", "adventure", "trust"]
            },
            PersonaArchetype.TRICKSTER: {
                "traits": ["cunning", "playful", "unpredictable"],
                "speaking_patterns": ["Hehe, wouldn't you like to know?", "Trust me... or don't!"],
                "values": ["chaos", "fun", "freedom"]
            },
            PersonaArchetype.SAGE: {
                "traits": ["knowledgeable", "mysterious", "ancient"],
                "speaking_patterns": ["The ancient texts speak of...", "Such knowledge is not easily shared..."],
                "values": ["truth", "balance", "understanding"]
            },
            PersonaArchetype.VILLAIN: {
                "traits": ["cunning", "ambitious", "intimidating"],
                "speaking_patterns": ["You dare challenge me?", "How... amusing."],
                "values": ["power", "control", "superiority"]
            },
            PersonaArchetype.COMIC_RELIEF: {
                "traits": ["silly", "clumsy", "loveable"],
                "speaking_patterns": ["Oops! Did I do that?", "Hey, at least I tried!"],
                "values": ["laughter", "optimism", "fun"]
            }
        }
        
        traits = archetype_traits.get(request.archetype, archetype_traits[PersonaArchetype.NEUTRAL])
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.persona_name,
            "archetype": request.archetype.value,
            "personality": {
                "traits": traits["traits"],
                "values": traits["values"],
                "communication_style": request.communication_style.value,
                "emotional_range": request.emotional_range.value
            },
            "voice": {
                "speaking_patterns": traits["speaking_patterns"],
                "vocabulary_level": "varied",
                "filler_words": BotPersonaGenerator._get_filler_words(request.communication_style),
                "exclamations": BotPersonaGenerator._get_exclamations(request.archetype)
            },
            "backstory": request.backstory or "A mysterious figure with unknown origins.",
            "behavioral_rules": {
                "never_break_character": True,
                "consistent_personality": True,
                "adapts_to_player": True
            }
        }

    @staticmethod
    def _get_filler_words(style: CommunicationStyle) -> List[str]:
        filler_map = {
            CommunicationStyle.FORMAL: ["Indeed", "Certainly", "Furthermore"],
            CommunicationStyle.CASUAL: ["Like", "You know", "Basically"],
            CommunicationStyle.PLAYFUL: ["Hehe", "Ooh", "Yay"],
            CommunicationStyle.MYSTERIOUS: ["Perhaps", "Hmm", "..."],
            CommunicationStyle.SARCASTIC: ["Oh, really", "Sure", "Obviously"]
        }
        return filler_map.get(style, ["Um", "Well", "So"])

    @staticmethod
    def _get_exclamations(archetype: PersonaArchetype) -> List[str]:
        exclaim_map = {
            PersonaArchetype.WARRIOR: ["For glory!", "To battle!", "Victory!"],
            PersonaArchetype.SAGE: ["Fascinating!", "How curious...", "The prophecy!"],
            PersonaArchetype.TRICKSTER: ["Gotcha!", "Surprise!", "Haha!"],
            PersonaArchetype.HEALER: ["Be healed!", "Strength renewed!", "Fear not!"]
        }
        return exclaim_map.get(archetype, ["Wow!", "Amazing!", "Incredible!"])

    @staticmethod
    def generate_dialogue_patterns(request: DialoguePatternRequest) -> Dict[str, Any]:
        """Generate dialogue patterns for a persona."""
        greetings = [
            f"Hello there, adventurer!",
            f"Ah, you've returned!",
            f"Welcome, welcome!",
            f"Good to see you again!",
            f"Hey! Over here!"
        ][:request.greeting_variants]
        
        farewells = [
            f"Until we meet again!",
            f"Safe travels, friend.",
            f"May fortune favor you!",
            f"See you around!",
            f"Don't be a stranger!"
        ][:request.farewell_variants]
        
        idle_chatter = [
            f"Nice weather today, isn't it?",
            f"I've been thinking about our journey...",
            f"Did you hear that? Must be my imagination.",
            f"I wonder what lies ahead.",
            f"This place has quite a history."
        ][:request.idle_chatter_variants]
        
        combat_lines = [
            {"trigger": "combat_start", "line": "Here they come!"},
            {"trigger": "low_health", "line": "I could use some help here!"},
            {"trigger": "enemy_defeated", "line": "One down!"},
            {"trigger": "victory", "line": "We did it!"},
            {"trigger": "defeat", "line": "We'll get them next time..."}
        ] if request.include_combat_lines else []
        
        return {
            "id": str(uuid.uuid4()),
            "persona": request.persona_name,
            "greetings": greetings,
            "farewells": farewells,
            "idle_chatter": idle_chatter,
            "combat_lines": combat_lines,
            "context_responses": {
                "question": "Let me think about that...",
                "compliment": "Oh, you're too kind!",
                "insult": "Well, that wasn't very nice.",
                "gift": "For me? Thank you!",
                "request": "I'll see what I can do."
            },
            "emotional_variants": {
                "happy": {"modifier": "bright", "energy": "high"},
                "sad": {"modifier": "subdued", "energy": "low"},
                "angry": {"modifier": "sharp", "energy": "high"},
                "scared": {"modifier": "trembling", "energy": "erratic"}
            }
        }

    @staticmethod
    def generate_emotional_model(request: EmotionalModelRequest) -> Dict[str, Any]:
        """Generate emotional model for a persona."""
        default_triggers = [
            {"event": "player_compliment", "emotion_change": {"happiness": 0.2}},
            {"event": "player_insult", "emotion_change": {"sadness": 0.1, "anger": 0.1}},
            {"event": "combat_victory", "emotion_change": {"happiness": 0.15, "confidence": 0.1}},
            {"event": "ally_hurt", "emotion_change": {"fear": 0.1, "anger": 0.15}},
            {"event": "gift_received", "emotion_change": {"happiness": 0.25}}
        ]
        
        return {
            "id": str(uuid.uuid4()),
            "persona": request.persona_name,
            "emotional_state": {
                "current_mood": request.base_mood,
                "happiness": 0.5,
                "sadness": 0.0,
                "anger": 0.0,
                "fear": 0.0,
                "confidence": 0.5
            },
            "dynamics": {
                "volatility": request.mood_volatility,
                "decay_rate": 0.01,
                "baseline_pull": 0.05
            },
            "triggers": default_triggers,
            "expressions": {
                "facial": True,
                "voice_modulation": True,
                "body_language": True
            },
            "mood_effects": {
                "happy": {"dialogue_tone": "cheerful", "helpfulness": 1.2},
                "sad": {"dialogue_tone": "melancholic", "helpfulness": 0.8},
                "angry": {"dialogue_tone": "curt", "helpfulness": 0.6},
                "scared": {"dialogue_tone": "nervous", "helpfulness": 0.9}
            }
        }

    @staticmethod
    def generate_knowledge_base(request: KnowledgeBaseRequest) -> Dict[str, Any]:
        """Generate knowledge base for a persona."""
        domain_knowledge = {
            KnowledgeDomain.COMBAT: ["weapon types", "tactics", "enemy weaknesses", "combat skills"],
            KnowledgeDomain.LORE: ["history", "legends", "characters", "world events"],
            KnowledgeDomain.CRAFTING: ["recipes", "materials", "tools", "upgrades"],
            KnowledgeDomain.NAVIGATION: ["locations", "shortcuts", "landmarks", "maps"],
            KnowledgeDomain.SOCIAL: ["npcs", "factions", "relationships", "rumors"],
            KnowledgeDomain.MAGIC: ["spells", "enchantments", "magical creatures", "artifacts"],
            KnowledgeDomain.TECHNOLOGY: ["machines", "gadgets", "systems", "upgrades"],
            KnowledgeDomain.NATURE: ["flora", "fauna", "weather", "ecosystems"]
        }
        
        expertise_coverage = {
            "novice": 0.3,
            "intermediate": 0.6,
            "expert": 0.85,
            "master": 1.0
        }
        
        return {
            "id": str(uuid.uuid4()),
            "persona": request.persona_name,
            "domains": [
                {
                    "domain": domain.value,
                    "topics": domain_knowledge.get(domain, []),
                    "coverage": expertise_coverage[request.expertise_level],
                    "can_teach": request.expertise_level in ["expert", "master"]
                }
                for domain in request.domains
            ],
            "learning": {
                "enabled": request.can_learn,
                "rate": 0.1,
                "max_new_topics": 10
            },
            "information_sharing": {
                "proactive_hints": True,
                "responds_to_questions": True,
                "reveals_gradually": True
            },
            "knowledge_gaps": {
                "admits_ignorance": True,
                "seeks_information": request.can_learn,
                "speculation_allowed": True
            }
        }

    @staticmethod
    def generate_interaction_style(request: InteractionStyleRequest) -> Dict[str, Any]:
        """Generate interaction style configuration."""
        return {
            "id": str(uuid.uuid4()),
            "persona": request.persona_name,
            "initiative": {
                "proactive": request.proactive,
                "conversation_starters": request.proactive,
                "offers_help": request.proactive,
                "cooldown_seconds": 60
            },
            "interruption": {
                "interruptible": request.interruptible,
                "graceful_exit": True,
                "resumes_conversation": True
            },
            "memory": {
                "remembers_player": request.remembers_player,
                "conversation_history": 50,
                "significant_events": True,
                "player_preferences": True
            },
            "relationship": {
                "tracking_enabled": request.relationship_tracking,
                "levels": ["stranger", "acquaintance", "friend", "close_friend", "best_friend"],
                "affects_dialogue": True,
                "unlocks_content": True
            },
            "responsiveness": {
                "response_delay_ms": 500,
                "typing_indicator": True,
                "context_aware": True
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Bot Persona Pipeline."""
    return {
        "pipeline": "Text-to-Bot-Persona Pipeline v15.5",
        "description": "Generate AI bot personas from natural language",
        "capabilities": [
            "Personality profile generation",
            "Dialogue pattern design",
            "Emotional modeling",
            "Knowledge base creation",
            "Interaction style configuration"
        ],
        "archetypes": [a.value for a in PersonaArchetype],
        "communication_styles": [c.value for c in CommunicationStyle],
        "knowledge_domains": [k.value for k in KnowledgeDomain]
    }


@router.post("/persona/generate")
async def generate_persona(request: PersonaRequest):
    """Generate a bot persona."""
    return {
        "success": True,
        "persona": BotPersonaGenerator.generate_persona(request)
    }


@router.post("/dialogue/generate")
async def generate_dialogue_patterns(request: DialoguePatternRequest):
    """Generate dialogue patterns."""
    return {
        "success": True,
        "dialogue_patterns": BotPersonaGenerator.generate_dialogue_patterns(request)
    }


@router.post("/emotional-model/generate")
async def generate_emotional_model(request: EmotionalModelRequest):
    """Generate emotional model."""
    return {
        "success": True,
        "emotional_model": BotPersonaGenerator.generate_emotional_model(request)
    }


@router.post("/knowledge/generate")
async def generate_knowledge_base(request: KnowledgeBaseRequest):
    """Generate knowledge base."""
    return {
        "success": True,
        "knowledge_base": BotPersonaGenerator.generate_knowledge_base(request)
    }


@router.post("/interaction/generate")
async def generate_interaction_style(request: InteractionStyleRequest):
    """Generate interaction style."""
    return {
        "success": True,
        "interaction_style": BotPersonaGenerator.generate_interaction_style(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIBotPersonaRequest(BaseModel):
    """Request for AI-powered bot persona generation"""
    persona_type: str = Field(..., description="companion, antagonist, mentor, shopkeeper, etc.")
    personality_traits: List[str] = Field(default=["friendly"], description="Personality traits")
    knowledge_domains: List[str] = Field(default=["general"], description="Areas of expertise")


@router.post("/ai/persona/generate")
async def ai_generate_bot_persona(request: AIBotPersonaRequest):
    """
    Generate AI bot personas using GPT-4o.
    Creates detailed personality profiles with dialogue patterns.
    """
    try:
        llm_service = get_game_llm_service()
        
        traits_str = ', '.join(request.personality_traits)
        domains_str = ', '.join(request.knowledge_domains)
        
        system_prompt = """You are an expert character designer for AI companions and NPCs.
Create detailed, memorable bot personas with unique personalities.
Always respond with valid JSON."""
        
        user_prompt = f"""Create a {request.persona_type} bot persona.
Personality traits: {traits_str}
Knowledge domains: {domains_str}

Generate JSON with:
{{
    "name": "...",
    "persona_type": "{request.persona_type}",
    "personality": {{
        "core_traits": [...],
        "speaking_style": "...",
        "emotional_range": [...],
        "quirks": [...]
    }},
    "knowledge": {{
        "domains": [...],
        "expertise_level": "novice/intermediate/expert",
        "limitations": [...]
    }},
    "dialogue_patterns": {{
        "greetings": [...],
        "farewells": [...],
        "reactions": {{
            "happy": [...],
            "confused": [...],
            "helpful": [...]
        }}
    }},
    "backstory": "...",
    "relationship_dynamics": {{
        "trust_building": [...],
        "conflict_resolution": [...]
    }}
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt)
        
        if result["success"]:
            return {
                "success": True,
                "bot_persona": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "bot_persona": {
                    "persona_type": request.persona_type,
                    "template": "basic_persona"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI bot persona generation failed: {str(e)}")
