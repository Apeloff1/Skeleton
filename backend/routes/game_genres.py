"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  3D GAME GENRES & SUBGENRES SYSTEM                                           ║
║  Complete Game Development Pipeline for All Game Types                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
import os

router = APIRouter(prefix="/game-genres", tags=["Game Genres"])

# Try to import LLM
try:
    from emergentintegrations.llm.chat import LlmChat
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")

# ============================================================================
# COMPLETE GAME GENRES DATABASE
# ============================================================================

GAME_GENRES = {
    "action": {
        "name": "Action",
        "icon": "⚔️",
        "description": "Fast-paced games focused on physical challenges",
        "subgenres": {
            "platformer_2d": {
                "name": "2D Platformer",
                "examples": ["Super Mario", "Celeste", "Hollow Knight"],
                "mechanics": ["jumping", "running", "collectibles", "enemies", "platforms"],
                "assets_needed": ["player_sprite", "enemy_sprites", "tileset", "backgrounds", "collectibles", "ui"]
            },
            "platformer_3d": {
                "name": "3D Platformer",
                "examples": ["Super Mario 64", "Crash Bandicoot", "Astro Bot"],
                "mechanics": ["3d_movement", "camera_control", "collectibles", "puzzles"],
                "assets_needed": ["player_model", "enemy_models", "level_geometry", "props", "skybox"]
            },
            "beat_em_up": {
                "name": "Beat 'em Up",
                "examples": ["Streets of Rage", "Castle Crashers"],
                "mechanics": ["combo_system", "multiple_enemies", "weapons", "co_op"],
                "assets_needed": ["player_characters", "enemy_types", "weapons", "environments"]
            },
            "hack_and_slash": {
                "name": "Hack and Slash",
                "examples": ["Devil May Cry", "God of War", "Bayonetta"],
                "mechanics": ["combo_system", "special_moves", "boss_fights", "upgrades"],
                "assets_needed": ["hero_model", "weapon_models", "enemy_models", "effects", "arenas"]
            }
        }
    },
    "shooter": {
        "name": "Shooter",
        "icon": "🔫",
        "description": "Games focused on ranged combat",
        "subgenres": {
            "fps": {
                "name": "First-Person Shooter",
                "examples": ["Call of Duty", "DOOM", "Counter-Strike"],
                "mechanics": ["first_person_camera", "weapons", "reloading", "health", "multiplayer"],
                "assets_needed": ["weapon_models", "hand_models", "enemy_models", "level_geometry", "effects"]
            },
            "tps": {
                "name": "Third-Person Shooter",
                "examples": ["Gears of War", "Uncharted", "Resident Evil 4"],
                "mechanics": ["cover_system", "over_shoulder_camera", "melee", "traversal"],
                "assets_needed": ["player_model", "weapons", "cover_objects", "environments"]
            },
            "shoot_em_up": {
                "name": "Shoot 'em Up (Shmup)",
                "examples": ["Gradius", "Ikaruga", "Enter the Gungeon"],
                "mechanics": ["bullet_patterns", "power_ups", "scrolling", "bosses"],
                "assets_needed": ["player_ship", "enemy_ships", "bullets", "power_ups", "backgrounds"]
            },
            "battle_royale": {
                "name": "Battle Royale",
                "examples": ["Fortnite", "PUBG", "Apex Legends"],
                "mechanics": ["shrinking_zone", "looting", "last_man_standing", "large_map"],
                "assets_needed": ["player_models", "weapons", "vehicles", "large_terrain", "buildings"]
            },
            "tactical_shooter": {
                "name": "Tactical Shooter",
                "examples": ["Rainbow Six", "Valorant", "SWAT"],
                "mechanics": ["team_based", "objective_modes", "abilities", "strategic_planning"],
                "assets_needed": ["operator_models", "weapons", "gadgets", "maps", "destructibles"]
            }
        }
    },
    "rpg": {
        "name": "Role-Playing Game",
        "icon": "🗡️",
        "description": "Character progression and story-driven games",
        "subgenres": {
            "jrpg": {
                "name": "Japanese RPG",
                "examples": ["Final Fantasy", "Persona", "Dragon Quest"],
                "mechanics": ["turn_based_combat", "party_system", "story_heavy", "level_up"],
                "assets_needed": ["party_characters", "enemies", "world_map", "towns", "dungeons", "ui"]
            },
            "action_rpg": {
                "name": "Action RPG",
                "examples": ["Dark Souls", "Diablo", "Monster Hunter"],
                "mechanics": ["real_time_combat", "loot_system", "character_builds", "bosses"],
                "assets_needed": ["player_models", "weapons", "armor", "monsters", "environments"]
            },
            "mmorpg": {
                "name": "MMORPG",
                "examples": ["World of Warcraft", "Final Fantasy XIV", "Guild Wars 2"],
                "mechanics": ["persistent_world", "raids", "pvp", "economy", "guilds"],
                "assets_needed": ["races", "classes", "mounts", "world_zones", "dungeons", "ui"]
            },
            "roguelike": {
                "name": "Roguelike/Roguelite",
                "examples": ["Hades", "Dead Cells", "Binding of Isaac"],
                "mechanics": ["permadeath", "procedural_generation", "runs", "unlocks"],
                "assets_needed": ["player_character", "enemies", "weapons", "room_tiles", "bosses"]
            },
            "crpg": {
                "name": "Computer RPG",
                "examples": ["Baldur's Gate 3", "Divinity", "Pillars of Eternity"],
                "mechanics": ["tactical_combat", "dialogue_choices", "party_management", "d&d_rules"],
                "assets_needed": ["characters", "portraits", "environments", "spell_effects", "items"]
            }
        }
    },
    "strategy": {
        "name": "Strategy",
        "icon": "♟️",
        "description": "Games requiring strategic thinking and planning",
        "subgenres": {
            "rts": {
                "name": "Real-Time Strategy",
                "examples": ["StarCraft", "Age of Empires", "Command & Conquer"],
                "mechanics": ["base_building", "resource_gathering", "unit_production", "fog_of_war"],
                "assets_needed": ["buildings", "units", "terrain", "resources", "ui"]
            },
            "turn_based": {
                "name": "Turn-Based Strategy",
                "examples": ["Civilization", "XCOM", "Fire Emblem"],
                "mechanics": ["turn_system", "grid_movement", "unit_types", "terrain_effects"],
                "assets_needed": ["units", "terrain_tiles", "buildings", "world_map", "ui"]
            },
            "tower_defense": {
                "name": "Tower Defense",
                "examples": ["Bloons TD", "Kingdom Rush", "Plants vs Zombies"],
                "mechanics": ["tower_placement", "waves", "upgrades", "paths"],
                "assets_needed": ["towers", "enemies", "paths", "projectiles", "ui"]
            },
            "auto_battler": {
                "name": "Auto Battler",
                "examples": ["Teamfight Tactics", "Dota Underlords"],
                "mechanics": ["unit_placement", "synergies", "economy", "auto_combat"],
                "assets_needed": ["champion_models", "board", "effects", "ui"]
            }
        }
    },
    "racing": {
        "name": "Racing",
        "icon": "🏎️",
        "description": "Speed-focused competitive games",
        "subgenres": {
            "arcade_racing": {
                "name": "Arcade Racing",
                "examples": ["Mario Kart", "Burnout", "Need for Speed"],
                "mechanics": ["drifting", "power_ups", "boost", "shortcuts"],
                "assets_needed": ["vehicles", "tracks", "power_ups", "effects", "environment"]
            },
            "sim_racing": {
                "name": "Simulation Racing",
                "examples": ["Gran Turismo", "Forza Motorsport", "iRacing"],
                "mechanics": ["realistic_physics", "car_tuning", "tire_wear", "pit_stops"],
                "assets_needed": ["detailed_cars", "realistic_tracks", "cockpit_view", "telemetry_ui"]
            },
            "kart_racing": {
                "name": "Kart Racing",
                "examples": ["Mario Kart", "Crash Team Racing"],
                "mechanics": ["items", "drifting", "characters", "themed_tracks"],
                "assets_needed": ["karts", "characters", "items", "fantasy_tracks"]
            }
        }
    },
    "sports": {
        "name": "Sports",
        "icon": "⚽",
        "description": "Real-world and fantasy sports simulations",
        "subgenres": {
            "football": {"name": "Football/Soccer", "examples": ["FIFA", "eFootball"]},
            "basketball": {"name": "Basketball", "examples": ["NBA 2K"]},
            "extreme_sports": {"name": "Extreme Sports", "examples": ["Tony Hawk's", "SSX"]},
            "fighting": {
                "name": "Fighting Games",
                "examples": ["Street Fighter", "Tekken", "Mortal Kombat"],
                "mechanics": ["combos", "special_moves", "blocking", "meters"],
                "assets_needed": ["fighters", "stages", "effects", "ui"]
            }
        }
    },
    "simulation": {
        "name": "Simulation",
        "icon": "🏠",
        "description": "Games that simulate real-world activities",
        "subgenres": {
            "life_sim": {
                "name": "Life Simulation",
                "examples": ["The Sims", "Animal Crossing", "Stardew Valley"],
                "mechanics": ["needs_management", "relationships", "customization", "activities"],
                "assets_needed": ["characters", "furniture", "buildings", "items", "environment"]
            },
            "city_builder": {
                "name": "City Builder",
                "examples": ["SimCity", "Cities Skylines"],
                "mechanics": ["zoning", "infrastructure", "economy", "citizens"],
                "assets_needed": ["buildings", "roads", "vehicles", "terrain", "ui"]
            },
            "management": {
                "name": "Management Sim",
                "examples": ["Planet Coaster", "Two Point Hospital"],
                "mechanics": ["building", "staff", "finance", "guest_satisfaction"],
                "assets_needed": ["buildings", "characters", "objects", "ui"]
            }
        }
    },
    "horror": {
        "name": "Horror",
        "icon": "👻",
        "description": "Games designed to scare and create tension",
        "subgenres": {
            "survival_horror": {
                "name": "Survival Horror",
                "examples": ["Resident Evil", "Silent Hill", "Amnesia"],
                "mechanics": ["limited_resources", "puzzles", "tension", "monsters"],
                "assets_needed": ["protagonist", "monsters", "dark_environments", "items", "effects"]
            },
            "psychological_horror": {
                "name": "Psychological Horror",
                "examples": ["Layers of Fear", "SOMA"],
                "mechanics": ["narrative", "atmosphere", "mind_games", "minimal_combat"],
                "assets_needed": ["environments", "effects", "audio", "narrative_items"]
            },
            "action_horror": {
                "name": "Action Horror",
                "examples": ["Dead Space", "Evil Within"],
                "mechanics": ["combat", "horror_elements", "resource_management"],
                "assets_needed": ["player", "weapons", "enemies", "environments", "effects"]
            }
        }
    },
    "puzzle": {
        "name": "Puzzle",
        "icon": "🧩",
        "description": "Games focused on problem-solving",
        "subgenres": {
            "logic_puzzle": {
                "name": "Logic Puzzle",
                "examples": ["Portal", "The Witness", "Baba Is You"],
                "mechanics": ["rules", "spatial_reasoning", "progressive_difficulty"],
                "assets_needed": ["puzzle_elements", "environments", "ui"]
            },
            "match_puzzle": {
                "name": "Match Puzzle",
                "examples": ["Candy Crush", "Bejeweled"],
                "mechanics": ["matching", "combos", "power_ups", "levels"],
                "assets_needed": ["gems", "effects", "ui", "backgrounds"]
            }
        }
    },
    "adventure": {
        "name": "Adventure",
        "icon": "🗺️",
        "description": "Story and exploration focused games",
        "subgenres": {
            "point_and_click": {
                "name": "Point and Click",
                "examples": ["Monkey Island", "Broken Age"],
                "mechanics": ["inventory_puzzles", "dialogue", "exploration"],
                "assets_needed": ["backgrounds", "characters", "items", "ui"]
            },
            "walking_sim": {
                "name": "Walking Simulator",
                "examples": ["Firewatch", "Gone Home"],
                "mechanics": ["exploration", "narrative", "atmosphere"],
                "assets_needed": ["detailed_environments", "props", "audio"]
            },
            "metroidvania": {
                "name": "Metroidvania",
                "examples": ["Metroid", "Castlevania", "Hollow Knight"],
                "mechanics": ["ability_gating", "backtracking", "map_exploration", "upgrades"],
                "assets_needed": ["player", "enemies", "bosses", "tileset", "abilities"]
            },
            "open_world": {
                "name": "Open World",
                "examples": ["GTA", "Zelda: BotW", "Elden Ring"],
                "mechanics": ["exploration", "quests", "fast_travel", "dynamic_world"],
                "assets_needed": ["vast_terrain", "characters", "vehicles", "buildings", "props"]
            }
        }
    },
    "sandbox": {
        "name": "Sandbox",
        "icon": "🏗️",
        "description": "Creative freedom and emergent gameplay",
        "subgenres": {
            "survival_craft": {
                "name": "Survival Crafting",
                "examples": ["Minecraft", "Terraria", "Valheim"],
                "mechanics": ["gathering", "crafting", "building", "survival"],
                "assets_needed": ["blocks", "items", "creatures", "biomes", "ui"]
            },
            "creative": {
                "name": "Creative Sandbox",
                "examples": ["Minecraft Creative", "Roblox"],
                "mechanics": ["building", "customization", "sharing"],
                "assets_needed": ["building_blocks", "tools", "ui"]
            }
        }
    }
}

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_genres_info():
    """Get game genres system information"""
    total_subgenres = sum(len(g.get("subgenres", {})) for g in GAME_GENRES.values())
    return {
        "name": "CodeDock Game Genres System",
        "version": "11.2.0",
        "total_genres": len(GAME_GENRES),
        "total_subgenres": total_subgenres,
        "features": [
            "Complete game genre database",
            "Asset requirements per genre",
            "Mechanics specifications",
            "Example games reference",
            "Full pipeline integration"
        ]
    }

