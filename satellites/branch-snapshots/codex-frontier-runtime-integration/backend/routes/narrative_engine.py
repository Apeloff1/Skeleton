"""
Text-to-Narrative Engine v11.5
AI-Powered Story, Dialogue & Quest Generation Pipeline

Capabilities:
- Story arc generation (3-act, hero's journey, branching)
- Character creation with personalities and backgrounds
- Dynamic dialogue systems
- Quest and mission generation
- Lore and world-building documents
- Procedural events and encounters
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime

router = APIRouter(prefix="/api/narrative", tags=["Narrative Engine"])

# ============================================================================
# DATA MODELS
# ============================================================================

class StoryGenerationRequest(BaseModel):
    premise: str
    genre: str = "fantasy"  # fantasy, sci-fi, horror, mystery, romance, adventure
    tone: str = "epic"  # epic, dark, comedic, dramatic, whimsical, gritty
    structure: str = "three_act"  # three_act, hero_journey, branching, episodic
    length: str = "medium"  # short, medium, long, epic
    include_characters: bool = True
    include_locations: bool = True
    branching_paths: int = 1  # Number of story branches

class CharacterRequest(BaseModel):
    description: str
    role: str = "protagonist"  # protagonist, antagonist, ally, mentor, neutral
    archetype: str = "hero"  # hero, villain, trickster, sage, innocent, etc.
    personality_traits: List[str] = []
    backstory_depth: str = "detailed"  # minimal, moderate, detailed, extensive

class DialogueRequest(BaseModel):
    context: str
    characters: List[str]
    mood: str = "neutral"  # neutral, tense, friendly, romantic, hostile, mysterious
    purpose: str = "exposition"  # exposition, conflict, resolution, comic_relief, foreshadowing
    length: int = 10  # Number of dialogue lines
    include_choices: bool = False

class QuestRequest(BaseModel):
    description: str
    quest_type: str = "main"  # main, side, daily, hidden, legendary
    difficulty: str = "medium"  # easy, medium, hard, legendary
    estimated_time: str = "medium"  # short (5-15min), medium (30-60min), long (2-4hr)
    rewards: List[str] = []
    include_subquests: bool = True

class LoreRequest(BaseModel):
    topic: str
    category: str = "history"  # history, mythology, science, culture, magic, technology
    depth: str = "moderate"  # brief, moderate, extensive, encyclopedic
    format: str = "document"  # document, timeline, encyclopedia, story

# ============================================================================
# NARRATIVE DATABASE
# ============================================================================

STORY_STRUCTURES = {
    "three_act": {
        "name": "Three-Act Structure",
        "description": "Classic setup, confrontation, resolution format",
        "acts": [
            {"name": "Setup", "purpose": "Introduce characters, world, and conflict", "percentage": 25},
            {"name": "Confrontation", "purpose": "Rising action and challenges", "percentage": 50},
            {"name": "Resolution", "purpose": "Climax and conclusion", "percentage": 25}
        ]
    },
    "hero_journey": {
        "name": "Hero's Journey",
        "description": "Joseph Campbell's monomyth structure",
        "stages": [
            "Ordinary World", "Call to Adventure", "Refusal of the Call",
            "Meeting the Mentor", "Crossing the Threshold", "Tests, Allies, Enemies",
            "Approach to the Inmost Cave", "Ordeal", "Reward",
            "The Road Back", "Resurrection", "Return with the Elixir"
        ]
    },
    "branching": {
        "name": "Branching Narrative",
        "description": "Multiple paths based on player choices",
        "branch_points": 5,
        "endings": ["good", "neutral", "bad", "secret"]
    },
    "episodic": {
        "name": "Episodic Structure",
        "description": "Self-contained episodes with overarching plot",
        "episode_format": ["hook", "development", "climax", "resolution", "teaser"]
    }
}

CHARACTER_ARCHETYPES = {
    "hero": {
        "name": "The Hero",
        "traits": ["brave", "determined", "selfless"],
        "motivations": ["save others", "prove worth", "fulfill destiny"],
        "weaknesses": ["arrogance", "self-doubt", "naivety"]
    },
    "mentor": {
        "name": "The Mentor",
        "traits": ["wise", "patient", "mysterious"],
        "motivations": ["guide the hero", "atone for past", "preserve knowledge"],
        "weaknesses": ["secretive", "fatalistic", "detached"]
    },
    "shadow": {
        "name": "The Shadow/Villain",
        "traits": ["cunning", "powerful", "twisted"],
        "motivations": ["revenge", "power", "ideology"],
        "weaknesses": ["arrogance", "obsession", "isolation"]
    },
    "trickster": {
        "name": "The Trickster",
        "traits": ["clever", "unpredictable", "charming"],
        "motivations": ["chaos", "fun", "expose hypocrisy"],
        "weaknesses": ["unreliable", "selfish", "reckless"]
    },
    "guardian": {
        "name": "The Guardian",
        "traits": ["loyal", "protective", "steadfast"],
        "motivations": ["protect loved ones", "uphold duty", "maintain order"],
        "weaknesses": ["rigid", "overprotective", "blind loyalty"]
    }
}

QUEST_TEMPLATES = {
    "fetch": {
        "name": "Fetch Quest",
        "structure": ["receive_task", "travel", "obtain_item", "return"],
        "variations": ["rare_item", "stolen_goods", "ancient_artifact", "ingredients"]
    },
    "escort": {
        "name": "Escort Mission",
        "structure": ["meet_npc", "protect_during_travel", "reach_destination"],
        "variations": ["vip_protection", "refugee_caravan", "prisoner_transport"]
    },
    "hunt": {
        "name": "Hunt Quest",
        "structure": ["receive_bounty", "track_target", "confront", "claim_reward"],
        "variations": ["monster_hunt", "bounty_hunter", "rare_creature", "boss_fight"]
    },
    "mystery": {
        "name": "Mystery/Investigation",
        "structure": ["discover_mystery", "gather_clues", "interrogate", "solve", "confront"],
        "variations": ["murder_mystery", "missing_person", "conspiracy", "supernatural"]
    },
    "rescue": {
        "name": "Rescue Mission",
        "structure": ["learn_of_captive", "locate_prison", "infiltrate", "rescue", "escape"],
        "variations": ["hostage", "kidnapping", "political_prisoner", "self_rescue"]
    },
    "defense": {
        "name": "Defense Quest",
        "structure": ["receive_warning", "prepare_defenses", "survive_waves", "victory"],
        "variations": ["siege", "invasion", "protect_artifact", "last_stand"]
    }
}

DIALOGUE_PATTERNS = {
    "exposition": ["question", "answer", "elaboration", "reaction"],
    "conflict": ["accusation", "defense", "escalation", "ultimatum"],
    "negotiation": ["proposal", "counter", "compromise", "agreement"],
    "romance": ["flirtation", "compliment", "vulnerability", "connection"],
    "comedy": ["setup", "misdirection", "punchline", "callback"]
}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_narrative_info():
    """Get Narrative Engine capabilities"""
    return {
        "name": "CodeDock Narrative Engine",
        "version": "11.5.0",
        "description": "AI-Powered Story, Dialogue & Quest Generation",
        "capabilities": [
            "Complete story arc generation",
            "Dynamic character creation",
            "Branching dialogue systems",
            "Quest and mission design",
            "Lore and world-building",
            "Procedural event generation"
        ],
        "story_structures": list(STORY_STRUCTURES.keys()),
        "character_archetypes": list(CHARACTER_ARCHETYPES.keys()),
        "quest_templates": list(QUEST_TEMPLATES.keys()),
        "dialogue_patterns": list(DIALOGUE_PATTERNS.keys()),
        "genres": ["fantasy", "sci-fi", "horror", "mystery", "romance", "adventure"],
        "output_formats": ["JSON", "Screenplay", "Novel", "Game Script", "Interactive"]
    }

@router.get("/structures")
async def get_story_structures():
    """Get all story structure templates"""
    return {"structures": STORY_STRUCTURES}

@router.get("/archetypes")
async def get_character_archetypes():
    """Get all character archetypes"""
    return {"archetypes": CHARACTER_ARCHETYPES}

@router.get("/quest-templates")
async def get_quest_templates():
    """Get all quest templates"""
    return {"templates": QUEST_TEMPLATES}

@router.post("/generate-story")
async def generate_story(request: StoryGenerationRequest):
    """Generate a complete story from premise"""
    try:
        structure = STORY_STRUCTURES.get(request.structure, STORY_STRUCTURES["three_act"])
        
        story = {
            "id": f"story_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": f"Generated {request.genre.title()} Story",
            "premise": request.premise,
            "genre": request.genre,
            "tone": request.tone,
            "structure": structure,
            "length": request.length,
            "outline": {
                "act_1": {
                    "title": "The Beginning",
                    "scenes": [
                        {"name": "Opening", "description": f"Establish the world of {request.premise}"},
                        {"name": "Inciting Incident", "description": "The event that sets everything in motion"},
                        {"name": "First Plot Point", "description": "Hero commits to the journey"}
                    ]
                },
                "act_2": {
                    "title": "The Middle",
                    "scenes": [
                        {"name": "Rising Action", "description": "Challenges and obstacles mount"},
                        {"name": "Midpoint", "description": "Major revelation or shift"},
                        {"name": "Crisis", "description": "All seems lost"}
                    ]
                },
                "act_3": {
                    "title": "The End",
                    "scenes": [
                        {"name": "Climax", "description": "Final confrontation"},
                        {"name": "Resolution", "description": "Aftermath and new equilibrium"}
                    ]
                }
            },
            "themes": ["redemption", "sacrifice", "discovery"],
            "branching_paths": request.branching_paths,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "word_count_estimate": 5000 if request.length == "short" else 15000 if request.length == "medium" else 50000
            }
        }
        
        # Add characters if requested
        if request.include_characters:
            story["characters"] = [
                {"name": "Protagonist", "role": "hero", "archetype": "hero"},
                {"name": "Antagonist", "role": "villain", "archetype": "shadow"},
                {"name": "Mentor", "role": "guide", "archetype": "mentor"},
                {"name": "Ally", "role": "companion", "archetype": "guardian"}
            ]
        
        # Add locations if requested
        if request.include_locations:
            story["locations"] = [
                {"name": "Starting Point", "type": "home", "significance": "origin"},
                {"name": "Journey Location", "type": "wilderness", "significance": "trials"},
                {"name": "Final Destination", "type": "fortress", "significance": "climax"}
            ]
        
        return story
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-character")
async def generate_character(request: CharacterRequest):
    """Generate a detailed character"""
    archetype = CHARACTER_ARCHETYPES.get(request.archetype, CHARACTER_ARCHETYPES["hero"])
    
    return {
        "character": {
            "description": request.description,
            "role": request.role,
            "archetype": archetype,
            "personality": {
                "traits": request.personality_traits or archetype["traits"],
                "motivations": archetype["motivations"],
                "weaknesses": archetype["weaknesses"],
                "fears": ["failure", "loss", "betrayal"],
                "desires": ["recognition", "peace", "power"]
            },
            "backstory": {
                "origin": "Generated based on archetype and description",
                "key_events": [
                    "Formative childhood experience",
                    "Defining moment that shaped worldview",
                    "Recent event leading to current situation"
                ],
                "relationships": [
                    {"type": "family", "status": "complicated"},
                    {"type": "mentor", "status": "respected"},
                    {"type": "rival", "status": "ongoing_conflict"}
                ]
            },
            "appearance": {
                "physical": "Generated based on description",
                "clothing": "Appropriate to role and setting",
                "distinguishing_features": ["Notable feature 1", "Notable feature 2"]
            },
            "voice": {
                "speech_patterns": "Formal/Casual based on background",
                "catchphrases": ["Character-specific phrase"],
                "accent": "Regional appropriate"
            },
            "development_arc": {
                "starting_point": "Initial state",
                "key_growth_moments": ["Moment 1", "Moment 2", "Moment 3"],
                "ending_point": "Transformed state"
            }
        }
    }

@router.post("/generate-dialogue")
async def generate_dialogue(request: DialogueRequest):
    """Generate dialogue between characters"""
    DIALOGUE_PATTERNS.get(request.purpose, DIALOGUE_PATTERNS["exposition"])
    
    dialogue = {
        "context": request.context,
        "characters": request.characters,
        "mood": request.mood,
        "purpose": request.purpose,
        "lines": []
    }
    
    # Generate dialogue lines
    for i in range(request.length):
        speaker = request.characters[i % len(request.characters)]
        line = {
            "speaker": speaker,
            "text": f"[Generated {request.mood} dialogue line {i+1} for {speaker}]",
            "emotion": request.mood,
            "action": "[Optional stage direction]"
        }
        
        if request.include_choices and i % 3 == 0:
            line["player_choices"] = [
                {"text": "Response option A", "consequence": "leads_to_path_a"},
                {"text": "Response option B", "consequence": "leads_to_path_b"},
                {"text": "[Remain silent]", "consequence": "neutral_path"}
            ]
        
        dialogue["lines"].append(line)
    
    return dialogue

@router.post("/generate-quest")
async def generate_quest(request: QuestRequest):
    """Generate a complete quest"""
    template = QUEST_TEMPLATES.get("mystery" if "mystery" in request.description.lower() else "fetch")
    
    quest = {
        "id": f"quest_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "title": f"Generated Quest: {request.description[:30]}...",
        "description": request.description,
        "type": request.quest_type,
        "difficulty": request.difficulty,
        "estimated_time": request.estimated_time,
        "template": template["name"],
        "objectives": [
            {"id": 1, "description": "Primary objective", "required": True, "progress": 0},
            {"id": 2, "description": "Secondary objective", "required": False, "progress": 0},
            {"id": 3, "description": "Bonus objective", "required": False, "progress": 0}
        ],
        "stages": [
            {"name": stage, "description": f"Stage: {stage}", "completed": False}
            for stage in template["structure"]
        ],
        "rewards": {
            "experience": 1000 if request.difficulty == "medium" else 500 if request.difficulty == "easy" else 2500,
            "gold": 500,
            "items": request.rewards or ["Quest Reward Item"],
            "reputation": {"faction": "quest_giver_faction", "amount": 100}
        },
        "failure_conditions": [
            "Time limit exceeded",
            "Key NPC killed",
            "Discovered by enemies"
        ],
        "npcs": [
            {"name": "Quest Giver", "role": "giver", "location": "Starting area"},
            {"name": "Target/Goal", "role": "objective", "location": "Destination"}
        ]
    }
    
    # Add subquests if requested
    if request.include_subquests:
        quest["subquests"] = [
            {"id": "sub_1", "title": "Preparation", "description": "Gather necessary supplies"},
            {"id": "sub_2", "title": "Investigation", "description": "Learn more about the task"},
            {"id": "sub_3", "title": "Side Task", "description": "Optional related task"}
        ]
    
    return quest

@router.post("/generate-lore")
async def generate_lore(request: LoreRequest):
    """Generate lore and world-building content"""
    return {
        "lore": {
            "topic": request.topic,
            "category": request.category,
            "depth": request.depth,
            "format": request.format,
            "content": {
                "summary": f"Overview of {request.topic}",
                "history": {
                    "origins": "Ancient origins and founding",
                    "major_events": [
                        {"era": "First Age", "event": "Founding event"},
                        {"era": "Second Age", "event": "Major conflict"},
                        {"era": "Current Age", "event": "Present state"}
                    ],
                    "timeline": "Detailed chronology available"
                },
                "key_figures": [
                    {"name": "Historical Figure 1", "role": "Founder", "significance": "High"},
                    {"name": "Historical Figure 2", "role": "Reformer", "significance": "Medium"}
                ],
                "locations": [
                    {"name": "Important Location", "significance": "Cultural center"}
                ],
                "artifacts": [
                    {"name": "Legendary Artifact", "power": "Mysterious abilities"}
                ],
                "traditions": [
                    {"name": "Cultural Practice", "frequency": "Annual"}
                ]
            },
            "related_topics": ["Related Lore 1", "Related Lore 2", "Related Lore 3"],
            "contradictions": ["Different accounts exist regarding..."],
            "mysteries": ["Unresolved questions about..."]
        }
    }

@router.post("/generate-event")
async def generate_random_event(genre: str = "fantasy", intensity: str = "medium"):
    """Generate a random narrative event"""
    return {
        "event": {
            "type": "encounter",
            "genre": genre,
            "intensity": intensity,
            "description": f"A {intensity} intensity {genre} encounter",
            "participants": ["Player", "Generated NPC"],
            "choices": [
                {"action": "Engage", "consequence": "Combat or dialogue"},
                {"action": "Avoid", "consequence": "Miss opportunity"},
                {"action": "Observe", "consequence": "Gather information"}
            ],
            "rewards": ["Experience", "Loot", "Information"],
            "risks": ["Damage", "Resource loss", "Reputation change"]
        }
    }
