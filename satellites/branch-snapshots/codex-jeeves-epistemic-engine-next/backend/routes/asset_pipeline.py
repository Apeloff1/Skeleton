"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  TEXT-TO-ASSET PIPELINE - 2D Sprites & 3D Models Generation System          ║
║  Complete Asset Creation for Games & Applications                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import os

router = APIRouter(prefix="/assets", tags=["Asset Pipeline"])

# Try to import LLM for AI-powered generation
try:
    from emergentintegrations.llm.chat import LlmChat
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")

# ============================================================================
# ASSET TYPES & CONFIGURATIONS
# ============================================================================

SPRITE_CATEGORIES = {
    "characters": {
        "types": ["player", "enemy", "npc", "boss", "companion", "creature"],
        "styles": ["pixel_art", "hand_drawn", "vector", "anime", "realistic", "chibi", "isometric"],
        "animations": ["idle", "walk", "run", "jump", "attack", "hurt", "death", "special"]
    },
    "environment": {
        "types": ["tileset", "background", "parallax", "platform", "obstacle", "decoration"],
        "themes": ["forest", "desert", "ice", "lava", "underwater", "space", "dungeon", "city", "sky"]
    },
    "ui": {
        "types": ["button", "panel", "icon", "cursor", "health_bar", "inventory_slot", "dialog_box"],
        "styles": ["minimal", "fantasy", "sci_fi", "cartoon", "pixel", "glass", "wooden"]
    },
    "items": {
        "types": ["weapon", "armor", "potion", "key", "coin", "gem", "food", "tool", "collectible"],
        "rarities": ["common", "uncommon", "rare", "epic", "legendary"]
    },
    "effects": {
        "types": ["explosion", "magic", "smoke", "fire", "water", "lightning", "heal", "buff", "projectile"]
    }
}

MODEL_3D_CATEGORIES = {
    "characters": {
        "types": ["humanoid", "creature", "robot", "animal", "monster", "vehicle_character"],
        "detail_levels": ["low_poly", "mid_poly", "high_poly", "sculpted"],
        "rigging": ["none", "basic", "full", "facial"]
    },
    "environment": {
        "types": ["building", "terrain", "vegetation", "rock", "water_body", "sky_dome"],
        "scales": ["prop", "structure", "landmark", "terrain_chunk", "full_level"]
    },
    "props": {
        "types": ["furniture", "weapon", "vehicle", "container", "decoration", "interactive"],
        "interactivity": ["static", "animated", "physics", "destructible"]
    },
    "vehicles": {
        "types": ["car", "truck", "motorcycle", "aircraft", "spacecraft", "boat", "mech", "fantasy_mount"],
        "detail": ["exterior_only", "with_interior", "fully_detailed"]
    },
    "weapons": {
        "types": ["sword", "axe", "bow", "gun", "staff", "shield", "futuristic", "fantasy"],
        "attachments": ["none", "basic", "modular"]
    }
}

EXPORT_FORMATS = {
    "2d": ["png", "svg", "gif", "webp", "psd", "aseprite"],
    "3d": ["glb", "gltf", "fbx", "obj", "blend", "usdz", "dae"]
}

# ============================================================================
# REQUEST MODELS
# ============================================================================

class Sprite2DRequest(BaseModel):
    description: str
    category: str  # characters, environment, ui, items, effects
    asset_type: str
    style: str = "pixel_art"
    resolution: str = "32x32"  # 16x16, 32x32, 64x64, 128x128, 256x256
    color_palette: Optional[str] = None  # custom colors or preset
    animation_frames: int = 1
    include_variations: bool = False
    export_format: str = "png"
    game_context: Optional[str] = None

class Model3DRequest(BaseModel):
    description: str
    category: str  # characters, environment, props, vehicles, weapons
    asset_type: str
    style: str = "stylized"  # realistic, stylized, low_poly, cartoon
    poly_count: str = "mid_poly"  # low_poly, mid_poly, high_poly
    textures: bool = True
    texture_resolution: str = "1024"  # 512, 1024, 2048, 4096
    rigging: str = "none"  # none, basic, full
    animations: List[str] = []
    export_format: str = "glb"
    game_engine: Optional[str] = None  # unity, unreal, godot
    lod_levels: int = 1  # Level of Detail variants

class AssetBatchRequest(BaseModel):
    project_name: str
    game_type: str  # platformer, rpg, fps, puzzle, etc.
    art_style: str
    assets: List[Dict[str, Any]]
    consistent_style: bool = True