@router.get("/all")
async def get_all_genres():
    """Get all game genres"""
    genres = []
    for key, genre in GAME_GENRES.items():
        genres.append({
            "key": key,
            "name": genre["name"],
            "icon": genre["icon"],
            "description": genre["description"],
            "subgenre_count": len(genre.get("subgenres", {}))
        })
    return {"genres": genres}

@router.get("/{genre_key}")
async def get_genre_details(genre_key: str):
    """Get detailed genre information"""
    if genre_key not in GAME_GENRES:
        raise HTTPException(status_code=404, detail="Genre not found")
    return GAME_GENRES[genre_key]

@router.get("/{genre_key}/{subgenre_key}")
async def get_subgenre_details(genre_key: str, subgenre_key: str):
    """Get detailed subgenre information with full pipeline"""
    if genre_key not in GAME_GENRES:
        raise HTTPException(status_code=404, detail="Genre not found")
    
    genre = GAME_GENRES[genre_key]
    if subgenre_key not in genre.get("subgenres", {}):
        raise HTTPException(status_code=404, detail="Subgenre not found")
    
    subgenre = genre["subgenres"][subgenre_key]
    
    return {
        "genre": genre["name"],
        "subgenre": subgenre,
        "pipeline": {
            "design_phase": [
                "Game Design Document (GDD)",
                "Core mechanics definition",
                "Level design planning",
                "Art style guide"
            ],
            "asset_phase": subgenre.get("assets_needed", []),
            "code_phase": [
                "Core game loop",
                "Player controller",
                "Game mechanics",
                "UI system",
                "Audio system"
            ],
            "polish_phase": [
                "Visual effects",
                "Sound design",
                "Game feel tuning",
                "Bug fixing"
            ]
        }
    }

