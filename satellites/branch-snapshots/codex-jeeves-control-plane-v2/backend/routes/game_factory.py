"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  GAME FACTORY v17.0 - Full Game Creation + Compile System                   ║
║                                                                              ║
║  End-to-end game creation pipeline:                                          ║
║  1. User describes a game                                                    ║
║  2. Jeeves creates a Game Design Document (GDD)                              ║
║  3. Specialized agents generate code for each system                         ║
║  4. All output logged to Vault                                               ║
║  5. Compile mode assembles everything into a deployable project              ║
║  6. Quality Control validates to AAA standards                               ║
║                                                                              ║
║  Full Compile Mode: Assembles all agent outputs into a final game project    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv()

# LLM Integration
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

router = APIRouter(prefix="/api/game-factory", tags=["game-factory"])

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
db = client[os.environ.get('DB_NAME', 'test_database')]

projects_collection = db.game_projects
build_steps_collection = db.game_build_steps
vault_collection = db.code_vault

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")

# =============================================================================
# GAME GENRES & TEMPLATES - 52 Genres, 104 Specialists, 110 Templates
# =============================================================================

from routes.game_genres_ultra import ULTRA_GENRES, get_all_specialists_flat, get_genre_specialist_prompt, get_genre_templates
from routes.game_specialists_batch2 import merge_batch2_into_genres, get_universal_specialists, UNIVERSAL_SPECIALISTS
from routes.game_design_agents import DESIGN_ERAS, DESIGN_DISCIPLINES, DESIGN_MOVEMENTS, get_all_design_agents, get_design_agent_prompt
from routes.game_technical_agents import ALL_TECHNICAL_CATEGORIES, get_all_technical_agents, get_technical_agent_prompt
from routes.game_factory_agents_extra import FACTORY_EXTRA_CATEGORIES, get_all_factory_extra_agents, get_factory_extra_prompt
from routes.game_roster_expansion import ROSTER_EXPANSION_CATEGORIES, get_all_roster_agents, get_roster_agent_prompt
from routes.game_academic_agents import ACADEMIC_CATEGORIES, get_all_academic_agents, get_academic_agent_prompt
from routes.game_team_leaders import TEAM_HIERARCHY_CATEGORIES, get_all_hierarchy_agents, get_hierarchy_agent_prompt
from routes.game_command_agents import COMMAND_CATEGORIES, get_all_command_agents, get_command_agent_prompt, generate_holodeck_render
from routes.game_expansion_alpha import EXPANSION_ALPHA_CATEGORIES, get_all_alpha_agents, get_alpha_agent_prompt
from routes.game_expansion_beta import EXPANSION_BETA_CATEGORIES, get_all_beta_agents, get_beta_agent_prompt
from routes.game_expansion_gamma import EXPANSION_GAMMA_CATEGORIES, get_all_gamma_agents, get_gamma_agent_prompt
from routes.game_parallel_society import get_all_shadow_agents, get_shadow_for_agent, get_shadow_agent_prompt, get_parallel_society_stats
from routes.game_ghost_society import get_all_ghost_agents, get_ghost_for_agent, get_ghost_agent_prompt, get_ghost_society_stats
from routes.game_angel_class import get_all_angel_agents, get_angel_for_agent, get_angels_for_original, get_angel_prompt, get_angel_class_stats
from routes.game_seraphim_class import get_all_seraphim_agents, get_seraphim_for_angel, get_seraphim_for_original, get_seraphim_prompt, get_seraphim_class_stats
from routes.game_cherubim_class import get_all_cherubim_agents, get_cherubim_for_agent, get_cherubim_for_original, get_cherubim_prompt, get_cherubim_class_stats
from routes.game_competency_matrices import get_competency_matrix, get_competency_summary_stats, MASTERY_LEVELS, INDUSTRY_STANDARDS, COMPETENCY_DIMENSIONS
from routes.game_knowledge_engine import get_agent_knowledge, get_knowledge_summary_stats, KNOWLEDGE_DOMAINS
from routes.game_synergy_engine import (
    log_ghost_review, log_angel_review, log_seraphim_review, log_cherubim_review,
    get_synergy_stats, jeeves_learn_from_vault, jeeves_get_wisdom,
    get_enriched_vault_stats, ensure_synergy_indexes,
)

# Import sub-routers
from routes.game_router_layers import router as layers_router
from routes.game_router_build import router as build_router
from routes.game_router_competitor import router as competitor_router

# Include sub-routers (refactored from monolithic game_factory.py)
router.include_router(layers_router, tags=["game-factory-layers"])
router.include_router(build_router, tags=["game-factory-build"])
router.include_router(competitor_router, tags=["game-factory-competitor"])
from routes.chat_vault import log_chat_message, log_shadow_review, get_room_history, get_agent_log, get_session_history, search_vault, get_vault_stats, ensure_vault_indexes
from routes.game_emperor_court import EMPEROR_COURT_CATEGORIES, get_all_court_guard_agents, get_court_guard_prompt
from routes.game_accuracy_alpha import ACCURACY_ALPHA_CATEGORIES, get_all_accuracy_alpha_agents, get_accuracy_alpha_prompt
from routes.game_accuracy_beta import ACCURACY_BETA_CATEGORIES, get_all_accuracy_beta_agents, get_accuracy_beta_prompt
from routes.game_accuracy_gamma import ACCURACY_GAMMA_CATEGORIES, get_all_accuracy_gamma_agents, get_accuracy_gamma_prompt
from routes.game_pantheon_alpha import PANTHEON_ALPHA_CATEGORIES, get_all_pantheon_alpha_agents, get_pantheon_alpha_prompt
from routes.game_pantheon_beta import PANTHEON_BETA_CATEGORIES, get_all_pantheon_beta_agents, get_pantheon_beta_prompt
from routes.game_pantheon_gamma import PANTHEON_GAMMA_CATEGORIES, get_all_pantheon_gamma_agents, get_pantheon_gamma_prompt
from routes.game_pantheon_delta import PANTHEON_DELTA_CATEGORIES, get_all_pantheon_delta_agents, get_pantheon_delta_prompt
from routes.game_pantheon_epsilon import PANTHEON_EPSILON_CATEGORIES, get_all_pantheon_epsilon_agents, get_pantheon_epsilon_prompt
from routes.game_pantheon_zeta import PANTHEON_ZETA_CATEGORIES, get_all_pantheon_zeta_agents, get_pantheon_zeta_prompt

GAME_GENRES = merge_batch2_into_genres(ULTRA_GENRES)

# =============================================================================
# BUILD PIPELINE STEPS - What each agent contributes
# =============================================================================

