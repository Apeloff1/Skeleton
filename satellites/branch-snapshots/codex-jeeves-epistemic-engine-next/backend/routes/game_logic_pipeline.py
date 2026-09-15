"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          TEXT-TO-GAME-LOGIC PIPELINE v15.5 - AI-POWERED MECHANICS            ║
║                                                                              ║
║  Generate complete game mechanics from natural language with LLM:            ║
║  • AI-powered rule systems and game loops                                    ║
║  • Intelligent combat mechanics design                                       ║
║  • Dynamic economy systems                                                   ║
║  • Smart progression systems                                                 ║
║  • AI behavior pattern generation                                            ║
║  • Physics and collision rules                                               ║
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
import math

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/game-logic-pipeline", tags=["Text-to-Game-Logic Pipeline v15.5"])

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class MechanicType(str, Enum):
    COMBAT = "combat"
    MOVEMENT = "movement"
    INVENTORY = "inventory"
    CRAFTING = "crafting"
    DIALOGUE = "dialogue"
    ECONOMY = "economy"
    PROGRESSION = "progression"
    PHYSICS = "physics"
    AI_BEHAVIOR = "ai_behavior"
    PUZZLE = "puzzle"
    STEALTH = "stealth"
    SURVIVAL = "survival"

class CombatStyle(str, Enum):
    TURN_BASED = "turn_based"
    REAL_TIME = "real_time"
    HYBRID = "hybrid"
    TACTICAL = "tactical"
    ACTION = "action"
    CARD_BASED = "card_based"

class ProgressionStyle(str, Enum):
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    MILESTONE = "milestone"
    SKILL_TREE = "skill_tree"
    PRESTIGE = "prestige"

# Mechanic Templates
MECHANIC_TEMPLATES = {
    MechanicType.COMBAT: {
        "turn_based": {
            "structure": "initiative_order",
            "actions_per_turn": 1,
            "time_limit": None,
            "components": ["attack", "defend", "skill", "item", "flee"],
            "damage_formula": "base_damage * (1 + strength/10) * random(0.9, 1.1)",
            "defense_formula": "incoming_damage * (1 - armor/100)",
            "critical_chance": 0.1,
            "critical_multiplier": 2.0
        },
        "real_time": {
            "structure": "continuous",
            "cooldown_based": True,
            "hitbox_detection": "AABB",
            "components": ["light_attack", "heavy_attack", "block", "dodge", "special"],
            "damage_formula": "base_damage * attack_speed * multiplier",
            "stagger_system": True,
            "combo_system": True
        },
        "tactical": {
            "structure": "grid_based",
            "movement_points": 6,
            "action_points": 2,
            "components": ["move", "attack", "overwatch", "ability", "wait"],
            "cover_system": True,
            "flanking_bonus": 1.25,
            "height_advantage": 1.15
        }
    },
    MechanicType.PROGRESSION: {
        "linear": {
            "xp_formula": "base_xp * level",
            "level_cap": 100,
            "stat_increase_per_level": 5,
            "unlock_frequency": "every_level"
        },
        "exponential": {
            "xp_formula": "base_xp * (1.5 ^ level)",
            "level_cap": 50,
            "stat_increase_per_level": 3,
            "milestone_levels": [10, 20, 30, 40, 50]
        },
        "skill_tree": {
            "points_per_level": 1,
            "tree_branches": 3,
            "nodes_per_branch": 10,
            "prerequisite_system": True,
            "respec_allowed": True
        }
    },
    MechanicType.ECONOMY: {
        "basic": {
            "currencies": ["gold"],
            "trading_enabled": True,
            "crafting_enabled": False,
            "inflation_rate": 0
        },
        "advanced": {
            "currencies": ["gold", "gems", "tokens"],
            "trading_enabled": True,
            "crafting_enabled": True,
            "auction_house": True,
            "supply_demand": True,
            "inflation_rate": 0.01
        }
    }
}

