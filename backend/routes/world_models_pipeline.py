"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          TEXT-TO-WORLD-MODELS PIPELINE v15.5 - AI 3D ENVIRONMENTS            ║
║                                                                              ║
║  Generate 3D world models with LLM integration:                              ║
║  • AI-powered terrain generation                                             ║
║  • Intelligent building/structure placement                                  ║
║  • Smart vegetation systems                                                  ║
║  • AI props and decoration                                                   ║
║  • Dynamic lighting and atmosphere                                           ║
║  • Optimized LOD systems                                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal, Tuple
from enum import Enum
import uuid
import random
import math

# Import LLM service
from services.game_llm_service import get_game_llm_service

router = APIRouter(prefix="/api/world-models", tags=["Text-to-World-Models v15.5"])


# ============================================================================
# ENUMS & TYPE DEFINITIONS
# ============================================================================

class TerrainType(str, Enum):
    HEIGHTMAP = "heightmap"
    VOXEL = "voxel"
    MARCHING_CUBES = "marching_cubes"
    PROCEDURAL_MESH = "procedural_mesh"
    HYBRID = "hybrid"


class BiomeType(str, Enum):
    PLAINS = "plains"
    FOREST = "forest"
    DESERT = "desert"
    TUNDRA = "tundra"
    JUNGLE = "jungle"
    MOUNTAINS = "mountains"
    SWAMP = "swamp"
    VOLCANIC = "volcanic"
    OCEAN = "ocean"
    URBAN = "urban"


class LODStrategy(str, Enum):
    DISTANCE_BASED = "distance_based"
    SCREEN_COVERAGE = "screen_coverage"
    HYBRID = "hybrid"
    MANUAL = "manual"


class PropDensity(str, Enum):
    SPARSE = "sparse"
    NORMAL = "normal"
    DENSE = "dense"
    VERY_DENSE = "very_dense"


# ============================================================================
# REQUEST MODELS
# ============================================================================

class TerrainRequest(BaseModel):
    terrain_name: str
    terrain_type: TerrainType = TerrainType.HEIGHTMAP
    size_km: float = Field(4.0, ge=0.1, le=100.0)
    resolution: int = Field(1024, ge=128, le=8192)
    max_height: float = Field(1000.0, ge=10.0, le=10000.0)
    seed: Optional[int] = None


class BiomeRequest(BaseModel):
    biome_type: BiomeType
    blend_edges: bool = True
    vegetation_density: PropDensity = PropDensity.NORMAL
    rock_formations: bool = True
    water_features: bool = True


class BuildingRequest(BaseModel):
    building_type: Literal["house", "tower", "castle", "ruins", "modern", "industrial", "fantasy"]
    style: str = "medieval"
    size: Literal["small", "medium", "large", "massive"] = "medium"
    interior_enabled: bool = True
    destructible: bool = False


class VegetationRequest(BaseModel):
    biome: BiomeType
    density: PropDensity = PropDensity.NORMAL
    tree_types: List[str] = []
    grass_enabled: bool = True
    flowers_enabled: bool = True
    wind_animation: bool = True


class AtmosphereRequest(BaseModel):
    time_of_day: float = Field(12.0, ge=0.0, le=24.0)
    weather: Literal["clear", "cloudy", "rain", "storm", "fog", "snow"] = "clear"
    season: Literal["spring", "summer", "autumn", "winter"] = "summer"
    volumetric_lighting: bool = True


class LODRequest(BaseModel):
    target_object: str
    strategy: LODStrategy = LODStrategy.DISTANCE_BASED
    lod_levels: int = Field(4, ge=2, le=8)
    max_distance: float = Field(1000.0, ge=100.0, le=10000.0)
    transition_type: Literal["instant", "dither", "cross_fade"] = "cross_fade"


# ============================================================================
# WORLD MODELS GENERATOR
# ============================================================================