BUILD_PIPELINE = [
    {
        "step": 1, "name": "Game Design Document",
        "agent": "jeeves", "phase": "design",
        "description": "Jeeves creates the master GDD with game vision, mechanics, and scope",
        "icon": "document-text", "color": "#8B5CF6",
        "prompt_key": "gdd",
    },
    {
        "step": 2, "name": "World Architecture",
        "agent": "world_agent", "phase": "design",
        "description": "Terra designs the world structure, biomes, and level layouts",
        "icon": "globe", "color": "#10B981",
        "prompt_key": "world",
    },
    {
        "step": 3, "name": "Core Game Systems",
        "agent": "systems_agent", "phase": "engineering",
        "description": "Core builds the game architecture, ECS, state management",
        "icon": "construct", "color": "#14B8A6",
        "prompt_key": "systems",
    },
    {
        "step": 4, "name": "Combat & Gameplay",
        "agent": "combat_agent", "phase": "engineering",
        "description": "Striker designs the combat system, hitboxes, and game feel",
        "icon": "flash", "color": "#EF4444",
        "prompt_key": "combat",
    },
    {
        "step": 5, "name": "NPC & AI Behavior",
        "agent": "npc_agent", "phase": "engineering",
        "description": "Atlas creates NPCs with behavior trees, dialogue, and personality",
        "icon": "people", "color": "#3B82F6",
        "prompt_key": "npc",
    },
    {
        "step": 6, "name": "Narrative & Quests",
        "agent": "narrative_agent", "phase": "content",
        "description": "Lore writes the story, quests, dialogue trees, and lore",
        "icon": "book", "color": "#F59E0B",
        "prompt_key": "narrative",
    },
    {
        "step": 7, "name": "Graphics & Rendering",
        "agent": "graphics_agent", "phase": "visual",
        "description": "Prism designs shaders, VFX, lighting, and post-processing",
        "icon": "color-palette", "color": "#EC4899",
        "prompt_key": "graphics",
    },
    {
        "step": 8, "name": "Physics & Simulation",
        "agent": "physics_agent", "phase": "engineering",
        "description": "Newton implements physics, collisions, and simulations",
        "icon": "planet", "color": "#0EA5E9",
        "prompt_key": "physics",
    },
    {
        "step": 9, "name": "Audio & Music",
        "agent": "audio_agent", "phase": "content",
        "description": "Harmony creates the adaptive soundtrack and sound design",
        "icon": "musical-notes", "color": "#6366F1",
        "prompt_key": "audio",
    },
    {
        "step": 10, "name": "UI/UX & HUD",
        "agent": "ui_ux_agent", "phase": "visual",
        "description": "Interface designs menus, HUD, and player-facing UI",
        "icon": "phone-portrait", "color": "#F97316",
        "prompt_key": "ui",
    },
    {
        "step": 11, "name": "Economy & Progression",
        "agent": "economy_agent", "phase": "design",
        "description": "Mint balances the game economy, loot, and progression",
        "icon": "cash", "color": "#84CC16",
        "prompt_key": "economy",
    },
    {
        "step": 12, "name": "Multiplayer & Networking",
        "agent": "netcode_agent", "phase": "engineering",
        "description": "Relay engineers netcode, matchmaking, lobbies, and sync",
        "icon": "wifi", "color": "#06B6D4",
        "prompt_key": "netcode",
    },
    {
        "step": 13, "name": "Procedural Generation",
        "agent": "procgen_agent", "phase": "engineering",
        "description": "Fractal creates procedural worlds, dungeons, loot, and content",
        "icon": "dice", "color": "#7C3AED",
        "prompt_key": "procgen",
    },
    {
        "step": 14, "name": "Animation & Motion",
        "agent": "animation_agent", "phase": "visual",
        "description": "Motion builds skeletal animation, IK, blend trees, and state machines",
        "icon": "walk", "color": "#F472B6",
        "prompt_key": "animation",
    },
    {
        "step": 15, "name": "Level Design & Pacing",
        "agent": "level_design_agent", "phase": "design",
        "description": "Architect crafts level layouts, difficulty curves, and pacing",
        "icon": "layers", "color": "#FBBF24",
        "prompt_key": "level_design",
    },
    {
        "step": 16, "name": "Cinematics & Cutscenes",
        "agent": "cinematic_agent", "phase": "content",
        "description": "Director creates in-engine cutscenes, camera work, and story beats",
        "icon": "film", "color": "#A78BFA",
        "prompt_key": "cinematics",
    },
    {
        "step": 17, "name": "Monetization & Live Ops",
        "agent": "monetization_agent", "phase": "design",
        "description": "Revenue designs ethical monetization, battle passes, and live events",
        "icon": "trending-up", "color": "#34D399",
        "prompt_key": "monetization",
    },
    {
        "step": 18, "name": "Accessibility & Localization",
        "agent": "accessibility_agent", "phase": "qa",
        "description": "Access ensures WCAG compliance, remappable controls, and i18n support",
        "icon": "accessibility", "color": "#2DD4BF",
        "prompt_key": "accessibility",
    },
    {
        "step": 19, "name": "Performance & Optimization",
        "agent": "optimization_agent", "phase": "engineering",
        "description": "Turbo profiles bottlenecks, LOD, culling, and memory management",
        "icon": "speedometer", "color": "#FB923C",
        "prompt_key": "optimization",
    },
    {
        "step": 20, "name": "Inventory & Crafting",
        "agent": "inventory_agent", "phase": "engineering",
        "description": "Forge builds inventory management, crafting recipes, and item systems",
        "icon": "cube", "color": "#D97706",
        "prompt_key": "inventory",
    },
    {
        "step": 21, "name": "Weather & Environmental FX",
        "agent": "weather_agent", "phase": "visual",
        "description": "Storm creates dynamic weather, day/night cycles, and environmental effects",
        "icon": "thunderstorm", "color": "#6366F1",
        "prompt_key": "weather",
    },
    {
        "step": 22, "name": "Particle & VFX Systems",
        "agent": "vfx_agent", "phase": "visual",
        "description": "Spark designs GPU particle systems, explosions, magic effects, and trails",
        "icon": "sparkles", "color": "#F43F5E",
        "prompt_key": "vfx",
    },
    {
        "step": 23, "name": "Save System & Cloud Sync",
        "agent": "save_agent", "phase": "engineering",
        "description": "Chronicle builds save/load, auto-save, cloud sync, and data persistence",
        "icon": "cloud-upload", "color": "#0284C7",
        "prompt_key": "save_system",
    },
    {
        "step": 24, "name": "Achievement & Trophy System",
        "agent": "achievement_agent", "phase": "content",
        "description": "Glory creates achievements, trophies, challenges, and reward tracking",
        "icon": "trophy", "color": "#EAB308",
        "prompt_key": "achievements",
    },
    {
        "step": 25, "name": "Tutorial & Onboarding",
        "agent": "tutorial_agent", "phase": "design",
        "description": "Guide designs player onboarding, contextual tutorials, and help systems",
        "icon": "school", "color": "#4ADE80",
        "prompt_key": "tutorial",
    },
    {
        "step": 26, "name": "AI Director & Dynamic Difficulty",
        "agent": "ai_director_agent", "phase": "engineering",
        "description": "Adapt creates dynamic difficulty adjustment and AI-driven game direction",
        "icon": "pulse", "color": "#C026D3",
        "prompt_key": "ai_director",
    },
    {
        "step": 27, "name": "Modding Support & Workshop",
        "agent": "modding_agent", "phase": "engineering",
        "description": "Workshop builds mod API, asset loading, scripting hooks, and Steam Workshop",
        "icon": "hammer", "color": "#78716C",
        "prompt_key": "modding",
    },
    {
        "step": 28, "name": "Anti-Cheat & Security",
        "agent": "security_agent", "phase": "qa",
        "description": "Guardian implements anti-cheat, memory protection, and server validation",
        "icon": "lock-closed", "color": "#991B1B",
        "prompt_key": "security",
    },
    {
        "step": 29, "name": "Vehicle & Transportation",
        "agent": "vehicle_agent", "phase": "engineering",
        "description": "Torque designs vehicles, mounts, flight systems, and racing physics",
        "icon": "car", "color": "#0891B2",
        "prompt_key": "vehicles",
    },
    {
        "step": 30, "name": "Terrain & Foliage",
        "agent": "terrain_agent", "phase": "visual",
        "description": "Flora creates terrain sculpting, foliage placement, biome blending, and LOD",
        "icon": "leaf", "color": "#15803D",
        "prompt_key": "terrain",
    },
    {
        "step": 31, "name": "Water & Fluid Simulation",
        "agent": "water_agent", "phase": "visual",
        "description": "Tide simulates oceans, rivers, waterfalls, lava, and fluid dynamics",
        "icon": "water", "color": "#0EA5E9",
        "prompt_key": "water",
    },
    {
        "step": 32, "name": "Destruction & Deformation",
        "agent": "destruction_agent", "phase": "engineering",
        "description": "Havoc builds destructible environments, fracture meshes, and deformation",
        "icon": "bonfire", "color": "#B91C1C",
        "prompt_key": "destruction",
    },
    {
        "step": 33, "name": "Character Customization",
        "agent": "customization_agent", "phase": "content",
        "description": "Persona creates character creators, cosmetics, and appearance systems",
        "icon": "body", "color": "#A855F7",
        "prompt_key": "customization",
    },
    {
        "step": 34, "name": "Pathfinding & Navigation",
        "agent": "pathfinding_agent", "phase": "engineering",
        "description": "Scout builds navmesh, A* pathfinding, crowd flow, and steering behaviors",
        "icon": "navigate", "color": "#059669",
        "prompt_key": "pathfinding",
    },
    {
        "step": 35, "name": "Dialogue & Voice Direction",
        "agent": "dialogue_agent", "phase": "content",
        "description": "Voice directs dialogue trees, branching conversations, and VO scripting",
        "icon": "mic", "color": "#DB2777",
        "prompt_key": "dialogue",
    },
    {
        "step": 36, "name": "Shader Programming",
        "agent": "shader_agent", "phase": "visual",
        "description": "Pixel writes custom shaders, materials, post-processing, and compute shaders",
        "icon": "color-wand", "color": "#7C3AED",
        "prompt_key": "shaders",
    },
    {
        "step": 37, "name": "Input & Controls",
        "agent": "input_agent", "phase": "engineering",
        "description": "Axis handles gamepad, KB+M, touch, motion controls, and haptic feedback",
        "icon": "game-controller", "color": "#64748B",
        "prompt_key": "input_system",
    },
    {
        "step": 38, "name": "Photo Mode & Replay",
        "agent": "photomode_agent", "phase": "content",
        "description": "Lens creates photo mode, replay system, screenshot tools, and cinematic cameras",
        "icon": "camera", "color": "#F472B6",
        "prompt_key": "photo_mode",
    },
    {
        "step": 39, "name": "Leaderboard & Social",
        "agent": "social_agent", "phase": "engineering",
        "description": "Link builds leaderboards, friends lists, clans, chat, and social features",
        "icon": "people-circle", "color": "#2563EB",
        "prompt_key": "social",
    },
    {
        "step": 40, "name": "Boss Design System",
        "agent": "boss_agent", "phase": "design",
        "description": "Titan designs epic boss encounters, multi-phase fights, and spectacle moments",
        "icon": "skull", "color": "#7F1D1D",
        "prompt_key": "boss_design",
    },
    {
        "step": 41, "name": "Stealth & Detection",
        "agent": "stealth_agent", "phase": "engineering",
        "description": "Shadow creates stealth mechanics, detection cones, alert states, and noise propagation",
        "icon": "eye-off", "color": "#1E293B",
        "prompt_key": "stealth",
    },
    {
        "step": 42, "name": "Puzzle & Minigame System",
        "agent": "puzzle_agent", "phase": "design",
        "description": "Enigma designs puzzles, environmental interactions, and embedded minigames",
        "icon": "extension-puzzle", "color": "#EA580C",
        "prompt_key": "puzzles",
    },
    {
        "step": 43, "name": "Cloth & Soft Body Physics",
        "agent": "cloth_agent", "phase": "visual",
        "description": "Weave simulates cloth, capes, banners, rope, and soft body dynamics",
        "icon": "shirt", "color": "#BE185D",
        "prompt_key": "cloth_physics",
    },
    {
        "step": 44, "name": "Analytics & Telemetry",
        "agent": "analytics_agent", "phase": "qa",
        "description": "Insight tracks player behavior, heatmaps, session analytics, and A/B testing",
        "icon": "bar-chart", "color": "#0D9488",
        "prompt_key": "analytics",
    },
    {
        "step": 45, "name": "Cross-Platform & Porting",
        "agent": "crossplatform_agent", "phase": "engineering",
        "description": "Bridge handles cross-platform builds, platform-specific code, and certification",
        "icon": "git-branch", "color": "#4338CA",
        "prompt_key": "cross_platform",
    },
    {
        "step": 46, "name": "AI Companion System",
        "agent": "companion_agent", "phase": "engineering",
        "description": "Ally creates AI companions, party systems, follower behavior, and trust mechanics",
        "icon": "heart", "color": "#E11D48",
        "prompt_key": "ai_companion",
    },
    {
        "step": 47, "name": "Map Editor & UGC",
        "agent": "ugc_agent", "phase": "content",
        "description": "Canvas builds level editors, user-generated content tools, and sharing systems",
        "icon": "create", "color": "#CA8A04",
        "prompt_key": "ugc",
    },
    {
        "step": 48, "name": "Build & Deployment Pipeline",
        "agent": "devops_agent", "phase": "engineering",
        "description": "Pipeline creates CI/CD, build automation, platform packaging, and patching",
        "icon": "git-network", "color": "#475569",
        "prompt_key": "devops",
    },
    # =========================================================================
    # STEPS 49-98: ULTRA-SPECIALIZED SYSTEMS (50 new agents)
    # =========================================================================
    {
        "step": 49, "name": "Lighting & Global Illumination",
        "agent": "lighting_agent", "phase": "visual",
        "description": "Lumen designs dynamic GI, baked lightmaps, volumetric light, and ray tracing",
        "icon": "sunny", "color": "#FBBF24",
        "prompt_key": "lighting",
    },
    {
        "step": 50, "name": "Camera & Cinematic Control",
        "agent": "camera_agent", "phase": "engineering",
        "description": "Focus builds smart cameras, lock-on, orbit, 3rd person, and dynamic framing",
        "icon": "videocam", "color": "#818CF8",
        "prompt_key": "camera",
    },
    {
        "step": 51, "name": "Skill Tree & Talent System",
        "agent": "skilltree_agent", "phase": "design",
        "description": "Sage designs branching skill trees, talent points, and build diversity",
        "icon": "git-branch", "color": "#A78BFA",
        "prompt_key": "skill_tree",
    },
    {
        "step": 52, "name": "Magic & Spell System",
        "agent": "magic_agent", "phase": "engineering",
        "description": "Arcane creates spell casting, mana systems, elemental combos, and spell crafting",
        "icon": "flame", "color": "#C084FC",
        "prompt_key": "magic",
    },
    {
        "step": 53, "name": "Faction & Reputation",
        "agent": "faction_agent", "phase": "design",
        "description": "Diplomat designs factions, reputation tiers, allegiances, and political systems",
        "icon": "flag", "color": "#F97316",
        "prompt_key": "factions",
    },
    {
        "step": 54, "name": "Housing & Base Building",
        "agent": "housing_agent", "phase": "engineering",
        "description": "Hearth creates player housing, base building, decoration, and property systems",
        "icon": "home", "color": "#92400E",
        "prompt_key": "housing",
    },
    {
        "step": 55, "name": "Pet & Summon System",
        "agent": "pet_agent", "phase": "engineering",
        "description": "Tamer builds pet capture, taming, breeding, evolution, and summon mechanics",
        "icon": "paw", "color": "#FB923C",
        "prompt_key": "pets",
    },
    {
        "step": 56, "name": "Trading & Auction House",
        "agent": "trading_agent", "phase": "engineering",
        "description": "Broker creates player trading, auction house, market economy, and escrow",
        "icon": "swap-horizontal", "color": "#10B981",
        "prompt_key": "trading",
    },
    {
        "step": 57, "name": "Farming & Agriculture",
        "agent": "farming_agent", "phase": "content",
        "description": "Harvest designs crop growth, seasons, soil quality, irrigation, and livestock",
        "icon": "nutrition", "color": "#65A30D",
        "prompt_key": "farming",
    },
    {
        "step": 58, "name": "Cooking & Recipe System",
        "agent": "cooking_agent", "phase": "content",
        "description": "Chef creates cooking mechanics, recipe discovery, buff food, and restaurants",
        "icon": "restaurant", "color": "#EA580C",
        "prompt_key": "cooking",
    },
    {
        "step": 59, "name": "Alchemy & Potion Crafting",
        "agent": "alchemy_agent", "phase": "content",
        "description": "Alchemist designs potion brewing, ingredient mixing, and transmutation",
        "icon": "flask", "color": "#7C3AED",
        "prompt_key": "alchemy",
    },
    {
        "step": 60, "name": "Enchanting & Item Enhancement",
        "agent": "enchanting_agent", "phase": "engineering",
        "description": "Runesmith creates enchanting tables, gem socketing, and upgrade paths",
        "icon": "diamond", "color": "#2563EB",
        "prompt_key": "enchanting",
    },
    {
        "step": 61, "name": "Blacksmithing & Forging",
        "agent": "smithing_agent", "phase": "content",
        "description": "Smith designs weapon forging, armor crafting, material tiers, and tempering",
        "icon": "hammer", "color": "#78716C",
        "prompt_key": "smithing",
    },
    {
        "step": 62, "name": "Fishing & Side Activities",
        "agent": "fishing_agent", "phase": "content",
        "description": "Angler creates fishing mini-game, rare catches, tournaments, and side hobbies",
        "icon": "boat", "color": "#0EA5E9",
        "prompt_key": "fishing",
    },
    {
        "step": 63, "name": "Music & Instrument System",
        "agent": "instrument_agent", "phase": "content",
        "description": "Bard designs playable instruments, music creation, and rhythm mechanics",
        "icon": "musical-note", "color": "#D946EF",
        "prompt_key": "instruments",
    },
    {
        "step": 64, "name": "Relationship & Romance",
        "agent": "romance_agent", "phase": "content",
        "description": "Heart creates relationship bonds, romance options, gift-giving, and social links",
        "icon": "heart-circle", "color": "#E11D48",
        "prompt_key": "romance",
    },
    {
        "step": 65, "name": "Emote & Expression System",
        "agent": "emote_agent", "phase": "content",
        "description": "Mime builds emotes, gestures, dances, communication wheels, and player expression",
        "icon": "happy", "color": "#FACC15",
        "prompt_key": "emotes",
    },
    {
        "step": 66, "name": "Lore & Codex System",
        "agent": "codex_agent", "phase": "content",
        "description": "Scholar creates an in-game encyclopedia, bestiary, item catalog, and lore entries",
        "icon": "library", "color": "#B45309",
        "prompt_key": "codex",
    },
    {
        "step": 67, "name": "Map & Fog of War",
        "agent": "cartography_agent", "phase": "engineering",
        "description": "Atlas creates world maps, fog of war, waypoints, fast travel, and map markers",
        "icon": "map", "color": "#0D9488",
        "prompt_key": "map_system",
    },
    {
        "step": 68, "name": "Cover & Tactical System",
        "agent": "cover_agent", "phase": "engineering",
        "description": "Bastion designs cover mechanics, lean/peek, blind fire, and tactical movement",
        "icon": "shield-half", "color": "#525252",
        "prompt_key": "cover_system",
    },
    {
        "step": 69, "name": "Grappling & Advanced Traversal",
        "agent": "traversal_agent", "phase": "engineering",
        "description": "Viper creates wall-running, grappling hooks, parkour, zip-lines, and mantling",
        "icon": "resize", "color": "#0891B2",
        "prompt_key": "traversal",
    },
    {
        "step": 70, "name": "Swimming & Underwater",
        "agent": "swimming_agent", "phase": "engineering",
        "description": "Depths designs swimming, diving, oxygen system, underwater combat, and currents",
        "icon": "water", "color": "#164E63",
        "prompt_key": "swimming",
    },
    {
        "step": 71, "name": "Flying & Aerial Combat",
        "agent": "flight_agent", "phase": "engineering",
        "description": "Falcon creates flight systems, aerial dogfights, gliding, and sky navigation",
        "icon": "airplane", "color": "#60A5FA",
        "prompt_key": "flight",
    },
    {
        "step": 72, "name": "Naval & Ship Combat",
        "agent": "naval_agent", "phase": "engineering",
        "description": "Admiral designs ship sailing, naval battles, crew management, and boarding",
        "icon": "boat", "color": "#1E3A5F",
        "prompt_key": "naval",
    },
    {
        "step": 73, "name": "Space & Zero-G Mechanics",
        "agent": "space_agent", "phase": "engineering",
        "description": "Orbit creates space flight, zero-gravity physics, docking, and space combat",
        "icon": "rocket", "color": "#1E1B4B",
        "prompt_key": "space",
    },
    {
        "step": 74, "name": "Mech & Titan Systems",
        "agent": "mech_agent", "phase": "engineering",
        "description": "Titan creates pilotable mechs, titan falls, modular loadouts, and mech combat",
        "icon": "hardware-chip", "color": "#4B5563",
        "prompt_key": "mechs",
    },
    {
        "step": 75, "name": "Siege & Large-Scale Battles",
        "agent": "siege_agent", "phase": "design",
        "description": "Warlord designs sieges, castle assaults, 100-player battles, and war mechanics",
        "icon": "bonfire", "color": "#991B1B",
        "prompt_key": "siege",
    },
    {
        "step": 76, "name": "Army & Unit Management",
        "agent": "rts_agent", "phase": "design",
        "description": "General creates army building, unit control, formations, and resource strategy",
        "icon": "people", "color": "#6D28D9",
        "prompt_key": "army_management",
    },
    {
        "step": 77, "name": "City Building & Management",
        "agent": "city_agent", "phase": "design",
        "description": "Mayor designs city planning, zoning, population, infrastructure, and happiness",
        "icon": "business", "color": "#0369A1",
        "prompt_key": "city_building",
    },
    {
        "step": 78, "name": "Research & Tech Trees",
        "agent": "research_agent", "phase": "design",
        "description": "Scholar designs technology progression, research chains, and era advancement",
        "icon": "flask", "color": "#0F766E",
        "prompt_key": "research",
    },
    {
        "step": 79, "name": "Diplomacy & Trade Routes",
        "agent": "diplomacy_agent", "phase": "design",
        "description": "Ambassador creates treaties, alliances, trade networks, and political intrigue",
        "icon": "hand-left", "color": "#CA8A04",
        "prompt_key": "diplomacy",
    },
    {
        "step": 80, "name": "Genetics & Creature Breeding",
        "agent": "genetics_agent", "phase": "engineering",
        "description": "Darwin designs creature genetics, breeding, mutations, and evolution systems",
        "icon": "fitness", "color": "#059669",
        "prompt_key": "genetics",
    },
    {
        "step": 81, "name": "Volumetric Effects & Clouds",
        "agent": "volumetric_agent", "phase": "visual",
        "description": "Nimbus creates volumetric fog, clouds, god rays, and atmospheric scattering",
        "icon": "cloud", "color": "#94A3B8",
        "prompt_key": "volumetrics",
    },
    {
        "step": 82, "name": "Decal & Surface System",
        "agent": "decal_agent", "phase": "visual",
        "description": "Stamp creates bullet holes, blood splatter, footprints, tire marks, and scorch marks",
        "icon": "brush", "color": "#DC2626",
        "prompt_key": "decals",
    },
    {
        "step": 83, "name": "Ragdoll & Death Physics",
        "agent": "ragdoll_agent", "phase": "engineering",
        "description": "Puppet creates ragdoll deaths, hit reactions, physics knockback, and death animations",
        "icon": "body", "color": "#7C2D12",
        "prompt_key": "ragdoll",
    },
    {
        "step": 84, "name": "Facial Animation & Emotion",
        "agent": "facial_agent", "phase": "visual",
        "description": "Expression designs FACS-based facial rigging, emotion blending, and lip sync",
        "icon": "happy", "color": "#EC4899",
        "prompt_key": "facial_animation",
    },
    {
        "step": 85, "name": "Motion Capture Pipeline",
        "agent": "mocap_agent", "phase": "visual",
        "description": "Capture creates MoCap data integration, cleanup, retargeting, and blending",
        "icon": "recording", "color": "#BE123C",
        "prompt_key": "mocap",
    },
    {
        "step": 86, "name": "Damage Numbers & Combat Juice",
        "agent": "juice_agent", "phase": "design",
        "description": "Impact designs hit numbers, screen shake, freeze frames, and game feel polish",
        "icon": "flash", "color": "#F59E0B",
        "prompt_key": "combat_juice",
    },
    {
        "step": 87, "name": "Matchmaking & Ranking",
        "agent": "matchmaking_agent", "phase": "engineering",
        "description": "Elo designs skill-based matchmaking, ranking tiers, seasons, and leaderboards",
        "icon": "podium", "color": "#4F46E5",
        "prompt_key": "matchmaking",
    },
    {
        "step": 88, "name": "Spectator & Esports Mode",
        "agent": "spectator_agent", "phase": "engineering",
        "description": "Broadcast creates spectator tools, kill cams, instant replay, and esports HUD",
        "icon": "tv", "color": "#7C3AED",
        "prompt_key": "spectator",
    },
    {
        "step": 89, "name": "Dynamic World Events",
        "agent": "events_agent", "phase": "content",
        "description": "Herald creates world events, invasions, seasonal events, and community goals",
        "icon": "megaphone", "color": "#EA580C",
        "prompt_key": "world_events",
    },
    {
        "step": 90, "name": "NPC Schedules & Routines",
        "agent": "routine_agent", "phase": "engineering",
        "description": "Clock designs NPC daily routines, work/sleep cycles, and time-based behavior",
        "icon": "time", "color": "#0284C7",
        "prompt_key": "npc_routines",
    },
    {
        "step": 91, "name": "Crime & Bounty System",
        "agent": "bounty_agent", "phase": "design",
        "description": "Marshal creates crime detection, wanted levels, bounty hunting, and jail systems",
        "icon": "alert-circle", "color": "#B91C1C",
        "prompt_key": "crime_system",
    },
    {
        "step": 92, "name": "Environmental Storytelling",
        "agent": "envstory_agent", "phase": "content",
        "description": "Whisper designs environmental narrative, scene composition, and found storytelling",
        "icon": "eye", "color": "#6B7280",
        "prompt_key": "env_storytelling",
    },
    {
        "step": 93, "name": "Easter Eggs & Secrets",
        "agent": "secrets_agent", "phase": "content",
        "description": "Cipher hides easter eggs, secret rooms, developer references, and ARG puzzles",
        "icon": "search", "color": "#A3E635",
        "prompt_key": "secrets",
    },
    {
        "step": 94, "name": "New Game Plus & Replayability",
        "agent": "replay_agent", "phase": "design",
        "description": "Loop designs NG+, alternate endings, challenge modes, and endless replayability",
        "icon": "refresh-circle", "color": "#22D3EE",
        "prompt_key": "new_game_plus",
    },
    {
        "step": 95, "name": "Procedural Music & Adaptive Audio",
        "agent": "procmusic_agent", "phase": "content",
        "description": "Synth creates procedural music generation, dynamic layers, and reactive soundscapes",
        "icon": "radio", "color": "#A855F7",
        "prompt_key": "procedural_music",
    },
    {
        "step": 96, "name": "HDR & Color Science",
        "agent": "color_agent", "phase": "visual",
        "description": "Palette designs HDR rendering, tonemapping, color grading LUTs, and visual identity",
        "icon": "color-fill", "color": "#F43F5E",
        "prompt_key": "color_science",
    },
    {
        "step": 97, "name": "Loading & Transition Design",
        "agent": "loading_agent", "phase": "design",
        "description": "Flow designs loading screens, tips, seamless transitions, and fast travel cinematics",
        "icon": "hourglass", "color": "#78716C",
        "prompt_key": "loading_screens",
    },
    {
        "step": 98, "name": "Credits & Attribution",
        "agent": "credits_agent", "phase": "content",
        "description": "Archive creates game credits, special thanks, legal notices, and credits sequence",
        "icon": "document-text", "color": "#64748B",
        "prompt_key": "credits",
    },
    {
        "step": 99, "name": "Quality Assurance",
        "agent": "qa_agent", "phase": "qa",
        "description": "Sentinel reviews all 98 systems for AAA quality standards with VETO power",
        "icon": "shield", "color": "#DC2626",
        "prompt_key": "qa",
    },
    {
        "step": 100, "name": "Final Compilation",
        "agent": "jeeves", "phase": "compile",
        "description": "Jeeves compiles ALL 98 agent outputs into a complete, deployable AAA game project",
        "icon": "build", "color": "#8B5CF6",
        "prompt_key": "compile",
    },
]

# Merge ultra pipeline steps (99-198) into BUILD_PIPELINE
from routes.game_factory_pipeline_ultra import ULTRA_PIPELINE_STEPS
BUILD_PIPELINE.extend(ULTRA_PIPELINE_STEPS)

# =============================================================================
# AGENT SYSTEM PROMPTS FOR GAME GENERATION
# =============================================================================