# Rule System Templates
RULE_TEMPLATES = {
    "rpg": {
        "dice_system": "d20",
        "attribute_system": ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"],
        "skill_checks": "attribute_modifier + skill_bonus + d20 >= difficulty",
        "saving_throws": True,
        "advantage_disadvantage": True
    },
    "arcade": {
        "score_based": True,
        "lives_system": True,
        "power_ups": True,
        "difficulty_scaling": "continuous"
    },
    "simulation": {
        "resource_management": True,
        "time_progression": "real_time_with_pause",
        "random_events": True,
        "feedback_loops": True
    },
    "puzzle": {
        "state_machine": True,
        "valid_moves_check": True,
        "win_condition": "goal_state_reached",
        "hint_system": True
    }
}

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class MechanicGenerationRequest(BaseModel):
    description: str = Field(..., description="Natural language description of the mechanic")
    mechanic_type: Optional[MechanicType] = None
    genre: str = "rpg"
    complexity: Literal["simple", "moderate", "complex"] = "moderate"
    target_platform: str = "all"

class CombatSystemRequest(BaseModel):
    style: CombatStyle
    include_magic: bool = True
    include_status_effects: bool = True
    party_based: bool = False
    enemy_ai_complexity: str = "moderate"

class ProgressionSystemRequest(BaseModel):
    style: ProgressionStyle
    max_level: int = 100
    include_prestige: bool = False
    skill_tree_branches: int = 3

class EconomySystemRequest(BaseModel):
    currencies: List[str] = ["gold"]
    include_trading: bool = True
    include_crafting: bool = False
    inflation_model: bool = False

class AIBehaviorRequest(BaseModel):
    entity_type: str
    behaviors: List[str] = []
    aggression_level: float = 0.5
    intelligence_level: float = 0.5

# ============================================================================
# GAME LOGIC GENERATOR ENGINE
# ============================================================================

