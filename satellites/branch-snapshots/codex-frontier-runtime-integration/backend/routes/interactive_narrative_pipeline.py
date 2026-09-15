"""
╔══════════════════════════════════════════════════════════════════════════════╗
║       TEXT-TO-INTERACTIVE-NARRATIVE PIPELINE v15.5 - AI STORYTELLING         ║
║                                                                              ║
║  Generate interactive narratives with LLM integration:                       ║
║  • AI-powered branching storylines                                           ║
║  • Intelligent dialogue systems                                              ║
║  • Dynamic character arcs                                                    ║
║  • AI-generated plot developments                                            ║
║  • Smart consequence systems                                                 ║
║  • World-reactive narratives                                                 ║
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

router = APIRouter(prefix="/api/interactive-narrative", tags=["Text-to-Interactive-Narrative v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class NarrativeStructure(str, Enum):
    LINEAR = "linear"
    BRANCHING = "branching"
    OPEN_WORLD = "open_world"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    EMERGENT = "emergent"


class PlotArchetype(str, Enum):
    HEROS_JOURNEY = "heros_journey"
    RAGS_TO_RICHES = "rags_to_riches"
    OVERCOMING_MONSTER = "overcoming_monster"
    VOYAGE_RETURN = "voyage_and_return"
    COMEDY = "comedy"
    TRAGEDY = "tragedy"
    REBIRTH = "rebirth"
    MYSTERY = "mystery"


class DialogueStyle(str, Enum):
    CINEMATIC = "cinematic"
    RPG_CLASSIC = "rpg_classic"
    VISUAL_NOVEL = "visual_novel"
    WHEEL = "wheel"
    KEYWORD = "keyword"
    NATURAL = "natural"


class ConsequenceScope(str, Enum):
    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    PERMANENT = "permanent"
    WORLD_CHANGING = "world_changing"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class StorylineRequest(BaseModel):
    title: str
    genre: str
    structure: NarrativeStructure = NarrativeStructure.BRANCHING
    archetype: PlotArchetype = PlotArchetype.HEROS_JOURNEY
    num_acts: int = Field(3, ge=1, le=7)
    branching_factor: int = Field(3, ge=1, le=10)


class DialogueSystemRequest(BaseModel):
    style: DialogueStyle = DialogueStyle.CINEMATIC
    max_options: int = Field(4, ge=2, le=8)
    skill_checks: bool = True
    relationship_modifiers: bool = True
    voice_acted: bool = False


class CharacterArcRequest(BaseModel):
    character_name: str
    starting_trait: str
    ending_trait: str
    arc_type: Literal["positive", "negative", "flat", "corrupted"] = "positive"
    num_beats: int = Field(5, ge=3, le=12)


class ConsequenceSystemRequest(BaseModel):
    system_name: str
    scopes: List[ConsequenceScope] = [ConsequenceScope.IMMEDIATE, ConsequenceScope.LONG_TERM]
    track_morality: bool = True
    butterfly_effect: bool = True


class QuestGeneratorRequest(BaseModel):
    quest_type: Literal["main", "side", "companion", "faction", "random"]
    complexity: Literal["simple", "moderate", "complex"] = "moderate"
    narrative_weight: float = Field(0.5, ge=0.0, le=1.0)


# ============================================================================
# NARRATIVE GENERATOR
# ============================================================================

class NarrativeGenerator:
    """Advanced interactive narrative generation engine."""

    @staticmethod
    def generate_storyline(request: StorylineRequest) -> Dict[str, Any]:
        """Generate a complete storyline structure."""
        archetype_beats = {
            PlotArchetype.HEROS_JOURNEY: [
                "ordinary_world", "call_to_adventure", "refusal_of_call",
                "meeting_mentor", "crossing_threshold", "tests_allies_enemies",
                "approach_cave", "ordeal", "reward", "road_back",
                "resurrection", "return_elixir"
            ],
            PlotArchetype.OVERCOMING_MONSTER: [
                "anticipation", "dream", "frustration", "nightmare", "thrilling_escape"
            ],
            PlotArchetype.MYSTERY: [
                "crime", "investigation", "red_herrings", "revelation", "resolution"
            ]
        }
        
        beats = archetype_beats.get(request.archetype, ["setup", "confrontation", "resolution"])
        
        acts = []
        beats_per_act = len(beats) // request.num_acts
        
        for i in range(request.num_acts):
            act_beats = beats[i * beats_per_act:(i + 1) * beats_per_act]
            acts.append({
                "act_number": i + 1,
                "name": f"Act {i + 1}",
                "beats": act_beats,
                "branches": [
                    {"id": str(uuid.uuid4())[:8], "condition": f"choice_{j}", "outcome": f"branch_{j}"}
                    for j in range(request.branching_factor)
                ] if request.structure == NarrativeStructure.BRANCHING else []
            })
        
        return {
            "id": str(uuid.uuid4()),
            "title": request.title,
            "genre": request.genre,
            "structure": request.structure.value,
            "archetype": request.archetype.value,
            "acts": acts,
            "total_beats": len(beats),
            "estimated_playtime_hours": len(beats) * 0.5,
            "endings": {
                "count": request.branching_factor ** request.num_acts if request.structure == NarrativeStructure.BRANCHING else 1,
                "types": ["good", "neutral", "bad", "secret"]
            }
        }

    @staticmethod
    def generate_dialogue_system(request: DialogueSystemRequest) -> Dict[str, Any]:
        """Generate a dialogue system configuration."""
        return {
            "id": str(uuid.uuid4()),
            "style": request.style.value,
            "config": {
                "max_options": request.max_options,
                "skill_checks": request.skill_checks,
                "relationship_modifiers": request.relationship_modifiers,
                "voice_acted": request.voice_acted
            },
            "node_types": [
                {"type": "dialogue", "icon": "speech"},
                {"type": "choice", "icon": "fork"},
                {"type": "skill_check", "icon": "dice"},
                {"type": "condition", "icon": "gate"},
                {"type": "consequence", "icon": "ripple"}
            ],
            "options_schema": {
                "text": "string",
                "tone": ["neutral", "friendly", "aggressive", "sarcastic", "romantic"],
                "skill_requirement": "optional<skill_check>",
                "relationship_change": "optional<int>",
                "leads_to": "node_id"
            },
            "sample_tree": NarrativeGenerator._generate_sample_dialogue_tree()
        }

    @staticmethod
    def _generate_sample_dialogue_tree() -> Dict[str, Any]:
        return {
            "root": {
                "id": "node_001",
                "speaker": "npc",
                "text": "Greetings, traveler. What brings you to our village?",
                "options": [
                    {"text": "I'm looking for work.", "tone": "neutral", "leads_to": "node_002"},
                    {"text": "None of your business.", "tone": "aggressive", "leads_to": "node_003"},
                    {"text": "[Persuade] I'm a famous hero!", "skill": "persuasion", "dc": 15, "leads_to": "node_004"}
                ]
            }
        }

    @staticmethod
    def generate_character_arc(request: CharacterArcRequest) -> Dict[str, Any]:
        """Generate a character arc with development beats."""
        arc_templates = {
            "positive": ["flaw", "catalyst", "struggle", "growth", "transformation"],
            "negative": ["strength", "temptation", "corruption", "fall", "destruction"],
            "flat": ["belief", "challenge", "test", "reaffirmation", "impact"],
            "corrupted": ["virtue", "exposure", "doubt", "compromise", "loss"]
        }
        
        template = arc_templates.get(request.arc_type, arc_templates["positive"])
        
        beats = []
        for i in range(request.num_beats):
            template_idx = i * len(template) // request.num_beats
            beats.append({
                "beat_number": i + 1,
                "type": template[template_idx] if template_idx < len(template) else "development",
                "description": f"Character experiences {template[template_idx] if template_idx < len(template) else 'development'}",
                "trait_progress": (i + 1) / request.num_beats
            })
        
        return {
            "id": str(uuid.uuid4()),
            "character": request.character_name,
            "arc_type": request.arc_type,
            "starting_trait": request.starting_trait,
            "ending_trait": request.ending_trait,
            "beats": beats,
            "key_moments": {
                "inciting_incident": beats[0] if beats else None,
                "midpoint_shift": beats[len(beats)//2] if beats else None,
                "climax": beats[-2] if len(beats) > 1 else None,
                "resolution": beats[-1] if beats else None
            }
        }

    @staticmethod
    def generate_consequence_system(request: ConsequenceSystemRequest) -> Dict[str, Any]:
        """Generate a consequence tracking system."""
        return {
            "id": str(uuid.uuid4()),
            "name": request.system_name,
            "scopes": [s.value for s in request.scopes],
            "tracking": {
                "morality": {
                    "enabled": request.track_morality,
                    "spectrum": ["paragon", "neutral", "renegade"],
                    "visible": True
                },
                "reputation": {
                    "factions": [],
                    "npcs": [],
                    "range": [-100, 100]
                },
                "world_state": {
                    "flags": [],
                    "counters": [],
                    "timers": []
                }
            },
            "butterfly_effect": {
                "enabled": request.butterfly_effect,
                "propagation_depth": 3,
                "visibility": "hidden"
            },
            "consequence_types": [
                {"type": "dialogue_change", "scope": "immediate"},
                {"type": "npc_attitude", "scope": "short_term"},
                {"type": "quest_availability", "scope": "long_term"},
                {"type": "ending_variation", "scope": "permanent"},
                {"type": "world_event", "scope": "world_changing"}
            ]
        }

    @staticmethod
    def generate_quest(request: QuestGeneratorRequest) -> Dict[str, Any]:
        """Generate a quest with narrative elements."""
        complexity_objectives = {
            "simple": 1,
            "moderate": 3,
            "complex": 5
        }
        
        quest_templates = {
            "main": ["save_world", "defeat_evil", "discover_truth"],
            "side": ["fetch", "escort", "investigate", "collect"],
            "companion": ["backstory", "loyalty", "romance"],
            "faction": ["reputation", "territory", "resources"],
            "random": ["bounty", "delivery", "exploration"]
        }
        
        return {
            "id": str(uuid.uuid4()),
            "type": request.quest_type,
            "template": random.choice(quest_templates.get(request.quest_type, ["generic"])),
            "objectives": [
                {"id": f"obj_{i}", "type": "objective", "optional": i > 0}
                for i in range(complexity_objectives[request.complexity])
            ],
            "narrative_integration": {
                "weight": request.narrative_weight,
                "affects_main_story": request.narrative_weight > 0.7,
                "character_development": request.quest_type == "companion"
            },
            "rewards": {
                "xp": 100 * complexity_objectives[request.complexity],
                "items": [],
                "reputation": {}
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Interactive Narrative Pipeline."""
    return {
        "pipeline": "Text-to-Interactive-Narrative Pipeline v15.5",
        "description": "Generate interactive narratives from natural language",
        "capabilities": [
            "Branching storyline generation",
            "Dialogue system configuration",
            "Character arc development",
            "Consequence tracking systems",
            "Dynamic quest generation"
        ],
        "structures": [s.value for s in NarrativeStructure],
        "archetypes": [a.value for a in PlotArchetype],
        "dialogue_styles": [d.value for d in DialogueStyle]
    }