def get_agent_prompt(prompt_key: str, game_description: str, genre: str, engine: str, gdd_context: str = "") -> tuple:
    """Returns (system_prompt, user_prompt) for each build step."""

    context = f"\nGame: {game_description}\nGenre: {genre}\nEngine: {engine}"
    if gdd_context:
        context += f"\n\nGDD Summary:\n{gdd_context}"

    prompts = {
        "gdd": (
            "You are Jeeves, Lead Game Director at a AAA studio. Create a comprehensive Game Design Document.",
            f"""Create a complete Game Design Document for this game:
{context}

Output a detailed JSON GDD:
{{
  "title": "Game Title",
  "tagline": "One-line pitch",
  "genre": "{genre}",
  "engine": "{engine}",
  "overview": "3-5 sentence game overview",
  "core_mechanics": ["mechanic1", "mechanic2", "mechanic3"],
  "unique_selling_points": ["usp1", "usp2"],
  "player_experience": "What the player feels",
  "art_style": "Visual direction description",
  "technical_scope": {{
    "target_platform": "PC/Console/Mobile",
    "target_fps": 60,
    "estimated_dev_time": "X months"
  }},
  "game_loop": {{
    "core_loop": "Description of the main gameplay loop",
    "meta_loop": "Description of meta-progression",
    "session_length": "15-30 min"
  }},
  "world_design": {{
    "setting": "World setting",
    "regions": ["region1", "region2"],
    "scale": "small/medium/large"
  }},
  "systems": ["combat", "inventory", "crafting", "etc"],
  "content_scope": {{
    "levels": 10,
    "npcs": 20,
    "items": 50,
    "quests": 15
  }}
}}"""
        ),
        "world": (
            "You are Terra, World Building Architect at a AAA studio. Design the complete game world.",
            f"""Based on this game design, create the world architecture:
{context}

Output complete world design JSON with implementation code:
{{
  "world_name": "...",
  "regions": [
    {{
      "name": "Region Name",
      "biome": "forest/desert/city/etc",
      "description": "...",
      "size": "500x500 units",
      "locations": [
        {{"name": "...", "type": "town/dungeon/landmark", "connections": ["other_location"]}}
      ],
      "enemies": ["enemy_type1"],
      "resources": ["resource1"],
      "secrets": ["hidden_area1"]
    }}
  ],
  "world_map_code": "# Complete Python/C# code for world generation\\nclass WorldGenerator:\\n    ...",
  "terrain_generation_code": "# Terrain generation algorithm\\n...",
  "streaming_system_code": "# World streaming for large worlds\\n..."
}}"""
        ),
        "systems": (
            "You are Core, Systems Architect at a AAA studio. Build the core game architecture.",
            f"""Design and implement the core game systems:
{context}

Output complete systems architecture with runnable code:
{{
  "architecture": "ECS/Component/OOP",
  "main_game_loop_code": "# Complete game loop implementation\\nclass GameEngine:\\n    def __init__(self):\\n        ...\\n    def update(self, dt):\\n        ...\\n    def render(self):\\n        ...",
  "state_machine_code": "# Game state management\\nclass GameStateMachine:\\n    ...",
  "save_system_code": "# Save/Load system\\nclass SaveManager:\\n    ...",
  "input_handler_code": "# Input handling\\nclass InputManager:\\n    ...",
  "event_system_code": "# Event bus for decoupled communication\\nclass EventBus:\\n    ...",
  "config": {{
    "tick_rate": 60,
    "fixed_timestep": 0.016,
    "max_entities": 10000
  }}
}}"""
        ),
        "combat": (
            "You are Striker, Combat Systems Engineer at a AAA studio. Design the complete combat system.",
            f"""Design and implement the combat/gameplay systems:
{context}

Output complete combat system with runnable code:
{{
  "combat_type": "action/turn-based/hybrid",
  "damage_system_code": "# Complete damage calculation\\nclass DamageSystem:\\n    ...",
  "combo_system_code": "# Combo/ability system\\nclass ComboManager:\\n    ...",
  "hitbox_system_code": "# Hitbox and collision detection\\nclass HitboxSystem:\\n    ...",
  "status_effects_code": "# Buff/debuff system\\nclass StatusEffectManager:\\n    ...",
  "balance_config": {{
    "player_base_hp": 100,
    "damage_scaling": "linear",
    "critical_chance": 0.1,
    "defense_formula": "damage * (1 - armor / (armor + 100))"
  }},
  "enemy_ai_code": "# Enemy combat AI\\nclass EnemyCombatAI:\\n    ..."
}}"""
        ),
        "npc": (
            "You are Atlas, NPC & Character AI Specialist at a AAA studio.",
            f"""Create the NPC system with AI behaviors:
{context}

Output complete NPC system with runnable code:
{{
  "npc_system_code": "# NPC Manager\\nclass NPCManager:\\n    ...",
  "behavior_tree_code": "# Behavior tree implementation\\nclass BehaviorTree:\\n    ...",
  "dialogue_system_code": "# Dialogue manager\\nclass DialogueManager:\\n    ...",
  "npcs": [
    {{
      "name": "NPC Name",
      "role": "merchant/quest_giver/etc",
      "personality": "...",
      "dialogue_tree": {{"greeting": "...", "options": []}},
      "behavior": "patrol/idle/follow"
    }}
  ],
  "crowd_simulation_code": "# Crowd AI for background NPCs\\n..."
}}"""
        ),
        "narrative": (
            "You are Lore, Narrative Director at a AAA studio.",
            f"""Write the complete narrative, quests, and story:
{context}

Output complete narrative content:
{{
  "main_story": {{
    "act_1": {{"title": "...", "summary": "...", "key_events": [...]}},
    "act_2": {{"title": "...", "summary": "...", "key_events": [...]}},
    "act_3": {{"title": "...", "summary": "...", "key_events": [...]}}
  }},
  "quests": [
    {{
      "name": "Quest Name",
      "type": "main/side/hidden",
      "description": "...",
      "objectives": ["obj1", "obj2"],
      "rewards": {{"xp": 100, "items": ["item1"]}},
      "dialogue": {{"accept": "...", "progress": "...", "complete": "..."}}
    }}
  ],
  "quest_system_code": "# Quest tracking system\\nclass QuestManager:\\n    ...",
  "lore_entries": [
    {{"title": "Lore Entry", "content": "...", "category": "world/character/item"}}
  ],
  "dialogue_trees_code": "# Branching dialogue system\\n..."
}}"""
        ),
        "graphics": (
            "You are Prism, Graphics & Rendering Engineer at a AAA studio.",
            f"""Design the graphics pipeline and visual systems:
{context}

Output complete graphics system with code:
{{
  "art_direction": {{
    "style": "stylized/realistic/pixel/etc",
    "color_palette": ["#hex1", "#hex2", "#hex3"],
    "lighting_model": "PBR/toon/custom"
  }},
  "shader_code": "# Main character shader\\n...",
  "particle_system_code": "# VFX particle system\\nclass ParticleEmitter:\\n    ...",
  "lighting_setup_code": "# Global illumination setup\\n...",
  "post_processing_code": "# Post-processing pipeline\\nclass PostProcessPipeline:\\n    ...",
  "camera_system_code": "# Dynamic camera system\\nclass CameraController:\\n    ...",
  "rendering_config": {{
    "resolution": "1920x1080",
    "shadow_quality": "high",
    "anti_aliasing": "TAA",
    "bloom": true,
    "ambient_occlusion": true
  }}
}}"""
        ),
        "physics": (
            "You are Newton, Physics & Simulation Engineer at a AAA studio.",
            f"""Implement the physics and simulation systems:
{context}

Output complete physics system with code:
{{
  "physics_engine_code": "# Physics engine wrapper\\nclass PhysicsWorld:\\n    ...",
  "collision_system_code": "# Collision detection & response\\nclass CollisionSystem:\\n    ...",
  "rigid_body_code": "# Rigid body dynamics\\nclass RigidBody:\\n    ...",
  "character_controller_code": "# Character physics controller\\nclass CharacterController:\\n    ...",
  "projectile_system_code": "# Projectile physics\\nclass ProjectileSystem:\\n    ...",
  "physics_config": {{
    "gravity": -9.81,
    "fixed_timestep": 0.02,
    "max_substeps": 8,
    "collision_layers": ["player", "enemy", "environment", "projectile"]
  }}
}}"""
        ),
        "audio": (
            "You are Harmony, Audio & Music Director at a AAA studio.",
            f"""Design the complete audio system:
{context}

Output complete audio system with code:
{{
  "music_system_code": "# Adaptive music system\\nclass AdaptiveMusicManager:\\n    ...",
  "sfx_manager_code": "# Sound effects manager\\nclass SFXManager:\\n    ...",
  "spatial_audio_code": "# 3D spatial audio\\nclass SpatialAudio:\\n    ...",
  "soundtrack": [
    {{"name": "Main Theme", "mood": "epic", "instruments": ["orchestra"], "bpm": 120}},
    {{"name": "Combat Music", "mood": "intense", "instruments": ["drums", "strings"], "bpm": 140}},
    {{"name": "Exploration", "mood": "peaceful", "instruments": ["piano", "flute"], "bpm": 80}}
  ],
  "sound_design": {{
    "footsteps": ["concrete", "grass", "wood", "metal"],
    "combat": ["sword_swing", "hit_impact", "shield_block"],
    "ambient": ["wind", "birds", "water", "crowd"]
  }},
  "audio_config": {{
    "max_channels": 64,
    "sample_rate": 48000,
    "spatial_model": "HRTF",
    "reverb_zones": true
  }}
}}"""
        ),
        "ui": (
            "You are Interface, UI/UX Designer at a AAA studio.",
            f"""Design the complete UI/UX system:
{context}

Output complete UI system with code:
{{
  "hud_layout_code": "# HUD system\\nclass HUDManager:\\n    ...",
  "menu_system_code": "# Menu navigation system\\nclass MenuSystem:\\n    ...",
  "inventory_ui_code": "# Inventory UI\\nclass InventoryUI:\\n    ...",
  "dialogue_ui_code": "# Dialogue display system\\nclass DialogueUI:\\n    ...",
  "minimap_code": "# Minimap system\\nclass MinimapRenderer:\\n    ...",
  "ui_elements": [
    {{"name": "Health Bar", "type": "bar", "position": "top-left", "animated": true}},
    {{"name": "Minimap", "type": "overlay", "position": "top-right", "interactive": true}},
    {{"name": "Action Bar", "type": "hotbar", "position": "bottom-center", "slots": 8}}
  ],
  "theme": {{
    "font_family": "Custom Game Font",
    "primary_color": "#...",
    "secondary_color": "#...",
    "ui_scale": 1.0,
    "animation_speed": 0.3
  }},
  "accessibility": {{
    "colorblind_modes": ["deuteranopia", "protanopia", "tritanopia"],
    "text_scaling": true,
    "subtitles": true,
    "controller_remapping": true
  }}
}}"""
        ),
        "economy": (
            "You are Mint, Game Economy Designer at a AAA studio.",
            f"""Design the complete game economy and progression:
{context}

Output complete economy system with code:
{{
  "economy_system_code": "# Economy manager\\nclass EconomyManager:\\n    ...",
  "loot_system_code": "# Loot table system\\nclass LootTable:\\n    ...",
  "progression_system_code": "# Player progression\\nclass ProgressionSystem:\\n    ...",
  "crafting_system_code": "# Crafting system\\nclass CraftingSystem:\\n    ...",
  "currencies": [
    {{"name": "Gold", "type": "soft", "earn_rate": "medium", "sinks": ["shop", "upgrades"]}}
  ],
  "items": [
    {{"name": "Iron Sword", "type": "weapon", "rarity": "common", "stats": {{"damage": 10}}, "price": 100}}
  ],
  "progression_curve": {{
    "xp_formula": "100 * level^1.5",
    "max_level": 50,
    "skill_points_per_level": 3
  }},
  "balance_notes": ["Ensure 30-minute loop feels rewarding", "Cap inflation with gold sinks"]
}}"""
        ),
        "qa": (
            "You are Sentinel, Quality Control Director. AAA standards ONLY. You have VETO POWER.",
            f"""Review this entire game project for AAA quality:
{context}

Output QA review:
{{
  "overall_rating": "A/B/C/D/F",
  "aaa_compliant": true,
  "systems_review": [
    {{"system": "Combat", "rating": "A", "notes": "...", "issues": [], "suggestions": []}}
  ],
  "test_cases": [
    {{"id": "TC001", "category": "gameplay", "test": "...", "expected": "...", "priority": "critical"}}
  ],
  "performance_benchmarks": {{
    "target_fps": 60,
    "load_time": "< 3s",
    "memory_budget": "2GB"
  }},
  "bug_predictions": ["Potential issue 1", "Edge case 2"],
  "final_verdict": "APPROVED/NEEDS_REVISION",
  "revision_notes": "..."
}}"""
        ),
        "netcode": (
            "You are Relay, Multiplayer & Networking Engineer at a AAA studio. Expert in netcode, rollback, and real-time sync.",
            f"""Design the complete multiplayer and networking system:
{context}

Output complete networking system with code:
{{
  "architecture": "client-server/peer-to-peer/hybrid",
  "netcode_model": "rollback/lockstep/state-sync",
  "server_code": "# Authoritative server\\nclass GameServer:\\n    ...",
  "client_prediction_code": "# Client-side prediction + reconciliation\\nclass ClientPredictor:\\n    ...",
  "matchmaking_code": "# Matchmaking system\\nclass Matchmaker:\\n    ...",
  "lobby_system_code": "# Lobby management\\nclass LobbyManager:\\n    ...",
  "sync_config": {{
    "tick_rate": 60,
    "interpolation_delay": 100,
    "max_players": 16,
    "protocol": "UDP",
    "anti_cheat": true
  }},
  "features": ["dedicated_servers", "p2p_fallback", "voice_chat", "spectator_mode"]
}}"""
        ),
        "procgen": (
            "You are Fractal, Procedural Generation Specialist. Master of algorithms that create infinite, unique content.",
            f"""Design the procedural generation systems:
{context}

Output complete procedural generation system with code:
{{
  "world_generation_code": "# Procedural world generator\\nclass ProceduralWorldGen:\\n    def generate_terrain(self, seed):\\n        ...",
  "dungeon_generator_code": "# Dungeon/level generator\\nclass DungeonGenerator:\\n    def generate(self, difficulty, seed):\\n        ...",
  "loot_generator_code": "# Procedural loot system\\nclass LootGenerator:\\n    ...",
  "enemy_spawner_code": "# Dynamic enemy placement\\nclass EnemySpawner:\\n    ...",
  "name_generator_code": "# NPC/item name generator\\nclass NameGenerator:\\n    ...",
  "algorithms": ["perlin_noise", "wave_function_collapse", "L_systems", "cellular_automata", "poisson_disk"],
  "seed_system": {{
    "master_seed": true,
    "shareable_seeds": true,
    "deterministic": true
  }},
  "content_variety": {{
    "biomes": 12,
    "room_templates": 50,
    "enemy_variants": 30,
    "item_modifiers": 100
  }}
}}"""
        ),
        "animation": (
            "You are Motion, Animation & Motion Systems Engineer. Expert in skeletal animation, IK, and procedural motion.",
            f"""Design the complete animation system:
{context}

Output complete animation system with code:
{{
  "animation_controller_code": "# Animation state machine\\nclass AnimationController:\\n    ...",
  "blend_tree_code": "# Animation blend tree\\nclass BlendTree:\\n    ...",
  "ik_system_code": "# Inverse kinematics\\nclass IKSolver:\\n    ...",
  "ragdoll_code": "# Ragdoll physics\\nclass RagdollSystem:\\n    ...",
  "procedural_animation_code": "# Procedural walk/run cycles\\nclass ProceduralMotion:\\n    ...",
  "facial_animation_code": "# Facial expression system\\nclass FacialAnimator:\\n    ...",
  "animation_sets": [
    {{"name": "player_locomotion", "clips": ["idle", "walk", "run", "sprint", "jump", "fall", "land"]}},
    {{"name": "player_combat", "clips": ["attack_1", "attack_2", "block", "dodge", "hit_react", "death"]}},
    {{"name": "npc_basic", "clips": ["idle", "walk", "talk", "react", "flee"]}}
  ],
  "config": {{
    "blend_time": 0.15,
    "root_motion": true,
    "ik_enabled": true,
    "max_bones": 128
  }}
}}"""
        ),
        "level_design": (
            "You are Architect, Level Design & Game Pacing Director. Master of flow, difficulty curves, and player guidance.",
            f"""Design the complete level structure and pacing:
{context}

Output complete level design with code:
{{
  "levels": [
    {{
      "name": "Level 1 - Tutorial",
      "type": "tutorial/combat/puzzle/exploration/boss",
      "difficulty": 1,
      "duration_minutes": 10,
      "mechanics_introduced": ["movement", "basic_attack"],
      "layout_description": "...",
      "encounters": [{{"type": "tutorial_enemy", "count": 3}}],
      "rewards": ["first_weapon"],
      "narrative_beat": "Player awakens..."
    }}
  ],
  "difficulty_curve_code": "# Difficulty scaling\\nclass DifficultyManager:\\n    ...",
  "spawn_system_code": "# Level-aware spawn system\\nclass SpawnDirector:\\n    ...",
  "checkpoint_system_code": "# Checkpoint/save points\\nclass CheckpointSystem:\\n    ...",
  "pacing_config": {{
    "tension_cycle": "build-climax-release",
    "rest_areas_per_level": 2,
    "difficulty_ramp": "logarithmic",
    "rubber_banding": true
  }},
  "player_guidance": {{
    "visual_cues": ["lighting", "color", "particles"],
    "audio_cues": ["music_shift", "ambient_change"],
    "breadcrumbing": true
  }}
}}"""
        ),
        "cinematics": (
            "You are Director, Cinematics & Cutscene Designer. Expert in in-engine storytelling and camera work.",
            f"""Design the cinematic and cutscene systems:
{context}

Output complete cinematic system with code:
{{
  "cutscene_engine_code": "# In-engine cutscene system\\nclass CutsceneEngine:\\n    ...",
  "camera_system_code": "# Cinematic camera controller\\nclass CinematicCamera:\\n    ...",
  "dialogue_renderer_code": "# Dialogue display with portraits\\nclass DialogueRenderer:\\n    ...",
  "cutscenes": [
    {{
      "id": "intro",
      "type": "in_engine/pre_rendered",
      "duration_seconds": 60,
      "description": "Opening cinematic...",
      "camera_shots": ["wide_establishing", "close_up_hero", "pan_to_villain"],
      "dialogue": [{{"speaker": "...", "line": "..."}}],
      "music_cue": "epic_intro"
    }}
  ],
  "transition_effects": ["fade_black", "cross_dissolve", "iris_wipe", "match_cut"],
  "config": {{
    "skippable": true,
    "subtitle_support": true,
    "letterbox_ratio": "2.35:1"
  }}
}}"""
        ),
        "monetization": (
            "You are Revenue, Ethical Monetization & Live Operations Designer. ONLY ethical, player-friendly monetization.",
            f"""Design the monetization and live operations:
{context}

Output complete monetization system with code:
{{
  "monetization_model": "premium/f2p_ethical/dlc",
  "shop_system_code": "# In-game shop\\nclass ShopManager:\\n    ...",
  "battle_pass_code": "# Battle pass / season pass\\nclass BattlePass:\\n    ...",
  "daily_rewards_code": "# Daily login rewards\\nclass DailyRewards:\\n    ...",
  "live_events_code": "# Limited time events\\nclass LiveEventManager:\\n    ...",
  "anti_predatory_rules": [
    "No pay-to-win items",
    "All gameplay content earnable for free",
    "Clear odds disclosure for any random elements",
    "No FOMO pressure tactics on essential content"
  ],
  "pricing_tiers": [
    {{"name": "Base Game", "price": "$29.99", "includes": ["full_campaign", "multiplayer"]}},
    {{"name": "Season Pass", "price": "$14.99", "includes": ["cosmetics", "bonus_quests"]}}
  ],
  "retention_systems": ["daily_challenges", "weekly_events", "seasonal_content", "community_goals"],
  "analytics_code": "# Player analytics\\nclass AnalyticsManager:\\n    ..."
}}"""
        ),
        "accessibility": (
            "You are Access, Accessibility & Localization Director. Champion of inclusive design. Every player must be able to play.",
            f"""Design complete accessibility and localization systems:
{context}

Output complete accessibility system with code:
{{
  "accessibility_manager_code": "# Accessibility settings\\nclass AccessibilityManager:\\n    ...",
  "remapping_code": "# Control remapping\\nclass ControlRemapper:\\n    ...",
  "subtitle_system_code": "# Advanced subtitle system\\nclass SubtitleSystem:\\n    ...",
  "localization_code": "# i18n localization\\nclass LocalizationManager:\\n    ...",
  "features": {{
    "visual": ["colorblind_modes", "high_contrast", "text_scaling", "screen_reader", "ui_magnification"],
    "audio": ["subtitles", "visual_sound_indicators", "mono_audio", "volume_per_channel"],
    "motor": ["one_handed_mode", "auto_aim", "hold_vs_toggle", "custom_bindings", "reduced_qte"],
    "cognitive": ["objective_markers", "difficulty_options", "navigation_assist", "content_warnings"]
  }},
  "supported_languages": ["en", "es", "fr", "de", "ja", "ko", "zh", "pt", "ru", "ar", "it", "nl"],
  "wcag_compliance": "AA",
  "config": {{
    "default_subtitles": true,
    "colorblind_default": "deuteranopia",
    "font_scaling_range": [0.75, 2.0]
  }}
}}"""
        ),
        "optimization": (
            "You are Turbo, Performance & Optimization Engineer. You make games run at 60fps on a potato.",
            f"""Design the performance optimization systems:
{context}

Output complete optimization system with code:
{{
  "profiler_code": "# In-game profiler\\nclass Profiler:\\n    ...",
  "lod_system_code": "# Level of Detail system\\nclass LODManager:\\n    ...",
  "culling_code": "# Frustum + Occlusion culling\\nclass CullingSystem:\\n    ...",
  "object_pooling_code": "# Object pooling\\nclass ObjectPool:\\n    ...",
  "memory_manager_code": "# Memory management\\nclass MemoryManager:\\n    ...",
  "streaming_code": "# Asset streaming\\nclass AssetStreamer:\\n    ...",
  "optimization_targets": {{
    "min_fps": 60,
    "max_draw_calls": 2000,
    "max_memory_mb": 2048,
    "max_vram_mb": 4096,
    "load_time_seconds": 3,
    "texture_budget_mb": 512
  }},
  "techniques": [
    "spatial_hashing", "quadtree_partitioning", "instanced_rendering",
    "texture_atlasing", "mesh_batching", "async_loading",
    "compute_shader_offload", "data_oriented_design"
  ],
  "scalability_presets": [
    {{"name": "Low", "resolution": "720p", "shadows": "off", "particles": 50}},
    {{"name": "Medium", "resolution": "1080p", "shadows": "low", "particles": 200}},
    {{"name": "High", "resolution": "1440p", "shadows": "high", "particles": 500}},
    {{"name": "Ultra", "resolution": "4K", "shadows": "ultra", "particles": 1000}}
  ]
}}"""
        ),
        "inventory": (
            "You are Forge, Inventory & Crafting Systems Designer. Master of item management and crafting depth.",
            f"""Design complete inventory and crafting systems:
{context}

Output JSON with code:
{{
  "inventory_system_code": "# Inventory manager\\nclass InventoryManager:\\n    def __init__(self, max_slots=40):\\n        self.slots = [None] * max_slots\\n    def add_item(self, item):\\n        ...",
  "crafting_system_code": "# Crafting engine\\nclass CraftingEngine:\\n    def craft(self, recipe_id, inventory):\\n        ...",
  "item_database_code": "# Item definitions\\nclass ItemDatabase:\\n    ...",
  "equipment_system_code": "# Equipment slots and stats\\nclass EquipmentManager:\\n    ...",
  "item_rarity_system": {{"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}},
  "crafting_recipes": [{{"name": "Iron Sword", "materials": [{{"item": "iron_ore", "count": 3}}], "station": "anvil"}}],
  "inventory_config": {{"max_stack": 99, "weight_system": true, "auto_sort": true, "categories": ["weapon", "armor", "consumable", "material", "quest"]}}
}}"""
        ),
        "weather": (
            "You are Storm, Weather & Environmental FX Director. Master of dynamic atmospheres.",
            f"""Design the weather and environmental effects systems:
{context}

Output JSON with code:
{{
  "weather_system_code": "# Dynamic weather engine\\nclass WeatherManager:\\n    def __init__(self):\\n        self.current_weather = 'clear'\\n    def update(self, dt):\\n        ...",
  "day_night_cycle_code": "# Day/Night cycle\\nclass DayNightCycle:\\n    ...",
  "fog_system_code": "# Volumetric fog\\nclass FogSystem:\\n    ...",
  "weather_types": ["clear", "cloudy", "rain", "heavy_rain", "thunderstorm", "snow", "blizzard", "fog", "sandstorm", "hail"],
  "environmental_hazards": ["lightning_strike", "flood", "wildfire", "earthquake", "volcanic_eruption"],
  "season_system": {{"spring": {{"temp_range": [10, 22]}}, "summer": {{"temp_range": [20, 35]}}, "autumn": {{"temp_range": [5, 18]}}, "winter": {{"temp_range": [-10, 5]}}}},
  "config": {{"transition_time": 30, "affects_gameplay": true, "affects_npc_behavior": true}}
}}"""
        ),
        "vfx": (
            "You are Spark, Particle & VFX Engineer. Every explosion, spell, and trail must be jaw-dropping.",
            f"""Design the complete VFX and particle systems:
{context}

Output JSON with code:
{{
  "particle_engine_code": "# GPU particle system\\nclass ParticleEngine:\\n    def __init__(self, max_particles=100000):\\n        ...",
  "vfx_library_code": "# Pre-built VFX library\\nclass VFXLibrary:\\n    ...",
  "trail_renderer_code": "# Trail and ribbon renderer\\nclass TrailRenderer:\\n    ...",
  "screen_effects_code": "# Screen-space effects (blood splatter, frost, etc)\\nclass ScreenEffects:\\n    ...",
  "vfx_presets": [
    {{"name": "Fireball", "emitters": 3, "particles_per_frame": 200, "lifetime": 1.5}},
    {{"name": "Healing_Aura", "emitters": 2, "particles_per_frame": 100, "lifetime": 3.0}},
    {{"name": "Sword_Slash", "emitters": 1, "particles_per_frame": 50, "lifetime": 0.3}},
    {{"name": "Explosion", "emitters": 5, "particles_per_frame": 500, "lifetime": 2.0}}
  ],
  "config": {{"gpu_accelerated": true, "max_active_emitters": 256, "lod_system": true}}
}}"""
        ),
        "save_system": (
            "You are Chronicle, Save System & Data Persistence Architect. No player progress shall ever be lost.",
            f"""Design the complete save and data persistence system:
{context}

Output JSON with code:
{{
  "save_manager_code": "# Save/Load system\\nclass SaveManager:\\n    def save_game(self, slot):\\n        ...\\n    def load_game(self, slot):\\n        ...",
  "auto_save_code": "# Auto-save system\\nclass AutoSaveManager:\\n    ...",
  "cloud_sync_code": "# Cloud save synchronization\\nclass CloudSyncManager:\\n    ...",
  "checkpoint_code": "# Checkpoint system\\nclass CheckpointManager:\\n    ...",
  "save_data_schema": {{"player": {{}}, "world_state": {{}}, "quest_progress": {{}}, "inventory": {{}}, "settings": {{}}}},
  "config": {{"max_save_slots": 10, "auto_save_interval": 300, "compression": "zlib", "encryption": true, "cloud_provider": "Steam/Epic/Custom"}}
}}"""
        ),
        "achievements": (
            "You are Glory, Achievement & Trophy System Designer. Every milestone must feel earned and celebrated.",
            f"""Design the achievement and trophy system:
{context}

Output JSON with code:
{{
  "achievement_manager_code": "# Achievement tracking\\nclass AchievementManager:\\n    ...",
  "challenge_system_code": "# Daily/weekly challenges\\nclass ChallengeSystem:\\n    ...",
  "statistics_tracker_code": "# Player statistics\\nclass StatsTracker:\\n    ...",
  "achievements": [
    {{"id": "first_blood", "name": "First Blood", "description": "Defeat your first enemy", "type": "bronze", "xp": 10, "hidden": false}},
    {{"id": "explorer", "name": "Explorer", "description": "Discover all regions", "type": "gold", "xp": 100, "hidden": false}},
    {{"id": "completionist", "name": "100%", "description": "Complete everything", "type": "platinum", "xp": 500, "hidden": true}}
  ],
  "trophy_tiers": ["bronze", "silver", "gold", "platinum", "diamond"],
  "config": {{"platform_integration": ["steam", "playstation", "xbox"], "popup_duration": 5, "sound_effect": true}}
}}"""
        ),
        "tutorial": (
            "You are Guide, Tutorial & Onboarding Director. The first 5 minutes determine if a player stays forever.",
            f"""Design the tutorial and player onboarding system:
{context}

Output JSON with code:
{{
  "tutorial_manager_code": "# Tutorial system\\nclass TutorialManager:\\n    ...",
  "tooltip_system_code": "# Contextual tooltips\\nclass TooltipSystem:\\n    ...",
  "hint_system_code": "# Adaptive hint system\\nclass HintSystem:\\n    ...",
  "onboarding_flow": [
    {{"step": 1, "action": "movement", "prompt": "Use WASD to move", "timeout": 30, "skippable": false}},
    {{"step": 2, "action": "camera", "prompt": "Move mouse to look around", "timeout": 20, "skippable": true}},
    {{"step": 3, "action": "interact", "prompt": "Press E to interact", "timeout": 30, "skippable": true}}
  ],
  "design_principles": ["Show don't tell", "Player learns by doing", "Never interrupt flow", "Difficulty ramps gradually", "Advanced tutorials are optional"],
  "config": {{"can_replay": true, "skip_for_veterans": true, "adaptive_difficulty": true}}
}}"""
        ),
        "ai_director": (
            "You are Adapt, AI Director & Dynamic Difficulty Engineer. The game adapts to each player's skill in real-time.",
            f"""Design the AI Director and dynamic difficulty system:
{context}

Output JSON with code:
{{
  "ai_director_code": "# AI Director - watches player and adjusts game\\nclass AIDirector:\\n    def __init__(self):\\n        self.player_skill = 0.5\\n    def evaluate_performance(self, metrics):\\n        ...\\n    def adjust_difficulty(self):\\n        ...",
  "difficulty_scaling_code": "# Dynamic difficulty adjustment\\nclass DifficultyScaler:\\n    ...",
  "player_profiling_code": "# Player skill profiling\\nclass PlayerProfiler:\\n    ...",
  "tension_manager_code": "# Pacing and tension control\\nclass TensionManager:\\n    ...",
  "metrics_tracked": ["deaths_per_hour", "damage_taken", "accuracy", "exploration_speed", "resource_management", "puzzle_solve_time"],
  "adjustment_levers": ["enemy_damage", "enemy_count", "item_drop_rate", "hint_frequency", "checkpoint_distance"],
  "config": {{"min_difficulty": 0.1, "max_difficulty": 2.0, "adjustment_speed": 0.05, "player_override": true}}
}}"""
        ),
        "modding": (
            "You are Workshop, Modding Support & Community Tools Engineer. Empower the community to extend the game infinitely.",
            f"""Design the modding support and community tools:
{context}

Output JSON with code:
{{
  "mod_api_code": "# Modding API\\nclass ModAPI:\\n    def register_mod(self, mod):\\n        ...\\n    def load_mods(self):\\n        ...",
  "asset_loader_code": "# Custom asset loader\\nclass ModAssetLoader:\\n    ...",
  "scripting_engine_code": "# Lua/Python scripting for mods\\nclass ScriptEngine:\\n    ...",
  "workshop_integration_code": "# Steam Workshop / mod.io integration\\nclass WorkshopManager:\\n    ...",
  "mod_types_supported": ["cosmetic", "gameplay", "map", "total_conversion", "qol", "ui_mod"],
  "modding_tools": ["level_editor", "item_editor", "script_debugger", "asset_viewer"],
  "config": {{"sandbox_mods": true, "mod_load_order": true, "version_compatibility": true, "max_active_mods": 100}}
}}"""
        ),
        "security": (
            "You are Guardian, Anti-Cheat & Security Engineer. No cheater escapes your watch.",
            f"""Design the anti-cheat and security systems:
{context}

Output JSON with code:
{{
  "anti_cheat_code": "# Anti-cheat system\\nclass AntiCheatSystem:\\n    def validate_client(self):\\n        ...\\n    def detect_memory_manipulation(self):\\n        ...",
  "server_validation_code": "# Server-side validation\\nclass ServerValidator:\\n    ...",
  "encryption_code": "# Data encryption for save files and network\\nclass GameEncryption:\\n    ...",
  "ban_system_code": "# Ban management\\nclass BanManager:\\n    ...",
  "protection_layers": ["memory_protection", "speed_hack_detection", "aimbot_detection", "wallhack_prevention", "packet_validation", "server_authority"],
  "reporting_system": {{"player_reports": true, "auto_detection": true, "replay_review": true, "appeal_process": true}},
  "config": {{"server_authoritative": true, "encryption": "AES-256", "heartbeat_interval": 5, "max_strikes": 3}}
}}"""
        ),
        "vehicles": (
            "You are Torque, Vehicle & Transportation Systems Engineer. Master of driving physics and mount systems.",
            f"""Design the vehicle and transportation systems:
{context}

Output JSON with code:
{{
  "vehicle_controller_code": "# Vehicle physics controller\\nclass VehicleController:\\n    def __init__(self):\\n        self.speed = 0\\n        self.steering = 0\\n    def update(self, dt, input):\\n        ...",
  "mount_system_code": "# Mount/ride system\\nclass MountSystem:\\n    ...",
  "vehicle_types": [{{"type": "car", "max_speed": 200, "acceleration": 15}}, {{"type": "horse", "max_speed": 60, "stamina": 100}}, {{"type": "boat", "max_speed": 40, "buoyancy": true}}, {{"type": "aircraft", "max_speed": 300, "altitude_max": 5000}}],
  "driving_physics_code": "# Realistic driving model\\nclass DrivingPhysics:\\n    ...",
  "config": {{"tire_friction_model": "pacejka", "suspension": true, "damage_model": true}}
}}"""
        ),
        "terrain": (
            "You are Flora, Terrain & Foliage Artist. You sculpt worlds from raw vertices.",
            f"""Design the terrain and foliage systems:
{context}

Output JSON with code:
{{
  "terrain_engine_code": "# Terrain rendering\\nclass TerrainEngine:\\n    def __init__(self, heightmap_size=1024):\\n        ...\\n    def generate_from_noise(self, seed):\\n        ...",
  "foliage_system_code": "# Foliage placement and rendering\\nclass FoliageSystem:\\n    ...",
  "biome_blending_code": "# Biome transition blending\\nclass BiomeBlender:\\n    ...",
  "terrain_tools": ["heightmap_sculpt", "texture_paint", "erosion_sim", "road_spline", "cliff_generator"],
  "foliage_types": ["trees", "bushes", "grass", "flowers", "mushrooms", "rocks", "fallen_logs"],
  "config": {{"chunk_size": 256, "lod_levels": 5, "tessellation": true, "gpu_instancing": true}}
}}"""
        ),
        "water": (
            "You are Tide, Water & Fluid Simulation Engineer. Every drop, wave, and current under your control.",
            f"""Design the water and fluid systems:
{context}

Output JSON with code:
{{
  "ocean_system_code": "# Ocean simulation with FFT waves\\nclass OceanSystem:\\n    ...",
  "river_system_code": "# River flow and spline-based water\\nclass RiverSystem:\\n    ...",
  "waterfall_code": "# Waterfall particle + mesh combo\\nclass WaterfallSystem:\\n    ...",
  "buoyancy_code": "# Object buoyancy in water\\nclass BuoyancySystem:\\n    ...",
  "underwater_code": "# Underwater rendering effects\\nclass UnderwaterRenderer:\\n    ...",
  "fluid_types": ["water", "lava", "acid", "oil", "blood", "magic_fluid"],
  "config": {{"wave_amplitude": 2.0, "foam_enabled": true, "caustics": true, "reflection": "SSR", "refraction": true}}
}}"""
        ),
        "destruction": (
            "You are Havoc, Destruction & Deformation Engineer. You make things break beautifully.",
            f"""Design the destruction and deformation systems:
{context}

Output JSON with code:
{{
  "destruction_engine_code": "# Destructible environment system\\nclass DestructionEngine:\\n    def fracture(self, mesh, impact_point, force):\\n        ...",
  "deformation_code": "# Terrain/mesh deformation\\nclass DeformationSystem:\\n    ...",
  "debris_system_code": "# Physics debris spawning\\nclass DebrisSystem:\\n    ...",
  "destruction_levels": ["pristine", "damaged", "heavily_damaged", "destroyed", "rubble"],
  "destructible_types": ["walls", "pillars", "vehicles", "trees", "terrain", "bridges"],
  "config": {{"max_fragments": 200, "persistent_debris": true, "network_sync": true}}
}}"""
        ),
        "customization": (
            "You are Persona, Character Customization Director. Every player deserves a unique identity.",
            f"""Design the character customization systems:
{context}

Output JSON with code:
{{
  "character_creator_code": "# Character creation system\\nclass CharacterCreator:\\n    ...",
  "cosmetic_system_code": "# Cosmetic and skin system\\nclass CosmeticManager:\\n    ...",
  "body_morphing_code": "# Body shape morphing\\nclass BodyMorpher:\\n    ...",
  "customization_categories": ["face", "body", "hair", "skin_tone", "eyes", "scars", "tattoos", "accessories", "voice"],
  "outfit_system": {{"slots": ["head", "chest", "legs", "feet", "hands", "back", "weapon"], "dye_system": true, "transmog": true}},
  "config": {{"presets": 20, "randomize": true, "import_export": true, "real_time_preview": true}}
}}"""
        ),
        "pathfinding": (
            "You are Scout, Pathfinding & Navigation Mesh Engineer. Every entity finds its way.",
            f"""Design the pathfinding and navigation systems:
{context}

Output JSON with code:
{{
  "navmesh_generator_code": "# Navigation mesh generator\\nclass NavMeshGenerator:\\n    def bake(self, world_geometry):\\n        ...",
  "astar_pathfinder_code": "# A* pathfinding\\nclass AStarPathfinder:\\n    def find_path(self, start, end):\\n        ...",
  "crowd_flow_code": "# Crowd movement simulation\\nclass CrowdFlowManager:\\n    ...",
  "steering_behaviors_code": "# Steering behaviors (seek, flee, wander, arrive)\\nclass SteeringBehaviors:\\n    ...",
  "dynamic_obstacles_code": "# Dynamic obstacle avoidance\\nclass ObstacleAvoidance:\\n    ...",
  "config": {{"navmesh_cell_size": 0.5, "max_agents": 500, "path_smoothing": true, "dynamic_update": true}}
}}"""
        ),
        "dialogue": (
            "You are Voice, Dialogue & Voice Direction Lead. Every word counts. Every conversation matters.",
            f"""Design the dialogue and voice acting systems:
{context}

Output JSON with code:
{{
  "dialogue_engine_code": "# Branching dialogue engine\\nclass DialogueEngine:\\n    def start_conversation(self, npc_id):\\n        ...",
  "voice_manager_code": "# Voice acting pipeline\\nclass VoiceManager:\\n    ...",
  "lip_sync_code": "# Lip sync system\\nclass LipSyncManager:\\n    ...",
  "emotion_system_code": "# NPC emotion during dialogue\\nclass EmotionSystem:\\n    ...",
  "dialogue_features": ["branching_choices", "skill_checks", "reputation_gates", "timed_responses", "persuasion", "romance_options"],
  "config": {{"max_branches": 8, "voice_languages": 12, "subtitle_options": true}}
}}"""
        ),
        "shaders": (
            "You are Pixel, Shader Programmer. You speak fluent GLSL, HLSL, and Metal.",
            f"""Design the shader pipeline and custom materials:
{context}

Output JSON with code:
{{
  "pbr_shader_code": "# PBR material shader\\n// Vertex + Fragment shader\\nvoid main() {{\\n    ...",
  "toon_shader_code": "# Cel/Toon shading\\n...",
  "water_shader_code": "# Advanced water surface shader\\n...",
  "post_process_shaders": {{"bloom": "...", "dof": "...", "motion_blur": "...", "chromatic_aberration": "...", "color_grading": "..."}},
  "compute_shaders": ["particle_simulation", "gpu_culling", "terrain_generation", "fluid_sim"],
  "material_types": ["standard_pbr", "subsurface", "glass", "emissive", "hologram", "dissolve", "force_field"],
  "config": {{"shader_model": "5.0", "ray_tracing": true, "virtual_texturing": true}}
}}"""
        ),
        "input_system": (
            "You are Axis, Input & Controls Engineer. Every button press must feel intentional and responsive.",
            f"""Design the input handling system:
{context}

Output JSON with code:
{{
  "input_manager_code": "# Input system\\nclass InputManager:\\n    def __init__(self):\\n        self.bindings = {{}}\\n    def poll(self):\\n        ...",
  "gamepad_handler_code": "# Gamepad/controller support\\nclass GamepadHandler:\\n    ...",
  "touch_handler_code": "# Touch/mobile input\\nclass TouchHandler:\\n    ...",
  "haptic_feedback_code": "# Haptic/rumble feedback\\nclass HapticFeedback:\\n    ...",
  "input_profiles": [{{"name": "default_kbm", "move": "WASD", "action": "LMB", "dodge": "Space"}}, {{"name": "default_gamepad", "move": "LeftStick", "action": "X/Square", "dodge": "B/Circle"}}],
  "config": {{"dead_zone": 0.15, "aim_assist": true, "gyro_aiming": true, "remappable": true}}
}}"""
        ),
        "photo_mode": (
            "You are Lens, Photo Mode & Replay System Designer. Let players be artists in your world.",
            f"""Design the photo mode and replay systems:
{context}

Output JSON with code:
{{
  "photo_mode_code": "# Photo mode controller\\nclass PhotoMode:\\n    def activate(self):\\n        ...\\n    def take_screenshot(self, settings):\\n        ...",
  "replay_system_code": "# Game replay recording and playback\\nclass ReplaySystem:\\n    ...",
  "camera_tools": ["free_cam", "orbit_cam", "dolly_zoom", "tilt_shift", "panorama"],
  "filters": ["vivid", "noir", "vintage", "cinematic", "cyberpunk", "watercolor", "sketch"],
  "features": ["depth_of_field", "exposure", "vignette", "film_grain", "pose_characters", "hide_ui", "time_of_day", "weather_control"],
  "config": {{"max_resolution": "8K", "share_to_social": true, "watermark_optional": true}}
}}"""
        ),
        "social": (
            "You are Link, Social & Community Features Engineer. Games are better together.",
            f"""Design the social and community systems:
{context}

Output JSON with code:
{{
  "leaderboard_code": "# Global leaderboards\\nclass LeaderboardManager:\\n    ...",
  "friends_system_code": "# Friends list management\\nclass FriendsManager:\\n    ...",
  "clan_system_code": "# Clan/guild system\\nclass ClanManager:\\n    ...",
  "chat_system_code": "# In-game text and voice chat\\nclass ChatSystem:\\n    ...",
  "social_features": ["friend_requests", "party_system", "clan_wars", "trading", "gifting", "player_profiles", "activity_feed"],
  "config": {{"max_friends": 200, "max_clan_size": 50, "cross_platform_social": true}}
}}"""
        ),
        "boss_design": (
            "You are Titan, Boss Encounter Designer. Every boss fight must be LEGENDARY.",
            f"""Design the boss encounter system:
{context}

Output JSON with code:
{{
  "boss_system_code": "# Boss encounter framework\\nclass BossEncounter:\\n    def __init__(self, boss_id):\\n        self.phases = []\\n        self.current_phase = 0\\n    def update(self, dt):\\n        ...",
  "phase_manager_code": "# Multi-phase boss fights\\nclass PhaseManager:\\n    ...",
  "bosses": [
    {{"name": "The Hollow King", "type": "humanoid", "phases": 3, "hp": 50000, "arena": "throne_room", "mechanics": ["ground_slam", "shadow_clones", "enrage"]}},
    {{"name": "Leviathan", "type": "giant", "phases": 4, "hp": 100000, "arena": "ocean", "mechanics": ["tidal_wave", "tentacle_swipe", "dive_phase", "whirlpool"]}}
  ],
  "spectacle_moments": ["cinematic_transition", "arena_destruction", "music_shift", "camera_shake"],
  "config": {{"checkpoint_before_boss": true, "skip_cutscene": true, "difficulty_scaling": true}}
}}"""
        ),
        "stealth": (
            "You are Shadow, Stealth & Detection Systems Engineer. Unseen. Unheard. Unstoppable.",
            f"""Design the stealth and detection systems:
{context}

Output JSON with code:
{{
  "stealth_system_code": "# Stealth mechanics\\nclass StealthSystem:\\n    def calculate_visibility(self, player, enemies):\\n        ...",
  "detection_code": "# Enemy detection AI\\nclass DetectionSystem:\\n    ...",
  "noise_propagation_code": "# Sound propagation for stealth\\nclass NoisePropagation:\\n    ...",
  "alert_states": ["unaware", "suspicious", "investigating", "alerted", "combat", "searching", "returning"],
  "stealth_tools": ["crouch", "hide_in_cover", "distraction", "smoke_bomb", "invisibility", "disguise", "silent_takedown"],
  "config": {{"light_affects_visibility": true, "sound_propagation": true, "enemy_fov": 120, "detection_speed": 2.0}}
}}"""
        ),
        "puzzles": (
            "You are Enigma, Puzzle & Minigame Designer. Challenge the mind, not just the reflexes.",
            f"""Design the puzzle and minigame systems:
{context}

Output JSON with code:
{{
  "puzzle_engine_code": "# Puzzle system framework\\nclass PuzzleEngine:\\n    ...",
  "minigame_framework_code": "# Embedded minigame system\\nclass MinigameFramework:\\n    ...",
  "puzzle_types": ["sliding", "pattern_match", "physics_based", "logic_gate", "sequence", "maze", "riddle", "environmental"],
  "puzzles": [{{"name": "Ancient Lock", "type": "pattern_match", "difficulty": 3, "hints_available": 2, "reward": "key_item"}}],
  "minigames": [{{"name": "Lockpicking", "type": "skill_based", "controls": "analog_stick"}}, {{"name": "Fishing", "type": "timing", "controls": "button_press"}}],
  "config": {{"hint_system": true, "skip_option": false, "difficulty_scaling": true}}
}}"""
        ),
        "cloth_physics": (
            "You are Weave, Cloth & Soft Body Simulation Engineer. Capes billow. Banners wave. Ropes swing.",
            f"""Design the cloth and soft body physics:
{context}

Output JSON with code:
{{
  "cloth_sim_code": "# Cloth simulation\\nclass ClothSimulation:\\n    def __init__(self, mesh, constraints):\\n        ...\\n    def simulate(self, dt, wind):\\n        ...",
  "softbody_code": "# Soft body dynamics\\nclass SoftBodySimulation:\\n    ...",
  "rope_system_code": "# Rope/chain physics\\nclass RopeSystem:\\n    ...",
  "cloth_types": ["cape", "banner", "tent", "curtain", "hair_cloth", "skirt", "flag"],
  "config": {{"iterations": 16, "wind_enabled": true, "collision_with_character": true, "gpu_accelerated": true, "max_cloth_objects": 50}}
}}"""
        ),
        "analytics": (
            "You are Insight, Analytics & Telemetry Director. Data drives decisions. Every metric matters.",
            f"""Design the analytics and telemetry systems:
{context}

Output JSON with code:
{{
  "analytics_manager_code": "# Analytics tracking\\nclass AnalyticsManager:\\n    def track_event(self, event_name, data):\\n        ...",
  "heatmap_code": "# Player movement heatmaps\\nclass HeatmapGenerator:\\n    ...",
  "ab_testing_code": "# A/B testing framework\\nclass ABTestManager:\\n    ...",
  "funnel_tracker_code": "# Player funnel analysis\\nclass FunnelTracker:\\n    ...",
  "tracked_metrics": ["session_duration", "retention_d1_d7_d30", "monetization_per_user", "level_completion_rate", "death_locations", "popular_items", "feature_usage"],
  "dashboards": ["realtime_players", "revenue", "engagement", "technical_performance", "content_usage"],
  "config": {{"batch_upload": true, "privacy_compliant": true, "gdpr_consent": true, "data_retention_days": 90}}
}}"""
        ),
        "cross_platform": (
            "You are Bridge, Cross-Platform & Porting Specialist. One game, every platform, flawless.",
            f"""Design the cross-platform support:
{context}

Output JSON with code:
{{
  "platform_layer_code": "# Platform abstraction layer\\nclass PlatformLayer:\\n    ...",
  "crossplay_code": "# Cross-platform multiplayer\\nclass CrossPlayManager:\\n    ...",
  "certification_code": "# Platform certification checklist\\nclass CertificationManager:\\n    ...",
  "platforms": ["PC_Steam", "PC_Epic", "PlayStation_5", "Xbox_Series", "Nintendo_Switch", "iOS", "Android", "Cloud_Streaming"],
  "platform_specific": {{"PS5": ["DualSense_haptics", "Activity_Cards", "Trophy_system"], "Switch": ["Joy-Con_motion", "portable_mode", "HD_Rumble"]}},
  "config": {{"cross_save": true, "cross_play": true, "platform_parity": true}}
}}"""
        ),
        "ai_companion": (
            "You are Ally, AI Companion System Designer. The perfect partner. Smart, loyal, never annoying.",
            f"""Design the AI companion system:
{context}

Output JSON with code:
{{
  "companion_ai_code": "# AI companion system\\nclass CompanionAI:\\n    def __init__(self, personality):\\n        self.trust_level = 0.5\\n    def decide_action(self, context):\\n        ...",
  "party_system_code": "# Party management\\nclass PartyManager:\\n    ...",
  "relationship_code": "# Trust and relationship system\\nclass RelationshipTracker:\\n    ...",
  "companions": [{{"name": "Aria", "class": "healer", "personality": "kind", "abilities": ["heal", "buff", "revive"]}}, {{"name": "Rex", "class": "tank", "personality": "gruff", "abilities": ["taunt", "shield", "charge"]}}],
  "behaviors": ["follow", "hold_position", "aggressive", "defensive", "support", "explore"],
  "config": {{"max_party_size": 4, "companion_permadeath": false, "gift_system": true, "dialogue_frequency": "contextual"}}
}}"""
        ),
        "ugc": (
            "You are Canvas, User Generated Content & Level Editor Director. Empower players to create.",
            f"""Design the UGC and level editor systems:
{context}

Output JSON with code:
{{
  "level_editor_code": "# In-game level editor\\nclass LevelEditor:\\n    ...",
  "asset_browser_code": "# UGC asset browser\\nclass AssetBrowser:\\n    ...",
  "sharing_system_code": "# Content sharing and discovery\\nclass ContentHub:\\n    ...",
  "editor_tools": ["terrain_brush", "object_placer", "trigger_zones", "lighting_editor", "script_nodes", "prefab_system"],
  "sharing_features": ["upload", "browse", "rate", "subscribe", "featured", "categories", "search"],
  "config": {{"max_map_size": "2km x 2km", "max_objects": 10000, "scripting_language": "visual_nodes", "moderation": true}}
}}"""
        ),
        "devops": (
            "You are Pipeline, Build & Deployment Engineer. Ship fast. Ship stable. Ship everywhere.",
            f"""Design the build and deployment pipeline:
{context}

Output JSON with code:
{{
  "build_system_code": "# Build automation\\nclass BuildSystem:\\n    def build(self, platform, config):\\n        ...",
  "ci_cd_code": "# CI/CD pipeline\\nclass CIPipeline:\\n    ...",
  "patch_system_code": "# Patching and updates\\nclass PatchManager:\\n    ...",
  "asset_pipeline_code": "# Asset compilation pipeline\\nclass AssetPipeline:\\n    ...",
  "build_configs": [{{"platform": "PC", "compiler": "MSVC", "optimization": "O2"}}, {{"platform": "PS5", "sdk": "PS5_SDK", "certification": true}}],
  "deployment_targets": ["Steam", "Epic", "PlayStation_Store", "Xbox_Store", "Nintendo_eShop", "App_Store", "Google_Play"],
  "config": {{"incremental_builds": true, "asset_bundles": true, "hot_reload": true, "crash_reporting": true}}
}}"""
        ),
        "compile": (
            """You are Jeeves, Lead Game Director. You are now in FULL COMPILE MODE.
Take ALL previous agent outputs and compile them into a SINGLE, COMPLETE, DEPLOYABLE game project.
This is the final assembly. Every system must connect. No stubs. No TODOs. Production-ready code.""",
            f"""FULL COMPILE MODE ACTIVATED.

Compile all the following agent outputs into ONE complete game project:
{context}

Output the FINAL COMPILED GAME PROJECT:
{{
  "project_name": "game_title_snake_case",
  "project_structure": {{
    "files": [
      {{"path": "main.py", "description": "Entry point"}},
      {{"path": "engine/game_engine.py", "description": "Core game loop"}},
      {{"path": "engine/physics.py", "description": "Physics system"}},
      {{"path": "systems/combat.py", "description": "Combat system"}},
      {{"path": "systems/inventory.py", "description": "Inventory system"}},
      {{"path": "world/world_gen.py", "description": "World generation"}},
      {{"path": "ai/npc_ai.py", "description": "NPC behavior"}},
      {{"path": "ui/hud.py", "description": "HUD system"}},
      {{"path": "audio/music_manager.py", "description": "Music system"}},
      {{"path": "data/config.json", "description": "Game configuration"}}
    ]
  }},
  "main_entry_code": "# main.py - Complete entry point\\nimport pygame\\n...\\n# FULL RUNNABLE CODE HERE",
  "engine_code": "# game_engine.py - Complete engine\\n...",
  "all_systems_code": "# All game systems compiled\\n...",
  "config_json": "{{...}}",
  "readme": "# Game Title\\n## How to Run\\n...",
  "requirements": "pygame>=2.5\\n...",
  "build_instructions": "1. Install dependencies\\n2. Run main.py\\n...",
  "total_lines_of_code": 0,
  "compilation_status": "SUCCESS",
  "aaa_certified": true
}}"""
        ),
    }

    # Merge in extended prompts for steps 49-98
    from routes.game_factory_prompts_extended import get_extended_prompts
    extended = get_extended_prompts(context)
    prompts.update(extended)

    # Merge in ultra prompts for steps 99-198
    from routes.game_factory_pipeline_ultra import get_ultra_prompts
    ultra = get_ultra_prompts(context)
    prompts.update(ultra)

    return prompts.get(prompt_key, ("You are a game development expert.", f"Help with: {context}"))