class TilesetRequest(BaseModel):
    theme: str
    style: str = "pixel_art"
    tile_size: int = 32
    tile_count: int = 48  # Standard tileset size
    include_autotile: bool = True
    include_animated: bool = False
    terrain_types: List[str] = ["ground", "wall", "decoration"]

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_asset_pipeline_info():
    """Get Asset Pipeline system information"""
    return {
        "name": "CodeDock Asset Pipeline",
        "version": "11.2.0",
        "description": "AI-powered 2D & 3D asset generation for games",
        "capabilities": {
            "2d_sprites": {
                "categories": list(SPRITE_CATEGORIES.keys()),
                "styles": ["pixel_art", "hand_drawn", "vector", "anime", "realistic"],
                "max_resolution": "512x512",
                "animation_support": True,
                "export_formats": EXPORT_FORMATS["2d"]
            },
            "3d_models": {
                "categories": list(MODEL_3D_CATEGORIES.keys()),
                "styles": ["realistic", "stylized", "low_poly", "cartoon", "pbr"],
                "rigging_support": True,
                "animation_support": True,
                "export_formats": EXPORT_FORMATS["3d"]
            },
            "batch_generation": True,
            "style_consistency": True,
            "game_engine_optimization": ["unity", "unreal", "godot", "custom"]
        },
        "integrations": [
            "OpenAI DALL-E 3 (2D generation)",
            "Stability AI (2D generation)",
            "Meshy.ai (3D generation)",
            "Tripo3D (3D generation)",
            "Custom prompt pipelines"
        ]
    }

@router.get("/categories/2d")
async def get_2d_categories():
    """Get all 2D sprite categories and options"""
    return SPRITE_CATEGORIES

@router.get("/categories/3d")
async def get_3d_categories():
    """Get all 3D model categories and options"""
    return MODEL_3D_CATEGORIES