class GameProjectRequest(BaseModel):
    name: str
    genre: str
    subgenre: str
    description: str
    target_platform: str = "pc"  # pc, mobile, console, web
    art_style: str = "stylized"
    scope: str = "indie"  # indie, aa, aaa

@router.post("/create-project")
async def create_game_project(request: GameProjectRequest):
    """Create a full game project specification"""
    
    if request.genre not in GAME_GENRES:
        raise HTTPException(status_code=404, detail="Genre not found")
    
    genre = GAME_GENRES[request.genre]
    subgenre = genre.get("subgenres", {}).get(request.subgenre, {})
    
    # Generate comprehensive project spec
    project = {
        "id": f"game_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "name": request.name,
        "genre": request.genre,
        "subgenre": request.subgenre,
        "description": request.description,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # AI-enhanced project generation
    if LLM_AVAILABLE and EMERGENT_KEY:
        try:
            llm = LlmChat(api_key=EMERGENT_KEY, model="gpt-4o")
            llm.add_message("system", """You are an expert game designer and technical director.
            Create comprehensive game project specifications with detailed technical requirements.""")
            llm.add_message("user", f"""Create a detailed game project specification for:
            
            Name: {request.name}
            Genre: {request.genre} - {request.subgenre}
            Description: {request.description}
            Platform: {request.target_platform}
            Art Style: {request.art_style}
            Scope: {request.scope}
            
            Provide:
            1. Game Design Document outline
            2. Core mechanics list
            3. Technical requirements
            4. Asset list with priorities
            5. Development milestones
            6. Estimated timeline""")
            project["ai_specification"] = llm.chat()
        except Exception:
            pass
    
    project["assets_required"] = subgenre.get("assets_needed", [])
    project["mechanics"] = subgenre.get("mechanics", [])
    project["reference_games"] = subgenre.get("examples", [])
    
    return project