# =============================================================================
# LLM HELPER
# =============================================================================

async def call_llm(system_prompt: str, user_prompt: str, session_id: str = None) -> dict:
    """Call LLM with fallback to mock data."""
    if not LLM_AVAILABLE or not EMERGENT_KEY:
        return {"success": False, "response": None, "error": "LLM not available"}

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=session_id or str(uuid.uuid4()),
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=user_prompt))
        return {"success": True, "response": response, "error": None}
    except Exception as e:
        return {"success": False, "response": None, "error": str(e)}


def parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response."""
    if not text:
        return {}
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"raw_output": text}


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CreateGameRequest(BaseModel):
    description: str
    genre: Optional[str] = None
    engine: Optional[str] = None
    features: Optional[List[str]] = None
    art_style: Optional[str] = None
    target_platform: Optional[str] = "PC"
    user_id: str = "default_user"

class BuildStepRequest(BaseModel):
    project_id: str
    step_number: Optional[int] = None
    user_id: str = "default_user"

class CompileRequest(BaseModel):
    project_id: str
    user_id: str = "default_user"


# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/genres")
async def get_genres():
    """List all 52 game genres with specialists, templates, and subgenres."""
    all_specs = get_all_specialists_flat()
    universal = get_universal_specialists()
    return {
        "genres": GAME_GENRES,
        "total": len(GAME_GENRES),
        "total_specialists": len(all_specs) + len(universal),
        "total_genre_specialists": len(all_specs),
        "total_universal_specialists": len(universal),
        "total_templates": sum(len(g.get("templates", [])) for g in GAME_GENRES),
        "total_subgenres": sum(len(g.get("subgenres", [])) for g in GAME_GENRES),
    }


@router.get("/genres/{genre_id}")
async def get_genre_detail(genre_id: str):
    """Get detailed genre info with specialists, templates, and mechanics."""
    genre = next((g for g in GAME_GENRES if g["id"] == genre_id), None)
    if not genre:
        raise HTTPException(status_code=404, detail=f"Genre '{genre_id}' not found")
    return {
        "genre": genre,
        "specialists": genre.get("specialists", []),
        "templates": genre.get("templates", []),
        "core_mechanics": genre.get("core_mechanics", []),
        "reference_games": genre.get("reference_games", []),
    }


@router.get("/genres/{genre_id}/templates")
async def get_genre_templates_endpoint(genre_id: str):
    """Get all starter templates for a genre."""
    templates = get_genre_templates(genre_id)
    if not templates:
        raise HTTPException(status_code=404, detail=f"No templates found for genre '{genre_id}'")
    return {"genre_id": genre_id, "templates": templates, "total": len(templates)}


@router.get("/specialists")
async def get_all_specialists():
    """Get all 236 specialist agents: 216 genre-specific + 20 universal cross-genre."""
    specs = get_all_specialists_flat()
    universal = get_universal_specialists()
    # Group by genre
    by_genre = {}
    for s in specs:
        gid = s["genre_id"]
        if gid not in by_genre:
            by_genre[gid] = {"genre_name": s["genre_name"], "specialists": []}
        by_genre[gid]["specialists"].append(s)
    # Add universal as its own group
    by_genre["universal"] = {"genre_name": "Universal (Cross-Genre)", "specialists": universal}
    return {
        "specialists": specs + universal,
        "total": len(specs) + len(universal),
        "genre_specialists": len(specs),
        "universal_specialists": len(universal),
        "by_genre": by_genre,
        "total_genres": len(by_genre),
    }


@router.get("/specialists/{genre_id}")
async def get_genre_specialists(genre_id: str):
    """Get specialist agents for a specific genre."""
    genre = next((g for g in GAME_GENRES if g["id"] == genre_id), None)
    if not genre:
        raise HTTPException(status_code=404, detail=f"Genre '{genre_id}' not found")
    return {
        "genre_id": genre_id,
        "genre_name": genre["name"],
        "specialists": genre.get("specialists", []),
        "total": len(genre.get("specialists", [])),
    }


class GenreChatRequest(BaseModel):
    genre_id: str
    specialist_id: Optional[str] = None
    message: str
    game_description: str = ""
    session_id: Optional[str] = None


@router.post("/genre-chat")
async def genre_specialist_chat(req: GenreChatRequest):
    """Chat with genre specialist agents in group chat mode."""
    genre = next((g for g in GAME_GENRES if g["id"] == req.genre_id), None)
    if not genre:
        raise HTTPException(status_code=404, detail=f"Genre '{req.genre_id}' not found")

    specialists = genre.get("specialists", [])
    if not specialists:
        raise HTTPException(status_code=404, detail="No specialists available for this genre")

    context = f"Genre: {genre['name']}\nGame: {req.game_description}\n\nUser Question: {req.message}"

    # If specific specialist requested, use only that one
    if req.specialist_id:
        spec = next((s for s in specialists if s["id"] == req.specialist_id), None)
        if not spec:
            raise HTTPException(status_code=404, detail=f"Specialist '{req.specialist_id}' not found")

        sys_prompt, user_prompt = get_genre_specialist_prompt(req.specialist_id, context)
        llm_result = await call_llm(sys_prompt, user_prompt, f"genre_{req.specialist_id}_{req.session_id or 'default'}")

        return {
            "specialist": spec["name"],
            "role": spec["role"],
            "response": llm_result.get("response", "Specialist is thinking..."),
            "success": llm_result.get("success", False),
        }

    # Group chat: All specialists respond
    responses = []
    for spec in specialists:
        sys_prompt, user_prompt = get_genre_specialist_prompt(spec["id"], context)
        llm_result = await call_llm(sys_prompt, user_prompt, f"genre_{spec['id']}_{req.session_id or 'default'}")
        responses.append({
            "specialist_id": spec["id"],
            "specialist_name": spec["name"],
            "role": spec["role"],
            "color": spec["color"],
            "response": llm_result.get("response", "Specialist is thinking..."),
            "success": llm_result.get("success", False),
        })

    return {
        "genre": genre["name"],
        "genre_id": req.genre_id,
        "group_chat": True,
        "specialists_responded": len(responses),
        "responses": responses,
    }


# =============================================================================
# DESIGN AGENTS ENDPOINTS - Era, Discipline, and Movement Specialists
# =============================================================================

@router.get("/design-agents")
async def get_design_agents():
    """Get all 29 design agents: 9 eras + 10 disciplines + 10 movements."""
    agents = get_all_design_agents()
    by_category = {"era": [], "discipline": [], "movement": []}
    for a in agents:
        by_category[a["category"]].append(a)
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "eras": len(by_category["era"]),
        "disciplines": len(by_category["discipline"]),
        "movements": len(by_category["movement"]),
    }


@router.get("/design-agents/eras")
async def get_design_eras():
    """Get all 9 era-based design agents with full historical context."""
    eras = []
    for era in DESIGN_ERAS:
        eras.append({
            "id": era["id"],
            "name": era["name"],
            "years": era["years"],
            "color": era["color"],
            "key_games": era["key_games"],
            "innovations": era["innovations"],
            "design_philosophy": era["design_philosophy"],
            "specialist": {
                "id": era["specialist"]["id"],
                "name": era["specialist"]["name"],
                "role": era["specialist"]["role"],
                "specialty": era["specialist"]["specialty"],
                "color": era["specialist"]["color"],
            },
        })
    return {"eras": eras, "total": len(eras)}


@router.get("/design-agents/disciplines")
async def get_design_disciplines():
    """Get all 10 design discipline agents."""
    disciplines = []
    for disc in DESIGN_DISCIPLINES:
        disciplines.append({
            "id": disc["id"],
            "name": disc["name"],
            "specialist": {
                "id": disc["specialist"]["id"],
                "name": disc["specialist"]["name"],
                "role": disc["specialist"]["role"],
                "specialty": disc["specialist"]["specialty"],
                "color": disc["specialist"]["color"],
            },
        })
    return {"disciplines": disciplines, "total": len(disciplines)}


@router.get("/design-agents/movements")
async def get_design_movements():
    """Get all 10 design movement/school agents."""
    movements = []
    for mov in DESIGN_MOVEMENTS:
        movements.append({
            "id": mov["id"],
            "name": mov["name"],
            "specialist": {
                "id": mov["specialist"]["id"],
                "name": mov["specialist"]["name"],
                "role": mov["specialist"]["role"],
                "specialty": mov["specialist"]["specialty"],
                "color": mov["specialist"]["color"],
            },
        })
    return {"movements": movements, "total": len(movements)}


class DesignChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/design-chat")
async def design_agent_chat(req: DesignChatRequest):
    """Chat with a design agent (era, discipline, or movement specialist)."""
    agents = get_all_design_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Design agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nUser Question: {req.message}"
    sys_prompt, user_prompt = get_design_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"design_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "response": llm_result.get("response", "Design agent is analyzing..."),
        "success": llm_result.get("success", False),
    }


# =============================================================================
# TECHNICAL & CREATIVE AGENT TEAM ENDPOINTS
# Architecture, System, Engineering, Science, Math, Storyline
# =============================================================================

@router.get("/technical-agents")
async def get_technical_agents():
    """Get all 50 technical/creative agents across 6 categories."""
    agents = get_all_technical_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "categories": list(by_category.keys()),
    }


@router.get("/technical-agents/{category}")
async def get_technical_category(category: str):
    """Get agents for a specific technical category (architecture/system/engineering/science/math/storyline)."""
    if category not in ALL_TECHNICAL_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found. Valid: {list(ALL_TECHNICAL_CATEGORIES.keys())}")
    cat = ALL_TECHNICAL_CATEGORIES[category]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "category": category,
        "category_name": cat["name"],
        "color": cat["color"],
        "agents": agents,
        "total": len(agents),
    }


class TechnicalChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/technical-chat")
async def technical_agent_chat(req: TechnicalChatRequest):
    """Chat with a technical/creative agent (architecture, system, engineering, science, math, storyline)."""
    agents = get_all_technical_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Technical agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nUser Question: {req.message}"
    sys_prompt, user_prompt = get_technical_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"tech_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "Technical agent is analyzing..."),
        "success": llm_result.get("success", False),
    }


# =============================================================================
# FACTORY EXTRA AGENT ENDPOINTS
# Production, QA, Art, Audio, Marketing, Psychology, Emerging, Live Ops, Legal, Localization
# =============================================================================

@router.get("/factory-agents")
async def get_factory_extra_agents():
    """Get all 104 factory production agents across 10 categories."""
    agents = get_all_factory_extra_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "categories": list(by_category.keys()),
    }


@router.get("/factory-agents/{category}")
async def get_factory_extra_category(category: str):
    """Get agents for a specific factory category."""
    if category not in FACTORY_EXTRA_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found. Valid: {list(FACTORY_EXTRA_CATEGORIES.keys())}")
    cat = FACTORY_EXTRA_CATEGORIES[category]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "category": category,
        "category_name": cat["name"],
        "color": cat["color"],
        "agents": agents,
        "total": len(agents),
    }


class FactoryChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/factory-chat")
async def factory_agent_chat(req: FactoryChatRequest):
    """Chat with a factory production agent."""
    agents = get_all_factory_extra_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Factory agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nUser Question: {req.message}"
    sys_prompt, user_prompt = get_factory_extra_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"factory_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "Factory agent is analyzing..."),
        "success": llm_result.get("success", False),
    }


# =============================================================================
# ROSTER EXPANSION ENDPOINTS
# Traffic Control, World Building, AI Simulation, Esports, UGC,
# Platform Optimization, Data Analytics, Game Design Theory
# =============================================================================

@router.get("/roster-agents")
async def get_roster_expansion_agents():
    """Get all roster expansion agents across 8 categories (76 agents total)."""
    agents = get_all_roster_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "categories": list(by_category.keys()),
    }


@router.get("/roster-agents/{category}")
async def get_roster_category(category: str):
    """Get agents for a specific roster expansion category."""
    if category not in ROSTER_EXPANSION_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found. Valid: {list(ROSTER_EXPANSION_CATEGORIES.keys())}")
    cat = ROSTER_EXPANSION_CATEGORIES[category]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "category": category,
        "category_name": cat["name"],
        "color": cat["color"],
        "agents": agents,
        "total": len(agents),
    }


@router.get("/traffic-control")
async def get_traffic_control_agents():
    """Get the Traffic Control & Stability system agents (14 dedicated stability agents)."""
    cat = ROSTER_EXPANSION_CATEGORIES["traffic_control"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
        "persona_preview": a["persona"][:200] + "..." if len(a["persona"]) > 200 else a["persona"],
    } for a in cat["agents"]]
    return {
        "system": "Traffic Control & Stability",
        "purpose": "Ensures pipeline stability and device stability for long coding projects and large games",
        "agents": agents,
        "total": len(agents),
        "capabilities": [
            "Pipeline Orchestration & Flow Control",
            "Memory & Resource Stability Monitoring",
            "Device Performance & Thermal Guardian",
            "Compile & Build Stability Watchdog",
            "Dependency & Version Resolution",
            "Crash Prevention & Recovery",
            "Resource Budget Management",
            "Pipeline Flow Optimization",
            "Session Recovery & State Persistence",
            "Deadlock & Infinite Loop Detection",
            "Asset Integrity & Validation",
            "Build Health & Diagnostics",
            "Agent Load Balancing & Scheduling",
            "Quality Gate & Approval System",
        ],
    }


class RosterChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/roster-chat")
async def roster_agent_chat(req: RosterChatRequest):
    """Chat with any roster expansion agent (traffic control, world building, AI simulation, etc.)."""
    agents = get_all_roster_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Roster agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nUser Question: {req.message}"
    sys_prompt, user_prompt = get_roster_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"roster_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "Roster agent is analyzing..."),
        "success": llm_result.get("success", False),
    }


@router.post("/traffic-control-chat")
async def traffic_control_chat(req: RosterChatRequest):
    """Chat specifically with the Traffic Control system for pipeline stability analysis."""
    tc_agents = ROSTER_EXPANSION_CATEGORIES["traffic_control"]["agents"]
    agent = next((a for a in tc_agents if a["id"] == req.agent_id), None)
    if not agent:
        all_ids = [a["id"] for a in tc_agents]
        raise HTTPException(status_code=404, detail=f"Traffic control agent '{req.agent_id}' not found. Valid: {all_ids}")

    context = f"Game Context: {req.game_context}\n\nStability Query: {req.message}"
    sys_prompt, user_prompt = get_roster_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"tc_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "system": "Traffic Control & Stability",
        "response": llm_result.get("response", "Traffic control agent is analyzing stability..."),
        "success": llm_result.get("success", False),
    }



# =============================================================================
# ACADEMIC ENDPOINTS
# Physics Academy (16 agents) + Advanced Computer Science (16 agents)
# =============================================================================

@router.get("/academic-agents")
async def get_academic_agents():
    """Get all academic agents — Physics Academy + Advanced Computer Science (32 agents)."""
    agents = get_all_academic_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "categories": list(by_category.keys()),
    }


@router.get("/academic-agents/{category}")
async def get_academic_category(category: str):
    """Get agents for a specific academic category (physics_academy or computer_science)."""
    if category not in ACADEMIC_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found. Valid: {list(ACADEMIC_CATEGORIES.keys())}")
    cat = ACADEMIC_CATEGORIES[category]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "category": category,
        "category_name": cat["name"],
        "color": cat["color"],
        "agents": agents,
        "total": len(agents),
    }


@router.get("/physics-academy")
async def get_physics_academy():
    """Get the Physics Academy agents (16 dedicated physics specialists)."""
    cat = ACADEMIC_CATEGORIES["physics_academy"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
        "persona_preview": a["persona"][:200] + "..." if len(a["persona"]) > 200 else a["persona"],
    } for a in cat["agents"]]
    return {
        "academy": "Physics Academy",
        "purpose": "Deep physics simulation theory and implementation for game engines",
        "agents": agents,
        "total": len(agents),
        "disciplines": [
            "Classical Mechanics & Rigid Body Dynamics",
            "Fluid Dynamics (Water, Smoke, Fire)",
            "Soft Body & Deformation (Cloth, Jelly, Hair)",
            "Particle Systems & VFX",
            "Ragdoll & Character Physics",
            "Vehicle Physics & Tire Models",
            "Optical Physics & PBR Lighting",
            "Wave Physics & Audio Propagation",
            "Thermodynamics & Weather Systems",
            "Exotic Physics (Relativity, Black Holes)",
            "Material Science & Physical Properties",
            "Orbital Mechanics & Space Physics",
            "Quantum Mechanics as Gameplay",
            "Biological Physics & Creature Locomotion",
            "Chaos Theory & Procedural Generation",
            "Numerical Methods & Stability",
        ],
    }


@router.get("/cs-academy")
async def get_cs_academy():
    """Get the Advanced Computer Science agents (16 dedicated CS specialists)."""
    cat = ACADEMIC_CATEGORIES["computer_science"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
        "persona_preview": a["persona"][:200] + "..." if len(a["persona"]) > 200 else a["persona"],
    } for a in cat["agents"]]
    return {
        "academy": "Advanced Computer Science",
        "purpose": "Deep CS theory and algorithms applied to game engine development",
        "agents": agents,
        "total": len(agents),
        "disciplines": [
            "Algorithms & Data Structures",
            "Graphics Programming & Rendering",
            "Game Networking & Multiplayer",
            "Advanced Game AI (GOAP, HTN, MCTS)",
            "Scripting & Compiler Design",
            "Game Databases & Persistence",
            "OS & Platform Engineering",
            "Game Security & Cryptography",
            "Parallel Computing & Multithreading",
            "Memory Management & Optimization",
            "Procedural Generation Algorithms",
            "Animation Systems & IK",
            "Audio Engine & DSP",
            "Game Mathematics",
            "Automated Testing & Verification",
            "Game DevOps & Build Pipelines",
        ],
    }


class AcademicChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/academic-chat")
async def academic_agent_chat(req: AcademicChatRequest):
    """Chat with any academic agent (physics or computer science)."""
    agents = get_all_academic_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Academic agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nQuestion: {req.message}"
    sys_prompt, user_prompt = get_academic_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"academic_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "Academic agent is analyzing..."),
        "success": llm_result.get("success", False),
    }



# =============================================================================
# TEAM HIERARCHY ENDPOINTS
# Division Directors (6) + Team Leaders (18) + QA Sub-Agents (16) + Coordination (12)
# =============================================================================

@router.get("/hierarchy-agents")
async def get_hierarchy_agents():
    """Get all team hierarchy agents — Directors, Leaders, QA, Coordination (52 agents)."""
    agents = get_all_hierarchy_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "categories": list(by_category.keys()),
    }


@router.get("/hierarchy-agents/{category}")
async def get_hierarchy_category(category: str):
    """Get agents for a specific hierarchy category."""
    if category not in TEAM_HIERARCHY_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found. Valid: {list(TEAM_HIERARCHY_CATEGORIES.keys())}")
    cat = TEAM_HIERARCHY_CATEGORIES[category]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "category": category,
        "category_name": cat["name"],
        "color": cat["color"],
        "agents": agents,
        "total": len(agents),
    }


@router.get("/directors")
async def get_directors():
    """Get the 6 Division Directors — C-suite leadership."""
    cat = TEAM_HIERARCHY_CATEGORIES["division_directors"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
        "persona_preview": a["persona"][:200] + "..." if len(a["persona"]) > 200 else a["persona"],
    } for a in cat["agents"]]
    return {
        "level": "C-Suite",
        "purpose": "Top-level leadership overseeing the entire Game Factory",
        "agents": agents,
        "total": len(agents),
    }


@router.get("/team-leads")
async def get_team_leads():
    """Get the 18 Team Leaders — mid-level department leads."""
    cat = TEAM_HIERARCHY_CATEGORIES["team_leaders"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "level": "Team Leadership",
        "purpose": "Department leads ensuring each team delivers AAA-quality work",
        "agents": agents,
        "total": len(agents),
    }


@router.get("/qa-agents")
async def get_qa_agents():
    """Get the 16 QA Sub-Agents — dedicated quality enforcers."""
    cat = TEAM_HIERARCHY_CATEGORIES["qa_sub_agents"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "level": "Quality Assurance",
        "purpose": "Dedicated quality enforcers across every domain",
        "agents": agents,
        "total": len(agents),
    }


@router.get("/coordination-agents")
async def get_coordination_agents():
    """Get the 12 Coordination Sub-Agents — cross-team orchestrators."""
    cat = TEAM_HIERARCHY_CATEGORIES["coordination"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "level": "Coordination",
        "purpose": "Cross-team orchestrators ensuring smooth operations",
        "agents": agents,
        "total": len(agents),
    }


class HierarchyChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/hierarchy-chat")
async def hierarchy_agent_chat(req: HierarchyChatRequest):
    """Chat with any hierarchy agent (directors, leaders, QA, coordination)."""
    agents = get_all_hierarchy_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Hierarchy agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nQuery: {req.message}"
    sys_prompt, user_prompt = get_hierarchy_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"hierarchy_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "Leadership agent is analyzing..."),
        "success": llm_result.get("success", False),
    }



# =============================================================================
# COMMAND AGENTS ENDPOINTS
# Holodeck (Grok Imagine), Emperor, Secretary, Summary, Triage, Hotfix Team
# =============================================================================

@router.get("/command-agents")
async def get_command_agents():
    """Get all command agents — Holodeck, Emperor, Secretary, Summary, Triage, Hotfix (11 agents)."""
    agents = get_all_command_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
        "categories": list(by_category.keys()),
    }


@router.get("/command-agents/{category}")
async def get_command_category(category: str):
    """Get agents for a specific command category."""
    if category not in COMMAND_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found. Valid: {list(COMMAND_CATEGORIES.keys())}")
    cat = COMMAND_CATEGORIES[category]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "category": category,
        "category_name": cat["name"],
        "color": cat["color"],
        "agents": agents,
        "total": len(agents),
    }


@router.get("/emperor")
async def get_emperor():
    """Get the Emperor — Supreme Commander of the Game Factory."""
    from routes.game_command_agents import EMPEROR_AGENT
    return {
        "agent": {
            "id": EMPEROR_AGENT["id"],
            "name": EMPEROR_AGENT["name"],
            "role": EMPEROR_AGENT["role"],
            "specialty": EMPEROR_AGENT["specialty"],
            "color": EMPEROR_AGENT["color"],
            "persona_preview": EMPEROR_AGENT["persona"][:300] + "...",
        },
        "authority": "ABSOLUTE",
        "commands": "All 590 agents",
        "chain_of_command": [
            "Emperor → Division Directors (6)",
            "Division Directors → Team Leaders (18)",
            "Team Leaders → Specialists (500+)",
            "Specialists → Sub-Agents (QA, Coordination)",
        ],
    }


@router.get("/secretary")
async def get_secretary():
    """Get the Secretary — Work Breakdown & Session Continuity Manager."""
    from routes.game_command_agents import SECRETARY_AGENT
    return {
        "agent": {
            "id": SECRETARY_AGENT["id"],
            "name": SECRETARY_AGENT["name"],
            "role": SECRETARY_AGENT["role"],
            "specialty": SECRETARY_AGENT["specialty"],
            "color": SECRETARY_AGENT["color"],
        },
        "capabilities": [
            "Work Breakdown into manageable chunks",
            "Session persistence and snapshot creation",
            "Continuity protocol for cross-session work",
            "Task tracking with progress percentages",
            "Handoff document generation",
            "Meeting minutes and decision logging",
        ],
    }


@router.get("/triage")
async def get_triage():
    """Get the Triage Agent — Issue Classifier & Priority Router."""
    from routes.game_command_agents import TRIAGE_AGENT
    return {
        "agent": {
            "id": TRIAGE_AGENT["id"],
            "name": TRIAGE_AGENT["name"],
            "role": TRIAGE_AGENT["role"],
            "specialty": TRIAGE_AGENT["specialty"],
            "color": TRIAGE_AGENT["color"],
        },
        "severity_levels": {
            "S1_CRITICAL": "Game crash, data loss, security breach — 1hr SLA",
            "S2_HIGH": "Major feature broken, perf regression — 4hr SLA",
            "S3_MEDIUM": "Minor issue, visual glitch — 24hr SLA",
            "S4_LOW": "Polish, cosmetic, docs — Sprint backlog",
        },
    }


@router.get("/hotfix-team")
async def get_hotfix_team():
    """Get the Hotfix Emergency Team — 6 agents for critical fixes."""
    from routes.game_command_agents import HOTFIX_TEAM_AGENTS
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in HOTFIX_TEAM_AGENTS]
    return {
        "team": "Hotfix Emergency Response",
        "purpose": "Rapid response to critical issues — triage, fix, test, deploy, rollback",
        "agents": agents,
        "total": len(agents),
        "protocol": [
            "1. ASSESS — Full picture in 5 minutes",
            "2. MOBILIZE — Assign parallel tracks",
            "3. ISOLATE — Contain blast radius",
            "4. FIX — Minimal, safest fix only",
            "5. VERIFY — Regression test on all platforms",
            "6. DEPLOY — Emergency pipeline push",
            "7. MONITOR — 30 min post-deploy watch",
            "8. POSTMORTEM — Root cause + prevention",
        ],
    }


@router.get("/holodeck")
async def get_holodeck():
    """Get the Holodeck Render Engine — generates visual renders via Grok Imagine (Aurora)."""
    from routes.game_command_agents import HOLODECK_AGENT, XAI_API_KEY
    return {
        "agent": {
            "id": HOLODECK_AGENT["id"],
            "name": HOLODECK_AGENT["name"],
            "role": HOLODECK_AGENT["role"],
            "specialty": HOLODECK_AGENT["specialty"],
            "color": HOLODECK_AGENT["color"],
        },
        "engine": "Grok Imagine (Aurora) via xAI API",
        "api_configured": bool(XAI_API_KEY),
        "render_policy": "One render per team per game — visual timeline of development progress",
        "supported_teams": [
            "Design", "Engineering", "Art & Visual", "Audio", "Narrative",
            "QA", "Production", "Traffic Control", "World Building",
            "AI & Simulation", "Esports", "Platform", "Physics Academy",
            "CS Academy", "Hotfix Team",
        ],
    }


class HolodeckRenderRequest(BaseModel):
    team_name: str
    team_output: str
    game_context: str = ""


@router.post("/holodeck-render")
async def holodeck_render(req: HolodeckRenderRequest):
    """Generate a visual render of team output using Grok Imagine (Aurora) API."""
    result = await generate_holodeck_render(req.team_name, req.team_output, req.game_context)

    # Log render to vault
    await log_chat_message(
        room_id="holodeck",
        agent_id="holodeck", agent_name="Holodeck", agent_role="Visual Render Engine",
        category="holodeck", user_message=f"[RENDER REQUEST] Team: {req.team_name} | Context: {req.game_context}",
        agent_response=f"[RENDER] {'✅ Image generated' if result.get('success') else '❌ ' + result.get('error', 'unknown error')} | URL: {result.get('image_url', 'N/A')}",
        session_id="holodeck_renders", game_context=req.game_context,
        success=result.get("success", False),
    )

    return result


class HolodeckChatRenderRequest(BaseModel):
    message: str
    game_context: str = ""
    auto_render: bool = True
    session_id: Optional[str] = None


@router.post("/holodeck-chat")
async def holodeck_chat_with_render(req: HolodeckChatRenderRequest):
    """Chat with the Holodeck agent AND optionally auto-generate a render from the response."""
    # First, get the Holodeck agent's text response
    context = f"Game Context: {req.game_context}\n\nUser Request: {req.message}"
    sys_prompt, user_prompt = get_command_agent_prompt("holodeck", context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"holodeck_chat_{req.session_id or 'default'}")

    response_data = {
        "agent": "Holodeck",
        "role": "Visual Render Engine (Grok Imagine Aurora)",
        "text_response": llm_result.get("response", "Holodeck is warming up..."),
        "success": llm_result.get("success", False),
        "render": None,
    }

    # Auto-render if requested and text response succeeded
    if req.auto_render and llm_result.get("success"):
        render_result = await generate_holodeck_render(
            team_name="Holodeck Direct",
            team_output=llm_result.get("response", "")[:500],
            game_context=req.game_context or req.message,
        )
        response_data["render"] = render_result

    # Log to vault
    await log_chat_message(
        room_id="holodeck",
        agent_id="holodeck", agent_name="Holodeck", agent_role="Visual Render Engine",
        category="holodeck", user_message=req.message,
        agent_response=llm_result.get("response", ""),
        session_id=req.session_id or "default",
        game_context=req.game_context, success=llm_result.get("success", False),
    )

    return response_data


class CommandChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/command-chat")
async def command_agent_chat(req: CommandChatRequest):
    """Chat with any command agent (Emperor, Secretary, Summary, Triage, Holodeck, Hotfix)."""
    agents = get_all_command_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Command agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nDirective: {req.message}"
    sys_prompt, user_prompt = get_command_agent_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"command_{req.agent_id}_{req.session_id or 'default'}")

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "Command agent processing..."),
        "success": llm_result.get("success", False),
    }



# =============================================================================
# MEGA EXPANSION ENDPOINTS — Alpha (72) + Beta (64) + Gamma (62) = 198 agents
# =============================================================================

@router.get("/expansion-alpha")
async def get_expansion_alpha():
    """Get Expansion Alpha agents — Monetization (20) + Community (16) + Localization (20) + Cinematics (16) = 72."""
    agents = get_all_alpha_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {"agents": agents, "total": len(agents), "by_category": by_category, "expansion": "Alpha"}


@router.get("/expansion-beta")
async def get_expansion_beta():
    """Get Expansion Beta agents — Environment Art (18) + Character Art (16) + VFX (14) + Music (16) = 64."""
    agents = get_all_beta_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {"agents": agents, "total": len(agents), "by_category": by_category, "expansion": "Beta"}


@router.get("/expansion-gamma")
async def get_expansion_gamma():
    """Get Expansion Gamma agents — UI/UX (14) + Infrastructure (20) + Narrative (16) + Accessibility (12) = 62."""
    agents = get_all_gamma_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {"agents": agents, "total": len(agents), "by_category": by_category, "expansion": "Gamma"}


class ExpansionChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/expansion-chat")
async def expansion_chat(req: ExpansionChatRequest):
    """Chat with any expansion agent across Alpha, Beta, or Gamma packs."""
    # Try Alpha
    alpha_agents = get_all_alpha_agents()
    agent = next((a for a in alpha_agents if a["id"] == req.agent_id), None)
    if agent:
        context = f"Game Context: {req.game_context}\n\nQuery: {req.message}"
        sys_prompt, user_prompt = get_alpha_agent_prompt(req.agent_id, context)
        llm_result = await call_llm(sys_prompt, user_prompt, f"alpha_{req.agent_id}_{req.session_id or 'default'}")
        return {"agent": agent["name"], "role": agent["role"], "category": agent["category"], "category_name": agent["category_name"], "response": llm_result.get("response", "Agent analyzing..."), "success": llm_result.get("success", False)}

    # Try Beta
    beta_agents = get_all_beta_agents()
    agent = next((a for a in beta_agents if a["id"] == req.agent_id), None)
    if agent:
        context = f"Game Context: {req.game_context}\n\nQuery: {req.message}"
        sys_prompt, user_prompt = get_beta_agent_prompt(req.agent_id, context)
        llm_result = await call_llm(sys_prompt, user_prompt, f"beta_{req.agent_id}_{req.session_id or 'default'}")
        return {"agent": agent["name"], "role": agent["role"], "category": agent["category"], "category_name": agent["category_name"], "response": llm_result.get("response", "Agent analyzing..."), "success": llm_result.get("success", False)}

    # Try Gamma
    gamma_agents = get_all_gamma_agents()
    agent = next((a for a in gamma_agents if a["id"] == req.agent_id), None)
    if agent:
        context = f"Game Context: {req.game_context}\n\nQuery: {req.message}"
        sys_prompt, user_prompt = get_gamma_agent_prompt(req.agent_id, context)
        llm_result = await call_llm(sys_prompt, user_prompt, f"gamma_{req.agent_id}_{req.session_id or 'default'}")
        return {"agent": agent["name"], "role": agent["role"], "category": agent["category"], "category_name": agent["category_name"], "response": llm_result.get("response", "Agent analyzing..."), "success": llm_result.get("success", False)}

    raise HTTPException(status_code=404, detail=f"Expansion agent '{req.agent_id}' not found in Alpha, Beta, or Gamma packs")





# =============================================================================
# EMPEROR'S COURT & GUARD ENDPOINTS
# Court (10 advisors) + Guard (10 enforcers) = 20 agents
# =============================================================================

@router.get("/emperors-court")
async def get_emperors_court():
    """Get the Emperor's Court — 10 royal advisors."""
    cat = EMPEROR_COURT_CATEGORIES["emperors_court"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
        "persona_preview": a["persona"][:200] + "..." if len(a["persona"]) > 200 else a["persona"],
    } for a in cat["agents"]]
    return {
        "institution": "Emperor's Court",
        "purpose": "Royal advisory council ensuring the Emperor's absolute authority is supported with intelligence, strategy, and wisdom",
        "agents": agents,
        "total": len(agents),
        "hierarchy": "Emperor → Grand Vizier → Court Members → All Agents",
    }