class GameLogicGenerator:
    """
    Comprehensive game mechanics and systems generator.
    """
    
    @staticmethod
    def parse_mechanic_description(description: str) -> Dict[str, Any]:
        """Parse natural language to detect mechanic types and parameters."""
        desc_lower = description.lower()
        
        detected = {
            "mechanic_types": [],
            "combat_style": None,
            "genre_hints": [],
            "complexity_hints": [],
            "parameters": {}
        }
        
        # Detect mechanic types
        mechanic_keywords = {
            MechanicType.COMBAT: ["combat", "fight", "battle", "attack", "damage"],
            MechanicType.MOVEMENT: ["movement", "walk", "run", "jump", "climb"],
            MechanicType.INVENTORY: ["inventory", "items", "equipment", "bag"],
            MechanicType.CRAFTING: ["craft", "forge", "create", "build", "recipe"],
            MechanicType.ECONOMY: ["economy", "money", "gold", "trade", "shop"],
            MechanicType.PROGRESSION: ["level", "xp", "experience", "skill", "upgrade"],
            MechanicType.AI_BEHAVIOR: ["ai", "enemy", "behavior", "patrol", "chase"],
            MechanicType.PUZZLE: ["puzzle", "riddle", "logic", "solve"],
            MechanicType.STEALTH: ["stealth", "sneak", "hide", "detection"],
            MechanicType.SURVIVAL: ["survival", "hunger", "thirst", "stamina"]
        }
        
        for mtype, keywords in mechanic_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                detected["mechanic_types"].append(mtype)
        
        # Detect combat style
        if "turn" in desc_lower or "turn-based" in desc_lower:
            detected["combat_style"] = CombatStyle.TURN_BASED
        elif "real-time" in desc_lower or "action" in desc_lower:
            detected["combat_style"] = CombatStyle.REAL_TIME
        elif "tactical" in desc_lower or "grid" in desc_lower:
            detected["combat_style"] = CombatStyle.TACTICAL
        elif "card" in desc_lower:
            detected["combat_style"] = CombatStyle.CARD_BASED
        
        # Detect genre
        genre_keywords = {
            "rpg": ["rpg", "role-playing", "character", "stats"],
            "platformer": ["platformer", "jump", "platform"],
            "shooter": ["shooter", "fps", "gun", "shoot"],
            "strategy": ["strategy", "rts", "build", "manage"],
            "puzzle": ["puzzle", "logic", "brain"],
            "survival": ["survival", "craft", "hunger"]
        }
        
        for genre, keywords in genre_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                detected["genre_hints"].append(genre)
        
        return detected
    
    @staticmethod
    def generate_combat_system(request: CombatSystemRequest) -> Dict[str, Any]:
        """Generate a complete combat system."""
        base_template = MECHANIC_TEMPLATES[MechanicType.COMBAT].get(
            request.style.value.replace("_", "-"),
            MECHANIC_TEMPLATES[MechanicType.COMBAT]["turn_based"]
        )
        
        combat_system = {
            "id": str(uuid.uuid4()),
            "style": request.style.value,
            "core_mechanics": base_template.copy(),
            "damage_types": ["physical", "magical", "true"] if request.include_magic else ["physical"],
            "status_effects": [],
            "enemy_ai": {},
            "balance_parameters": {}
        }
        
        # Add status effects
        if request.include_status_effects:
            combat_system["status_effects"] = [
                {"name": "poison", "type": "dot", "duration": 3, "damage_per_tick": 5},
                {"name": "burn", "type": "dot", "duration": 2, "damage_per_tick": 8},
                {"name": "freeze", "type": "cc", "duration": 1, "effect": "skip_turn"},
                {"name": "stun", "type": "cc", "duration": 1, "effect": "cannot_act"},
                {"name": "bleed", "type": "dot", "duration": 5, "damage_per_tick": 3},
                {"name": "buff_attack", "type": "buff", "duration": 3, "modifier": 1.25},
                {"name": "debuff_defense", "type": "debuff", "duration": 3, "modifier": 0.75}
            ]
        
        # Add magic system
        if request.include_magic:
            combat_system["magic_system"] = {
                "resource": "mana",
                "regeneration": "per_turn",
                "schools": ["fire", "ice", "lightning", "earth", "light", "dark"],
                "spell_types": ["damage", "heal", "buff", "debuff", "summon"],
                "casting_time": request.style != CombatStyle.REAL_TIME
            }
        
        # Party mechanics
        if request.party_based:
            combat_system["party_mechanics"] = {
                "max_party_size": 4,
                "formation_system": True,
                "combo_attacks": True,
                "switch_cost": 0 if request.style == CombatStyle.TURN_BASED else 0.5,
                "shared_resources": ["items"],
                "individual_resources": ["hp", "mana"]
            }
        
        # Enemy AI
        ai_complexity_map = {
            "simple": {
                "decision_tree_depth": 2,
                "behavior_patterns": ["attack_lowest_hp", "random_target"],
                "adapts_to_player": False
            },
            "moderate": {
                "decision_tree_depth": 4,
                "behavior_patterns": ["focus_healer", "use_abilities", "retreat_low_hp"],
                "adapts_to_player": True,
                "threat_system": True
            },
            "complex": {
                "decision_tree_depth": 8,
                "behavior_patterns": ["analyze_party", "counter_strategy", "coordinate_attacks"],
                "adapts_to_player": True,
                "learning_enabled": True,
                "personality_variance": True
            }
        }
        combat_system["enemy_ai"] = ai_complexity_map.get(request.enemy_ai_complexity, ai_complexity_map["moderate"])
        
        # Balance parameters
        combat_system["balance_parameters"] = {
            "base_hp_formula": "10 + (constitution * 5) + (level * 10)",
            "base_damage_formula": "weapon_damage + (strength * 0.5)",
            "accuracy_formula": "base_accuracy + (dexterity * 2)",
            "crit_rate_base": 0.05,
            "crit_damage_multiplier": 1.5,
            "level_scaling": 1.1
        }
        
        return combat_system
    
    @staticmethod
    def generate_progression_system(request: ProgressionSystemRequest) -> Dict[str, Any]:
        """Generate a complete progression system."""
        base_template = MECHANIC_TEMPLATES[MechanicType.PROGRESSION].get(
            request.style.value,
            MECHANIC_TEMPLATES[MechanicType.PROGRESSION]["linear"]
        )
        
        progression = {
            "id": str(uuid.uuid4()),
            "style": request.style.value,
            "level_cap": request.max_level,
            "xp_table": [],
            "stat_growth": {},
            "unlocks": [],
            "skill_tree": None,
            "prestige": None
        }
        
        # Generate XP table
        base_xp = 100
        for level in range(1, request.max_level + 1):
            if request.style == ProgressionStyle.LINEAR:
                xp_required = base_xp * level
            elif request.style == ProgressionStyle.EXPONENTIAL:
                xp_required = int(base_xp * (1.5 ** level))
            elif request.style == ProgressionStyle.LOGARITHMIC:
                xp_required = int(base_xp * (level + math.log(level + 1) * 10))
            else:
                xp_required = base_xp * level
            
            progression["xp_table"].append({
                "level": level,
                "xp_required": xp_required,
                "total_xp": sum(base_xp * l for l in range(1, level + 1))
            })
        
        # Stat growth
        progression["stat_growth"] = {
            "hp_per_level": 10,
            "mana_per_level": 5,
            "stat_points_per_level": 3,
            "skill_points_per_level": 1
        }
        
        # Skill tree
        if request.style == ProgressionStyle.SKILL_TREE or request.skill_tree_branches > 0:
            branches = []
            branch_names = ["Combat", "Magic", "Utility", "Defense", "Support"][:request.skill_tree_branches]
            
            for i, name in enumerate(branch_names):
                nodes = []
                for j in range(10):
                    nodes.append({
                        "id": f"skill_{i}_{j}",
                        "name": f"{name} Skill {j+1}",
                        "tier": j // 3 + 1,
                        "cost": j + 1,
                        "prerequisites": [f"skill_{i}_{j-1}"] if j > 0 else [],
                        "effect": f"Enhances {name.lower()} capabilities"
                    })
                branches.append({
                    "id": f"branch_{i}",
                    "name": name,
                    "nodes": nodes
                })
            
            progression["skill_tree"] = {
                "branches": branches,
                "points_per_level": 1,
                "respec_cost": 100,
                "max_points": request.max_level
            }
        
        # Prestige system
        if request.include_prestige:
            progression["prestige"] = {
                "unlock_level": request.max_level,
                "prestige_levels": 10,
                "bonuses_per_prestige": {
                    "xp_multiplier": 0.1,
                    "stat_bonus": 0.05,
                    "unique_unlocks": True
                },
                "reset_on_prestige": ["level", "skills"],
                "keep_on_prestige": ["achievements", "cosmetics"]
            }
        
        return progression
    
    @staticmethod
    def generate_economy_system(request: EconomySystemRequest) -> Dict[str, Any]:
        """Generate a complete economy system."""
        economy = {
            "id": str(uuid.uuid4()),
            "currencies": {},
            "trading": None,
            "crafting": None,
            "shops": [],
            "loot_tables": {},
            "inflation": None
        }
        
        # Currency setup
        for currency in request.currencies:
            economy["currencies"][currency] = {
                "name": currency,
                "symbol": currency[0].upper(),
                "decimal_places": 0,
                "cap": 999999999,
                "sources": ["enemies", "quests", "trading"],
                "sinks": ["shops", "upgrades", "services"]
            }
        
        # Trading system
        if request.include_trading:
            economy["trading"] = {
                "player_to_npc": True,
                "player_to_player": False,
                "auction_house": False,
                "price_variance": 0.1,
                "reputation_discount": True,
                "max_discount": 0.25,
                "haggling": {
                    "enabled": True,
                    "skill_based": True,
                    "max_discount": 0.15
                }
            }
        
        # Crafting system
        if request.include_crafting:
            economy["crafting"] = {
                "stations": ["forge", "alchemy_table", "enchanting_table", "workbench"],
                "skill_based": True,
                "quality_tiers": ["common", "uncommon", "rare", "epic", "legendary"],
                "failure_chance": True,
                "recipes": {
                    "discovery": "experimentation",
                    "unlock_method": "find_or_buy",
                    "auto_craft": True
                },
                "material_grades": ["basic", "refined", "pure", "perfect"]
            }
        
        # Generate sample shop
        economy["shops"].append({
            "id": "general_store",
            "name": "General Store",
            "type": "general",
            "inventory_refresh": "daily",
            "price_modifier": 1.0,
            "buys_from_player": True,
            "buy_rate": 0.5
        })
        
        # Loot tables
        economy["loot_tables"] = {
            "common_enemy": {
                "gold": {"min": 1, "max": 10, "chance": 0.9},
                "items": {"tier": "common", "count": 1, "chance": 0.3}
            },
            "rare_enemy": {
                "gold": {"min": 50, "max": 200, "chance": 1.0},
                "items": {"tier": "uncommon", "count": 2, "chance": 0.6}
            },
            "boss": {
                "gold": {"min": 500, "max": 1000, "chance": 1.0},
                "items": {"tier": "rare", "count": 3, "chance": 1.0},
                "unique": {"chance": 0.1}
            }
        }
        
        # Inflation model
        if request.inflation_model:
            economy["inflation"] = {
                "enabled": True,
                "rate": 0.001,
                "calculation": "per_transaction",
                "price_floor": 0.5,
                "price_ceiling": 2.0,
                "reset_events": ["new_season", "economic_event"]
            }
        
        return economy
    
    @staticmethod
    def generate_ai_behavior(request: AIBehaviorRequest) -> Dict[str, Any]:
        """Generate AI behavior patterns."""
        behavior_tree = {
            "id": str(uuid.uuid4()),
            "entity_type": request.entity_type,
            "root": {
                "type": "selector",
                "children": []
            },
            "states": {},
            "parameters": {}
        }
        
        # Base behaviors by aggression
        if request.aggression_level > 0.7:
            base_behaviors = ["attack_on_sight", "pursue_aggressively", "call_reinforcements"]
        elif request.aggression_level > 0.3:
            base_behaviors = ["patrol", "investigate_noise", "attack_if_threatened"]
        else:
            base_behaviors = ["wander", "flee_if_threatened", "hide"]
        
        # Intelligence-based additions
        if request.intelligence_level > 0.7:
            base_behaviors.extend(["use_cover", "flank_target", "coordinate_with_allies", "set_traps"])
        elif request.intelligence_level > 0.3:
            base_behaviors.extend(["seek_advantage", "retreat_when_hurt"])
        
        # Combine with requested behaviors
        all_behaviors = list(set(base_behaviors + request.behaviors))
        
        # Generate behavior nodes
        for behavior in all_behaviors:
            behavior_tree["root"]["children"].append({
                "type": "sequence",
                "name": behavior,
                "children": [
                    {"type": "condition", "check": f"can_{behavior}"},
                    {"type": "action", "execute": behavior}
                ]
            })
        
        # State machine
        behavior_tree["states"] = {
            "idle": {"transitions": ["alert", "patrol"]},
            "patrol": {"transitions": ["idle", "alert", "chase"]},
            "alert": {"transitions": ["patrol", "chase", "attack"]},
            "chase": {"transitions": ["attack", "search", "return"]},
            "attack": {"transitions": ["chase", "flee", "idle"]},
            "flee": {"transitions": ["hide", "idle"]},
            "search": {"transitions": ["patrol", "chase", "idle"]}
        }
        
        # Parameters
        behavior_tree["parameters"] = {
            "sight_range": 10 + request.intelligence_level * 10,
            "hearing_range": 5 + request.intelligence_level * 5,
            "reaction_time": 0.5 - request.intelligence_level * 0.3,
            "memory_duration": 10 + request.intelligence_level * 20,
            "aggression": request.aggression_level,
            "courage": 0.5 + request.aggression_level * 0.3,
            "flee_threshold": 0.3 - request.aggression_level * 0.2
        }
        
        return behavior_tree
    
    @staticmethod
    def generate_game_rules(genre: str) -> Dict[str, Any]:
        """Generate game rules based on genre."""
        template = RULE_TEMPLATES.get(genre, RULE_TEMPLATES["rpg"])
        
        rules = {
            "id": str(uuid.uuid4()),
            "genre": genre,
            "core_rules": template,
            "win_conditions": [],
            "lose_conditions": [],
            "game_loop": {}
        }
        
        # Genre-specific conditions
        if genre == "rpg":
            rules["win_conditions"] = ["defeat_final_boss", "complete_main_quest"]
            rules["lose_conditions"] = ["party_wipe", "game_over_screen"]
            rules["game_loop"] = {
                "phases": ["exploration", "combat", "dialogue", "rest"],
                "save_system": "checkpoint_and_manual",
                "difficulty_options": ["easy", "normal", "hard", "nightmare"]
            }
        elif genre == "arcade":
            rules["win_conditions"] = ["reach_high_score", "complete_all_levels"]
            rules["lose_conditions"] = ["lose_all_lives", "time_out"]
            rules["game_loop"] = {
                "phases": ["play", "score", "retry"],
                "save_system": "high_score_only",
                "difficulty_options": ["auto_scaling"]
            }
        elif genre == "puzzle":
            rules["win_conditions"] = ["solve_all_puzzles"]
            rules["lose_conditions"] = ["give_up"]
            rules["game_loop"] = {
                "phases": ["present_puzzle", "solve", "reward"],
                "save_system": "per_puzzle",
                "difficulty_options": ["hint_frequency"]
            }
        
        return rules

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_pipeline_overview():
    """Get overview of the Text-to-Game-Logic Pipeline"""
    return {
        "pipeline": "Text-to-Game-Logic Pipeline v15.0",
        "description": "Generate complete game mechanics and systems from natural language",
        "capabilities": [
            "Combat system generation (turn-based, real-time, tactical)",
            "Progression system design (XP curves, skill trees, prestige)",
            "Economy modeling (currencies, trading, crafting)",
            "AI behavior tree generation",
            "Rule system templates",
            "Balance parameter calculation"
        ],
        "mechanic_types": [m.value for m in MechanicType],
        "combat_styles": [c.value for c in CombatStyle],
        "progression_styles": [p.value for p in ProgressionStyle],
        "co_coding_enabled": True,
        "jeeves_integration": True
    }

