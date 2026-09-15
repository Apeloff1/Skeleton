"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        TEXT-TO-WORLD-MANAGEMENT PIPELINE v15.5 - AI-POWERED WORLDS           ║
║                                                                              ║
║  Generate world management systems with LLM integration:                     ║
║  • AI-powered level design & streaming                                       ║
║  • Intelligent scene transitions                                             ║
║  • Dynamic world state management                                            ║
║  • Procedural environment generation                                         ║
║  • Smart instance management                                                 ║
║  • World persistence systems                                                 ║
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

router = APIRouter(prefix="/api/world-management", tags=["Text-to-World-Management v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class WorldType(str, Enum):
    OPEN_WORLD = "open_world"
    LINEAR = "linear"
    HUB_BASED = "hub_based"
    PROCEDURAL = "procedural"
    INSTANCED = "instanced"
    SEAMLESS = "seamless"


class StreamingStrategy(str, Enum):
    DISTANCE_BASED = "distance_based"
    TRIGGER_BASED = "trigger_based"
    TIME_BASED = "time_based"
    PLAYER_ACTION = "player_action"
    HYBRID = "hybrid"


class TransitionType(str, Enum):
    FADE = "fade"
    CROSS_FADE = "cross_fade"
    SLIDE = "slide"
    ZOOM = "zoom"
    PORTAL = "portal"
    SEAMLESS = "seamless"
    LOADING_SCREEN = "loading_screen"


class PersistenceType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    SESSION_ONLY = "session_only"
    CHECKPOINT = "checkpoint"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class WorldConfigRequest(BaseModel):
    world_name: str
    world_type: WorldType = WorldType.OPEN_WORLD
    size_km: float = Field(10.0, ge=0.1, le=1000.0)
    streaming_strategy: StreamingStrategy = StreamingStrategy.DISTANCE_BASED
    max_loaded_chunks: int = Field(16, ge=1, le=256)
    persistence_type: PersistenceType = PersistenceType.FULL


class LevelStreamingRequest(BaseModel):
    region_name: str
    streaming_distance: float = Field(500.0, ge=100.0, le=10000.0)
    preload_distance: float = Field(1000.0, ge=200.0, le=20000.0)
    priority: int = Field(1, ge=1, le=10)
    async_loading: bool = True


class SceneTransitionRequest(BaseModel):
    from_scene: str
    to_scene: str
    transition_type: TransitionType = TransitionType.FADE
    duration_ms: int = Field(1000, ge=100, le=10000)
    preserve_player_state: bool = True


class WorldStateRequest(BaseModel):
    state_name: str
    tracked_entities: List[str] = []
    tracked_variables: List[str] = []
    auto_save: bool = True
    save_interval_seconds: int = Field(300, ge=60, le=3600)


class EnvironmentRequest(BaseModel):
    biome: Literal["forest", "desert", "tundra", "ocean", "mountain", "urban", "fantasy", "sci_fi"]
    time_of_day_enabled: bool = True
    weather_enabled: bool = True
    day_length_minutes: int = Field(24, ge=1, le=1440)


# ============================================================================
# WORLD MANAGEMENT GENERATOR
# ============================================================================

class WorldManagementGenerator:
    """Advanced world management system generator."""

    @staticmethod
    def generate_world_config(request: WorldConfigRequest) -> Dict[str, Any]:
        """Generate complete world configuration."""
        chunk_size = 250 if request.world_type == WorldType.OPEN_WORLD else 100
        total_chunks = int((request.size_km * 1000 / chunk_size) ** 2)
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.world_name,
            "type": request.world_type.value,
            "dimensions": {
                "size_km": request.size_km,
                "chunk_size_m": chunk_size,
                "total_chunks": total_chunks,
                "height_range": [-100, 1000]
            },
            "streaming": {
                "strategy": request.streaming_strategy.value,
                "max_loaded_chunks": request.max_loaded_chunks,
                "load_radius": 3,
                "unload_radius": 5,
                "async_loading": True,
                "priority_queue": True
            },
            "persistence": {
                "type": request.persistence_type.value,
                "auto_save": True,
                "compression": True,
                "versioning": True
            },
            "lod_system": {
                "levels": [0, 50, 150, 500, 1500],
                "transition_time": 0.5,
                "streaming_priority": "distance"
            },
            "code_template": WorldManagementGenerator._generate_world_code(request)
        }

    @staticmethod
    def _generate_world_code(request: WorldConfigRequest) -> str:
        return f'''
class WorldManager:
    """World management system for {request.world_name}"""
    
    def __init__(self):
        self.loaded_chunks: Dict[Tuple[int, int], Chunk] = {{}}
        self.loading_queue: PriorityQueue = PriorityQueue()
        self.world_type = "{request.world_type.value}"
        self.max_loaded = {request.max_loaded_chunks}
    
    async def update(self, player_position: Vector3):
        """Update world streaming based on player position."""
        current_chunk = self._get_chunk_coords(player_position)
        
        # Queue nearby chunks for loading
        for offset in self._get_load_offsets():
            chunk_coords = (current_chunk[0] + offset[0], current_chunk[1] + offset[1])
            if chunk_coords not in self.loaded_chunks:
                priority = self._calculate_priority(chunk_coords, current_chunk)
                self.loading_queue.put((priority, chunk_coords))
        
        # Unload distant chunks
        await self._unload_distant_chunks(current_chunk)
        
        # Process loading queue
        await self._process_loading_queue()
    
    async def transition_to(self, target_scene: str):
        """Handle scene transition."""
        await self._save_current_state()
        await self._unload_current_scene()
        await self._load_scene(target_scene)
'''

    @staticmethod
    def generate_level_streaming(request: LevelStreamingRequest) -> Dict[str, Any]:
        """Generate level streaming configuration."""
        return {
            "id": str(uuid.uuid4()),
            "region": request.region_name,
            "streaming_config": {
                "trigger_distance": request.streaming_distance,
                "preload_distance": request.preload_distance,
                "priority": request.priority,
                "async": request.async_loading
            },
            "loading_stages": [
                {"stage": "geometry", "priority": 1, "blocking": True},
                {"stage": "textures", "priority": 2, "blocking": False},
                {"stage": "lighting", "priority": 3, "blocking": False},
                {"stage": "ai_navigation", "priority": 4, "blocking": False},
                {"stage": "audio", "priority": 5, "blocking": False}
            ],
            "memory_budget_mb": request.streaming_distance / 10,
            "dependencies": [],
            "events": {
                "on_load_start": f"on_{request.region_name}_load_start",
                "on_load_complete": f"on_{request.region_name}_load_complete",
                "on_unload": f"on_{request.region_name}_unload"
            }
        }

    @staticmethod
    def generate_scene_transition(request: SceneTransitionRequest) -> Dict[str, Any]:
        """Generate scene transition configuration."""
        return {
            "id": str(uuid.uuid4()),
            "from": request.from_scene,
            "to": request.to_scene,
            "transition": {
                "type": request.transition_type.value,
                "duration_ms": request.duration_ms,
                "easing": "ease_in_out"
            },
            "player_state": {
                "preserve": request.preserve_player_state,
                "properties": ["position", "rotation", "inventory", "health", "status_effects"]
            },
            "loading_screen": {
                "enabled": request.transition_type == TransitionType.LOADING_SCREEN,
                "tips_enabled": True,
                "progress_bar": True
            },
            "audio": {
                "fade_out_current": True,
                "fade_duration_ms": request.duration_ms // 2
            }
        }

    @staticmethod
    def generate_world_state(request: WorldStateRequest) -> Dict[str, Any]:
        """Generate world state management system."""
        return {
            "id": str(uuid.uuid4()),
            "name": request.state_name,
            "tracking": {
                "entities": request.tracked_entities,
                "variables": request.tracked_variables,
                "events": []
            },
            "persistence": {
                "auto_save": request.auto_save,
                "interval_seconds": request.save_interval_seconds,
                "format": "binary",
                "compression": "lz4"
            },
            "synchronization": {
                "mode": "eventual",
                "conflict_resolution": "server_wins"
            },
            "history": {
                "enabled": True,
                "max_snapshots": 10,
                "rewind_enabled": False
            }
        }

    @staticmethod
    def generate_environment(request: EnvironmentRequest) -> Dict[str, Any]:
        """Generate environment configuration."""
        biome_configs = {
            "forest": {"trees": 0.7, "grass": 0.9, "water": 0.2, "fog": 0.3},
            "desert": {"trees": 0.05, "grass": 0.1, "water": 0.02, "fog": 0.1},
            "tundra": {"trees": 0.2, "grass": 0.3, "water": 0.4, "fog": 0.5},
            "ocean": {"trees": 0.0, "grass": 0.0, "water": 1.0, "fog": 0.2},
            "mountain": {"trees": 0.3, "grass": 0.4, "water": 0.15, "fog": 0.6},
            "urban": {"trees": 0.1, "grass": 0.2, "water": 0.05, "fog": 0.2},
            "fantasy": {"trees": 0.5, "grass": 0.6, "water": 0.3, "fog": 0.4},
            "sci_fi": {"trees": 0.1, "grass": 0.1, "water": 0.1, "fog": 0.3}
        }
        
        return {
            "id": str(uuid.uuid4()),
            "biome": request.biome,
            "density": biome_configs.get(request.biome, biome_configs["forest"]),
            "time_system": {
                "enabled": request.time_of_day_enabled,
                "day_length_minutes": request.day_length_minutes,
                "start_time": 8.0,
                "time_scale": 1.0
            },
            "weather_system": {
                "enabled": request.weather_enabled,
                "types": ["clear", "cloudy", "rain", "storm", "fog"],
                "transition_time": 60,
                "randomization": True
            },
            "ambient": {
                "sounds": True,
                "particles": True,
                "wildlife": True
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the World Management Pipeline."""
    return {
        "pipeline": "Text-to-World-Management Pipeline v15.5",
        "description": "Generate world management systems from natural language",
        "capabilities": [
            "World configuration & setup",
            "Level streaming systems",
            "Scene transitions",
            "World state management",
            "Environment systems",
            "Instance management"
        ],
        "world_types": [w.value for w in WorldType],
        "streaming_strategies": [s.value for s in StreamingStrategy],
        "transition_types": [t.value for t in TransitionType]
    }


@router.post("/world/generate")
async def generate_world_config(request: WorldConfigRequest):
    """Generate a world configuration."""
    return {
        "success": True,
        "world_config": WorldManagementGenerator.generate_world_config(request)
    }


@router.post("/streaming/generate")
async def generate_level_streaming(request: LevelStreamingRequest):
    """Generate level streaming configuration."""
    return {
        "success": True,
        "streaming_config": WorldManagementGenerator.generate_level_streaming(request)
    }


@router.post("/transition/generate")
async def generate_scene_transition(request: SceneTransitionRequest):
    """Generate scene transition configuration."""
    return {
        "success": True,
        "transition": WorldManagementGenerator.generate_scene_transition(request)
    }


@router.post("/state/generate")
async def generate_world_state(request: WorldStateRequest):
    """Generate world state management system."""
    return {
        "success": True,
        "world_state": WorldManagementGenerator.generate_world_state(request)
    }


@router.post("/environment/generate")
async def generate_environment(request: EnvironmentRequest):
    """Generate environment configuration."""
    return {
        "success": True,
        "environment": WorldManagementGenerator.generate_environment(request)
    }


# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIWorldRegionRequest(BaseModel):
    """Request for AI-powered world region generation"""
    biome: str = Field(..., description="Biome type: forest, desert, mountain, etc.")
    size: str = Field(default="medium", description="Region size: small, medium, large")
    features: List[str] = Field(default=["village", "dungeon"], description="Features to include")
    game_genre: Optional[str] = "fantasy"
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — auto-thread matrix dials + ml_config into LLM prompt")


class AILevelDesignRequest(BaseModel):
    """Request for AI-powered level design"""
    level_type: str = Field(..., description="Type: dungeon, city, outdoor, etc.")
    objectives: List[str] = Field(default=["reach_exit"], description="Level objectives")
    difficulty: str = Field(default="medium", description="easy/medium/hard")
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — auto-thread matrix dials + ml_config into LLM prompt")


@router.post("/ai/region/generate")
async def ai_generate_world_region(request: AIWorldRegionRequest):
    """
    Generate a complete world region using AI (GPT-4o).
    Creates detailed locations, NPCs, encounters, and loot tables.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_world_region(
            biome=request.biome,
            size=request.size,
            features=request.features,
            build_id=request.build_id,
        )
        
        if result["success"]:
            return {
                "success": True,
                "world_region": result["response"],
                "ai_generated": True,
                "model": "gpt-4o",
                "generation_metadata": {
                    "biome": request.biome,
                    "size": request.size,
                    "features_count": len(request.features)
                }
            }
        else:
            # Fallback to template generation
            fallback_request = WorldGenerationRequest(
                world_type=WorldType.OPEN_WORLD,
                biome=request.biome.lower()
            )
            return {
                "success": True,
                "world_region": WorldManagementGenerator.generate_world(fallback_request),
                "ai_generated": False,
                "fallback_reason": result.get("error", "LLM unavailable")
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI world region generation failed: {str(e)}")


@router.post("/ai/level/design")
async def ai_design_level(request: AILevelDesignRequest):
    """
    Design a complete game level using AI.
    Generates layout, objectives, enemies, puzzles, and pacing.
    """
    try:
        llm_service = get_game_llm_service()
        
        result = await llm_service.generate_level_design(
            level_type=request.level_type,
            objectives=request.objectives,
            difficulty=request.difficulty,
            build_id=request.build_id,
        )
        
        if result["success"]:
            return {
                "success": True,
                "level_design": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "level_design": {
                    "level_type": request.level_type,
                    "objectives": request.objectives,
                    "difficulty": request.difficulty,
                    "template": "basic_level_template"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI level design failed: {str(e)}")
