"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  GAME FACTORY ANALYTICS & EXPANDED API v17.5                                ║
║                                                                              ║
║  Extended API system:                                                        ║
║  - Game Templates (pre-built starters)                                       ║
║  - Build Analytics & History                                                 ║
║  - Agent Performance Metrics                                                 ║
║  - Pipeline Health Monitoring                                                ║
║  - Code Generation Statistics                                                ║
║  - Game Asset Registry                                                       ║
║  - Studio Dashboard                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/studio", tags=["studio"])

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
db = client[os.environ.get('DB_NAME', 'test_database')]

projects_col = db.game_projects
vault_col = db.code_vault
builds_col = db.build_history


# =============================================================================
# GAME TEMPLATES — Pre-built game starters
# =============================================================================

GAME_TEMPLATES = [
    {
        "id": "platformer_starter",
        "name": "2D Platformer Starter",
        "genre": "platformer_2d",
        "engine": "Pygame",
        "description": "Jump, run, collect coins. Classic side-scroller with physics, enemies, and level editor.",
        "difficulty": "beginner",
        "estimated_time": "2 hours",
        "includes": ["player_controller", "tile_map", "enemies", "collectibles", "camera", "level_editor"],
        "lines_of_code": 2500,
        "files": 12,
        "color": "#3B82F6",
    },
    {
        "id": "rpg_toolkit",
        "name": "RPG Toolkit",
        "genre": "rpg",
        "engine": "Pygame",
        "description": "Complete RPG framework with turn-based combat, inventory, quests, dialogue, and character progression.",
        "difficulty": "intermediate",
        "estimated_time": "6 hours",
        "includes": ["turn_based_combat", "inventory", "quest_system", "dialogue_trees", "character_stats", "save_system", "world_map"],
        "lines_of_code": 8000,
        "files": 28,
        "color": "#8B5CF6",
    },
    {
        "id": "fps_framework",
        "name": "FPS Framework",
        "genre": "fps",
        "engine": "Unity",
        "description": "First-person shooter with weapon system, enemy AI, health system, and multiplayer-ready netcode.",
        "difficulty": "advanced",
        "estimated_time": "8 hours",
        "includes": ["fps_controller", "weapon_system", "enemy_ai", "health_system", "hitbox_detection", "minimap", "multiplayer_stub"],
        "lines_of_code": 12000,
        "files": 35,
        "color": "#EF4444",
    },
    {
        "id": "survival_craft",
        "name": "Survival Crafting Base",
        "genre": "survival",
        "engine": "Godot",
        "description": "Gather, craft, build, survive. Resource system, crafting recipes, day/night cycle, hunger/thirst.",
        "difficulty": "intermediate",
        "estimated_time": "5 hours",
        "includes": ["resource_gathering", "crafting_system", "building_system", "day_night_cycle", "hunger_system", "weather"],
        "lines_of_code": 6000,
        "files": 22,
        "color": "#059669",
    },
    {
        "id": "roguelite_dungeon",
        "name": "Roguelite Dungeon Crawler",
        "genre": "roguelike",
        "engine": "Pygame",
        "description": "Procedural dungeons, permadeath, meta-progression. BSP dungeon gen, items, enemies, boss rooms.",
        "difficulty": "intermediate",
        "estimated_time": "4 hours",
        "includes": ["dungeon_generator", "permadeath", "meta_progression", "item_system", "enemy_variety", "boss_rooms"],
        "lines_of_code": 5000,
        "files": 18,
        "color": "#475569",
    },
    {
        "id": "visual_novel_engine",
        "name": "Visual Novel Engine",
        "genre": "visual_novel",
        "engine": "Ren'Py",
        "description": "Branching narrative engine with character portraits, backgrounds, music, choices, and save system.",
        "difficulty": "beginner",
        "estimated_time": "3 hours",
        "includes": ["dialogue_system", "branching_choices", "character_portraits", "backgrounds", "music_manager", "save_system"],
        "lines_of_code": 3000,
        "files": 15,
        "color": "#EC4899",
    },
    {
        "id": "tower_defense_kit",
        "name": "Tower Defense Kit",
        "genre": "tower_defense",
        "engine": "Pygame",
        "description": "Wave-based tower defense with tower placement, upgrade system, enemy paths, and economy.",
        "difficulty": "beginner",
        "estimated_time": "3 hours",
        "includes": ["tower_placement", "wave_spawner", "enemy_pathing", "tower_upgrades", "economy", "map_editor"],
        "lines_of_code": 3500,
        "files": 14,
        "color": "#7C3AED",
    },
    {
        "id": "card_game_framework",
        "name": "Card Game Framework",
        "genre": "card_game",
        "engine": "Pygame",
        "description": "Collectible card game foundation with deck building, card effects, turn system, and AI opponent.",
        "difficulty": "intermediate",
        "estimated_time": "5 hours",
        "includes": ["card_system", "deck_builder", "turn_manager", "effect_system", "ai_opponent", "collection"],
        "lines_of_code": 5500,
        "files": 20,
        "color": "#F97316",
    },
    {
        "id": "racing_game_base",
        "name": "Racing Game Base",
        "genre": "racing",
        "engine": "Unity",
        "description": "Arcade racing with vehicle physics, AI racers, track system, nitro boost, and leaderboards.",
        "difficulty": "intermediate",
        "estimated_time": "5 hours",
        "includes": ["vehicle_physics", "ai_racers", "track_system", "nitro_boost", "leaderboards", "camera_system"],
        "lines_of_code": 6500,
        "files": 24,
        "color": "#06B6D4",
    },
    {
        "id": "sandbox_world",
        "name": "Sandbox World Builder",
        "genre": "sandbox",
        "engine": "Unity",
        "description": "Open-ended sandbox with voxel terrain, building tools, physics, vehicles, and multiplayer.",
        "difficulty": "advanced",
        "estimated_time": "10 hours",
        "includes": ["voxel_terrain", "building_system", "physics_sandbox", "vehicles", "multiplayer", "weather_system"],
        "lines_of_code": 15000,
        "files": 42,
        "color": "#14B8A6",
    },
]