@router.post("/generate")
async def generate_mechanic(request: MechanicGenerationRequest):
    """Generate game mechanic from natural language description"""
    try:
        parsed = GameLogicGenerator.parse_mechanic_description(request.description)
        
        mechanic_type = request.mechanic_type
        if not mechanic_type and parsed["mechanic_types"]:
            mechanic_type = parsed["mechanic_types"][0]
        
        result = {
            "id": str(uuid.uuid4()),
            "description": request.description,
            "parsed": parsed,
            "mechanic_type": mechanic_type.value if mechanic_type else "general",
            "genre": request.genre,
            "complexity": request.complexity,
            "generated_at": datetime.utcnow().isoformat()
        }
        
        # Generate appropriate system based on type
        if mechanic_type == MechanicType.COMBAT:
            combat_style = parsed["combat_style"] or CombatStyle.TURN_BASED
            result["system"] = GameLogicGenerator.generate_combat_system(
                CombatSystemRequest(style=combat_style)
            )
        elif mechanic_type == MechanicType.PROGRESSION:
            result["system"] = GameLogicGenerator.generate_progression_system(
                ProgressionSystemRequest(style=ProgressionStyle.LINEAR)
            )
        elif mechanic_type == MechanicType.ECONOMY:
            result["system"] = GameLogicGenerator.generate_economy_system(
                EconomySystemRequest()
            )
        elif mechanic_type == MechanicType.AI_BEHAVIOR:
            result["system"] = GameLogicGenerator.generate_ai_behavior(
                AIBehaviorRequest(entity_type="enemy")
            )
        else:
            result["system"] = {
                "template": MECHANIC_TEMPLATES.get(mechanic_type, {}),
                "rules": GameLogicGenerator.generate_game_rules(request.genre)
            }
        
        return {"success": True, "mechanic": result}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/combat/generate")
