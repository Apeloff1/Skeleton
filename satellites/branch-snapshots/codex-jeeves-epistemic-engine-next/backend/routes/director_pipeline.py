"""
╔══════════════════════════════════════════════════════════════════════════════╗
║            TEXT-TO-DIRECTOR PIPELINE v15.5 - AI CINEMATIC CONTROL            ║
║                                                                              ║
║  Generate cinematic director systems with LLM integration:                   ║
║  • AI-powered camera systems                                                 ║
║  • Intelligent cinematic sequences                                           ║
║  • Dynamic event generation                                                  ║
║  • Smart pacing control                                                      ║
║  • AI Director (like L4D)                                                    ║
║  • Adaptive tension management                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal, Tuple
from enum import Enum
import uuid
import random

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/director", tags=["Text-to-Director v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class CameraStyle(str, Enum):
    THIRD_PERSON = "third_person"
    FIRST_PERSON = "first_person"
    ISOMETRIC = "isometric"
    CINEMATIC = "cinematic"
    SIDE_SCROLLER = "side_scroller"
    TOP_DOWN = "top_down"
    DYNAMIC = "dynamic"


class ShotType(str, Enum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    OVER_SHOULDER = "over_shoulder"
    POV = "pov"
    ESTABLISHING = "establishing"
    TRACKING = "tracking"


class TensionLevel(str, Enum):
    CALM = "calm"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"
    CLIMAX = "climax"


class PacingStyle(str, Enum):
    RELAXED = "relaxed"
    STEADY = "steady"
    BUILDING = "building"
    INTENSE = "intense"
    FRANTIC = "frantic"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class CameraSystemRequest(BaseModel):
    system_name: str
    camera_style: CameraStyle = CameraStyle.THIRD_PERSON
    follow_target: bool = True
    collision_avoidance: bool = True
    smooth_factor: float = Field(0.1, ge=0.01, le=1.0)


class CinematicSequenceRequest(BaseModel):
    sequence_name: str
    duration_seconds: float = Field(10.0, ge=1.0, le=300.0)
    shots: int = Field(5, ge=1, le=50)
    dialogue: bool = True
    skippable: bool = True


class AIDirectorRequest(BaseModel):
    director_name: str
    game_genre: Literal["horror", "action", "adventure", "puzzle", "survival"] = "action"
    adaptive_difficulty: bool = True
    tension_management: bool = True
    player_profiling: bool = True


class TensionCurveRequest(BaseModel):
    curve_name: str
    duration_minutes: int = Field(30, ge=5, le=180)
    peaks: int = Field(3, ge=1, le=10)
    style: PacingStyle = PacingStyle.BUILDING


class DynamicEventRequest(BaseModel):
    event_name: str
    trigger_conditions: List[str] = []
    event_type: Literal["spawn", "ambient", "setpiece", "dialogue", "reward"] = "ambient"
    intensity: TensionLevel = TensionLevel.MEDIUM


# ============================================================================
# DIRECTOR GENERATOR
# ============================================================================

class DirectorGenerator:
    """Advanced cinematic director generation engine."""

    @staticmethod
    def generate_camera_system(request: CameraSystemRequest) -> Dict[str, Any]:
        """Generate a camera system configuration."""
        style_configs = {
            CameraStyle.THIRD_PERSON: {
                "distance": 5.0,
                "height": 2.0,
                "fov": 60,
                "orbit_enabled": True
            },
            CameraStyle.FIRST_PERSON: {
                "distance": 0,
                "height": 1.7,
                "fov": 90,
                "head_bob": True
            },
            CameraStyle.ISOMETRIC: {
                "distance": 20.0,
                "angle": 45,
                "fov": 30,
                "orthographic": True
            },
            CameraStyle.CINEMATIC: {
                "distance": "variable",
                "fov": 40,
                "letterbox": True,
                "depth_of_field": True
            }
        }
        
        config = style_configs.get(request.camera_style, style_configs[CameraStyle.THIRD_PERSON])
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.system_name,
            "style": request.camera_style.value,
            "config": config,
            "follow": {
                "enabled": request.follow_target,
                "smooth_time": request.smooth_factor,
                "look_ahead": 2.0,
                "dead_zone": 0.5
            },
            "collision": {
                "enabled": request.collision_avoidance,
                "layers": ["environment", "props"],
                "push_forward": True,
                "clip_planes": {"near": 0.1, "far": 1000}
            },
            "shake": {
                "trauma_decay": 0.5,
                "max_angle": 5,
                "max_offset": 0.5,
                "frequency": 20
            },
            "transitions": {
                "blend_time": 0.5,
                "curve": "ease_in_out"
            }
        }

    @staticmethod
    def generate_cinematic_sequence(request: CinematicSequenceRequest) -> Dict[str, Any]:
        """Generate a cinematic sequence."""
        shot_types = list(ShotType)
        shot_duration = request.duration_seconds / request.shots
        
        shots = []
        for i in range(request.shots):
            shot_type = random.choice(shot_types)
            shots.append({
                "index": i + 1,
                "shot_type": shot_type.value,
                "duration": shot_duration + random.uniform(-1, 1),
                "start_time": i * shot_duration,
                "camera_movement": random.choice(["static", "pan", "dolly", "crane"]),
                "focus_target": "character_a" if i % 2 == 0 else "character_b"
            })
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.sequence_name,
            "duration": request.duration_seconds,
            "shots": shots,
            "dialogue": {
                "enabled": request.dialogue,
                "subtitle": True,
                "voice_acted": True
            },
            "playback": {
                "skippable": request.skippable,
                "pauseable": True,
                "letterbox": True
            },
            "audio": {
                "music_track": f"{request.sequence_name}_music",
                "ambient": True,
                "sfx": True
            },
            "triggers": {
                "on_start": [],
                "on_end": [],
                "on_skip": []
            }
        }

    @staticmethod
    def generate_ai_director(request: AIDirectorRequest) -> Dict[str, Any]:
        """Generate an AI director system."""
        genre_configs = {
            "horror": {
                "tension_target": 0.7,
                "quiet_periods": True,
                "jump_scares": True,
                "enemy_spawning": "rare_but_impactful"
            },
            "action": {
                "tension_target": 0.6,
                "combat_frequency": "high",
                "set_pieces": True,
                "enemy_spawning": "waves"
            },
            "survival": {
                "tension_target": 0.8,
                "resource_scarcity": True,
                "threat_constant": True,
                "enemy_spawning": "adaptive"
            },
            "adventure": {
                "tension_target": 0.4,
                "exploration_rewards": True,
                "puzzle_hints": True,
                "enemy_spawning": "scripted"
            },
            "puzzle": {
                "tension_target": 0.3,
                "hint_system": True,
                "time_pressure": False,
                "enemy_spawning": "none"
            }
        }
        
        genre_config = genre_configs.get(request.game_genre, genre_configs["action"])
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.director_name,
            "genre": request.game_genre,
            "config": genre_config,
            "adaptive_difficulty": {
                "enabled": request.adaptive_difficulty,
                "metrics": ["deaths", "completion_time", "damage_taken", "resources_used"],
                "adjustment_rate": 0.1,
                "bounds": {"min": 0.5, "max": 1.5}
            },
            "tension_system": {
                "enabled": request.tension_management,
                "current_tension": 0.5,
                "target_tension": genre_config["tension_target"],
                "decay_rate": 0.01,
                "build_rate": 0.05
            },
            "player_profiling": {
                "enabled": request.player_profiling,
                "tracked_behaviors": ["aggression", "exploration", "caution", "speed"],
                "adaptation_delay": 60
            },
            "event_queue": {
                "max_size": 10,
                "cooldowns": {},
                "priority_system": True
            }
        }

    @staticmethod
    def generate_tension_curve(request: TensionCurveRequest) -> Dict[str, Any]:
        """Generate a tension curve."""
        total_points = request.duration_minutes * 2  # 2 points per minute
        curve_points = []
        
        peak_positions = sorted([random.uniform(0.1, 0.9) for _ in range(request.peaks)])
        
        style_configs = {
            PacingStyle.RELAXED: {"base": 0.2, "variation": 0.1, "peak_height": 0.5},
            PacingStyle.STEADY: {"base": 0.4, "variation": 0.15, "peak_height": 0.7},
            PacingStyle.BUILDING: {"base": 0.3, "variation": 0.2, "peak_height": 0.9},
            PacingStyle.INTENSE: {"base": 0.6, "variation": 0.2, "peak_height": 1.0},
            PacingStyle.FRANTIC: {"base": 0.7, "variation": 0.25, "peak_height": 1.0}
        }
        
        config = style_configs[request.style]
        
        for i in range(total_points):
            normalized_time = i / total_points
            
            # Base tension with building factor
            if request.style == PacingStyle.BUILDING:
                base = config["base"] + normalized_time * 0.3
            else:
                base = config["base"]
            
            # Check if near a peak
            near_peak = any(abs(normalized_time - peak) < 0.05 for peak in peak_positions)
            
            if near_peak:
                tension = config["peak_height"]
            else:
                tension = base + random.uniform(-config["variation"], config["variation"])
            
            curve_points.append({
                "time_normalized": normalized_time,
                "time_minutes": normalized_time * request.duration_minutes,
                "tension": max(0, min(1, tension))
            })
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.curve_name,
            "duration_minutes": request.duration_minutes,
            "style": request.style.value,
            "peaks": request.peaks,
            "curve": curve_points,
            "analysis": {
                "average_tension": sum(p["tension"] for p in curve_points) / len(curve_points),
                "max_tension": max(p["tension"] for p in curve_points),
                "min_tension": min(p["tension"] for p in curve_points)
            }
        }

    @staticmethod
    def generate_dynamic_event(request: DynamicEventRequest) -> Dict[str, Any]:
        """Generate a dynamic event."""
        event_type_configs = {
            "spawn": {
                "entity_types": ["enemy", "ally", "neutral"],
                "spawn_points": "dynamic",
                "count": "adaptive"
            },
            "ambient": {
                "sound_effect": True,
                "visual_effect": True,
                "duration": "temporary"
            },
            "setpiece": {
                "scripted": True,
                "destructible": True,
                "camera_event": True
            },
            "dialogue": {
                "characters": [],
                "interruptible": True,
                "voiced": True
            },
            "reward": {
                "loot_table": "dynamic",
                "quantity": "scaled",
                "rarity": "variable"
            }
        }
        
        intensity_scaling = {
            TensionLevel.CALM: 0.2,
            TensionLevel.LOW: 0.4,
            TensionLevel.MEDIUM: 0.6,
            TensionLevel.HIGH: 0.8,
            TensionLevel.EXTREME: 1.0,
            TensionLevel.CLIMAX: 1.2
        }
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.event_name,
            "type": request.event_type,
            "intensity": request.intensity.value,
            "intensity_scale": intensity_scaling[request.intensity],
            "triggers": {
                "conditions": request.trigger_conditions or ["tension_threshold", "player_action"],
                "probability": 1.0,
                "cooldown_seconds": 30
            },
            "config": event_type_configs[request.event_type],
            "feedback": {
                "audio_cue": True,
                "visual_cue": True,
                "haptic": request.intensity.value in ["high", "extreme", "climax"]
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the Director Pipeline."""
    return {
        "pipeline": "Text-to-Director Pipeline v15.5",
        "description": "Generate cinematic director systems from natural language",
        "capabilities": [
            "Camera system generation",
            "Cinematic sequences",
            "AI director systems",
            "Tension curve design",
            "Dynamic event generation"
        ],
        "camera_styles": [c.value for c in CameraStyle],
        "shot_types": [s.value for s in ShotType],
        "tension_levels": [t.value for t in TensionLevel]
    }