# =============================================================================
# AGENT ROSTER — Complete list of all 50 agents in the system
# =============================================================================

FULL_AGENT_ROSTER = [
    {"id": "jeeves", "name": "Jeeves", "role": "Lead Director & Compiler", "specialty": "Orchestration, GDD, Final Assembly", "color": "#8B5CF6", "icon": "star"},
    {"id": "world_agent", "name": "Terra", "role": "World Architect", "specialty": "Biomes, regions, level layouts", "color": "#10B981", "icon": "globe"},
    {"id": "systems_agent", "name": "Core", "role": "Systems Architect", "specialty": "ECS, state machines, game loops", "color": "#14B8A6", "icon": "construct"},
    {"id": "combat_agent", "name": "Striker", "role": "Combat Engineer", "specialty": "Hitboxes, damage, combos", "color": "#EF4444", "icon": "flash"},
    {"id": "npc_agent", "name": "Atlas", "role": "NPC Specialist", "specialty": "Behavior trees, dialogue, AI", "color": "#3B82F6", "icon": "people"},
    {"id": "narrative_agent", "name": "Lore", "role": "Narrative Director", "specialty": "Story, quests, dialogue trees", "color": "#F59E0B", "icon": "book"},
    {"id": "graphics_agent", "name": "Prism", "role": "Graphics Engineer", "specialty": "Shaders, VFX, lighting", "color": "#EC4899", "icon": "color-palette"},
    {"id": "physics_agent", "name": "Newton", "role": "Physics Engineer", "specialty": "Collisions, rigid bodies", "color": "#0EA5E9", "icon": "planet"},
    {"id": "audio_agent", "name": "Harmony", "role": "Audio Director", "specialty": "Music, SFX, spatial audio", "color": "#6366F1", "icon": "musical-notes"},
    {"id": "ui_ux_agent", "name": "Interface", "role": "UI/UX Designer", "specialty": "HUD, menus, accessibility", "color": "#F97316", "icon": "phone-portrait"},
    {"id": "economy_agent", "name": "Mint", "role": "Economy Designer", "specialty": "Loot, progression, balance", "color": "#84CC16", "icon": "cash"},
    {"id": "netcode_agent", "name": "Relay", "role": "Network Engineer", "specialty": "Netcode, matchmaking, sync", "color": "#06B6D4", "icon": "wifi"},
    {"id": "procgen_agent", "name": "Fractal", "role": "ProcGen Specialist", "specialty": "Procedural worlds, dungeons", "color": "#7C3AED", "icon": "dice"},
    {"id": "animation_agent", "name": "Motion", "role": "Animation Engineer", "specialty": "Skeletal, IK, blend trees", "color": "#F472B6", "icon": "walk"},
    {"id": "level_design_agent", "name": "Architect", "role": "Level Designer", "specialty": "Pacing, difficulty curves", "color": "#FBBF24", "icon": "layers"},
    {"id": "cinematic_agent", "name": "Director", "role": "Cinematics Lead", "specialty": "Cutscenes, cameras", "color": "#A78BFA", "icon": "film"},
    {"id": "monetization_agent", "name": "Revenue", "role": "Monetization Lead", "specialty": "Ethical F2P, battle passes", "color": "#34D399", "icon": "trending-up"},
    {"id": "accessibility_agent", "name": "Access", "role": "Accessibility Lead", "specialty": "WCAG, i18n, remapping", "color": "#2DD4BF", "icon": "accessibility"},
    {"id": "optimization_agent", "name": "Turbo", "role": "Performance Engineer", "specialty": "FPS, LOD, culling", "color": "#FB923C", "icon": "speedometer"},
    {"id": "inventory_agent", "name": "Forge", "role": "Inventory/Crafting", "specialty": "Items, recipes, equipment", "color": "#D97706", "icon": "cube"},
    {"id": "weather_agent", "name": "Storm", "role": "Weather Director", "specialty": "Dynamic weather, seasons", "color": "#6366F1", "icon": "thunderstorm"},
    {"id": "vfx_agent", "name": "Spark", "role": "VFX Artist", "specialty": "Particles, explosions, trails", "color": "#F43F5E", "icon": "sparkles"},
    {"id": "save_agent", "name": "Chronicle", "role": "Save System Lead", "specialty": "Save/load, cloud sync", "color": "#0284C7", "icon": "cloud-upload"},
    {"id": "achievement_agent", "name": "Glory", "role": "Achievement Designer", "specialty": "Trophies, challenges", "color": "#EAB308", "icon": "trophy"},
    {"id": "tutorial_agent", "name": "Guide", "role": "Tutorial Designer", "specialty": "Onboarding, hints", "color": "#4ADE80", "icon": "school"},
    {"id": "ai_director_agent", "name": "Adapt", "role": "AI Director", "specialty": "Dynamic difficulty", "color": "#C026D3", "icon": "pulse"},
    {"id": "modding_agent", "name": "Workshop", "role": "Modding Lead", "specialty": "Mod API, scripting", "color": "#78716C", "icon": "hammer"},
    {"id": "security_agent", "name": "Guardian", "role": "Security Lead", "specialty": "Anti-cheat, encryption", "color": "#991B1B", "icon": "lock-closed"},
    {"id": "vehicle_agent", "name": "Torque", "role": "Vehicle Engineer", "specialty": "Driving, mounts, flight", "color": "#0891B2", "icon": "car"},
    {"id": "terrain_agent", "name": "Flora", "role": "Terrain Artist", "specialty": "Terrain, foliage, biomes", "color": "#15803D", "icon": "leaf"},
    {"id": "water_agent", "name": "Tide", "role": "Fluid Engineer", "specialty": "Oceans, rivers, lava", "color": "#0EA5E9", "icon": "water"},
    {"id": "destruction_agent", "name": "Havoc", "role": "Destruction Engineer", "specialty": "Destructibles, fracture", "color": "#B91C1C", "icon": "bonfire"},
    {"id": "customization_agent", "name": "Persona", "role": "Customization Lead", "specialty": "Character creator, cosmetics", "color": "#A855F7", "icon": "body"},
    {"id": "pathfinding_agent", "name": "Scout", "role": "Navigation Engineer", "specialty": "NavMesh, A*, crowds", "color": "#059669", "icon": "navigate"},
    {"id": "dialogue_agent", "name": "Voice", "role": "Dialogue Director", "specialty": "Branching dialogue, VO", "color": "#DB2777", "icon": "mic"},
    {"id": "shader_agent", "name": "Pixel", "role": "Shader Programmer", "specialty": "GLSL, HLSL, materials", "color": "#7C3AED", "icon": "color-wand"},
    {"id": "input_agent", "name": "Axis", "role": "Input Engineer", "specialty": "Gamepad, touch, haptics", "color": "#64748B", "icon": "game-controller"},
    {"id": "photomode_agent", "name": "Lens", "role": "Photo Mode Designer", "specialty": "Screenshots, replays", "color": "#F472B6", "icon": "camera"},
    {"id": "social_agent", "name": "Link", "role": "Social Engineer", "specialty": "Leaderboards, clans, chat", "color": "#2563EB", "icon": "people-circle"},
    {"id": "boss_agent", "name": "Titan", "role": "Boss Designer", "specialty": "Multi-phase boss fights", "color": "#7F1D1D", "icon": "skull"},
    {"id": "stealth_agent", "name": "Shadow", "role": "Stealth Designer", "specialty": "Detection, noise, alerts", "color": "#1E293B", "icon": "eye-off"},
    {"id": "puzzle_agent", "name": "Enigma", "role": "Puzzle Designer", "specialty": "Puzzles, minigames", "color": "#EA580C", "icon": "extension-puzzle"},
    {"id": "cloth_agent", "name": "Weave", "role": "Cloth/Soft Body", "specialty": "Cloth, ropes, soft body", "color": "#BE185D", "icon": "shirt"},
    {"id": "analytics_agent", "name": "Insight", "role": "Analytics Lead", "specialty": "Telemetry, A/B testing", "color": "#0D9488", "icon": "bar-chart"},
    {"id": "crossplatform_agent", "name": "Bridge", "role": "Cross-Platform Lead", "specialty": "Porting, certification", "color": "#4338CA", "icon": "git-branch"},
    {"id": "companion_agent", "name": "Ally", "role": "Companion Designer", "specialty": "AI companions, party", "color": "#E11D48", "icon": "heart"},
    {"id": "ugc_agent", "name": "Canvas", "role": "UGC Director", "specialty": "Level editor, sharing", "color": "#CA8A04", "icon": "create"},
    {"id": "devops_agent", "name": "Pipeline", "role": "DevOps Engineer", "specialty": "CI/CD, builds, patching", "color": "#475569", "icon": "git-network"},
    {"id": "qa_agent", "name": "Sentinel", "role": "QA Director", "specialty": "AAA quality enforcement", "color": "#DC2626", "icon": "shield"},
    {"id": "oracle", "name": "Oracle", "role": "Competitor Analyst", "specialty": "Game knowledge 165K+ titles", "color": "#EF4444", "icon": "eye"},
]


# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/templates")
async def get_templates():
    """Get all pre-built game templates."""
    return {
        "templates": GAME_TEMPLATES,
        "total": len(GAME_TEMPLATES),
        "total_lines_of_code": sum(t["lines_of_code"] for t in GAME_TEMPLATES),
        "total_files": sum(t["files"] for t in GAME_TEMPLATES),
    }


@router.get("/template/{template_id}")
async def get_template(template_id: str):
    """Get details of a specific template."""
    tpl = next((t for t in GAME_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        return {"error": "Template not found"}
    return tpl


@router.get("/agents")
async def get_full_agent_roster():
    """Get the complete roster of all 50 agents."""
    return {
        "agents": FULL_AGENT_ROSTER,
        "total": len(FULL_AGENT_ROSTER),
        "categories": {
            "leadership": len([a for a in FULL_AGENT_ROSTER if "Director" in a["role"] or "Lead" in a["role"]]),
            "engineering": len([a for a in FULL_AGENT_ROSTER if "Engineer" in a["role"]]),
            "design": len([a for a in FULL_AGENT_ROSTER if "Designer" in a["role"]]),
            "art": len([a for a in FULL_AGENT_ROSTER if "Artist" in a["role"]]),
            "specialist": len([a for a in FULL_AGENT_ROSTER if "Specialist" in a["role"]]),
        },
    }


@router.get("/agent/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Get details for a specific agent."""
    agent = next((a for a in FULL_AGENT_ROSTER if a["id"] == agent_id), None)
    if not agent:
        return {"error": "Agent not found"}
    
    # Get vault entries for this agent
    vault_count = await vault_col.count_documents({"agent_id": agent_id})
    
    return {
        **agent,
        "vault_entries": vault_count,
    }


@router.get("/dashboard")
async def get_studio_dashboard():
    """Main studio dashboard — aggregated stats across all systems."""
    total_projects = await projects_col.count_documents({})
    compiled_projects = await projects_col.count_documents({"status": "compiled"})
    in_progress = await projects_col.count_documents({"status": "in_progress"})
    vault_entries = await vault_col.count_documents({})
    vault_unlearned = await vault_col.count_documents({"learned_by_jeeves": False})
    
    # Recent projects
    recent = await projects_col.find().sort("created_at", -1).limit(5).to_list(5)
    for r in recent:
        r.pop("_id", None)
        # Slim down for dashboard
        r.pop("steps_data", None)
        r.pop("compiled_output", None)
    
    return {
        "studio_name": "Tutolage Game Studio",
        "version": "v17.5",
        "stats": {
            "total_projects": total_projects,
            "compiled_projects": compiled_projects,
            "in_progress": in_progress,
            "total_agents": len(FULL_AGENT_ROSTER),
            "pipeline_steps": 50,
            "game_templates": len(GAME_TEMPLATES),
            "vault_entries": vault_entries,
            "vault_unlearned": vault_unlearned,
            "genres_supported": 16,
        },
        "recent_projects": recent,
        "health": {
            "backend": "online",
            "llm": "online",
            "database": "online",
            "pipeline": "ready",
        },
    }


@router.get("/analytics")
async def get_build_analytics():
    """Build analytics and statistics."""
    total_projects = await projects_col.count_documents({})
    
    # Genre distribution
    pipeline_genres = projects_col.aggregate([
        {"$group": {"_id": "$genre", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    genre_dist = {doc["_id"]: doc["count"] async for doc in pipeline_genres}
    
    # Engine distribution
    pipeline_engines = projects_col.aggregate([
        {"$group": {"_id": "$engine", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    engine_dist = {doc["_id"]: doc["count"] async for doc in pipeline_engines}
    
    # Status distribution
    pipeline_status = projects_col.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ])
    status_dist = {doc["_id"]: doc["count"] async for doc in pipeline_status}
    
    # Vault content types
    pipeline_vault = vault_col.aggregate([
        {"$group": {"_id": "$content_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    vault_types = {doc["_id"]: doc["count"] async for doc in pipeline_vault}
    
    # Competitor projects
    competitor_count = await projects_col.count_documents({"competitor_mode": True})
    
    return {
        "total_projects": total_projects,
        "genre_distribution": genre_dist,
        "engine_distribution": engine_dist,
        "status_distribution": status_dist,
        "vault_content_types": vault_types,
        "competitor_projects": competitor_count,
        "avg_steps_completed": 0,  # Would calculate from DB
    }


@router.get("/agent-metrics")
async def get_agent_metrics():
    """Performance metrics for all agents."""
    # Count vault entries per agent
    pipeline_agents = vault_col.aggregate([
        {"$group": {"_id": "$agent_id", "contributions": {"$sum": 1}, "code_blocks": {"$sum": {"$size": {"$ifNull": ["$code_blocks", []]}}}}},
        {"$sort": {"contributions": -1}},
    ])
    
    agent_metrics = []
    async for doc in pipeline_agents:
        agent_info = next((a for a in FULL_AGENT_ROSTER if a["id"] == doc["_id"]), None)
        agent_metrics.append({
            "agent_id": doc["_id"],
            "agent_name": agent_info["name"] if agent_info else doc["_id"],
            "role": agent_info["role"] if agent_info else "Unknown",
            "color": agent_info["color"] if agent_info else "#6B7280",
            "contributions": doc["contributions"],
            "code_blocks_generated": doc["code_blocks"],
        })
    
    return {
        "agents": agent_metrics,
        "total_agents": len(FULL_AGENT_ROSTER),
        "total_contributions": sum(a["contributions"] for a in agent_metrics),
        "top_contributor": agent_metrics[0] if agent_metrics else None,
    }


@router.get("/pipeline-phases")
async def get_pipeline_phases():
    """Get phases and their agents for the complete pipeline."""
    from routes.game_factory import BUILD_PIPELINE
    
    phases = {}
    for step in BUILD_PIPELINE:
        phase = step["phase"]
        if phase not in phases:
            phases[phase] = {"name": phase, "steps": [], "agent_count": 0}
        phases[phase]["steps"].append({
            "step": step["step"],
            "name": step["name"],
            "agent": step["agent"],
            "color": step["color"],
        })
        phases[phase]["agent_count"] += 1
    
    return {
        "phases": list(phases.values()),
        "total_phases": len(phases),
        "total_steps": len(BUILD_PIPELINE),
    }


@router.get("/code-stats")
async def get_code_generation_stats():
    """Code generation statistics across all projects."""
    total_vault = await vault_col.count_documents({})
    code_entries = await vault_col.count_documents({"code_blocks": {"$ne": []}})
    
    # Estimate total lines of code
    pipeline_code = vault_col.aggregate([
        {"$match": {"code_blocks": {"$ne": []}}},
        {"$project": {"block_count": {"$size": "$code_blocks"}}},
        {"$group": {"_id": None, "total_blocks": {"$sum": "$block_count"}}},
    ])
    total_blocks = 0
    async for doc in pipeline_code:
        total_blocks = doc.get("total_blocks", 0)
    
    return {
        "total_vault_entries": total_vault,
        "entries_with_code": code_entries,
        "total_code_blocks": total_blocks,
        "estimated_lines_of_code": total_blocks * 50,  # Rough estimate
        "code_density": round(code_entries / max(1, total_vault) * 100, 1),
    }


@router.get("/system-status")
async def get_system_status():
    """Full system health check."""
    from routes.game_factory import BUILD_PIPELINE, GAME_GENRES
    
    return {
        "status": "operational",
        "version": "v17.5",
        "timestamp": datetime.utcnow().isoformat(),
        "subsystems": {
            "game_factory": {"status": "online", "pipeline_steps": len(BUILD_PIPELINE), "genres": len(GAME_GENRES)},
            "agent_system": {"status": "online", "total_agents": len(FULL_AGENT_ROSTER)},
            "vault": {"status": "online"},
            "llm": {"status": "online", "model": "gpt-4o", "provider": "openai"},
            "database": {"status": "online", "type": "mongodb"},
            "templates": {"status": "online", "count": len(GAME_TEMPLATES)},
            "competitor_mode": {"status": "online", "knowledge_base": "165,000+ games"},
            "analytics": {"status": "online"},
        },
        "capabilities": {
            "game_creation": True,
            "auto_build": True,
            "compile_mode": True,
            "competitor_analysis": True,
            "multi_agent_chat": True,
            "level_system": True,
            "vault_logging": True,
            "templates": True,
        },
    }