async def generate_combat_system(request: CombatSystemRequest):
    """Generate a complete combat system"""
    return {
        "success": True,
        "combat_system": GameLogicGenerator.generate_combat_system(request)
    }

@router.post("/progression/generate")
async def generate_progression_system(request: ProgressionSystemRequest):
    """Generate a complete progression system"""
    return {
        "success": True,
        "progression_system": GameLogicGenerator.generate_progression_system(request)
    }

@router.post("/economy/generate")
async def generate_economy_system(request: EconomySystemRequest):
    """Generate a complete economy system"""
    return {
        "success": True,
        "economy_system": GameLogicGenerator.generate_economy_system(request)
    }

@router.post("/ai/generate")
async def generate_ai_behavior(request: AIBehaviorRequest):
    """Generate AI behavior tree"""
    return {
        "success": True,
        "behavior_tree": GameLogicGenerator.generate_ai_behavior(request)
    }

@router.get("/rules/{genre}")
async def get_game_rules(genre: str):
    """Get game rules template for genre"""
    return {
        "success": True,
        "rules": GameLogicGenerator.generate_game_rules(genre)
    }

@router.get("/templates")
async def get_all_templates():
    """Get all mechanic templates"""
    return {
        "mechanic_templates": MECHANIC_TEMPLATES,
        "rule_templates": RULE_TEMPLATES
    }


# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AICombatDesignRequest(BaseModel):
    """Request for AI-powered combat system design"""
    combat_style: str = Field(..., description="Style: turn_based, real_time, hybrid, tactical")
    mechanics: List[str] = Field(default=["basic_attack", "defend"], description="Combat mechanics to include")
    complexity: str = Field(default="moderate", description="simple/moderate/complex")
    game_genre: Optional[str] = "fantasy"


class AIProgressionDesignRequest(BaseModel):
    """Request for AI-powered progression system design"""
    game_type: str = Field(..., description="RPG, roguelike, shooter, etc.")
    progression_elements: List[str] = Field(default=["xp", "levels"], description="Elements to include")


class AIGameRulesRequest(BaseModel):
    """Request for AI-powered game rules generation"""
    game_type: str = Field(..., description="Board game, card game, etc.")
    core_mechanics: List[str] = Field(..., description="Core game mechanics")


@router.post("/ai/combat/design")
async def ai_design_combat_system(request: AICombatDesignRequest):
    """
    Design a complete combat system using AI (GPT-4o).
    Generates balanced mechanics, formulas, and implementation code.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_combat_system(
            style=request.combat_style,
            mechanics=request.mechanics,
            complexity=request.complexity
        )
        
        if result["success"]:
            return {
                "success": True,
                "combat_system": result.get("combat_system", result.get("response")),
                "ai_generated": True,
                "model": "gpt-4o",
                "design_metadata": {
                    "style": request.combat_style,
                    "complexity": request.complexity,
                    "mechanics_count": len(request.mechanics)
                }
            }
        else:
            # Fallback to template-based generation
            fallback_request = CombatSystemRequest(
                style=CombatStyle(request.combat_style) if request.combat_style in [e.value for e in CombatStyle] else CombatStyle.TURN_BASED
            )
            return {
                "success": True,
                "combat_system": GameLogicGenerator.generate_combat_system(fallback_request),
                "ai_generated": False,
                "fallback_reason": result.get("error", "LLM unavailable")
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI combat design failed: {str(e)}")


@router.post("/ai/progression/design")
async def ai_design_progression_system(request: AIProgressionDesignRequest):
    """
    Design a complete progression system using AI.
    Generates XP curves, skill trees, and unlockables.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_progression_system(
            game_type=request.game_type,
            progression_elements=request.progression_elements
        )
        
        if result["success"]:
            return {
                "success": True,
                "progression_system": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            # Fallback
            fallback_request = ProgressionSystemRequest()
            return {
                "success": True,
                "progression_system": GameLogicGenerator.generate_progression_system(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI progression design failed: {str(e)}")


@router.post("/ai/rules/generate")
async def ai_generate_game_rules(request: AIGameRulesRequest):
    """
    Generate complete game rules using AI.
    Creates balanced rules with edge case handling.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_game_rules(
            game_type=request.game_type,
            core_mechanics=request.core_mechanics
        )
        
        if result["success"]:
            return {
                "success": True,
                "game_rules": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "game_rules": GameLogicGenerator.generate_game_rules(request.game_type),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI rules generation failed: {str(e)}")


@router.post("/ai/behavior/design")
async def ai_design_ai_behavior(agent_type: str, behavior_style: str = "balanced"):
    """
    Design AI behavior trees using LLM.
    Creates intelligent enemy/NPC behavior patterns.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_ai_behavior(
            agent_type=agent_type,
            behavior_style=behavior_style
        )
        
        if result["success"]:
            return {
                "success": True,
                "behavior_design": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            # Fallback to template
            fallback_request = AIBehaviorRequest(entity_type=agent_type)
            return {
                "success": True,
                "behavior_design": GameLogicGenerator.generate_ai_behavior(fallback_request),
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI behavior design failed: {str(e)}")
