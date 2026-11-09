"""
Text-to-Logic Engine v11.5
AI-Powered Game Mechanics, Rules & AI Behavior Generation

Capabilities:
- Game mechanics generation (combat, crafting, skills)
- Rule systems (physics, economy, progression)
- AI behavior trees and state machines
- Procedural systems (loot, spawning, events)
- Balance and tuning parameters
- Game loop design
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
from enum import Enum

router = APIRouter(prefix="/api/game-logic", tags=["Logic Engine"])

# ============================================================================
# DATA MODELS
# ============================================================================

class MechanicType(str, Enum):
    COMBAT = "combat"
    CRAFTING = "crafting"
    PROGRESSION = "progression"
    ECONOMY = "economy"
    SOCIAL = "social"
    EXPLORATION = "exploration"
    PUZZLE = "puzzle"
    SURVIVAL = "survival"

class MechanicRequest(BaseModel):
    description: str
    mechanic_type: MechanicType = MechanicType.COMBAT
    complexity: str = "medium"  # simple, medium, complex, deep
    target_platform: str = "all"  # mobile, pc, console, all
    genre: str = "action_rpg"
    include_formulas: bool = True
    include_balance: bool = True

class AIBehaviorRequest(BaseModel):
    entity_type: str  # enemy, npc, companion, boss
    description: str
    behavior_style: str = "balanced"  # aggressive, defensive, balanced, support, tactical
    intelligence_level: str = "medium"  # basic, medium, advanced, boss
    include_state_machine: bool = True
    include_behavior_tree: bool = True

class RuleSystemRequest(BaseModel):
    system_type: str  # physics, economy, weather, day_night, reputation
    description: str
    realism_level: str = "arcade"  # realistic, arcade, abstract
    complexity: str = "medium"

class ProceduralSystemRequest(BaseModel):
    system_type: str  # loot, spawning, events, dungeons, names
    description: str
    randomness: float = 0.5  # 0.0 = deterministic, 1.0 = fully random
    constraints: List[str] = []

class BalanceRequest(BaseModel):
    mechanic_description: str
    player_power_curve: str = "linear"  # linear, exponential, logarithmic, s_curve
    difficulty_scaling: str = "adaptive"  # fixed, linear, adaptive, dynamic
    target_session_length: int = 30  # minutes

# ============================================================================
# LOGIC ENGINE DATABASE
# ============================================================================

MECHANIC_TEMPLATES = {
    "combat": {
        "turn_based": {
            "name": "Turn-Based Combat",
            "components": ["initiative", "action_points", "abilities", "status_effects"],
            "formulas": {
                "damage": "base_damage * (1 + strength/100) * skill_multiplier - defense",
                "hit_chance": "base_accuracy + dexterity - target_evasion",
                "critical": "base_crit_chance + luck/200"
            }
        },
        "real_time": {
            "name": "Real-Time Action Combat",
            "components": ["hitboxes", "combos", "stamina", "dodge_roll"],
            "formulas": {
                "dps": "base_damage * attack_speed * (1 + crit_chance * crit_multiplier)",
                "stamina_cost": "base_cost * (1 - efficiency/100)",
                "i_frames": "base_frames + agility/10"
            }
        },
        "tactical": {
            "name": "Tactical Grid Combat",
            "components": ["grid_movement", "cover_system", "flanking", "overwatch"],
            "formulas": {
                "accuracy": "base_accuracy - distance_penalty + height_bonus - cover_penalty",
                "damage_falloff": "base_damage * (1 - distance/max_range)",
                "flanking_bonus": "1.5 if angle > 90 else 1.25 if angle > 45 else 1.0"
            }
        }
    },
    "crafting": {
        "recipe_based": {
            "name": "Recipe-Based Crafting",
            "components": ["recipes", "materials", "workstations", "skill_requirements"],
            "formulas": {
                "success_rate": "base_rate + (skill - recipe_level) * 5",
                "quality": "base_quality * (1 + skill/100) * material_quality",
                "bonus_output": "floor(skill / 20) chance for extra item"
            }
        },
        "experimental": {
            "name": "Experimental Crafting",
            "components": ["ingredient_properties", "combinations", "discoveries"],
            "formulas": {
                "discovery_chance": "ingredient_rarity * experimentation_skill",
                "effect_strength": "sum(ingredient_potencies) * synergy_bonus",
                "stability": "100 - abs(property_a - property_b)"
            }
        }
    },
    "progression": {
        "experience_based": {
            "name": "Experience-Based Leveling",
            "components": ["experience_points", "levels", "stat_growth", "skill_points"],
            "formulas": {
                "xp_to_level": "base_xp * (level ^ 1.5)",
                "stat_increase": "base_stat + (level * growth_rate)",
                "skill_points_per_level": "base_points + floor(level / 10)"
            }
        },
        "skill_based": {
            "name": "Skill-Based Progression",
            "components": ["individual_skills", "practice_system", "mastery_levels"],
            "formulas": {
                "skill_xp": "action_difficulty * (1 + learning_bonus)",
                "mastery_threshold": "base_threshold * (mastery_level ^ 2)",
                "skill_decay": "current_skill * 0.001 * days_inactive"
            }
        }
    },
    "economy": {
        "market_based": {
            "name": "Dynamic Market Economy",
            "components": ["supply_demand", "merchants", "trading", "inflation"],
            "formulas": {
                "price": "base_price * (demand / supply) * inflation_rate",
                "demand_change": "base_demand + (popularity * 0.1) - (price * elasticity)",
                "merchant_profit": "sell_price - buy_price - overhead"
            }
        }
    }
}

AI_BEHAVIOR_TEMPLATES = {
    "patrol": {
        "name": "Patrol Behavior",
        "states": ["idle", "walking", "investigating", "returning"],
        "transitions": [
            {"from": "idle", "to": "walking", "condition": "patrol_timer_complete"},
            {"from": "walking", "to": "investigating", "condition": "noise_detected"},
            {"from": "investigating", "to": "returning", "condition": "nothing_found"}
        ]
    },
    "combat_aggressive": {
        "name": "Aggressive Combat AI",
        "states": ["idle", "chase", "attack", "pursue", "enraged"],
        "transitions": [
            {"from": "idle", "to": "chase", "condition": "player_detected"},
            {"from": "chase", "to": "attack", "condition": "in_attack_range"},
            {"from": "attack", "to": "pursue", "condition": "player_fled"},
            {"from": "*", "to": "enraged", "condition": "health < 25%"}
        ],
        "behavior_tree": {
            "type": "selector",
            "children": [
                {"type": "sequence", "name": "attack_sequence", "children": [
                    {"type": "condition", "check": "is_in_range"},
                    {"type": "action", "do": "attack_player"}
                ]},
                {"type": "sequence", "name": "chase_sequence", "children": [
                    {"type": "condition", "check": "can_see_player"},
                    {"type": "action", "do": "move_to_player"}
                ]},
                {"type": "action", "do": "patrol"}
            ]
        }
    },
    "companion": {
        "name": "Companion AI",
        "states": ["following", "combat", "healing", "gathering", "waiting"],
        "priorities": [
            {"priority": 1, "action": "heal_player_if_low"},
            {"priority": 2, "action": "attack_threats"},
            {"priority": 3, "action": "follow_player"},
            {"priority": 4, "action": "gather_nearby_items"}
        ]
    },
    "boss": {
        "name": "Boss AI",
        "phases": [
            {"phase": 1, "health_threshold": 100, "abilities": ["basic_attack", "summon_adds"]},
            {"phase": 2, "health_threshold": 60, "abilities": ["special_attack", "area_denial"]},
            {"phase": 3, "health_threshold": 30, "abilities": ["enrage", "ultimate"]}
        ],
        "mechanics": ["telegraphed_attacks", "vulnerability_windows", "add_spawns"]
    }
}

PROCEDURAL_SYSTEMS = {
    "loot": {
        "name": "Loot Generation System",
        "components": [
            "rarity_tiers",
            "item_pools",
            "modifier_system",
            "set_items"
        ],
        "rarity_weights": {
            "common": 60,
            "uncommon": 25,
            "rare": 10,
            "epic": 4,
            "legendary": 1
        },
        "formulas": {
            "drop_quality": "base_quality * (1 + luck/100) * area_modifier",
            "modifier_count": "rarity_tier + random(0, luck/50)"
        }
    },
    "spawning": {
        "name": "Enemy Spawning System",
        "components": [
            "spawn_points",
            "wave_system",
            "difficulty_scaling",
            "density_control"
        ],
        "formulas": {
            "spawn_count": "base_count * difficulty_multiplier * player_count",
            "elite_chance": "base_elite_chance + (wave_number * 0.05)",
            "respawn_time": "base_time / (1 + area_clear_bonus)"
        }
    },
    "events": {
        "name": "Random Event System",
        "event_types": [
            "world_events",
            "personal_events",
            "faction_events",
            "seasonal_events"
        ],
        "trigger_conditions": [
            "time_based",
            "location_based",
            "action_based",
            "random_chance"
        ]
    }
}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_logic_engine_info():
    """Get Logic Engine capabilities"""
    return {
        "name": "CodeDock Logic Engine",
        "version": "11.5.0",
        "description": "AI-Powered Game Mechanics, Rules & AI Behavior Generation",
        "capabilities": [
            "Combat system generation",
            "Crafting system design",
            "Progression system creation",
            "Economy simulation",
            "AI behavior trees & state machines",
            "Procedural content systems",
            "Balance and tuning tools",
            "Game loop design"
        ],
        "mechanic_types": [t.value for t in MechanicType],
        "ai_templates": list(AI_BEHAVIOR_TEMPLATES.keys()),
        "procedural_systems": list(PROCEDURAL_SYSTEMS.keys()),
        "output_formats": ["JSON", "C#", "GDScript", "Blueprints", "Lua"]
    }

@router.get("/templates")
async def get_mechanic_templates():
    """Get all mechanic templates"""
    return {"templates": MECHANIC_TEMPLATES}

@router.get("/ai-templates")
async def get_ai_templates():
    """Get all AI behavior templates"""
    return {"templates": AI_BEHAVIOR_TEMPLATES}

@router.get("/procedural")
async def get_procedural_systems():
    """Get procedural system templates"""
    return {"systems": PROCEDURAL_SYSTEMS}

@router.post("/generate-mechanic")
async def generate_mechanic(request: MechanicRequest):
    """Generate a complete game mechanic"""
    try:
        MECHANIC_TEMPLATES.get(request.mechanic_type.value, {})
        
        mechanic = {
            "id": f"mechanic_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": f"Generated {request.mechanic_type.value.title()} System",
            "description": request.description,
            "type": request.mechanic_type.value,
            "complexity": request.complexity,
            "target_platform": request.target_platform,
            "genre": request.genre,
            "components": {
                "core_loop": {
                    "input": "Player action/decision",
                    "process": "System calculation",
                    "feedback": "Visual/Audio response",
                    "reward": "Progress/Items/Experience"
                },
                "subsystems": [
                    {"name": "Primary System", "purpose": "Main mechanic functionality"},
                    {"name": "Feedback System", "purpose": "Player communication"},
                    {"name": "Progression Tie-in", "purpose": "Long-term engagement"}
                ]
            },
            "rules": [
                {"rule": "Core Rule 1", "description": "Fundamental system behavior"},
                {"rule": "Core Rule 2", "description": "Player interaction pattern"},
                {"rule": "Edge Case", "description": "Exception handling"}
            ],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "estimated_implementation_hours": 20 if request.complexity == "simple" else 40 if request.complexity == "medium" else 80
            }
        }
        
        # Add formulas if requested
        if request.include_formulas:
            mechanic["formulas"] = {
                "primary_calculation": "result = base_value * modifier * skill_bonus",
                "secondary_calculation": "effect = primary_result * (1 + bonus_percent/100)",
                "diminishing_returns": "effective_stat = stat * (1 - stat/(stat + soft_cap))"
            }
        
        # Add balance recommendations if requested
        if request.include_balance:
            mechanic["balance"] = {
                "power_curve": "Linear early, logarithmic late",
                "soft_caps": {"early_game": 50, "mid_game": 150, "end_game": 300},
                "breakpoints": [10, 25, 50, 100, 200],
                "tuning_parameters": [
                    {"param": "base_value", "default": 10, "range": [5, 20]},
                    {"param": "scaling_factor", "default": 1.5, "range": [1.2, 2.0]},
                    {"param": "cap_value", "default": 100, "range": [50, 200]}
                ]
            }
        
        return mechanic
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-ai")
async def generate_ai_behavior(request: AIBehaviorRequest):
    """Generate AI behavior system"""
    try:
        template = AI_BEHAVIOR_TEMPLATES.get(
            "boss" if request.entity_type == "boss" else 
            "companion" if request.entity_type == "companion" else
            "combat_aggressive" if request.behavior_style == "aggressive" else "patrol"
        )
        
        ai_system = {
            "id": f"ai_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": f"{request.entity_type.title()} AI - {request.behavior_style.title()}",
            "description": request.description,
            "entity_type": request.entity_type,
            "behavior_style": request.behavior_style,
            "intelligence_level": request.intelligence_level,
            "perception": {
                "sight_range": 20 if request.intelligence_level == "advanced" else 15,
                "hearing_range": 15 if request.intelligence_level == "advanced" else 10,
                "awareness": {
                    "player_detection": True,
                    "threat_assessment": request.intelligence_level in ["advanced", "boss"],
                    "ally_awareness": request.intelligence_level in ["advanced", "boss"]
                }
            },
            "decision_making": {
                "update_frequency": 0.1 if request.intelligence_level == "boss" else 0.3,
                "planning_depth": 3 if request.intelligence_level == "advanced" else 1,
                "adaptability": request.intelligence_level in ["advanced", "boss"]
            }
        }
        
        # Add state machine
        if request.include_state_machine:
            ai_system["state_machine"] = {
                "states": template.get("states", ["idle", "active", "combat"]),
                "current_state": "idle",
                "transitions": template.get("transitions", []),
                "state_behaviors": {
                    "idle": {"action": "wait", "duration": "variable"},
                    "active": {"action": "execute_behavior", "priority": "high"},
                    "combat": {"action": "engage_threat", "priority": "critical"}
                }
            }
        
        # Add behavior tree
        if request.include_behavior_tree:
            ai_system["behavior_tree"] = template.get("behavior_tree", {
                "type": "selector",
                "children": [
                    {
                        "type": "sequence",
                        "name": "combat_sequence",
                        "children": [
                            {"type": "condition", "check": "has_target"},
                            {"type": "action", "do": "engage_target"}
                        ]
                    },
                    {
                        "type": "action",
                        "do": "default_behavior"
                    }
                ]
            })
        
        return ai_system
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-rules")
async def generate_rule_system(request: RuleSystemRequest):
    """Generate a rule system"""
    return {
        "rule_system": {
            "id": f"rules_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": f"{request.system_type.title()} System",
            "description": request.description,
            "type": request.system_type,
            "realism": request.realism_level,
            "complexity": request.complexity,
            "rules": [
                {
                    "name": "Primary Rule",
                    "condition": "When X occurs",
                    "effect": "Y happens",
                    "parameters": {"intensity": 1.0, "duration": "instant"}
                },
                {
                    "name": "Secondary Rule",
                    "condition": "If condition A and B",
                    "effect": "Trigger effect C",
                    "parameters": {"chance": 0.5, "cooldown": 5.0}
                },
                {
                    "name": "Exception Rule",
                    "condition": "Edge case scenario",
                    "effect": "Special handling",
                    "parameters": {"override": True}
                }
            ],
            "interactions": [
                {"system_a": request.system_type, "system_b": "player", "interaction": "bidirectional"},
                {"system_a": request.system_type, "system_b": "environment", "interaction": "reactive"}
            ],
            "configuration": {
                "update_rate": "per_frame" if request.realism_level == "realistic" else "per_second",
                "precision": "high" if request.realism_level == "realistic" else "medium",
                "optimization": "spatial_partitioning"
            }
        }
    }

@router.post("/generate-procedural")
async def generate_procedural_system(request: ProceduralSystemRequest):
    """Generate a procedural content system"""
    system_template = PROCEDURAL_SYSTEMS.get(request.system_type, PROCEDURAL_SYSTEMS["loot"])
    
    return {
        "procedural_system": {
            "id": f"proc_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": f"Procedural {request.system_type.title()} System",
            "description": request.description,
            "type": request.system_type,
            "template": system_template,
            "randomness": request.randomness,
            "constraints": request.constraints,
            "generation_parameters": {
                "seed_based": True,
                "deterministic_option": True,
                "weighted_random": True,
                "constraint_satisfaction": len(request.constraints) > 0
            },
            "output_format": {
                "data_structure": "JSON",
                "streaming": False,
                "cacheable": True
            },
            "algorithms": [
                "weighted_random_selection",
                "perlin_noise" if request.system_type in ["spawning", "events"] else "table_lookup",
                "constraint_propagation" if request.constraints else "none"
            ]
        }
    }

@router.post("/balance")
async def generate_balance_config(request: BalanceRequest):
    """Generate balance configuration"""
    return {
        "balance": {
            "mechanic": request.mechanic_description,
            "power_curve": {
                "type": request.player_power_curve,
                "formula": {
                    "linear": "power = base + (level * growth)",
                    "exponential": "power = base * (growth ^ level)",
                    "logarithmic": "power = base + log(level) * growth",
                    "s_curve": "power = max_power / (1 + e^(-growth*(level-midpoint)))"
                }[request.player_power_curve],
                "parameters": {
                    "base": 10,
                    "growth": 1.5,
                    "soft_cap": 100,
                    "hard_cap": 200
                }
            },
            "difficulty": {
                "type": request.difficulty_scaling,
                "enemy_scaling": 1.1,
                "reward_scaling": 1.05,
                "adaptive_parameters": {
                    "death_count_adjustment": -0.05,
                    "success_streak_adjustment": 0.02,
                    "time_played_adjustment": 0.01
                } if request.difficulty_scaling == "adaptive" else {}
            },
            "session_design": {
                "target_length_minutes": request.target_session_length,
                "content_pacing": {
                    "action": 0.4,
                    "exploration": 0.3,
                    "story": 0.2,
                    "management": 0.1
                },
                "reward_frequency": f"every {request.target_session_length // 6} minutes",
                "milestone_placement": [
                    {"time": "25%", "type": "minor_achievement"},
                    {"time": "50%", "type": "major_milestone"},
                    {"time": "75%", "type": "climax_buildup"},
                    {"time": "100%", "type": "session_conclusion"}
                ]
            },
            "tuning_recommendations": [
                "Test with target demographic",
                "Implement telemetry for data-driven tuning",
                "Create difficulty presets for accessibility",
                "Monitor player retention at key friction points"
            ]
        }
    }

@router.post("/export")
async def export_logic(system_id: str, format: str = "json", engine: str = "unity"):
    """Export logic system to game engine format"""
    supported_formats = ["json", "csharp", "gdscript", "blueprints", "lua"]
    
    if format.lower() not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Use: {supported_formats}")
    
    return {
        "export": {
            "system_id": system_id,
            "format": format,
            "engine": engine,
            "status": "ready",
            "files": [
                f"{system_id}_logic.{format}",
                f"{system_id}_config.json",
                f"{system_id}_readme.md"
            ],
            "integration_notes": f"Import into {engine.title()} and configure as needed"
        }
    }
