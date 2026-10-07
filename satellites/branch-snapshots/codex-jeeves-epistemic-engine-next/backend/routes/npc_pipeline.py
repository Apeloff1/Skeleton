"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              TEXT-TO-NPC PIPELINE v15.5 - AI-POWERED NPC GENERATION          ║
║                                                                              ║
║  Generate complete NPCs from natural language descriptions with LLM:         ║
║  • AI-powered personality and backstory generation                           ║
║  • Dynamic dialogue with GPT-4o                                              ║
║  • Intelligent behavioral AI patterns                                        ║
║  • Combat/interaction stats                                                  ║
║  • Visual appearance descriptors                                             ║
║  • Quest/story integration hooks                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import uuid
import random
import json

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/npc-pipeline", tags=["Text-to-NPC Pipeline v15.5"])

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class NPCArchetype(str, Enum):
    MERCHANT = "merchant"
    WARRIOR = "warrior"
    MAGE = "mage"
    HEALER = "healer"
    ROGUE = "rogue"
    SCHOLAR = "scholar"
    ARTISAN = "artisan"
    NOBLE = "noble"
    PEASANT = "peasant"
    GUARDIAN = "guardian"
    TRICKSTER = "trickster"
    MENTOR = "mentor"
    VILLAIN = "villain"
    COMPANION = "companion"

class PersonalityTrait(str, Enum):
    # Big 5 Personality Traits
    OPENNESS = "openness"
    CONSCIENTIOUSNESS = "conscientiousness"
    EXTRAVERSION = "extraversion"
    AGREEABLENESS = "agreeableness"
    NEUROTICISM = "neuroticism"

class Alignment(str, Enum):
    LAWFUL_GOOD = "lawful_good"
    NEUTRAL_GOOD = "neutral_good"
    CHAOTIC_GOOD = "chaotic_good"
    LAWFUL_NEUTRAL = "lawful_neutral"
    TRUE_NEUTRAL = "true_neutral"
    CHAOTIC_NEUTRAL = "chaotic_neutral"
    LAWFUL_EVIL = "lawful_evil"
    NEUTRAL_EVIL = "neutral_evil"
    CHAOTIC_EVIL = "chaotic_evil"