@router.post("/generate/sprite")
async def generate_sprite(request: Sprite2DRequest):
    """Generate a 2D sprite asset"""
    
    # Build comprehensive prompt
    prompt = build_sprite_prompt(request)
    
    # Generate asset specification
    asset_spec = {
        "id": f"sprite_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "type": "2d_sprite",
        "category": request.category,
        "asset_type": request.asset_type,
        "description": request.description,
        "style": request.style,
        "resolution": request.resolution,
        "frames": request.animation_frames,
        "format": request.export_format,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # AI-enhanced generation prompt
    generation_prompt = ""
    if LLM_AVAILABLE and EMERGENT_KEY:
        try:
            llm = LlmChat(api_key=EMERGENT_KEY, model="gpt-4o")
            llm.add_message("system", """You are an expert pixel artist and game asset designer. 
            Generate detailed, professional asset creation specifications and prompts for AI image generators.
            Include specific details about colors, shapes, shading, and style consistency.""")
            llm.add_message("user", f"""Create a detailed asset generation specification for:
            
            Description: {request.description}
            Category: {request.category}
            Type: {request.asset_type}
            Style: {request.style}
            Resolution: {request.resolution}
            Animation Frames: {request.animation_frames}
            Game Context: {request.game_context or 'General game use'}
            
            Provide:
            1. Detailed visual description
            2. Color palette (hex codes)
            3. DALL-E prompt
            4. Stable Diffusion prompt
            5. Technical specifications
            6. Animation keyframe descriptions (if animated)""")
            generation_prompt = llm.chat()
        except Exception:
            generation_prompt = prompt
    else:
        generation_prompt = prompt
    
    return {
        "asset": asset_spec,
        "generation": {
            "dalle_prompt": f"{request.style} game sprite, {request.description}, {request.asset_type}, transparent background, game asset, high quality, {request.resolution}",
            "stable_diffusion_prompt": f"game sprite sheet, {request.style}, {request.description}, {request.category}, transparent background, ((game asset)), detailed, clean lines",
            "midjourney_prompt": f"{request.style} game {request.asset_type}, {request.description} --ar 1:1 --style raw",
            "detailed_spec": generation_prompt
        },
        "technical": {
            "file_format": request.export_format,
            "resolution": request.resolution,
            "color_depth": "32-bit RGBA",
            "transparency": True,
            "frames": request.animation_frames,
            "frame_rate": 12 if request.animation_frames > 1 else None
        },
        "export_options": {
            "formats": EXPORT_FORMATS["2d"],
            "sprite_sheet": request.animation_frames > 1,
            "individual_frames": request.animation_frames > 1
        }
    }

@router.post("/generate/model")
async def generate_3d_model(request: Model3DRequest):
    """Generate a 3D model asset"""
    
    # Build comprehensive prompt
    prompt = build_model_prompt(request)
    
    asset_spec = {
        "id": f"model_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "type": "3d_model",
        "category": request.category,
        "asset_type": request.asset_type,
        "description": request.description,
        "style": request.style,
        "poly_count": request.poly_count,
        "textured": request.textures,
        "rigged": request.rigging != "none",
        "format": request.export_format,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # AI-enhanced generation
    generation_prompt = ""
    if LLM_AVAILABLE and EMERGENT_KEY:
        try:
            llm = LlmChat(api_key=EMERGENT_KEY, model="gpt-4o")
            llm.add_message("system", """You are an expert 3D artist and game asset designer.
            Generate detailed, professional 3D model specifications and prompts for AI 3D generators like Meshy, Tripo, and manual modeling.""")
            llm.add_message("user", f"""Create a detailed 3D asset generation specification for:
            
            Description: {request.description}
            Category: {request.category}
            Type: {request.asset_type}
            Style: {request.style}
            Poly Count: {request.poly_count}
            Textures: {request.textures}
            Texture Resolution: {request.texture_resolution}
            Rigging: {request.rigging}
            Animations: {request.animations}
            Target Engine: {request.game_engine or 'Universal'}
            
            Provide:
            1. Detailed 3D model description
            2. Topology guidelines
            3. Meshy.ai prompt
            4. Tripo3D prompt
            5. Material/texture specifications
            6. Rigging requirements (if applicable)
            7. Animation specifications (if applicable)
            8. LOD recommendations""")
            generation_prompt = llm.chat()
        except Exception:
            generation_prompt = prompt
    else:
        generation_prompt = prompt
    
    poly_estimates = {
        "low_poly": "500-2000 tris",
        "mid_poly": "2000-10000 tris",
        "high_poly": "10000-50000 tris"
    }
    
    return {
        "asset": asset_spec,
        "generation": {
            "meshy_prompt": f"{request.style} 3D {request.asset_type}, {request.description}, game-ready, {request.poly_count}",
            "tripo_prompt": f"{request.description}, {request.style} style, {request.category}, detailed 3D model",
            "blender_description": f"Create a {request.style} {request.asset_type}: {request.description}",
            "detailed_spec": generation_prompt
        },
        "technical": {
            "file_format": request.export_format,
            "poly_count": poly_estimates.get(request.poly_count, "5000-15000 tris"),
            "texture_resolution": f"{request.texture_resolution}x{request.texture_resolution}",
            "texture_maps": ["diffuse", "normal", "roughness", "metallic", "ao"] if request.textures else [],
            "rigging": request.rigging,
            "animations": request.animations,
            "lod_levels": request.lod_levels
        },
        "engine_settings": {
            "unity": {
                "import_settings": "humanoid" if "character" in request.category else "generic",
                "compression": "standard"
            },
            "unreal": {
                "skeletal_mesh": request.rigging != "none",
                "nanite_compatible": request.poly_count == "high_poly"
            },
            "godot": {
                "import_as": "scene",
                "generate_colliders": True
            }
        },
        "export_options": {
            "formats": EXPORT_FORMATS["3d"],
            "include_textures": request.textures,
            "embed_textures": True
        }
    }

@router.post("/generate/tileset")
async def generate_tileset(request: TilesetRequest):
    """Generate a complete tileset"""
    
    tiles = []
    for terrain in request.terrain_types:
        tiles.extend([
            f"{terrain}_center",
            f"{terrain}_edge_top",
            f"{terrain}_edge_bottom",
            f"{terrain}_edge_left",
            f"{terrain}_edge_right",
            f"{terrain}_corner_tl",
            f"{terrain}_corner_tr",
            f"{terrain}_corner_bl",
            f"{terrain}_corner_br",
            f"{terrain}_inner_tl",
            f"{terrain}_inner_tr",
            f"{terrain}_inner_bl",
            f"{terrain}_inner_br",
            f"{terrain}_single",
            f"{terrain}_horizontal",
            f"{terrain}_vertical",
        ])
    
    return {
        "tileset": {
            "id": f"tileset_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "theme": request.theme,
            "style": request.style,
            "tile_size": request.tile_size,
            "total_tiles": len(tiles),
            "autotile_ready": request.include_autotile,
            "animated_tiles": request.include_animated
        },
        "tiles": tiles[:request.tile_count],
        "generation_prompt": f"{request.style} tileset, {request.theme} theme, {request.tile_size}x{request.tile_size} pixels, game tiles, seamless, top-down view",
        "layout": {
            "columns": 8,
            "rows": (len(tiles) // 8) + 1,
            "total_size": f"{8 * request.tile_size}x{((len(tiles) // 8) + 1) * request.tile_size}"
        },
        "autotile_rules": {
            "godot": "3x3 minimal bitmask",
            "unity": "Rule Tile compatible",
            "tiled": "Wang tiles / terrain sets"
        } if request.include_autotile else None
    }

@router.post("/generate/batch")
async def generate_asset_batch(request: AssetBatchRequest):
    """Generate multiple assets with consistent style"""
    
    generated_assets = []
    style_guide = {
        "project": request.project_name,
        "game_type": request.game_type,
        "art_style": request.art_style,
        "color_palette": [],
        "style_rules": []
    }
    
    # Generate style guide if AI available
    if LLM_AVAILABLE and EMERGENT_KEY and request.consistent_style:
        try:
            llm = LlmChat(api_key=EMERGENT_KEY, model="gpt-4o")
            llm.add_message("system", "You are a game art director. Create consistent style guides for game assets.")
            llm.add_message("user", f"""Create a style guide for a {request.game_type} game with {request.art_style} art style.
            Project: {request.project_name}
            Assets needed: {len(request.assets)}
            
            Provide:
            1. Color palette (5-8 hex colors)
            2. Style rules for consistency
            3. Technical specifications""")
            style_response = llm.chat()
            style_guide["ai_generated"] = style_response
        except Exception:
            pass
    
    for i, asset in enumerate(request.assets):
        generated_assets.append({
            "index": i,
            "asset": asset,
            "status": "queued",
            "style_applied": request.consistent_style
        })
    
    return {
        "batch_id": f"batch_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "project": request.project_name,
        "total_assets": len(request.assets),
        "style_guide": style_guide,
        "assets": generated_assets,
        "estimated_time": f"{len(request.assets) * 2} minutes"
    }

@router.get("/presets/{category}")
async def get_asset_presets(category: str):
    """Get preset configurations for common asset types"""
    
    presets = {
        "platformer": [
            {"name": "Player Character", "type": "sprite", "category": "characters", "style": "pixel_art", "resolution": "32x32", "frames": 8},
            {"name": "Enemy Slime", "type": "sprite", "category": "characters", "style": "pixel_art", "resolution": "32x32", "frames": 4},
            {"name": "Platform Tileset", "type": "tileset", "theme": "grass", "tile_size": 32, "tile_count": 48},
            {"name": "Collectible Coin", "type": "sprite", "category": "items", "style": "pixel_art", "resolution": "16x16", "frames": 6},
        ],
        "rpg": [
            {"name": "Hero Character", "type": "sprite", "category": "characters", "style": "pixel_art", "resolution": "64x64", "frames": 12},
            {"name": "Dungeon Tileset", "type": "tileset", "theme": "dungeon", "tile_size": 32, "tile_count": 96},
            {"name": "Sword Weapon", "type": "sprite", "category": "items", "style": "pixel_art", "resolution": "32x32"},
            {"name": "Potion Item", "type": "sprite", "category": "items", "style": "pixel_art", "resolution": "16x16"},
            {"name": "UI Panel", "type": "sprite", "category": "ui", "style": "fantasy", "resolution": "256x128"},
        ],
        "fps_3d": [
            {"name": "Assault Rifle", "type": "model", "category": "weapons", "style": "realistic", "poly": "mid_poly"},
            {"name": "Ammo Crate", "type": "model", "category": "props", "style": "realistic", "poly": "low_poly"},
            {"name": "Military Vehicle", "type": "model", "category": "vehicles", "style": "realistic", "poly": "mid_poly"},
            {"name": "Building Module", "type": "model", "category": "environment", "style": "realistic", "poly": "mid_poly"},
        ],
        "mobile_casual": [
            {"name": "Cute Character", "type": "sprite", "category": "characters", "style": "cartoon", "resolution": "128x128"},
            {"name": "UI Button Set", "type": "sprite", "category": "ui", "style": "cartoon", "resolution": "64x64"},
            {"name": "Background Parallax", "type": "sprite", "category": "environment", "style": "cartoon", "resolution": "1920x1080"},
        ]
    }
    
    if category not in presets:
        return {"available_categories": list(presets.keys())}
    
    return {
        "category": category,
        "presets": presets[category]
    }

def build_sprite_prompt(request: Sprite2DRequest) -> str:
    """Build a comprehensive sprite generation prompt"""
    return f"""2D Game Sprite Specification:
    - Description: {request.description}
    - Category: {request.category}
    - Type: {request.asset_type}
    - Art Style: {request.style}
    - Resolution: {request.resolution}
    - Animation Frames: {request.animation_frames}
    - Color Palette: {request.color_palette or 'Auto-generate'}
    - Export Format: {request.export_format}
    - Game Context: {request.game_context or 'General'}
    """

def build_model_prompt(request: Model3DRequest) -> str:
    """Build a comprehensive 3D model generation prompt"""
    return f"""3D Model Specification:
    - Description: {request.description}
    - Category: {request.category}
    - Type: {request.asset_type}
    - Art Style: {request.style}
    - Poly Count: {request.poly_count}
    - Textures: {request.textures} ({request.texture_resolution})
    - Rigging: {request.rigging}
    - Animations: {request.animations}
    - Export Format: {request.export_format}
    - Target Engine: {request.game_engine or 'Universal'}
    """