@router.post("/camera/generate")
async def generate_camera_system(request: CameraSystemRequest):
    """Generate a camera system."""
    return {
        "success": True,
        "camera_system": DirectorGenerator.generate_camera_system(request)
    }


@router.post("/cinematic/generate")
async def generate_cinematic_sequence(request: CinematicSequenceRequest):
    """Generate a cinematic sequence."""
    return {
        "success": True,
        "cinematic_sequence": DirectorGenerator.generate_cinematic_sequence(request)
    }


@router.post("/ai-director/generate")
async def generate_ai_director(request: AIDirectorRequest):
    """Generate an AI director system."""
    return {
        "success": True,
        "ai_director": DirectorGenerator.generate_ai_director(request)
    }


@router.post("/tension-curve/generate")
async def generate_tension_curve(request: TensionCurveRequest):
    """Generate a tension curve."""
    return {
        "success": True,
        "tension_curve": DirectorGenerator.generate_tension_curve(request)
    }


@router.post("/dynamic-event/generate")
async def generate_dynamic_event(request: DynamicEventRequest):
    """Generate a dynamic event."""
    return {
        "success": True,
        "dynamic_event": DirectorGenerator.generate_dynamic_event(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIDirectorSystemRequest(BaseModel):
    """Request for AI-powered director system design"""
    game_type: str = Field(..., description="horror, action, narrative, etc.")


@router.post("/ai/director/design")
async def ai_design_director_system(request: AIDirectorSystemRequest):
    """
    Design an AI Director system (like L4D's AI Director) using GPT-4o.
    Creates intelligent pacing and difficulty management.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_director_system(
            game_type=request.game_type
        )
        
        if result["success"]:
            return {
                "success": True,
                "director_system": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "director_system": {
                    "game_type": request.game_type,
                    "template": "basic_director"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI director design failed: {str(e)}")