class WorldModelsGenerator:
    """Advanced 3D world models generation engine."""

    @staticmethod
    def generate_terrain(request: TerrainRequest) -> Dict[str, Any]:
        """Generate terrain configuration."""
        seed = request.seed or random.randint(1, 999999)
        
        return {
            "id": str(uuid.uuid4()),
            "name": request.terrain_name,
            "type": request.terrain_type.value,
            "dimensions": {
                "size_km": request.size_km,
                "resolution": request.resolution,
                "max_height": request.max_height,
                "heightmap_resolution": request.resolution
            },
            "generation": {
                "seed": seed,
                "algorithm": "multi_octave_perlin" if request.terrain_type == TerrainType.HEIGHTMAP else "density_function",
                "noise_layers": [
                    {"name": "continental", "scale": 0.001, "weight": 1.0},
                    {"name": "mountains", "scale": 0.01, "weight": 0.5},
                    {"name": "hills", "scale": 0.05, "weight": 0.25},
                    {"name": "detail", "scale": 0.2, "weight": 0.1}
                ],
                "erosion": {
                    "enabled": True,
                    "iterations": 50000,
                    "types": ["hydraulic", "thermal"]
                }
            },
            "rendering": {
                "tessellation": True,
                "displacement_mapping": True,
                "normal_mapping": True,
                "triplanar_texturing": True
            },
            "optimization": {
                "chunking": True,
                "chunk_size": 256,
                "streaming": True,
                "gpu_culling": True
            }
        }

    @staticmethod
    def generate_biome(request: BiomeRequest) -> Dict[str, Any]:
        """Generate biome configuration."""
        biome_configs = {
            BiomeType.PLAINS: {
                "grass_density": 0.9,
                "tree_density": 0.1,
                "temperature": 20,
                "humidity": 0.5
            },
            BiomeType.FOREST: {
                "grass_density": 0.6,
                "tree_density": 0.8,
                "temperature": 15,
                "humidity": 0.7
            },
            BiomeType.DESERT: {
                "grass_density": 0.05,
                "tree_density": 0.02,
                "temperature": 35,
                "humidity": 0.1
            },
            BiomeType.TUNDRA: {
                "grass_density": 0.2,
                "tree_density": 0.05,
                "temperature": -10,
                "humidity": 0.3
            },
            BiomeType.JUNGLE: {
                "grass_density": 0.7,
                "tree_density": 0.95,
                "temperature": 28,
                "humidity": 0.95
            }
        }
        
        config = biome_configs.get(request.biome_type, biome_configs[BiomeType.PLAINS])
        density_multiplier = {"sparse": 0.3, "normal": 1.0, "dense": 1.5, "very_dense": 2.0}[request.vegetation_density.value]
        
        return {
            "id": str(uuid.uuid4()),
            "biome": request.biome_type.value,
            "climate": config,
            "vegetation": {
                "density_multiplier": density_multiplier,
                "grass_density": config["grass_density"] * density_multiplier,
                "tree_density": config["tree_density"] * density_multiplier
            },
            "features": {
                "blend_edges": request.blend_edges,
                "rock_formations": request.rock_formations,
                "water_features": request.water_features
            },
            "textures": {
                "ground": [f"{request.biome_type.value}_ground_01", f"{request.biome_type.value}_ground_02"],
                "cliff": [f"{request.biome_type.value}_cliff_01"],
                "detail": ["pebbles", "leaves", "debris"]
            },
            "audio": {
                "ambient": f"{request.biome_type.value}_ambient",
                "weather_variations": True
            }
        }

    @staticmethod
    def generate_building(request: BuildingRequest) -> Dict[str, Any]:
        """Generate building configuration."""
        size_dimensions = {
            "small": {"width": 10, "depth": 10, "height": 5},
            "medium": {"width": 20, "depth": 20, "height": 10},
            "large": {"width": 40, "depth": 40, "height": 20},
            "massive": {"width": 100, "depth": 100, "height": 50}
        }
        
        dims = size_dimensions[request.size]
        
        return {
            "id": str(uuid.uuid4()),
            "type": request.building_type,
            "style": request.style,
            "dimensions": dims,
            "structure": {
                "floors": max(1, dims["height"] // 4),
                "rooms_per_floor": max(1, (dims["width"] * dims["depth"]) // 50),
                "interior_enabled": request.interior_enabled
            },
            "components": [
                {"type": "foundation", "material": "stone"},
                {"type": "walls", "material": request.style},
                {"type": "roof", "material": f"{request.style}_roof"},
                {"type": "windows", "count": max(4, dims["width"] // 3)},
                {"type": "doors", "count": max(1, dims["width"] // 10)}
            ],
            "destruction": {
                "enabled": request.destructible,
                "debris_system": request.destructible,
                "structural_integrity": request.destructible
            },
            "occlusion": {
                "enabled": request.interior_enabled,
                "portals": True
            }
        }

    @staticmethod
    def generate_vegetation(request: VegetationRequest) -> Dict[str, Any]:
        """Generate vegetation system."""
        density_values = {
            PropDensity.SPARSE: 0.25,
            PropDensity.NORMAL: 1.0,
            PropDensity.DENSE: 2.0,
            PropDensity.VERY_DENSE: 4.0
        }
        
        default_trees = {
            BiomeType.FOREST: ["oak", "pine", "birch"],
            BiomeType.JUNGLE: ["palm", "banyan", "kapok"],
            BiomeType.DESERT: ["cactus", "joshua_tree"],
            BiomeType.TUNDRA: ["spruce", "dwarf_willow"]
        }
        
        trees = request.tree_types or default_trees.get(request.biome, ["generic_tree"])
        
        return {
            "id": str(uuid.uuid4()),
            "biome": request.biome.value,
            "density_multiplier": density_values[request.density],
            "trees": {
                "types": trees,
                "instances_per_km2": int(500 * density_values[request.density]),
                "lod_levels": 4,
                "billboard_distance": 500
            },
            "grass": {
                "enabled": request.grass_enabled,
                "density_per_m2": 100 * density_values[request.density],
                "render_distance": 100,
                "wind_response": request.wind_animation
            },
            "flowers": {
                "enabled": request.flowers_enabled,
                "types": ["wildflower_01", "wildflower_02", "wildflower_03"],
                "density_per_m2": 10 * density_values[request.density]
            },
            "wind": {
                "enabled": request.wind_animation,
                "global_strength": 1.0,
                "turbulence": 0.5,
                "vertex_animation": True
            },
            "instancing": {
                "enabled": True,
                "gpu_instancing": True,
                "indirect_rendering": True
            }
        }

    @staticmethod
    def generate_atmosphere(request: AtmosphereRequest) -> Dict[str, Any]:
        """Generate atmosphere and lighting."""
        weather_configs = {
            "clear": {"cloud_coverage": 0.1, "precipitation": 0, "fog_density": 0.001},
            "cloudy": {"cloud_coverage": 0.7, "precipitation": 0, "fog_density": 0.005},
            "rain": {"cloud_coverage": 0.9, "precipitation": 0.7, "fog_density": 0.02},
            "storm": {"cloud_coverage": 1.0, "precipitation": 1.0, "fog_density": 0.05},
            "fog": {"cloud_coverage": 0.5, "precipitation": 0, "fog_density": 0.2},
            "snow": {"cloud_coverage": 0.8, "precipitation": 0.8, "fog_density": 0.03}
        }
        
        weather = weather_configs[request.weather]
        sun_angle = (request.time_of_day - 6) * 15  # Degrees from horizon
        
        return {
            "id": str(uuid.uuid4()),
            "time_of_day": request.time_of_day,
            "season": request.season,
            "sun": {
                "angle": sun_angle,
                "intensity": max(0, math.sin(math.radians(sun_angle))) * 1.5,
                "color": WorldModelsGenerator._get_sun_color(request.time_of_day)
            },
            "sky": {
                "type": "procedural",
                "rayleigh_scattering": True,
                "mie_scattering": True
            },
            "weather": {
                "type": request.weather,
                **weather
            },
            "volumetrics": {
                "lighting": request.volumetric_lighting,
                "fog": True,
                "clouds": True,
                "quality": "high"
            },
            "effects": {
                "god_rays": request.volumetric_lighting and request.weather in ["clear", "cloudy"],
                "rainbow": request.weather == "rain" and request.time_of_day > 6 and request.time_of_day < 18,
                "aurora": request.season == "winter" and request.time_of_day < 6
            }
        }

    @staticmethod
    def _get_sun_color(time_of_day: float) -> Tuple[float, float, float]:
        if time_of_day < 6 or time_of_day > 18:
            return (0.2, 0.2, 0.4)  # Night/twilight
        elif time_of_day < 8 or time_of_day > 16:
            return (1.0, 0.7, 0.4)  # Golden hour
        else:
            return (1.0, 0.98, 0.95)  # Daylight

    @staticmethod
    def generate_lod_system(request: LODRequest) -> Dict[str, Any]:
        """Generate LOD system configuration."""
        lod_distances = []
        for i in range(request.lod_levels):
            distance = (request.max_distance / request.lod_levels) * (i + 1)
            triangle_reduction = 1.0 / (2 ** i)
            lod_distances.append({
                "level": i,
                "distance": distance,
                "triangle_budget": triangle_reduction,
                "texture_resolution_scale": max(0.125, triangle_reduction)
            })
        
        return {
            "id": str(uuid.uuid4()),
            "target": request.target_object,
            "strategy": request.strategy.value,
            "levels": lod_distances,
            "transition": {
                "type": request.transition_type,
                "duration": 0.5 if request.transition_type != "instant" else 0,
                "hysteresis": 0.1
            },
            "culling": {
                "frustum_culling": True,
                "occlusion_culling": True,
                "distance_culling": request.max_distance * 1.2
            },
            "imposters": {
                "enabled": request.lod_levels >= 4,
                "start_level": request.lod_levels - 1,
                "resolution": 256
            }
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/overview")
async def get_overview():
    """Get overview of the World Models Pipeline."""
    return {
        "pipeline": "Text-to-World-Models Pipeline v15.5",
        "description": "Generate 3D world models and environments from natural language",
        "capabilities": [
            "Procedural terrain generation",
            "Biome configuration",
            "Building generation",
            "Vegetation systems",
            "Atmosphere & lighting",
            "LOD systems"
        ],
        "terrain_types": [t.value for t in TerrainType],
        "biomes": [b.value for b in BiomeType],
        "lod_strategies": [l.value for l in LODStrategy]
    }


@router.post("/terrain/generate")
async def generate_terrain(request: TerrainRequest):
    """Generate terrain configuration."""
    return {
        "success": True,
        "terrain": WorldModelsGenerator.generate_terrain(request)
    }


@router.post("/biome/generate")
async def generate_biome(request: BiomeRequest):
    """Generate biome configuration."""
    return {
        "success": True,
        "biome": WorldModelsGenerator.generate_biome(request)
    }


@router.post("/building/generate")
async def generate_building(request: BuildingRequest):
    """Generate building configuration."""
    return {
        "success": True,
        "building": WorldModelsGenerator.generate_building(request)
    }


@router.post("/vegetation/generate")
async def generate_vegetation(request: VegetationRequest):
    """Generate vegetation system."""
    return {
        "success": True,
        "vegetation": WorldModelsGenerator.generate_vegetation(request)
    }


@router.post("/atmosphere/generate")
async def generate_atmosphere(request: AtmosphereRequest):
    """Generate atmosphere and lighting."""
    return {
        "success": True,
        "atmosphere": WorldModelsGenerator.generate_atmosphere(request)
    }


@router.post("/lod/generate")
async def generate_lod_system(request: LODRequest):
    """Generate LOD system."""
    return {
        "success": True,
        "lod_system": WorldModelsGenerator.generate_lod_system(request)
    }



# ============================================================================
# AI-POWERED ENDPOINTS (LLM Integration)
# ============================================================================

class AIEnvironmentRequest(BaseModel):
    """Request for AI-powered environment generation"""
    environment_type: str = Field(..., description="forest, desert, urban, underwater, etc.")
    style: str = Field(default="realistic", description="realistic, stylized, low_poly")
    features: List[str] = Field(default=["terrain", "vegetation"], description="Features to include")
    build_id: Optional[str] = Field(default=None, description="Galaxy Studio build_id — when provided, ml_config + matrix dials are auto-loaded and threaded into the LLM prompt")


@router.post("/ai/environment/generate")
async def ai_generate_environment(request: AIEnvironmentRequest):
    """
    Generate 3D environment layouts using AI (GPT-4o).
    Creates detailed terrain, props, and atmosphere specifications.
    """
    try:
        llm_service = get_game_llm_service()
        
        features_str = ', '.join(request.features)
        
        system_prompt = """You are an expert 3D environment artist and level designer.
Create detailed, production-ready environment specifications.
Always respond with valid JSON."""
        
        user_prompt = f"""Design a {request.style} {request.environment_type} environment.
Include these features: {features_str}

Generate JSON with:
{{
    "environment_name": "...",
    "type": "{request.environment_type}",
    "style": "{request.style}",
    "terrain": {{
        "heightmap_settings": {{"resolution": 2048, "height_range": [0, 100]}},
        "biomes": [{{"name": "...", "coverage": 0.5, "textures": [...]}}]
    }},
    "vegetation": [{{"type": "tree", "density": 0.3, "variation": 5}}],
    "props": [{{"category": "rocks", "count": 50, "scale_range": [0.5, 2.0]}}],
    "atmosphere": {{
        "sky_color": "#...",
        "fog_density": 0.01,
        "time_of_day": "noon"
    }},
    "performance_budget": {{
        "max_triangles": 2000000,
        "max_draw_calls": 1000
    }}
}}"""
        
        result = await llm_service.generate(system_prompt, user_prompt, build_id=request.build_id)

        if result["success"]:
            return {
                "success": True,
                "environment": result["response"],
                "ai_generated": True,
                "model": "gpt-4o"
            }
        else:
            return {
                "success": True,
                "environment": {
                    "type": request.environment_type,
                    "template": "basic_environment"
                },
                "ai_generated": False
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI environment generation failed: {str(e)}")
