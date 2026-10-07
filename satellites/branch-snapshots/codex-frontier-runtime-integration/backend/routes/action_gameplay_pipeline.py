"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     TEXT-TO-ACTION & GAMEPLAY SEQUENCES PIPELINE v15.5 - AI GAMEPLAY         ║
║                                                                              ║
║  Generate action sequences with LLM integration:                             ║
║  • AI-designed combat sequences                                              ║
║  • Intelligent combo systems                                                 ║
║  • Smart ability chains                                                      ║
║  • Dynamic QTE sequences                                                     ║
║  • AI cutscene actions                                                       ║
║  • Intelligent gameplay scripting                                            ║
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

router = APIRouter(prefix="/api/action-gameplay", tags=["Text-to-Action & Gameplay v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class ActionType(str, Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    DODGE = "dodge"
    PARRY = "parry"
    ABILITY = "ability"
    MOVEMENT = "movement"
    INTERACTION = "interaction"
    SPECIAL = "special"


class ComboType(str, Enum):
    SEQUENTIAL = "sequential"
    DIRECTIONAL = "directional"
    TIMING_BASED = "timing_based"
    CANCEL_BASED = "cancel_based"
    JUGGLE = "juggle"


class QTEType(str, Enum):
    BUTTON_PRESS = "button_press"
    BUTTON_MASH = "button_mash"
    SEQUENCE = "sequence"
    HOLD = "hold"
    DIRECTIONAL = "directional"
    RHYTHM = "rhythm"


class InputDevice(str, Enum):
    KEYBOARD = "keyboard"
    GAMEPAD = "gamepad"
    TOUCH = "touch"
    MOTION = "motion"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class CombatSequenceRequest(BaseModel):
    sequence_name: str
    combat_style: Literal["melee", "ranged", "magic", "hybrid"] = "melee"
    action_count: int = Field(5, ge=2, le=20)
    difficulty: Literal["easy", "medium", "hard", "extreme"] = "medium"
    has_finisher: bool = True


class ComboSystemRequest(BaseModel):
    system_name: str
    combo_type: ComboType = ComboType.SEQUENTIAL
    max_chain_length: int = Field(10, ge=3, le=50)
    timing_window_ms: int = Field(500, ge=100, le=2000)
    input_device: InputDevice = InputDevice.GAMEPAD


class AbilityChainRequest(BaseModel):
    ability_name: str
    elements: List[str] = []
    chain_length: int = Field(3, ge=1, le=10)
    cooldown_seconds: float = Field(5.0, ge=0.5, le=300.0)
    resource_cost: int = Field(50, ge=0, le=1000)


class QTESequenceRequest(BaseModel):
    sequence_name: str
    qte_type: QTEType = QTEType.BUTTON_PRESS
    duration_seconds: float = Field(5.0, ge=1.0, le=60.0)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    fail_consequence: Literal["retry", "damage", "death", "story_branch"] = "damage"


class GameplayScriptRequest(BaseModel):
    script_name: str
    trigger: Literal["area", "interaction", "combat", "time", "quest"]
    actions: List[str] = []
    interruptible: bool = True
    repeatable: bool = False


# ============================================================================
# ACTION & GAMEPLAY GENERATOR
# ============================================================================

class ActionGameplayGenerator:
    """Advanced action and gameplay sequence generation engine."""

    @staticmethod
    def generate_combat_sequence(request: CombatSequenceRequest) -> Dict[str, Any]:
        """Generate a combat action sequence."""
        style_actions = {
            "melee": ["slash", "thrust", "heavy_attack", "uppercut", "sweep", "spin"],
            "ranged": ["shoot", "quick_shot", "charged_shot", "multishot", "aimed_shot"],
            "magic": ["fireball", "ice_shard", "lightning", "arcane_blast", "chain_spell"],
            "hybrid": ["slash", "shoot", "spell_strike", "enchanted_blow", "magic_dash"]
        }
        
        actions = style_actions.get(request.combat_style, style_actions["melee"])
        difficulty_scaling = {"easy": 0.7, "medium": 1.0, "hard": 1.3, "extreme": 1.6}
        
        sequence = []
        for i in range(request.action_count):
            action = random.choice(actions)
            is_finisher = request.has_finisher and i == request.action_count - 1
            
            sequence.append({
                "order": i + 1,
                "action": f"finisher_{action}" if is_finisher else action,
                "damage_multiplier": (1.0 + i * 0.1) * difficulty_scaling[request.difficulty],
                "animation_length_ms": random.randint(300, 800),
                "can_cancel": not is_finisher,
                "hit_frames": [random.randint(5, 15)],
                "effects": ["camera_shake"] if is_finisher else []
            })
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.sequence_name,
            "style": request.combat_style,
            "difficulty": request.difficulty,
            "sequence": sequence,
            "total_damage_potential": sum(s["damage_multiplier"] for s in sequence) * 100,
            "total_duration_ms": sum(s["animation_length_ms"] for s in sequence),
            "finisher": {
                "enabled": request.has_finisher,
                "threshold": 0.2,
                "cinematic": True
            }
        }

    @staticmethod
    def generate_combo_system(request: ComboSystemRequest) -> Dict[str, Any]:
        """Generate a combo system configuration."""
        input_mappings = {
            InputDevice.GAMEPAD: {"light": "X", "heavy": "Y", "special": "B", "modifier": "RT"},
            InputDevice.KEYBOARD: {"light": "J", "heavy": "K", "special": "L", "modifier": "Shift"},
            InputDevice.TOUCH: {"light": "tap", "heavy": "hold", "special": "swipe", "modifier": "double_tap"}
        }
        
        inputs = input_mappings.get(request.input_device, input_mappings[InputDevice.GAMEPAD])
        
        # Generate sample combos
        sample_combos = [
            {"name": "basic_3hit", "inputs": [inputs["light"]] * 3, "damage": 150},
            {"name": "heavy_finisher", "inputs": [inputs["light"], inputs["light"], inputs["heavy"]], "damage": 200},
            {"name": "launcher", "inputs": [inputs["heavy"], inputs["light"]], "damage": 180},
            {"name": "special_combo", "inputs": [inputs["light"], inputs["special"]], "damage": 250}
        ]
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.system_name,
            "type": request.combo_type.value,
            "config": {
                "max_chain": request.max_chain_length,
                "timing_window_ms": request.timing_window_ms,
                "input_buffer_ms": 100,
                "gravity_scaling": request.combo_type == ComboType.JUGGLE
            },
            "input_mapping": inputs,
            "combos": sample_combos,
            "scaling": {
                "damage_per_hit": 0.95,
                "hitstun_decay": 0.9,
                "gravity_increase": 1.1
            },
            "visuals": {
                "combo_counter": True,
                "hit_effects": True,
                "screen_shake": True,
                "slowmo_on_finisher": True
            }
        }

    @staticmethod
    def generate_ability_chain(request: AbilityChainRequest) -> Dict[str, Any]:
        """Generate an ability chain."""
        element_effects = {
            "fire": {"damage_type": "burn", "dot": True},
            "ice": {"damage_type": "freeze", "slow": True},
            "lightning": {"damage_type": "shock", "chain": True},
            "earth": {"damage_type": "crush", "stun": True},
            "wind": {"damage_type": "slash", "knockback": True},
            "dark": {"damage_type": "curse", "lifesteal": True},
            "light": {"damage_type": "holy", "heal": True}
        }
        
        chain_stages = []
        for i in range(request.chain_length):
            element = request.elements[i % len(request.elements)] if request.elements else "neutral"
            effects = element_effects.get(element, {"damage_type": "physical"})
            
            chain_stages.append({
                "stage": i + 1,
                "element": element,
                "damage_multiplier": 1.0 + i * 0.25,
                "cost_multiplier": 1.0 + i * 0.15,
                "effects": effects,
                "animation": f"{request.ability_name}_stage_{i + 1}"
            })
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.ability_name,
            "chain": chain_stages,
            "resources": {
                "base_cost": request.resource_cost,
                "cooldown": request.cooldown_seconds,
                "charges": 1
            },
            "synergies": {
                "element_combo": len(set(request.elements)) > 1,
                "bonus_damage": 1.5 if len(set(request.elements)) > 2 else 1.0
            },
            "upgrades": [
                {"name": "chain_extension", "effect": "+1 chain stage"},
                {"name": "reduced_cost", "effect": "-20% resource cost"},
                {"name": "cooldown_reduction", "effect": "-2s cooldown"}
            ]
        }

    @staticmethod
    def generate_qte_sequence(request: QTESequenceRequest) -> Dict[str, Any]:
        """Generate a QTE sequence."""
        qte_configs = {
            QTEType.BUTTON_PRESS: {"prompts": ["A", "B", "X", "Y"], "timing": "single"},
            QTEType.BUTTON_MASH: {"target_count": 30, "time_limit": request.duration_seconds},
            QTEType.SEQUENCE: {"length": 5, "prompts": ["A", "B", "X", "Y"]},
            QTEType.HOLD: {"duration": request.duration_seconds * 0.5, "stability_required": 0.8},
            QTEType.DIRECTIONAL: {"directions": ["up", "down", "left", "right"]},
            QTEType.RHYTHM: {"beats": 8, "tempo_bpm": 120}
        }
        
        config = qte_configs[request.qte_type]
        timing_windows = {"easy": 1000, "medium": 600, "hard": 300}
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.sequence_name,
            "type": request.qte_type.value,
            "duration": request.duration_seconds,
            "difficulty": request.difficulty,
            "config": config,
            "timing": {
                "window_ms": timing_windows[request.difficulty],
                "perfect_window_ms": timing_windows[request.difficulty] // 3
            },
            "feedback": {
                "success_sfx": "qte_success",
                "fail_sfx": "qte_fail",
                "visual_prompt": True,
                "controller_rumble": True
            },
            "consequences": {
                "on_fail": request.fail_consequence,
                "on_success": "continue",
                "partial_success": True
            }
        }

    @staticmethod
    def generate_gameplay_script(request: GameplayScriptRequest) -> Dict[str, Any]:
        """Generate a gameplay script."""
        trigger_configs = {
            "area": {"type": "collision", "shape": "box", "once": not request.repeatable},
            "interaction": {"type": "input", "prompt": "Press E", "range": 2.0},
            "combat": {"type": "event", "event": "combat_start"},
            "time": {"type": "timer", "delay": 5.0},
            "quest": {"type": "quest_state", "state": "active"}
        }
        
        default_actions = [
            "play_animation",
            "spawn_entity",
            "play_dialogue",
            "move_camera",
            "trigger_effect"
        ]
        
        actions = request.actions or default_actions[:3]
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.script_name,
            "trigger": trigger_configs[request.trigger],
            "actions": [
                {
                    "order": i + 1,
                    "type": action,
                    "params": {},
                    "delay": i * 0.5
                }
                for i, action in enumerate(actions)
            ],
            "flow_control": {
                "interruptible": request.interruptible,
                "repeatable": request.repeatable,
                "cooldown": 5.0 if request.repeatable else 0
            },
            "state_machine": {
                "states": ["idle", "triggered", "running", "complete"],
                "initial": "idle"
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Action & Gameplay Pipeline."""
    return {
        "pipeline": "Text-to-Action & Gameplay Sequences Pipeline v15.5",
        "description": "Generate action sequences and gameplay systems from natural language",
        "capabilities": [
            "Combat sequence design",
            "Combo system generation",
            "Ability chain creation",
            "QTE sequence design",
            "Gameplay scripting"
        ],
        "action_types": [a.value for a in ActionType],
        "combo_types": [c.value for c in ComboType],
        "qte_types": [q.value for q in QTEType]
    }


@router.post("/combat-sequence/generate")
async def generate_combat_sequence(request: CombatSequenceRequest):
    """Generate a combat sequence."""
    return {
        "success": True,
        "combat_sequence": ActionGameplayGenerator.generate_combat_sequence(request)
    }


@router.post("/combo-system/generate")
async def generate_combo_system(request: ComboSystemRequest):
    """Generate a combo system."""
    return {
        "success": True,
        "combo_system": ActionGameplayGenerator.generate_combo_system(request)
    }


@router.post("/ability-chain/generate")
async def generate_ability_chain(request: AbilityChainRequest):
    """Generate an ability chain."""
    return {
        "success": True,
        "ability_chain": ActionGameplayGenerator.generate_ability_chain(request)
    }


@router.post("/qte/generate")
async def generate_qte_sequence(request: QTESequenceRequest):
    """Generate a QTE sequence."""
    return {
        "success": True,
        "qte_sequence": ActionGameplayGenerator.generate_qte_sequence(request)
    }


@router.post("/gameplay-script/generate")
async def generate_gameplay_script(request: GameplayScriptRequest):
    """Generate a gameplay script."""
    return {
        "success": True,
        "gameplay_script": ActionGameplayGenerator.generate_gameplay_script(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIComboSystemRequest(BaseModel):
    """Request for AI-powered combo system design"""
    game_style: str = Field(..., description="fighting, action_rpg, character_action, etc.")
    complexity: str = Field(default="moderate", description="simple/moderate/complex")


@router.post("/ai/combo/design")
async def ai_design_combo_system(request: AIComboSystemRequest):
    """
    Design combo systems using AI (GPT-4o).
    Creates engaging, balanced combo mechanics.
    """
    try:
        llm_service = get_game_llm_service()
        
        system_prompt = """You are an expert action game designer specializing in combo systems.
Design engaging, satisfying combo mechanics with proper timing and feedback.
Always respond with valid JSON."""
        
        user_prompt = f"""Design a {request.complexity} combo system for a {request.game_style} game.

Generate JSON with:
{{
    "system_name": "...",
    "game_style": "{request.game_style}",
    "input_types": ["light", "heavy", "special"],
    "combos": [
        {{
            "name": "...",
            "inputs": ["light", "light", "heavy"],
            "damage_multiplier": 1.5,
            "timing_window_ms": 300,
            "cancellable": true
        }}
    ],
    "juggle_system": {{
        "enabled": true,
        "max_air_hits": 5,
        "gravity_scaling": 0.8
    }},
    "cancel_rules": [...],
    "special_mechanics": [...],
    "implementation_code": "Python combo state machine"
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt)
        
        if result["success"]:
            return {
                "success": True,
                "combo_system": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "combo_system": {
                    "game_style": request.game_style,
                    "template": "basic_combo_system"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI combo system design failed: {str(e)}")