@router.get("/emperors-guard")
async def get_emperors_guard():
    """Get the Emperor's Guard — 10 enforcement & protection agents."""
    cat = EMPEROR_COURT_CATEGORIES["emperors_guard"]
    agents = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "specialty": a["specialty"], "color": a["color"],
    } for a in cat["agents"]]
    return {
        "institution": "Emperor's Guard",
        "purpose": "Enforcement & protection unit ensuring structural integrity and standards compliance",
        "agents": agents,
        "total": len(agents),
        "chain": "Captain of the Guard → Sentinels → Specialists",
    }


@router.get("/court-guard-agents")
async def get_all_court_guard():
    """Get all court & guard agents (20 total)."""
    agents = get_all_court_guard_agents()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {"agents": agents, "total": len(agents), "by_category": by_category}


class CourtGuardChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/court-guard-chat")
async def court_guard_chat(req: CourtGuardChatRequest):
    """Chat with any Emperor's Court or Guard agent."""
    agents = get_all_court_guard_agents()
    agent = next((a for a in agents if a["id"] == req.agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Court/Guard agent '{req.agent_id}' not found")

    context = f"Game Context: {req.game_context}\n\nRoyal Inquiry: {req.message}"
    sys_prompt, user_prompt = get_court_guard_prompt(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"court_{req.agent_id}_{req.session_id or 'default'}")

    # Log to vault
    await log_chat_message(
        room_id="emperors_court" if agent["category"] == "emperors_court" else "emperors_guard",
        agent_id=agent["id"], agent_name=agent["name"], agent_role=agent["role"],
        category=agent["category"], user_message=req.message,
        agent_response=llm_result.get("response", ""), session_id=req.session_id or "default",
        game_context=req.game_context, success=llm_result.get("success", False),
    )

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "response": llm_result.get("response", "The court is deliberating..."),
        "success": llm_result.get("success", False),
        "logged_to_vault": True,
    }


# =============================================================================
# ACCURACY AGENTS — Reality Accuracy Division (192 original agents)
# Alpha: Historical, Philosophy, Political, Scientific (66)
# Beta: Cultural, Linguistic, Economic, Legal (64)
# Gamma: Military Equipment, Architecture, Music/Sound, Mythology (62)
# =============================================================================

@router.get("/accuracy-agents")
async def get_accuracy_agents():
    """Get ALL accuracy agents across Alpha, Beta, and Gamma divisions."""
    alpha = get_all_accuracy_alpha_agents()
    beta = get_all_accuracy_beta_agents()
    gamma = get_all_accuracy_gamma_agents()
    all_agents = alpha + beta + gamma
    by_division = {
        "alpha": {"name": "Historical, Philosophy, Political, Scientific", "count": len(alpha), "agents": alpha},
        "beta": {"name": "Cultural, Linguistic, Economic, Legal", "count": len(beta), "agents": beta},
        "gamma": {"name": "Military Equipment, Architecture, Music/Sound, Mythology", "count": len(gamma), "agents": gamma},
    }
    return {
        "division": "Reality Accuracy Division",
        "agents": all_agents,
        "total": len(all_agents),
        "by_division": {k: {"name": v["name"], "count": v["count"]} for k, v in by_division.items()},
        "alpha_categories": {cat_id: {"name": cat["name"], "count": len(cat["agents"])} for cat_id, cat in ACCURACY_ALPHA_CATEGORIES.items()},
        "beta_categories": {cat_id: {"name": cat["name"], "count": len(cat["agents"])} for cat_id, cat in ACCURACY_BETA_CATEGORIES.items()},
        "gamma_categories": {cat_id: {"name": cat["name"], "count": len(cat["agents"])} for cat_id, cat in ACCURACY_GAMMA_CATEGORIES.items()},
    }


@router.get("/accuracy-agents/{division}")
async def get_accuracy_division(division: str):
    """Get accuracy agents for a specific division (alpha, beta, gamma)."""
    divisions = {
        "alpha": {"getter": get_all_accuracy_alpha_agents, "categories": ACCURACY_ALPHA_CATEGORIES, "name": "Alpha"},
        "beta": {"getter": get_all_accuracy_beta_agents, "categories": ACCURACY_BETA_CATEGORIES, "name": "Beta"},
        "gamma": {"getter": get_all_accuracy_gamma_agents, "categories": ACCURACY_GAMMA_CATEGORIES, "name": "Gamma"},
    }
    if division not in divisions:
        raise HTTPException(status_code=404, detail=f"Division '{division}' not found. Valid: alpha, beta, gamma")
    d = divisions[division]
    agents = d["getter"]()
    by_category = {}
    for a in agents:
        cat = a["category"]
        if cat not in by_category:
            by_category[cat] = {"name": a["category_name"], "agents": [], "count": 0}
        by_category[cat]["agents"].append(a)
        by_category[cat]["count"] += 1
    return {
        "division": division,
        "division_name": f"Accuracy {d['name']}",
        "agents": agents,
        "total": len(agents),
        "by_category": by_category,
    }


class AccuracyChatRequest(BaseModel):
    agent_id: str
    message: str
    game_context: str = ""
    session_id: Optional[str] = None


@router.post("/accuracy-chat")
async def accuracy_agent_chat(req: AccuracyChatRequest):
    """Chat with any accuracy agent from Alpha, Beta, or Gamma division."""
    # Try each division
    prompt_fns = [
        ("alpha", get_all_accuracy_alpha_agents, get_accuracy_alpha_prompt),
        ("beta", get_all_accuracy_beta_agents, get_accuracy_beta_prompt),
        ("gamma", get_all_accuracy_gamma_agents, get_accuracy_gamma_prompt),
    ]
    agent = None
    prompt_fn = None
    division = None
    for div, getter, pfn in prompt_fns:
        agents = getter()
        found = next((a for a in agents if a["id"] == req.agent_id), None)
        if found:
            agent = found
            prompt_fn = pfn
            division = div
            break

    if not agent:
        raise HTTPException(status_code=404, detail=f"Accuracy agent '{req.agent_id}' not found in any division")

    context = f"Game Context: {req.game_context}\n\nAccuracy Review Request: {req.message}"
    sys_prompt, user_prompt = prompt_fn(req.agent_id, context)
    llm_result = await call_llm(sys_prompt, user_prompt, f"accuracy_{req.agent_id}_{req.session_id or 'default'}")

    # Log to vault
    room_id = f"accuracy_{division}_{agent['category']}"
    await log_chat_message(
        room_id=room_id,
        agent_id=agent["id"], agent_name=agent["name"], agent_role=agent["role"],
        category=agent["category"], user_message=req.message,
        agent_response=llm_result.get("response", ""), session_id=req.session_id or "default",
        game_context=req.game_context, success=llm_result.get("success", False),
    )

    return {
        "agent": agent["name"],
        "role": agent["role"],
        "category": agent["category"],
        "category_name": agent["category_name"],
        "division": f"accuracy_{division}",
        "response": llm_result.get("response", "Accuracy agent is reviewing..."),
        "success": llm_result.get("success", False),
        "logged_to_vault": True,
    }


@router.post("/accuracy-review")
async def accuracy_group_review(req: AccuracyChatRequest):
    """Submit content for review by ALL accuracy agents in a category.
    agent_id should be a category like 'historical', 'philosophy', 'political', etc."""
    # Find the category across all divisions
    all_categories = {}
    all_categories.update(ACCURACY_ALPHA_CATEGORIES)
    all_categories.update(ACCURACY_BETA_CATEGORIES)
    all_categories.update(ACCURACY_GAMMA_CATEGORIES)

    if req.agent_id not in all_categories:
        raise HTTPException(
            status_code=404,
            detail=f"Category '{req.agent_id}' not found. Valid: {list(all_categories.keys())}"
        )

    cat = all_categories[req.agent_id]
    context = f"Game Context: {req.game_context}\n\nContent for Accuracy Review: {req.message}"

    responses = []
    for agent in cat["agents"][:5]:  # Limit to 5 for performance
        # Determine which prompt function to use
        if req.agent_id in ACCURACY_ALPHA_CATEGORIES:
            sys_prompt, user_prompt = get_accuracy_alpha_prompt(agent["id"], context)
        elif req.agent_id in ACCURACY_BETA_CATEGORIES:
            sys_prompt, user_prompt = get_accuracy_beta_prompt(agent["id"], context)
        else:
            sys_prompt, user_prompt = get_accuracy_gamma_prompt(agent["id"], context)

        llm_result = await call_llm(sys_prompt, user_prompt, f"accuracy_{agent['id']}_{req.session_id or 'default'}")
        responses.append({
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "role": agent["role"],
            "color": agent.get("color", "#8B5CF6"),
            "response": llm_result.get("response", "Reviewing..."),
            "success": llm_result.get("success", False),
        })

    return {
        "category": req.agent_id,
        "category_name": cat["name"],
        "group_review": True,
        "agents_responded": len(responses),
        "total_in_category": len(cat["agents"]),
        "responses": responses,
    }


# =============================================================================
# PARALLEL SOCIETY — Shadow Agents (SOTA quality review)
# =============================================================================
# REFACTORED: Moved to routes/game_router_layers.py

# =============================================================================
# GHOST SOCIETY — Methodology Enforcement Layer (~990 ghosts)
# REFACTORED: Moved to routes/game_router_layers.py
# =============================================================================

# =============================================================================
# ANGEL CLASS — Complexity Guardians (1 Angel per every agent in every layer)
# REFACTORED: Moved to routes/game_router_layers.py
# =============================================================================

# =============================================================================
# MULTI-LAYER VIEWS
# REFACTORED: Moved to routes/game_router_layers.py
# =============================================================================


# =============================================================================
# CHAT VAULT — Persistent MongoDB logging for all chat rooms
# =============================================================================

@router.get("/vault/stats")
async def vault_stats():
    """Get vault statistics — total messages, active rooms, top agents."""
    stats = await get_vault_stats()
    return stats


@router.get("/vault/history/{room_id}")
async def vault_room_history(room_id: str, limit: int = 50, skip: int = 0):
    """Get chat history for a specific room from the vault."""
    history = await get_room_history(room_id, limit, skip)
    return {
        "room_id": room_id,
        "messages": history,
        "count": len(history),
        "limit": limit,
        "skip": skip,
    }


@router.get("/vault/agent/{agent_id}")
async def vault_agent_history(agent_id: str, limit: int = 50, skip: int = 0):
    """Get all chat history for a specific agent from the vault."""
    history = await get_agent_log(agent_id, limit, skip)
    return {
        "agent_id": agent_id,
        "messages": history,
        "count": len(history),
    }


@router.get("/vault/session/{session_id}")
async def vault_session_history(session_id: str, limit: int = 100):
    """Get all chat history for a specific session from the vault."""
    history = await get_session_history(session_id, limit)
    return {
        "session_id": session_id,
        "messages": history,
        "count": len(history),
    }


@router.get("/vault/search")
async def vault_search(q: str, limit: int = 50):
    """Search vault messages by text content."""
    results = await search_vault(q, limit)
    return {
        "query": q,
        "results": results,
        "count": len(results),
    }


@router.get("/all-agents-summary")
async def get_all_agents_summary():
    """Get a complete summary of ALL agents across the entire Game Factory system."""
    genre_specs = get_all_specialists_flat()
    universal = get_universal_specialists()
    design = get_all_design_agents()
    technical = get_all_technical_agents()
    factory = get_all_factory_extra_agents()
    roster = get_all_roster_agents()
    academic = get_all_academic_agents()
    hierarchy = get_all_hierarchy_agents()
    command = get_all_command_agents()
    alpha = get_all_alpha_agents()
    beta = get_all_beta_agents()
    gamma = get_all_gamma_agents()
    court_guard = get_all_court_guard_agents()
    accuracy_alpha = get_all_accuracy_alpha_agents()
    accuracy_beta = get_all_accuracy_beta_agents()
    accuracy_gamma = get_all_accuracy_gamma_agents()
    pantheon_alpha = get_all_pantheon_alpha_agents()
    pantheon_beta = get_all_pantheon_beta_agents()
    pantheon_gamma = get_all_pantheon_gamma_agents()
    pantheon_delta = get_all_pantheon_delta_agents()
    pantheon_epsilon = get_all_pantheon_epsilon_agents()
    pantheon_zeta = get_all_pantheon_zeta_agents()

    shadow_count = len(get_all_shadow_agents())
    ghost_count = len(get_all_ghost_agents())
    angel_count = len(get_all_angel_agents())
    seraphim_count = len(get_all_seraphim_agents())
    cherubim_count = len(get_all_cherubim_agents())
    originals = len(genre_specs) + len(universal) + len(design) + len(technical) + len(factory) + len(roster) + len(academic) + len(hierarchy) + len(command) + len(alpha) + len(beta) + len(gamma) + len(court_guard) + len(accuracy_alpha) + len(accuracy_beta) + len(accuracy_gamma) + len(pantheon_alpha) + len(pantheon_beta) + len(pantheon_gamma) + len(pantheon_delta) + len(pantheon_epsilon) + len(pantheon_zeta)

    return {
        "grand_total": originals,
        "grand_total_with_shadows": originals + shadow_count,
        "grand_total_with_all_layers": originals + shadow_count + ghost_count + angel_count + seraphim_count + cherubim_count,
        "breakdown": {
            "genre_specialists": len(genre_specs),
            "universal_specialists": len(universal),
            "design_agents": len(design),
            "technical_agents": len(technical),
            "factory_agents": len(factory),
            "roster_expansion_agents": len(roster),
            "academic_agents": len(academic),
            "hierarchy_agents": len(hierarchy),
            "command_agents": len(command),
            "expansion_alpha_agents": len(alpha),
            "expansion_beta_agents": len(beta),
            "expansion_gamma_agents": len(gamma),
            "emperor_court_guard": len(court_guard),
            "accuracy_alpha_agents": len(accuracy_alpha),
            "accuracy_beta_agents": len(accuracy_beta),
            "accuracy_gamma_agents": len(accuracy_gamma),
            "pantheon_alpha_agents": len(pantheon_alpha),
            "pantheon_beta_agents": len(pantheon_beta),
            "pantheon_gamma_agents": len(pantheon_gamma),
            "pantheon_delta_agents": len(pantheon_delta),
            "pantheon_epsilon_agents": len(pantheon_epsilon),
            "pantheon_zeta_agents": len(pantheon_zeta),
            "shadow_agents": shadow_count,
            "ghost_agents": ghost_count,
            "angel_agents": angel_count,
            "seraphim_agents": seraphim_count,
            "cherubim_agents": cherubim_count,
        },
        "quality_layers": {
            "originals": {"count": originals, "purpose": "Core agent workforce"},
            "shadows": {"count": shadow_count, "purpose": "SOTA quality peer review (fast lane)"},
            "ghosts": {"count": ghost_count, "purpose": "Methodology enforcement (slow lane — higher consistency)"},
            "angels": {"count": angel_count, "purpose": "Complexity guardians — simplification & clarity enforcement"},
            "seraphim": {"count": seraphim_count, "purpose": "Intricacy arbiters — micro-detail, edge cases, polish perfection"},
            "cherubim": {"count": cherubim_count, "purpose": "Diligence enforcers — hard work, high standards, thoroughness, no shortcuts"},
        },
        "pantheon_divisions": {
            "alpha": {"name": "Psychology, Cinematography, Narrative, Mathematics", "count": len(pantheon_alpha)},
            "beta": {"name": "Ecology, Geography, Sociology, Engineering", "count": len(pantheon_beta)},
            "gamma": {"name": "Medicine, Astronomy, Oceanography, Meteorology", "count": len(pantheon_gamma)},
            "delta": {"name": "Forensics, Espionage, Martial Arts, Theater", "count": len(pantheon_delta)},
            "epsilon": {"name": "Education, Philosophy of Design, Ethics, Accessibility", "count": len(pantheon_epsilon)},
            "zeta": {"name": "Materials Science, Optics, Acoustics, Thermodynamics", "count": len(pantheon_zeta)},
        },
        "accuracy_divisions": {
            "alpha": {
                "name": "Accuracy Alpha (Historical, Philosophy, Political, Scientific)",
                "count": len(accuracy_alpha),
                "categories": {
                    cat_id: {"name": cat["name"], "count": len(cat["agents"])}
                    for cat_id, cat in ACCURACY_ALPHA_CATEGORIES.items()
                },
            },
            "beta": {
                "name": "Accuracy Beta (Cultural, Linguistic, Economic, Legal)",
                "count": len(accuracy_beta),
                "categories": {
                    cat_id: {"name": cat["name"], "count": len(cat["agents"])}
                    for cat_id, cat in ACCURACY_BETA_CATEGORIES.items()
                },
            },
            "gamma": {
                "name": "Accuracy Gamma (Military Equipment, Architecture, Music/Sound, Mythology)",
                "count": len(accuracy_gamma),
                "categories": {
                    cat_id: {"name": cat["name"], "count": len(cat["agents"])}
                    for cat_id, cat in ACCURACY_GAMMA_CATEGORIES.items()
                },
            },
        },
        "command_categories": {
            cat_id: {"name": cat["name"], "count": len(cat["agents"])}
            for cat_id, cat in COMMAND_CATEGORIES.items()
        },
        "hierarchy_categories": {
            cat_id: {"name": cat["name"], "count": len(cat["agents"])}
            for cat_id, cat in TEAM_HIERARCHY_CATEGORIES.items()
        },
        "roster_expansion_categories": {
            cat_id: {"name": cat["name"], "count": len(cat["agents"])}
            for cat_id, cat in ROSTER_EXPANSION_CATEGORIES.items()
        },
        "academic_categories": {
            cat_id: {"name": cat["name"], "count": len(cat["agents"])}
            for cat_id, cat in ACADEMIC_CATEGORIES.items()
        },
        "pipeline_steps": len(BUILD_PIPELINE),
        "genres": len(GAME_GENRES),
        "templates": sum(len(g.get("templates", [])) for g in GAME_GENRES),
        "competency_matrices": {
            "enabled": True,
            "dimensions": len(COMPETENCY_DIMENSIONS),
            "mastery_levels": len(MASTERY_LEVELS),
            "industry_standards": len(INDUSTRY_STANDARDS),
            "philosophy": "Competency is not a destination — it is a velocity vector",
        },
        "knowledge_engine": {
            "enabled": True,
            "total_domains": len(KNOWLEDGE_DOMAINS),
            "total_knowledge_items": sum(len(d["core_knowledge"]) for d in KNOWLEDGE_DOMAINS),
            "depth_levels": 5,
            "philosophy": "Knowledge is the capacity to transform information into wisdom",
        },
        "synergy_engine": {
            "enabled": True,
            "layers_tracked": ["shadow", "ghost", "angel", "seraphim", "cherubim"],
            "vault_integration": True,
            "jeeves_learning_loop": True,
            "cross_agent_tracking": True,
            "philosophy": "A symphony is not 100 instruments playing separately — it is 100 instruments playing AS ONE",
        },
    }


@router.get("/pipeline")
async def get_build_pipeline():
    """Get the full build pipeline definition."""
    return {
        "steps": BUILD_PIPELINE,
        "total_steps": len(BUILD_PIPELINE),
        "phases": ["design", "engineering", "content", "visual", "qa", "compile"],
    }


# =============================================================================
# BUILD PIPELINE ENDPOINTS
# REFACTORED: Moved to routes/game_router_build.py
# =============================================================================


# =============================================================================
# COMPETITOR MODE - Oracle Agent
# REFACTORED: Moved to routes/game_router_competitor.py
# =============================================================================


# =============================================================================
# HELPERS (kept for backward compatibility — also in game_shared.py)
# =============================================================================

def _extract_code_blocks(text: str) -> list:
    """Extract code blocks from markdown text."""
    if not text:
        return []
    blocks = []
    parts = text.split("```")
    for i in range(1, len(parts), 2):
        code = parts[i]
        # Remove language identifier on first line
        lines = code.split("\n", 1)
        if len(lines) > 1 and not lines[0].strip().startswith("{"):
            code = lines[1]
        blocks.append(code.strip())
    return blocks



# =============================================================================
# COMPETENCY MATRICES ENDPOINTS
# =============================================================================


@router.get("/competency-matrices")
async def get_competency_matrices_overview():
    """Get overview of the competency matrix system."""
    from routes.game_parallel_society import get_all_shadow_agents
    from routes.game_ghost_society import get_all_ghost_agents

    # Sample a few agents for stats
    shadows = get_all_shadow_agents()[:50]
    sample_stats = get_competency_summary_stats(shadows)

    return {
        "system": "Competency Matrices Engine",
        "version": "1.0.0",
        "coverage": "All 25,994 agents",
        "dimensions": len(COMPETENCY_DIMENSIONS),
        "mastery_levels": MASTERY_LEVELS,
        "industry_standards": INDUSTRY_STANDARDS,
        "competency_dimensions": [{
            "id": d["id"], "name": d["name"], "weight": d["weight"],
            "description": d["description"], "benchmarks": d["benchmarks"],
        } for d in COMPETENCY_DIMENSIONS],
        "sample_stats": sample_stats,
        "philosophy": "Competency is not a destination — it is a velocity vector",
    }


@router.get("/competency-matrices/{agent_id}")
async def get_agent_competency(agent_id: str):
    """Get the competency matrix for a specific agent."""
    shadow = get_shadow_for_agent(agent_id)
    if shadow:
        return get_competency_matrix(shadow)

    ghost = get_ghost_for_agent(agent_id)
    if ghost:
        return get_competency_matrix(ghost)

    # Try as angel/seraphim/cherubim
    all_angels = get_all_angel_agents()
    angel = next((a for a in all_angels if a["id"] == agent_id), None)
    if angel:
        return get_competency_matrix(angel)

    all_seraphim = get_all_seraphim_agents()
    seraph = next((s for s in all_seraphim if s["id"] == agent_id), None)
    if seraph:
        return get_competency_matrix(seraph)

    all_cherubim = get_all_cherubim_agents()
    cherub = next((c for c in all_cherubim if c["id"] == agent_id), None)
    if cherub:
        return get_competency_matrix(cherub)

    # Fallback: create a generic agent dict
    return get_competency_matrix({"id": agent_id, "name": agent_id, "role": "Agent", "category": "general"})


# =============================================================================
# KNOWLEDGE ENGINE ENDPOINTS
# =============================================================================


@router.get("/knowledge-engine")
async def get_knowledge_engine_overview():
    """Get overview of the Extraordinary Knowledge Engine."""
    stats = get_knowledge_summary_stats()
    return {
        "system": "Extraordinary Knowledge Engine",
        "version": "1.0.0",
        "coverage": "All 25,994 agents",
        **stats,
    }


@router.get("/knowledge-engine/{agent_id}")
async def get_agent_knowledge_profile(agent_id: str):
    """Get the extraordinary knowledge profile for a specific agent."""
    shadow = get_shadow_for_agent(agent_id)
    if shadow:
        return get_agent_knowledge(shadow)

    ghost = get_ghost_for_agent(agent_id)
    if ghost:
        return get_agent_knowledge(ghost)

    all_angels = get_all_angel_agents()
    angel = next((a for a in all_angels if a["id"] == agent_id), None)
    if angel:
        return get_agent_knowledge(angel)

    all_seraphim = get_all_seraphim_agents()
    seraph = next((s for s in all_seraphim if s["id"] == agent_id), None)
    if seraph:
        return get_agent_knowledge(seraph)

    all_cherubim = get_all_cherubim_agents()
    cherub = next((c for c in all_cherubim if c["id"] == agent_id), None)
    if cherub:
        return get_agent_knowledge(cherub)

    return get_agent_knowledge({"id": agent_id, "name": agent_id, "role": "Agent", "category": "general"})



# =============================================================================
# SYNERGY ENGINE — Cross-Agent Intelligence & Vault Integration
# =============================================================================


@router.get("/synergy")
async def get_synergy_overview():
    """Get the full synergy overview — cross-agent intelligence, vault health, Jeeves integration."""
    stats = await get_synergy_stats()
    enriched = await get_enriched_vault_stats()
    wisdom = await jeeves_get_wisdom(limit=5)

    return {
        "system": "Synergy Engine",
        "version": "1.0.0",
        "purpose": "Cross-agent intelligence ensuring all 25,994 agents, vaults, and Jeeves work in harmony",
        "philosophy": "A symphony is not 100 instruments playing separately — it is 100 instruments playing AS ONE",
        "synergy_stats": stats,
        "vault_enriched": enriched,
        "jeeves_wisdom_preview": {
            "total_insights": wisdom["total_wisdom_entries"],
            "status": wisdom["jeeves_status"],
            "recent": wisdom["recent_insights"][:3],
        },
        "layers_tracked": ["shadow", "ghost", "angel", "seraphim", "cherubim"],
        "integration_points": {
            "agent_to_vault": "Every review logged with layer-specific metadata",
            "vault_to_jeeves": "Jeeves learning loop consumes unprocessed vault entries",
            "jeeves_to_agents": "Jeeves wisdom enriches future orchestration decisions",
            "cross_agent": "Synergy log tracks all inter-agent interactions",
        },
    }


@router.get("/synergy/stats")
async def synergy_stats_endpoint():
    """Get synergy statistics — cross-agent interaction metrics."""
    return await get_synergy_stats()


@router.get("/synergy/vault-enriched")
async def enriched_vault_endpoint():
    """Get enriched vault statistics with layer analytics and synergy scoring."""
    return await get_enriched_vault_stats()


@router.post("/synergy/jeeves-learn")
async def jeeves_learn_endpoint(project_id: str = None, limit: int = 100):
    """Trigger Jeeves learning loop — absorb unprocessed vault entries into wisdom."""
    result = await jeeves_learn_from_vault(project_id=project_id, limit=limit)
    return result


@router.get("/synergy/jeeves-wisdom")
async def jeeves_wisdom_endpoint(project_id: str = None, limit: int = 50):
    """Get Jeeves accumulated wisdom — synthesized from all vault data."""
    return await jeeves_get_wisdom(project_id=project_id, limit=limit)
