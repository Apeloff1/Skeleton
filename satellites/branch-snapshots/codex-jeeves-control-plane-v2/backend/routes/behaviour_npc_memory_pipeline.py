"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      TEXT-TO-BEHAVIOUR & NPC MEMORY PIPELINE v15.5 - AI COGNITION            ║
║                                                                              ║
║  Generate NPC behavior systems and memory with LLM integration:              ║
║  • AI-powered behavior trees & state machines                                ║
║  • Intelligent long-term memory systems                                      ║
║  • Smart relationship tracking                                               ║
║  • AI learning & adaptation                                                  ║
║  • Dynamic personality evolution                                             ║
║  • Contextual emotional memory                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
import uuid
import random
from datetime import datetime

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/behaviour-npc-memory", tags=["Text-to-Behaviour & NPC Memory v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    EMOTIONAL = "emotional"
    WORKING = "working"


class BehaviourPattern(str, Enum):
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    PASSIVE = "passive"
    CURIOUS = "curious"
    FEARFUL = "fearful"
    HELPFUL = "helpful"
    NEUTRAL = "neutral"
    ADAPTIVE = "adaptive"


class LearningMode(str, Enum):
    REINFORCEMENT = "reinforcement"
    IMITATION = "imitation"
    INSTRUCTION = "instruction"
    OBSERVATION = "observation"
    TRIAL_ERROR = "trial_and_error"


class RelationshipType(str, Enum):
    FRIEND = "friend"
    ENEMY = "enemy"
    NEUTRAL = "neutral"
    FAMILY = "family"
    ROMANTIC = "romantic"
    RIVAL = "rival"
    MENTOR = "mentor"
    STUDENT = "student"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class MemorySystemRequest(BaseModel):
    npc_name: str
    memory_capacity: int = Field(1000, ge=100, le=100000)
    memory_types: List[MemoryType] = [MemoryType.EPISODIC, MemoryType.EMOTIONAL]
    decay_enabled: bool = True
    consolidation_enabled: bool = True


class BehaviourTreeRequest(BaseModel):
    npc_type: str
    base_pattern: BehaviourPattern = BehaviourPattern.NEUTRAL
    complexity: Literal["simple", "moderate", "complex"] = "moderate"
    adaptive: bool = True


class LearningSystemRequest(BaseModel):
    npc_name: str
    learning_modes: List[LearningMode] = [LearningMode.REINFORCEMENT]
    learning_rate: float = Field(0.1, ge=0.01, le=1.0)
    skill_domains: List[str] = []


class RelationshipSystemRequest(BaseModel):
    npc_name: str
    max_relationships: int = Field(50, ge=10, le=500)
    relationship_decay: bool = True
    faction_support: bool = True


class EmotionalMemoryRequest(BaseModel):
    npc_name: str
    emotional_range: List[str] = ["joy", "sadness", "anger", "fear", "surprise", "disgust"]
    mood_system: bool = True
    trauma_system: bool = False


# ============================================================================
# BEHAVIOUR & MEMORY GENERATOR
# ============================================================================

