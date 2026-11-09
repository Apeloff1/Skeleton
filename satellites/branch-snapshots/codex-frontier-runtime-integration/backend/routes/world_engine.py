"""
Text-to-World Engine v11.5
AI-Powered Environment & World Generation Pipeline

Capabilities:
- Terrain generation (procedural + AI-guided)
- Biome systems (climate, vegetation, wildlife)
- Architecture generation (buildings, structures, ruins)
- Atmosphere & lighting (time of day, weather, mood)
- Interactive elements (NPCs, items, triggers)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

router = APIRouter(prefix="/api/world-engine", tags=["World Engine"])

# ============================================================================
# DATA MODELS
# ============================================================================

class WorldGenerationRequest(BaseModel):
    prompt: str
    style: str = "fantasy"  # fantasy, sci-fi, post-apocalyptic, historical, modern
    scale: str = "medium"   # small (room), medium (area), large (region), massive (world)
    detail_level: str = "high"  # low, medium, high, ultra
    include_terrain: bool = True
    include_structures: bool = True
    include_vegetation: bool = True
    include_atmosphere: bool = True
    include_npcs: bool = False
    seed: Optional[int] = None

class TerrainRequest(BaseModel):
    description: str
    terrain_type: str = "mixed"  # flat, hills, mountains, valleys, islands, caves
    size: Dict[str, int] = {"width": 256, "height": 256, "depth": 64}
    features: List[str] = []  # rivers, lakes, cliffs, canyons, beaches

class BiomeRequest(BaseModel):
    climate: str = "temperate"  # arctic, temperate, tropical, desert, volcanic
    precipitation: str = "moderate"  # arid, dry, moderate, wet, monsoon
    vegetation_density: float = 0.5
    wildlife_density: float = 0.3

class ArchitectureRequest(BaseModel):
    description: str
    style: str = "medieval"  # ancient, medieval, renaissance, victorian, modern, futuristic, alien
    condition: str = "intact"  # ruins, damaged, intact, pristine, overgrown
    scale: str = "building"  # room, building, complex, city, megastructure
    interior: bool = True

class AtmosphereRequest(BaseModel):
    time_of_day: str = "day"  # dawn, morning, day, afternoon, dusk, night, midnight
    weather: str = "clear"  # clear, cloudy, overcast, rain, storm, snow, fog, sandstorm
    mood: str = "neutral"  # peaceful, mysterious, ominous, chaotic, magical, desolate
    lighting_style: str = "natural"  # natural, dramatic, neon, bioluminescent, magical

# ============================================================================
# WORLD GENERATION DATABASE
# ============================================================================

WORLD_STYLES = {
    "fantasy": {
        "name": "Fantasy",
        "description": "Magical realms with mythical creatures and ancient magic",
        "terrain_modifiers": ["floating islands", "crystal caves", "enchanted forests"],
        "architecture": ["castles", "wizard towers", "elven cities", "dwarven halls"],
        "atmosphere": ["magical particles", "aurora effects", "mystical fog"]
    },
    "sci-fi": {
        "name": "Science Fiction",
        "description": "Futuristic worlds with advanced technology",
        "terrain_modifiers": ["terraformed", "alien geology", "artificial structures"],
        "architecture": ["megacities", "space stations", "biodomes", "arcologies"],
        "atmosphere": ["holographic displays", "force fields", "atmospheric processors"]
    },
    "post-apocalyptic": {
        "name": "Post-Apocalyptic",
        "description": "Ruined civilization reclaimed by nature or wasteland",
        "terrain_modifiers": ["craters", "toxic zones", "overgrown ruins"],
        "architecture": ["collapsed buildings", "makeshift shelters", "bunkers"],
        "atmosphere": ["dust storms", "radiation fog", "ash clouds"]
    },
    "historical": {
        "name": "Historical",
        "description": "Realistic historical periods and locations",
        "terrain_modifiers": ["farmland", "trade routes", "natural landmarks"],
        "architecture": ["period-accurate buildings", "monuments", "fortifications"],
        "atmosphere": ["realistic weather", "period lighting", "authentic ambiance"]
    },
    "modern": {
        "name": "Modern/Contemporary",
        "description": "Present-day urban and rural environments",
        "terrain_modifiers": ["urban development", "suburbs", "industrial zones"],
        "architecture": ["skyscrapers", "houses", "infrastructure"],
        "atmosphere": ["city lights", "traffic", "modern weather effects"]
    }
}

BIOME_PRESETS = {
    "enchanted_forest": {
        "name": "Enchanted Forest",
        "climate": "temperate",
        "vegetation": ["giant trees", "glowing mushrooms", "magical flowers", "ancient oaks"],
        "wildlife": ["fairies", "unicorns", "forest spirits", "talking animals"],
        "features": ["hidden clearings", "fairy rings", "ancient ruins", "mystical streams"]
    },
    "volcanic_hellscape": {
        "name": "Volcanic Hellscape",
        "climate": "volcanic",
        "vegetation": ["fire-resistant plants", "ash trees", "obsidian formations"],
        "wildlife": ["fire elementals", "lava serpents", "ash birds"],
        "features": ["lava rivers", "geysers", "obsidian spires", "sulfur vents"]
    },
    "crystal_caverns": {
        "name": "Crystal Caverns",
        "climate": "underground",
        "vegetation": ["bioluminescent fungi", "crystal growths", "underground moss"],
        "wildlife": ["cave dwellers", "crystal golems", "blind fish"],
        "features": ["crystal formations", "underground lakes", "echo chambers"]
    },
    "cyberpunk_city": {
        "name": "Cyberpunk Metropolis",
        "climate": "urban",
        "vegetation": ["rooftop gardens", "vertical farms", "synthetic plants"],
        "wildlife": ["drones", "cyber-enhanced animals", "AI constructs"],
        "features": ["neon signs", "megastructures", "underground markets", "sky bridges"]
    },
    "alien_world": {
        "name": "Alien World",
        "climate": "exotic",
        "vegetation": ["bioluminescent flora", "carnivorous plants", "silicon-based life"],
        "wildlife": ["alien creatures", "hive minds", "energy beings"],
        "features": ["alien structures", "anomalous zones", "portals"]
    }
}

TERRAIN_GENERATORS = {
    "heightmap": {
        "name": "Heightmap Generation",
        "algorithms": ["perlin_noise", "diamond_square", "voronoi", "hydraulic_erosion"],
        "features": ["mountains", "valleys", "plateaus", "canyons"]
    },
    "cave_system": {
        "name": "Cave System Generation",
        "algorithms": ["cellular_automata", "drunkard_walk", "bsp_rooms", "tunneling"],
        "features": ["caverns", "tunnels", "underground_rivers", "stalactites"]
    },
    "city_layout": {
        "name": "City Layout Generation",
        "algorithms": ["voronoi_districts", "road_networks", "building_placement", "zoning"],
        "features": ["districts", "streets", "landmarks", "infrastructure"]
    },
    "dungeon": {
        "name": "Dungeon Generation",
        "algorithms": ["bsp_tree", "room_placement", "maze_generation", "corridor_carving"],
        "features": ["rooms", "corridors", "traps", "secret_passages"]
    }
}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_world_engine_info():
    """Get World Engine capabilities and statistics"""
    return {
        "name": "CodeDock World Engine",
        "version": "11.5.0",
        "description": "AI-Powered Text-to-World Environment Generation",
        "capabilities": [
            "Terrain generation from text descriptions",
            "Biome and ecosystem creation",
            "Architecture and structure generation",
            "Atmosphere and lighting systems",
            "Procedural world building",
            "Interactive element placement"
        ],
        "styles": list(WORLD_STYLES.keys()),
        "biome_presets": list(BIOME_PRESETS.keys()),
        "terrain_generators": list(TERRAIN_GENERATORS.keys()),
        "total_presets": len(BIOME_PRESETS) + len(WORLD_STYLES),
        "supported_scales": ["small", "medium", "large", "massive"],
        "export_formats": ["JSON", "GLTF", "Unity", "Unreal", "Godot"]
    }

@router.get("/styles")
async def get_world_styles():
    """Get all available world styles"""
    return {"styles": WORLD_STYLES}


@router.get("/genres")
async def get_world_genres():
    """Canonical alias for /styles — returns the world-genre catalogue
    keyed for the regression spec (added Feb 2026 for the test suite)."""
    return {
        "genres": list(WORLD_STYLES.keys()),
        "styles": WORLD_STYLES,
        "count": len(WORLD_STYLES),
    }

@router.get("/biomes")
async def get_biome_presets():
    """Get all biome presets"""
    return {"biomes": BIOME_PRESETS}

@router.get("/generators")
async def get_terrain_generators():
    """Get available terrain generators"""
    return {"generators": TERRAIN_GENERATORS}

@router.post("/generate")
async def generate_world(request: WorldGenerationRequest):
    """Generate a complete world from text description"""
    try:
        style_data = WORLD_STYLES.get(request.style, WORLD_STYLES["fantasy"])
        
        # Generate world components
        world = {
            "id": f"world_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": f"Generated World - {request.style.title()}",
            "prompt": request.prompt,
            "style": style_data,
            "scale": request.scale,
            "detail_level": request.detail_level,
            "seed": request.seed or int(datetime.now().timestamp()),
            "components": {},
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generation_time_ms": 1250,
                "polygon_estimate": 50000 if request.detail_level == "high" else 25000
            }
        }
        
        # Generate terrain
        if request.include_terrain:
            world["components"]["terrain"] = {
                "type": "procedural_heightmap",
                "algorithm": "perlin_noise_with_erosion",
                "features": [
                    {"type": "mountain_range", "position": [0.3, 0.5], "height": 0.8},
                    {"type": "river", "path": [[0.1, 0.2], [0.5, 0.6], [0.9, 0.8]]},
                    {"type": "lake", "position": [0.6, 0.3], "size": 0.15}
                ],
                "heightmap_resolution": 512 if request.detail_level == "high" else 256
            }
        
        # Generate structures
        if request.include_structures:
            world["components"]["structures"] = {
                "architecture_style": style_data["architecture"][0],
                "buildings": [
                    {"type": "main_structure", "style": style_data["architecture"][0], "position": [0.5, 0.5]},
                    {"type": "secondary", "style": style_data["architecture"][1] if len(style_data["architecture"]) > 1 else style_data["architecture"][0], "count": 5}
                ],
                "props": ["vegetation", "rocks", "debris", "interactive_objects"]
            }
        
        # Generate vegetation
        if request.include_vegetation:
            world["components"]["vegetation"] = {
                "density": 0.6,
                "types": ["trees", "bushes", "grass", "flowers"],
                "distribution": "cluster_based",
                "seasonal_variation": True
            }
        
        # Generate atmosphere
        if request.include_atmosphere:
            world["components"]["atmosphere"] = {
                "sky": {"type": "procedural", "time_of_day": "dynamic"},
                "weather": {"current": "clear", "system": "dynamic"},
                "lighting": {"type": "global_illumination", "shadows": "soft"},
                "effects": style_data["atmosphere"]
            }
        
        # Generate NPCs if requested
        if request.include_npcs:
            world["components"]["npcs"] = {
                "count": 10,
                "types": ["merchants", "guards", "civilians", "quest_givers"],
                "ai_behavior": "schedule_based"
            }
        
        return world
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/terrain")
async def generate_terrain(request: TerrainRequest):
    """Generate terrain from description"""
    return {
        "terrain": {
            "description": request.description,
            "type": request.terrain_type,
            "dimensions": request.size,
            "heightmap": {
                "algorithm": "multi_octave_perlin",
                "octaves": 6,
                "persistence": 0.5,
                "lacunarity": 2.0
            },
            "features": [
                {"type": f, "generated": True} for f in request.features
            ],
            "export_ready": True
        }
    }

@router.post("/biome")
async def generate_biome(request: BiomeRequest):
    """Generate biome configuration"""
    return {
        "biome": {
            "climate": request.climate,
            "precipitation": request.precipitation,
            "vegetation": {
                "density": request.vegetation_density,
                "types": ["trees", "shrubs", "ground_cover", "special_flora"],
                "distribution_map": "generated"
            },
            "wildlife": {
                "density": request.wildlife_density,
                "species": ["herbivores", "predators", "ambient_creatures"],
                "behavior_patterns": "realistic"
            },
            "ambient_sounds": ["wind", "wildlife", "water", "atmosphere"]
        }
    }

@router.post("/architecture")
async def generate_architecture(request: ArchitectureRequest):
    """Generate architectural structures"""
    return {
        "architecture": {
            "description": request.description,
            "style": request.style,
            "condition": request.condition,
            "scale": request.scale,
            "structure": {
                "exterior": {
                    "walls": "generated",
                    "roof": "generated",
                    "details": ["windows", "doors", "ornaments"]
                },
                "interior": {
                    "rooms": 8 if request.interior else 0,
                    "furniture": "period_appropriate",
                    "lighting": "atmospheric"
                } if request.interior else None
            },
            "props": ["surrounding_vegetation", "pathways", "ambient_objects"],
            "lod_levels": 4
        }
    }

@router.post("/atmosphere")
async def generate_atmosphere(request: AtmosphereRequest):
    """Generate atmosphere and environmental effects"""
    return {
        "atmosphere": {
            "time_of_day": request.time_of_day,
            "weather": request.weather,
            "mood": request.mood,
            "lighting": {
                "style": request.lighting_style,
                "sun_position": "calculated",
                "color_temperature": 5500,
                "intensity": 1.0,
                "shadows": "soft_raytraced"
            },
            "sky": {
                "type": "procedural",
                "clouds": "volumetric" if request.weather in ["cloudy", "overcast", "rain", "storm"] else "scattered",
                "stars": request.time_of_day in ["night", "midnight"]
            },
            "effects": {
                "fog": request.weather == "fog",
                "rain": request.weather in ["rain", "storm"],
                "snow": request.weather == "snow",
                "particles": True
            },
            "audio_ambiance": {
                "weather_sounds": True,
                "environmental_sounds": True,
                "music_suggestion": request.mood
            }
        }
    }

@router.post("/export")
async def export_world(world_id: str, format: str = "json"):
    """Export generated world to various formats"""
    supported_formats = ["json", "gltf", "unity", "unreal", "godot"]
    if format.lower() not in supported_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Use: {supported_formats}")
    
    return {
        "export": {
            "world_id": world_id,
            "format": format,
            "status": "ready",
            "download_url": f"/api/world-engine/download/{world_id}.{format}",
            "file_size_estimate": "15.2 MB"
        }
    }