class EmotionalState(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    CURIOUS = "curious"
    SUSPICIOUS = "suspicious"
    FRIENDLY = "friendly"

# NPC Templates for different archetypes
NPC_ARCHETYPE_TEMPLATES = {
    NPCArchetype.MERCHANT: {
        "base_stats": {"charisma": 14, "intelligence": 12, "wisdom": 10},
        "skills": ["persuasion", "appraisal", "negotiation", "inventory_management"],
        "typical_dialogue_topics": ["prices", "goods", "rumors", "trade_routes"],
        "behavior_patterns": ["haggle", "showcase_goods", "gossip", "protect_inventory"]
    },
    NPCArchetype.WARRIOR: {
        "base_stats": {"strength": 16, "constitution": 14, "dexterity": 12},
        "skills": ["combat", "tactics", "weapon_mastery", "intimidation"],
        "typical_dialogue_topics": ["battles", "honor", "training", "enemies"],
        "behavior_patterns": ["patrol", "challenge", "protect", "train"]
    },
    NPCArchetype.MAGE: {
        "base_stats": {"intelligence": 18, "wisdom": 14, "charisma": 10},
        "skills": ["arcana", "spellcasting", "alchemy", "ancient_languages"],
        "typical_dialogue_topics": ["magic", "research", "mysteries", "artifacts"],
        "behavior_patterns": ["study", "experiment", "lecture", "cast_spells"]
    },
    NPCArchetype.MENTOR: {
        "base_stats": {"wisdom": 18, "intelligence": 16, "charisma": 14},
        "skills": ["teaching", "guidance", "insight", "history"],
        "typical_dialogue_topics": ["lessons", "growth", "challenges", "wisdom"],
        "behavior_patterns": ["observe", "advise", "test", "encourage"]
    },
    NPCArchetype.VILLAIN: {
        "base_stats": {"intelligence": 16, "charisma": 14, "wisdom": 12},
        "skills": ["manipulation", "intimidation", "deception", "planning"],
        "typical_dialogue_topics": ["power", "revenge", "control", "superiority"],
        "behavior_patterns": ["scheme", "threaten", "monologue", "manipulate"]
    }
}

# Dialogue response templates by emotional state
DIALOGUE_RESPONSES = {
    EmotionalState.FRIENDLY: {
        "greetings": ["Well met, friend!", "Ah, a friendly face!", "Welcome, welcome!"],
        "farewells": ["Safe travels!", "Until we meet again!", "May fortune favor you!"],
        "reactions": ["How wonderful!", "I'm delighted!", "That's fantastic news!"]
    },
    EmotionalState.SUSPICIOUS: {
        "greetings": ["State your business.", "Who goes there?", "What do you want?"],
        "farewells": ["Don't cause any trouble.", "I'll be watching.", "Move along."],
        "reactions": ["Hmm, is that so?", "I don't quite believe that.", "Prove it."]
    },
    EmotionalState.ANGRY: {
        "greetings": ["What do YOU want?!", "Leave me be!", "This better be important!"],
        "farewells": ["Get out of my sight!", "Don't come back!", "Good riddance!"],
        "reactions": ["How DARE you!", "Unacceptable!", "You'll pay for this!"]
    }
}

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class NPCGenerationRequest(BaseModel):
    description: str = Field(..., description="Natural language description of the NPC")
    archetype: Optional[NPCArchetype] = None
    alignment: Optional[Alignment] = None
    include_dialogue: bool = True
    include_quests: bool = False
    complexity_level: Literal["simple", "moderate", "complex"] = "moderate"

class DialogueGenerationRequest(BaseModel):
    npc_id: str
    context: str
    player_reputation: int = 0
    emotional_modifier: Optional[EmotionalState] = None

class BehaviorTreeRequest(BaseModel):
    npc_id: str
    scenario: str
    environmental_factors: List[str] = []

class NPCRelationshipRequest(BaseModel):
    npc_id: str
    target_npc_id: str
    interaction_history: List[str] = []

# ============================================================================
# NPC GENERATOR ENGINE
# ============================================================================

class NPCGenerator:
    """
    Comprehensive NPC generation engine that creates fully-realized characters
    from natural language descriptions.
    """
    
    @staticmethod
    def parse_description(description: str) -> Dict[str, Any]:
        """Parse natural language description to extract NPC attributes."""
        # Keyword detection for attributes
        keywords = {
            "archetypes": {
                "merchant": ["merchant", "trader", "shopkeeper", "vendor", "seller"],
                "warrior": ["warrior", "soldier", "fighter", "knight", "guard"],
                "mage": ["mage", "wizard", "sorcerer", "witch", "spellcaster"],
                "healer": ["healer", "cleric", "priest", "medic", "doctor"],
                "rogue": ["rogue", "thief", "assassin", "spy", "scout"],
                "scholar": ["scholar", "sage", "researcher", "academic", "professor"],
                "mentor": ["mentor", "teacher", "master", "guide", "elder"],
                "villain": ["villain", "enemy", "antagonist", "evil", "corrupt"]
            },
            "traits": {
                "friendly": ["friendly", "kind", "warm", "welcoming", "helpful"],
                "hostile": ["hostile", "aggressive", "angry", "violent", "mean"],
                "mysterious": ["mysterious", "enigmatic", "secretive", "shadowy"],
                "wise": ["wise", "knowledgeable", "experienced", "sage"],
                "humorous": ["funny", "humorous", "witty", "joking", "comedic"]
            },
            "alignments": {
                "good": ["good", "righteous", "noble", "heroic", "virtuous"],
                "evil": ["evil", "wicked", "corrupt", "malicious", "dark"],
                "lawful": ["lawful", "orderly", "disciplined", "strict"],
                "chaotic": ["chaotic", "wild", "unpredictable", "free"]
            }
        }
        
        desc_lower = description.lower()
        parsed = {
            "detected_archetype": None,
            "detected_traits": [],
            "detected_alignment": None,
            "raw_description": description
        }
        
        # Detect archetype
        for archetype, words in keywords["archetypes"].items():
            if any(word in desc_lower for word in words):
                parsed["detected_archetype"] = archetype
                break
        
        # Detect traits
        for trait, words in keywords["traits"].items():
            if any(word in desc_lower for word in words):
                parsed["detected_traits"].append(trait)
        
        # Detect alignment
        alignment_parts = []
        for align, words in keywords["alignments"].items():
            if any(word in desc_lower for word in words):
                alignment_parts.append(align)
        
        if alignment_parts:
            if "lawful" in alignment_parts and "good" in alignment_parts:
                parsed["detected_alignment"] = Alignment.LAWFUL_GOOD
            elif "chaotic" in alignment_parts and "good" in alignment_parts:
                parsed["detected_alignment"] = Alignment.CHAOTIC_GOOD
            elif "lawful" in alignment_parts and "evil" in alignment_parts:
                parsed["detected_alignment"] = Alignment.LAWFUL_EVIL
            elif "chaotic" in alignment_parts and "evil" in alignment_parts:
                parsed["detected_alignment"] = Alignment.CHAOTIC_EVIL
            elif "good" in alignment_parts:
                parsed["detected_alignment"] = Alignment.NEUTRAL_GOOD
            elif "evil" in alignment_parts:
                parsed["detected_alignment"] = Alignment.NEUTRAL_EVIL
        
        return parsed
    
    @staticmethod
    def generate_personality(archetype: NPCArchetype, traits: List[str]) -> Dict[str, Any]:
        """Generate Big 5 personality profile."""
        # Base personality by archetype
        archetype_personalities = {
            NPCArchetype.MERCHANT: {"O": 60, "C": 75, "E": 70, "A": 65, "N": 40},
            NPCArchetype.WARRIOR: {"O": 40, "C": 80, "E": 55, "A": 45, "N": 35},
            NPCArchetype.MAGE: {"O": 90, "C": 70, "E": 35, "A": 50, "N": 55},
            NPCArchetype.MENTOR: {"O": 85, "C": 75, "E": 60, "A": 80, "N": 25},
            NPCArchetype.VILLAIN: {"O": 70, "C": 65, "E": 50, "A": 20, "N": 60}
        }
        
        base = archetype_personalities.get(archetype, {"O": 50, "C": 50, "E": 50, "A": 50, "N": 50})
        
        # Modify based on detected traits
        trait_modifiers = {
            "friendly": {"E": 10, "A": 15},
            "hostile": {"A": -20, "N": 15},
            "mysterious": {"E": -15, "O": 10},
            "wise": {"O": 10, "C": 5},
            "humorous": {"E": 15, "O": 10}
        }
        
        for trait in traits:
            if trait in trait_modifiers:
                for key, mod in trait_modifiers[trait].items():
                    base[key] = max(0, min(100, base[key] + mod))
        
        return {
            "openness": base["O"],
            "conscientiousness": base["C"],
            "extraversion": base["E"],
            "agreeableness": base["A"],
            "neuroticism": base["N"],
            "dominant_trait": max(base, key=base.get),
            "personality_summary": NPCGenerator._generate_personality_summary(base)
        }
    
    @staticmethod
    def _generate_personality_summary(scores: Dict[str, int]) -> str:
        """Generate a human-readable personality summary."""
        summaries = []
        if scores["O"] > 70:
            summaries.append("intellectually curious and creative")
        if scores["C"] > 70:
            summaries.append("organized and dependable")
        if scores["E"] > 70:
            summaries.append("outgoing and energetic")
        elif scores["E"] < 30:
            summaries.append("reserved and introspective")
        if scores["A"] > 70:
            summaries.append("compassionate and cooperative")
        elif scores["A"] < 30:
            summaries.append("competitive and challenging")
        if scores["N"] > 70:
            summaries.append("emotionally sensitive")
        
        if not summaries:
            return "balanced and adaptable"
        return ", ".join(summaries)
    
    @staticmethod
    def generate_stats(archetype: NPCArchetype, complexity: str) -> Dict[str, Any]:
        """Generate NPC stats based on archetype and complexity."""
        template = NPC_ARCHETYPE_TEMPLATES.get(archetype, {})
        base_stats = template.get("base_stats", {})
        
        # Add variance
        stats = {}
        stat_names = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
        
        for stat in stat_names:
            base = base_stats.get(stat, 10)
            variance = {"simple": 1, "moderate": 2, "complex": 3}.get(complexity, 2)
            stats[stat] = base + random.randint(-variance, variance)
        
        # Calculate derived stats
        stats["hit_points"] = 10 + (stats["constitution"] - 10) * 2
        stats["armor_class"] = 10 + (stats["dexterity"] - 10) // 2
        stats["initiative"] = (stats["dexterity"] - 10) // 2
        
        return {
            "primary_stats": stats,
            "skills": template.get("skills", []),
            "level": random.randint(1, 10) if complexity == "complex" else random.randint(1, 5)
        }
    
    @staticmethod
    def generate_dialogue_tree(
        archetype: NPCArchetype,
        personality: Dict[str, Any],
        topics: List[str]
    ) -> Dict[str, Any]:
        """Generate a dialogue tree based on personality and topics."""
        template = NPC_ARCHETYPE_TEMPLATES.get(archetype, {})
        base_topics = template.get("typical_dialogue_topics", ["greeting", "farewell"])
        all_topics = list(set(base_topics + topics))
        
        dialogue_tree = {
            "root": {
                "node_id": "greeting",
                "text": "How may I help you?",
                "options": []
            },
            "nodes": {}
        }
        
        # Generate dialogue nodes for each topic
        for i, topic in enumerate(all_topics[:5]):  # Limit to 5 topics
            node_id = f"topic_{i}"
            dialogue_tree["nodes"][node_id] = {
                "node_id": node_id,
                "topic": topic,
                "text": f"Let me tell you about {topic}...",
                "emotional_variants": {
                    "friendly": f"I'd love to share what I know about {topic}!",
                    "neutral": f"Regarding {topic}...",
                    "suspicious": f"Why do you want to know about {topic}?"
                },
                "leads_to": ["farewell", f"topic_{(i+1) % len(all_topics)}"]
            }
            dialogue_tree["root"]["options"].append({
                "text": f"Tell me about {topic}",
                "leads_to": node_id
            })
        
        # Add farewell node
        dialogue_tree["nodes"]["farewell"] = {
            "node_id": "farewell",
            "text": "Farewell, traveler.",
            "emotional_variants": {
                "friendly": "Safe travels, friend!",
                "neutral": "Goodbye.",
                "suspicious": "Don't cause any trouble."
            },
            "ends_conversation": True
        }
        
        dialogue_tree["root"]["options"].append({
            "text": "I should go",
            "leads_to": "farewell"
        })
        
        return dialogue_tree
    
    @staticmethod
    def generate_behavior_tree(archetype: NPCArchetype, scenario: str) -> Dict[str, Any]:
        """Generate AI behavior tree for the NPC."""
        template = NPC_ARCHETYPE_TEMPLATES.get(archetype, {})
        patterns = template.get("behavior_patterns", ["idle", "wander"])
        
        behavior_tree = {
            "root": {
                "type": "selector",
                "children": []
            }
        }
        
        # Priority behaviors
        priority_behaviors = [
            {
                "type": "sequence",
                "name": "danger_response",
                "condition": "threat_detected",
                "actions": ["assess_threat", "choose_response", "execute_response"]
            },
            {
                "type": "sequence",
                "name": "player_interaction",
                "condition": "player_nearby",
                "actions": ["face_player", "greet_if_friendly", "wait_for_input"]
            }
        ]
        
        # Archetype-specific behaviors
        for pattern in patterns:
            priority_behaviors.append({
                "type": "action",
                "name": pattern,
                "condition": "idle",
                "weight": random.uniform(0.1, 0.3)
            })
        
        behavior_tree["root"]["children"] = priority_behaviors
        behavior_tree["scenario_context"] = scenario
        behavior_tree["update_frequency"] = "every_frame"
        
        return behavior_tree
    
    @staticmethod
    def generate_appearance(description: str) -> Dict[str, Any]:
        """Generate visual appearance descriptors from description."""
        # Extract appearance keywords
        appearance = {
            "body_type": "average",
            "height": "medium",
            "hair": {},
            "eyes": {},
            "distinguishing_features": [],
            "clothing_style": "common",
            "accessories": []
        }
        
        desc_lower = description.lower()
        
        # Body type detection
        if any(w in desc_lower for w in ["tall", "towering", "giant"]):
            appearance["height"] = "tall"
        elif any(w in desc_lower for w in ["short", "small", "diminutive"]):
            appearance["height"] = "short"
        
        if any(w in desc_lower for w in ["muscular", "bulky", "strong"]):
            appearance["body_type"] = "muscular"
        elif any(w in desc_lower for w in ["thin", "slender", "lean"]):
            appearance["body_type"] = "slender"
        
        # Hair
        hair_colors = ["black", "brown", "blonde", "red", "white", "gray", "silver"]
        for color in hair_colors:
            if color in desc_lower:
                appearance["hair"]["color"] = color
                break
        
        # Eyes
        eye_colors = ["blue", "green", "brown", "hazel", "gray", "amber", "red"]
        for color in eye_colors:
            if color + " eye" in desc_lower:
                appearance["eyes"]["color"] = color
                break
        
        # Features
        features = ["scar", "tattoo", "beard", "glasses", "eyepatch", "piercing"]
        for feature in features:
            if feature in desc_lower:
                appearance["distinguishing_features"].append(feature)
        
        return appearance
    
    @staticmethod
    def generate_quest_hooks(archetype: NPCArchetype, personality: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate potential quest hooks for this NPC."""
        quest_templates = {
            NPCArchetype.MERCHANT: [
                {"type": "fetch", "title": "Supply Run", "description": "Retrieve rare goods from a distant location"},
                {"type": "escort", "title": "Safe Passage", "description": "Protect a trade caravan"},
                {"type": "investigate", "title": "Missing Shipment", "description": "Find out what happened to lost goods"}
            ],
            NPCArchetype.WARRIOR: [
                {"type": "combat", "title": "Honor Duel", "description": "Prove your worth in combat"},
                {"type": "hunt", "title": "Monster Hunt", "description": "Track and eliminate a dangerous creature"},
                {"type": "rescue", "title": "Rescue Mission", "description": "Save captured allies"}
            ],
            NPCArchetype.MENTOR: [
                {"type": "training", "title": "The Test", "description": "Complete a series of challenges"},
                {"type": "discovery", "title": "Hidden Knowledge", "description": "Uncover ancient secrets"},
                {"type": "growth", "title": "Inner Journey", "description": "Face your fears and grow"}
            ]
        }
        
        hooks = quest_templates.get(archetype, [
            {"type": "generic", "title": "A Simple Task", "description": "Help with a basic problem"}
        ])
        
        # Add unique IDs and difficulty
        for hook in hooks:
            hook["id"] = str(uuid.uuid4())[:8]
            hook["difficulty"] = random.choice(["easy", "medium", "hard"])
            hook["reward_tier"] = random.randint(1, 5)
        
        return hooks

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_pipeline_overview():
    """Get overview of the Text-to-NPC Pipeline"""
    return {
        "pipeline": "Text-to-NPC Pipeline v15.0",
        "description": "Generate complete NPCs from natural language descriptions",
        "capabilities": [
            "Personality generation (Big 5 model)",
            "Dialogue tree creation",
            "Behavior tree AI",
            "Stats and skills generation",
            "Visual appearance descriptors",
            "Quest hook generation",
            "Relationship modeling"
        ],
        "archetypes": [a.value for a in NPCArchetype],
        "alignments": [a.value for a in Alignment],
        "emotional_states": [e.value for e in EmotionalState],
        "co_coding_enabled": True,
        "jeeves_integration": True
    }

@router.post("/generate")
async def generate_npc(request: NPCGenerationRequest):
    """Generate a complete NPC from natural language description"""
    try:
        # Parse description
        parsed = NPCGenerator.parse_description(request.description)
        
        # Determine archetype
        archetype = request.archetype
        if not archetype and parsed["detected_archetype"]:
            archetype = NPCArchetype(parsed["detected_archetype"])
        if not archetype:
            archetype = NPCArchetype.PEASANT
        
        # Determine alignment
        alignment = request.alignment or parsed["detected_alignment"] or Alignment.TRUE_NEUTRAL
        
        # Generate all components
        personality = NPCGenerator.generate_personality(archetype, parsed["detected_traits"])
        stats = NPCGenerator.generate_stats(archetype, request.complexity_level)
        appearance = NPCGenerator.generate_appearance(request.description)
        
        npc = {
            "id": str(uuid.uuid4()),
            "name": f"NPC_{str(uuid.uuid4())[:6]}",
            "archetype": archetype.value,
            "alignment": alignment.value,
            "personality": personality,
            "stats": stats,
            "appearance": appearance,
            "parsed_description": parsed,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Optional components
        if request.include_dialogue:
            npc["dialogue_tree"] = NPCGenerator.generate_dialogue_tree(
                archetype, personality, []
            )
        
        if request.include_quests:
            npc["quest_hooks"] = NPCGenerator.generate_quest_hooks(archetype, personality)
        
        return {
            "success": True,
            "npc": npc,
            "generation_metadata": {
                "complexity": request.complexity_level,
                "components_generated": list(npc.keys())
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dialogue/generate")
async def generate_dialogue_response(request: DialogueGenerationRequest):
    """Generate contextual dialogue response"""
    emotional_state = request.emotional_modifier or EmotionalState.NEUTRAL
    
    # Adjust based on reputation
    if request.player_reputation > 50:
        emotional_state = EmotionalState.FRIENDLY
    elif request.player_reputation < -50:
        emotional_state = EmotionalState.HOSTILE if random.random() > 0.5 else EmotionalState.SUSPICIOUS
    
    responses = DIALOGUE_RESPONSES.get(emotional_state, DIALOGUE_RESPONSES[EmotionalState.NEUTRAL])
    
    return {
        "npc_id": request.npc_id,
        "context": request.context,
        "emotional_state": emotional_state.value,
        "response": {
            "greeting": random.choice(responses.get("greetings", ["Hello."])),
            "reaction": random.choice(responses.get("reactions", ["I see."])),
            "farewell": random.choice(responses.get("farewells", ["Goodbye."]))
        },
        "voice_hints": {
            "tone": emotional_state.value,
            "pace": "normal",
            "volume": "medium"
        }
    }

@router.post("/behavior/generate")
async def generate_behavior_tree(request: BehaviorTreeRequest):
    """Generate AI behavior tree for NPC"""
    # Default to merchant if archetype unknown
    archetype = NPCArchetype.MERCHANT
    
    behavior_tree = NPCGenerator.generate_behavior_tree(archetype, request.scenario)
    behavior_tree["environmental_modifiers"] = request.environmental_factors
    
    return {
        "npc_id": request.npc_id,
        "behavior_tree": behavior_tree,
        "scenario": request.scenario,
        "update_mode": "reactive"
    }

@router.get("/archetypes")
async def get_archetypes():
    """Get all available NPC archetypes with templates"""
    return {
        "archetypes": [
            {
                "id": archetype.value,
                "name": archetype.value.replace("_", " ").title(),
                "template": NPC_ARCHETYPE_TEMPLATES.get(archetype, {})
            }
            for archetype in NPCArchetype
        ]
    }

@router.post("/batch/generate")
async def batch_generate_npcs(descriptions: List[str], complexity: str = "moderate"):
    """Generate multiple NPCs in batch"""
    npcs = []
    for desc in descriptions[:10]:  # Limit to 10
        request = NPCGenerationRequest(
            description=desc,
            complexity_level=complexity,
            include_dialogue=True,
            include_quests=False
        )
        result = await generate_npc(request)
        if result["success"]:
            npcs.append(result["npc"])
    
    return {
        "success": True,
        "count": len(npcs),
        "npcs": npcs
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIGenerationRequest(BaseModel):
    """Request model for AI-powered NPC generation"""
    description: str = Field(..., description="Natural language description of the NPC")
    archetype: Optional[str] = None
    include_dialogue: bool = True
    include_quests: bool = False
    include_backstory: bool = True
    game_genre: Optional[str] = "fantasy"


class AIDialogueRequest(BaseModel):
    """Request model for AI-powered dialogue generation"""
    npc_name: str
    npc_personality: Dict[str, Any]
    situation: str
    player_input: Optional[str] = None
    conversation_history: List[Dict[str, str]] = []


@router.post("/ai/generate")
async def ai_generate_npc(request: AIGenerationRequest):
    """
    Generate a complete NPC using AI (GPT-4o).
    Creates rich backstories, personalities, and dialogue.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_npc(
            description=request.description,
            archetype=request.archetype,
            include_dialogue=request.include_dialogue,
            include_quests=request.include_quests
        )
        
        if result["success"] and "npc" in result:
            # Enhance with local generation for stats
            parsed = NPCGenerator.parse_description(request.description)
            archetype = NPCArchetype(parsed.get("detected_archetype", "peasant")) if parsed.get("detected_archetype") else NPCArchetype.PEASANT
            
            npc_data = result["npc"]
            npc_data["id"] = str(uuid.uuid4())
            npc_data["stats"] = NPCGenerator.generate_stats(archetype, "complex")
            npc_data["created_at"] = datetime.utcnow().isoformat()
            npc_data["ai_generated"] = True
            
            return {
                "success": True,
                "npc": npc_data,
                "generation_method": "ai_powered",
                "model": "gpt-4o"
            }
        else:
            # Fallback to local generation
            fallback_request = NPCGenerationRequest(
                description=request.description,
                include_dialogue=request.include_dialogue,
                include_quests=request.include_quests,
                complexity_level="complex"
            )
            return await generate_npc(fallback_request)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI NPC generation failed: {str(e)}")


@router.post("/ai/dialogue")
async def ai_generate_dialogue(request: AIDialogueRequest):
    """
    Generate contextual NPC dialogue using AI.
    Maintains character consistency and responds to player input.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_npc_dialogue(
            npc_context={
                "name": request.npc_name,
                "personality": request.npc_personality
            },
            situation=request.situation,
            player_input=request.player_input
        )
        
        if result["success"]:
            return {
                "success": True,
                "npc_name": request.npc_name,
                "dialogue": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            # Fallback to template-based dialogue
            return {
                "success": True,
                "npc_name": request.npc_name,
                "dialogue": "Greetings, traveler. How may I assist you?",
                "ai_generated": False,
                "fallback_reason": result.get("error", "LLM unavailable")
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI dialogue generation failed: {str(e)}")


@router.post("/ai/behavior")
async def ai_generate_behavior(npc_type: str, behavior_style: str = "defensive"):
    """
    Generate AI behavior trees using LLM.
    Creates intelligent decision-making patterns.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_ai_behavior(
            agent_type=npc_type,
            behavior_style=behavior_style
        )
        
        if result["success"]:
            return {
                "success": True,
                "npc_type": npc_type,
                "behavior_data": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            # Fallback to template behavior
            archetype = NPCArchetype.WARRIOR if "warrior" in npc_type.lower() else NPCArchetype.MERCHANT
            behavior_tree = NPCGenerator.generate_behavior_tree(archetype, "default scenario")
            return {
                "success": True,
                "npc_type": npc_type,
                "behavior_data": behavior_tree,
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI behavior generation failed: {str(e)}")


@router.post("/ai/quest")
async def ai_generate_npc_quest(
    npc_name: str,
    npc_archetype: str,
    difficulty: str = "medium",
    setting: str = "fantasy village"
):
    """
    Generate a quest for an NPC using AI.
    Creates engaging quest content with objectives and rewards.
    """
    try:
        llm_service = get_game_llm_service()
        
        # Determine quest type based on archetype
        quest_types = {
            "merchant": "fetch",
            "warrior": "combat",
            "mage": "investigation",
            "healer": "rescue",
            "rogue": "stealth"
        }
        quest_type = quest_types.get(npc_archetype.lower(), "adventure")
        
        result = await llm_service.generate_quest(
            quest_type=quest_type,
            difficulty=difficulty,
            setting=setting
        )
        
        if result["success"]:
            return {
                "success": True,
                "quest_giver": npc_name,
                "quest_data": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            # Fallback to template quest
            archetype = NPCArchetype(npc_archetype) if npc_archetype in [a.value for a in NPCArchetype] else NPCArchetype.MERCHANT
            quest_hooks = NPCGenerator.generate_quest_hooks(archetype, {})
            return {
                "success": True,
                "quest_giver": npc_name,
                "quest_data": quest_hooks[0] if quest_hooks else {"title": "A Simple Task"},
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI quest generation failed: {str(e)}")