class BehaviourMemoryGenerator:
    """Advanced NPC behaviour and memory generation engine."""

    @staticmethod
    def generate_memory_system(request: MemorySystemRequest) -> Dict[str, Any]:
        """Generate a comprehensive NPC memory system."""
        memory_configs = {
            MemoryType.EPISODIC: {
                "description": "Personal experiences and events",
                "retention_days": 365,
                "detail_levels": ["vivid", "moderate", "faded", "forgotten"],
                "triggers": ["location", "character", "emotion", "time"]
            },
            MemoryType.SEMANTIC: {
                "description": "Facts and knowledge",
                "retention_days": -1,
                "categories": ["world_facts", "character_info", "locations", "items"]
            },
            MemoryType.PROCEDURAL: {
                "description": "Skills and how-to knowledge",
                "retention_days": -1,
                "skill_decay": False
            },
            MemoryType.EMOTIONAL: {
                "description": "Emotional associations",
                "retention_days": 730,
                "intensity_levels": [1, 2, 3, 4, 5]
            },
            MemoryType.WORKING: {
                "description": "Short-term active memories",
                "capacity": 7,
                "duration_minutes": 30
            }
        }
        
        return {
            "id": str(uuid.uuid4()),
            "npc_name": request.npc_name,
            "capacity": request.memory_capacity,
            "memory_banks": {
                mem_type.value: memory_configs.get(mem_type, {})
                for mem_type in request.memory_types
            },
            "decay": {
                "enabled": request.decay_enabled,
                "base_rate": 0.01,
                "importance_factor": True,
                "emotion_factor": True
            },
            "consolidation": {
                "enabled": request.consolidation_enabled,
                "sleep_required": False,
                "threshold": 0.7
            },
            "retrieval": {
                "method": "associative",
                "context_weight": 0.4,
                "recency_weight": 0.3,
                "importance_weight": 0.3
            },
            "code_template": BehaviourMemoryGenerator._generate_memory_code(request)
        }

    @staticmethod
    def _generate_memory_code(request: MemorySystemRequest) -> str:
        return f'''
class NPCMemorySystem:
    """Memory system for {request.npc_name}"""
    
    def __init__(self):
        self.episodic_memories: List[Memory] = []
        self.semantic_knowledge: Dict[str, Any] = {{}}
        self.emotional_associations: Dict[str, float] = {{}}
        self.working_memory: List[Memory] = []
        self.capacity = {request.memory_capacity}
    
    def store_memory(self, event: Event, importance: float = 0.5):
        """Store a new memory with emotional tagging."""
        memory = Memory(
            content=event,
            timestamp=datetime.now(),
            importance=importance,
            emotion=self._tag_emotion(event),
            associations=self._find_associations(event)
        )
        self.episodic_memories.append(memory)
        self._consolidate_if_needed()
    
    def recall(self, cue: str, context: Dict = None) -> List[Memory]:
        """Recall memories based on cue and context."""
        candidates = self._search_memories(cue)
        ranked = self._rank_by_relevance(candidates, context)
        return ranked[:5]  # Return top 5 matches
    
    def _consolidate_if_needed(self):
        """Consolidate memories if over capacity."""
        if len(self.episodic_memories) > self.capacity:
            self._merge_similar_memories()
            self._decay_old_memories()
'''

    @staticmethod
    def generate_behaviour_tree(request: BehaviourTreeRequest) -> Dict[str, Any]:
        """Generate an NPC behaviour tree."""
        complexity_nodes = {
            "simple": 10,
            "moderate": 25,
            "complex": 50
        }
        
        pattern_behaviors = {
            BehaviourPattern.AGGRESSIVE: ["attack", "chase", "threaten", "patrol", "guard"],
            BehaviourPattern.DEFENSIVE: ["block", "retreat", "heal", "call_allies", "fortify"],
            BehaviourPattern.PASSIVE: ["wander", "idle", "observe", "flee", "hide"],
            BehaviourPattern.CURIOUS: ["investigate", "follow", "examine", "question", "explore"],
            BehaviourPattern.HELPFUL: ["assist", "heal", "guide", "trade", "teach"]
        }
        
        behaviors = pattern_behaviors.get(request.base_pattern, ["idle", "wander"])
        
        return {
            "id": str(uuid.uuid4()),
            "npc_type": request.npc_type,
            "root": {
                "type": "selector",
                "children": [
                    {
                        "type": "sequence",
                        "name": "combat_response",
                        "condition": "threat_detected",
                        "children": [b for b in behaviors if b in ["attack", "block", "flee"]]
                    },
                    {
                        "type": "sequence",
                        "name": "social_response",
                        "condition": "player_nearby",
                        "children": ["greet", "evaluate_relationship", "choose_interaction"]
                    },
                    {
                        "type": "random_selector",
                        "name": "idle_behaviors",
                        "children": ["wander", "idle", "perform_routine"]
                    }
                ]
            },
            "node_count": complexity_nodes[request.complexity],
            "adaptive": request.adaptive,
            "utility_ai": {
                "enabled": request.adaptive,
                "considerations": ["health", "threat_level", "relationship", "mood", "goals"]
            }
        }

    @staticmethod
    def generate_learning_system(request: LearningSystemRequest) -> Dict[str, Any]:
        """Generate an NPC learning system."""
        return {
            "id": str(uuid.uuid4()),
            "npc_name": request.npc_name,
            "learning_config": {
                "modes": [m.value for m in request.learning_modes],
                "learning_rate": request.learning_rate,
                "skill_domains": request.skill_domains or ["combat", "social", "crafting", "navigation"]
            },
            "skill_system": {
                "max_level": 100,
                "xp_curve": "exponential",
                "mastery_bonus": 1.5
            },
            "adaptation": {
                "strategy_learning": True,
                "player_pattern_recognition": True,
                "counter_strategy_development": True
            },
            "knowledge_transfer": {
                "enabled": True,
                "teaching_ability": 0.5,
                "learning_from_others": True
            }
        }

    @staticmethod
    def generate_relationship_system(request: RelationshipSystemRequest) -> Dict[str, Any]:
        """Generate a relationship tracking system."""
        return {
            "id": str(uuid.uuid4()),
            "npc_name": request.npc_name,
            "config": {
                "max_relationships": request.max_relationships,
                "decay_enabled": request.relationship_decay,
                "faction_support": request.faction_support
            },
            "relationship_schema": {
                "types": [r.value for r in RelationshipType],
                "attributes": ["trust", "respect", "affection", "fear", "rivalry"],
                "range": [-100, 100]
            },
            "modifiers": {
                "gift_giving": 5,
                "helping": 10,
                "betrayal": -50,
                "combat": -20,
                "dialogue_positive": 2,
                "dialogue_negative": -5
            },
            "memory_integration": {
                "past_interactions_weight": 0.3,
                "recent_interactions_weight": 0.7,
                "forgiveness_rate": 0.01
            }
        }

    @staticmethod
    def generate_emotional_memory(request: EmotionalMemoryRequest) -> Dict[str, Any]:
        """Generate an emotional memory system."""
        return {
            "id": str(uuid.uuid4()),
            "npc_name": request.npc_name,
            "emotional_range": request.emotional_range,
            "mood_system": {
                "enabled": request.mood_system,
                "base_mood": "neutral",
                "mood_inertia": 0.8,
                "external_influence": 0.3
            },
            "trauma_system": {
                "enabled": request.trauma_system,
                "threshold": 0.9,
                "triggers": [],
                "coping_mechanisms": ["avoidance", "aggression", "withdrawal"]
            },
            "emotional_memory_bank": {
                "associations": {},
                "triggers": {},
                "intensity_decay": 0.05
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Behaviour & NPC Memory Pipeline."""
    return {
        "pipeline": "Text-to-Behaviour & NPC Memory Pipeline v15.5",
        "description": "Generate NPC behavior and memory systems from natural language",
        "capabilities": [
            "Memory systems (episodic, semantic, emotional)",
            "Behaviour trees with utility AI",
            "Learning & adaptation systems",
            "Relationship tracking",
            "Emotional memory & mood systems"
        ],
        "memory_types": [m.value for m in MemoryType],
        "behaviour_patterns": [b.value for b in BehaviourPattern],
        "learning_modes": [l.value for l in LearningMode]
    }


@router.post("/memory/generate")
async def generate_memory_system(request: MemorySystemRequest):
    """Generate an NPC memory system."""
    return {
        "success": True,
        "memory_system": BehaviourMemoryGenerator.generate_memory_system(request)
    }


@router.post("/behaviour/generate")
async def generate_behaviour_tree(request: BehaviourTreeRequest):
    """Generate an NPC behaviour tree."""
    return {
        "success": True,
        "behaviour_tree": BehaviourMemoryGenerator.generate_behaviour_tree(request)
    }


@router.post("/learning/generate")
async def generate_learning_system(request: LearningSystemRequest):
    """Generate an NPC learning system."""
    return {
        "success": True,
        "learning_system": BehaviourMemoryGenerator.generate_learning_system(request)
    }


@router.post("/relationships/generate")
async def generate_relationship_system(request: RelationshipSystemRequest):
    """Generate a relationship tracking system."""
    return {
        "success": True,
        "relationship_system": BehaviourMemoryGenerator.generate_relationship_system(request)
    }


@router.post("/emotional-memory/generate")
async def generate_emotional_memory(request: EmotionalMemoryRequest):
    """Generate an emotional memory system."""
    return {
        "success": True,
        "emotional_memory": BehaviourMemoryGenerator.generate_emotional_memory(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIBehaviorTreeRequest(BaseModel):
    """Request for AI-powered behavior tree generation"""
    npc_type: str = Field(..., description="Type of NPC: guard, merchant, etc.")
    behavior_style: str = Field(default="defensive", description="aggressive, defensive, neutral")


class AIMemorySystemRequest(BaseModel):
    """Request for AI-powered memory system design"""
    memory_type: str = Field(default="persistent", description="episodic, semantic, persistent")


@router.post("/ai/behavior/generate")
async def ai_generate_behavior_tree(request: AIBehaviorTreeRequest):
    """
    Generate AI behavior trees using GPT-4o.
    Creates intelligent decision-making patterns for NPCs.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_ai_behavior(
            agent_type=request.npc_type,
            behavior_style=request.behavior_style
        )
        
        if result["success"]:
            return {
                "success": True,
                "behavior_tree": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "behavior_tree": {
                    "npc_type": request.npc_type,
                    "template": "basic_behavior_tree"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI behavior generation failed: {str(e)}")


@router.post("/ai/memory/design")
async def ai_design_memory_system(request: AIMemorySystemRequest):
    """
    Design NPC memory systems using AI.
    Creates realistic memory with decay and retrieval.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_npc_memory_system(
            memory_type=request.memory_type
        )
        
        if result["success"]:
            return {
                "success": True,
                "memory_system": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            fallback_request = MemorySystemRequest()
            return {
                "success": True,
                "memory_system": BehaviourMemoryGenerator.generate_memory_system(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI memory design failed: {str(e)}")