@router.post("/storyline/generate")
async def generate_storyline(request: StorylineRequest):
    """Generate a complete storyline."""
    return {
        "success": True,
        "storyline": NarrativeGenerator.generate_storyline(request)
    }


@router.post("/dialogue-system/generate")
async def generate_dialogue_system(request: DialogueSystemRequest):
    """Generate a dialogue system."""
    return {
        "success": True,
        "dialogue_system": NarrativeGenerator.generate_dialogue_system(request)
    }


@router.post("/character-arc/generate")
async def generate_character_arc(request: CharacterArcRequest):
    """Generate a character arc."""
    return {
        "success": True,
        "character_arc": NarrativeGenerator.generate_character_arc(request)
    }


@router.post("/consequences/generate")
async def generate_consequence_system(request: ConsequenceSystemRequest):
    """Generate a consequence system."""
    return {
        "success": True,
        "consequence_system": NarrativeGenerator.generate_consequence_system(request)
    }


@router.post("/quest/generate")
async def generate_quest(request: QuestGeneratorRequest):
    """Generate a quest."""
    return {
        "success": True,
        "quest": NarrativeGenerator.generate_quest(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIStoryBranchRequest(BaseModel):
    """Request for AI-powered story branch generation"""
    context: str = Field(..., description="Current story context")
    choices: List[str] = Field(..., description="Player choice options")
    tone: str = Field(default="dramatic", description="Story tone")


class AIQuestRequest(BaseModel):
    """Request for AI-powered quest generation"""
    quest_type: str = Field(..., description="main, side, fetch, combat, etc.")
    difficulty: str = Field(default="medium", description="easy/medium/hard")
    setting: str = Field(default="fantasy village", description="Quest setting")


class AIDialogueTreeRequest(BaseModel):
    """Request for AI-powered dialogue tree generation"""
    character_name: str = Field(..., description="NPC name")
    character_personality: str = Field(..., description="Personality description")
    topics: List[str] = Field(default=["greeting", "quest", "lore"], description="Topics to cover")


@router.post("/ai/story/branch")
async def ai_generate_story_branch(request: AIStoryBranchRequest):
    """
    Generate story branches with multiple outcomes using AI (GPT-4o).
    Creates compelling narratives with meaningful player choices.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_story_branch(
            context=request.context,
            choices=request.choices,
            tone=request.tone
        )
        
        if result["success"]:
            return {
                "success": True,
                "story_branch": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "story_branch": {
                    "context": request.context,
                    "choices": request.choices,
                    "template": "basic_branch"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI story branch generation failed: {str(e)}")


@router.post("/ai/quest/generate")
async def ai_generate_quest(request: AIQuestRequest):
    """
    Generate complete quests with objectives and rewards using AI.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_quest(
            quest_type=request.quest_type,
            difficulty=request.difficulty,
            setting=request.setting
        )
        
        if result["success"]:
            return {
                "success": True,
                "quest": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            fallback_request = QuestGeneratorRequest()
            return {
                "success": True,
                "quest": NarrativeGenerator.generate_quest(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI quest generation failed: {str(e)}")


@router.post("/ai/dialogue/tree")
async def ai_generate_dialogue_tree(request: AIDialogueTreeRequest):
    """
    Generate complete dialogue trees for NPCs using AI.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_dialogue_tree(
            character_name=request.character_name,
            character_personality=request.character_personality,
            topics=request.topics
        )
        
        if result["success"]:
            return {
                "success": True,
                "dialogue_tree": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "dialogue_tree": {
                    "character": request.character_name,
                    "template": "basic_dialogue"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI dialogue tree generation failed: {str(e)}")
