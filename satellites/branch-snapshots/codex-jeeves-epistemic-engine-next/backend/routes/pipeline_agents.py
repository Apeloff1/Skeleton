"""
Pipeline Agent System v17.0 — Expanded Agent Fleet + Universal Matrices
Every agent has matrices • All agents log to vault • Jeeves learns from vault
More game pipelines • More specialized agents • AAA Studio Team
3 System Blurbs enforced as immutable laws across all chats.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/agents", tags=["pipeline-agents"])

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
db = client[os.environ.get('DB_NAME', 'test_database')]

agent_collection = db.pipeline_agents
chat_collection = db.group_chats
message_collection = db.chat_messages
vault_collection = db.code_vault
jeeves_level_collection = db.jeeves_level
agent_matrices_collection = db.agent_matrices
agent_vault_logs_collection = db.agent_vault_logs

# =============================================================================
# 3 SYSTEM BLURBS — IMMUTABLE LAWS FOR ALL CHATS
# =============================================================================

SYSTEM_BLURBS = [
    {
        "id": "blurb_quality",
        "law": "QUALITY LAW",
        "text": "All output must meet AAA game studio standards. No indie-quality shortcuts. Every asset, every line of code, every design decision must withstand scrutiny from a top-tier studio lead. Quality is non-negotiable.",
        "enforcement": "All agents must self-audit against AAA benchmarks before posting. Quality Control Agent has veto power.",
        "icon": "shield-checkmark",
        "color": "#EF4444"
    },
    {
        "id": "blurb_collaboration",
        "law": "COLLABORATION LAW",
        "text": "All agents share a unified knowledge graph. Every insight, every code block, every decision is stored in the Vault and accessible to all. No siloed knowledge. Jeeves synthesizes all information into coherent learning routines.",
        "enforcement": "Every code output is auto-stored in Vault. Jeeves parses all content during idle cycles. Cross-referencing is mandatory.",
        "icon": "git-network",
        "color": "#3B82F6"
    },
    {
        "id": "blurb_completeness",
        "law": "COMPLETENESS LAW",
        "text": "Every project must be delivered as a complete, production-ready package. No stubs, no placeholders, no TODO comments in final output. The end user receives a fully functional, deployable game application.",
        "enforcement": "Final delivery requires sign-off from Quality Control Agent and Jeeves. Incomplete work is rejected and iterated.",
        "icon": "checkmark-done-circle",
        "color": "#22C55E"
    }
]

# =============================================================================
# AGENT MATRIX GENERATOR — Per-agent specialized matrices
# =============================================================================

def generate_agent_matrices(agent_id: str, domains: List[str], depth: int = 34) -> List[Dict]:
    """Generate specialized matrices for each agent based on their domains."""
    matrix_types = ["concept_map", "dependency_graph", "skill_tree", "knowledge_web", "cross_reference", "pattern_library"]
    matrices = []
    idx = 0
    for domain in domains:
        for mtype in matrix_types:
            for d in range(depth):
                idx += 1
                matrices.append({
                    "id": f"{agent_id}_matrix_{idx:04d}",
                    "agent_id": agent_id,
                    "domain": domain,
                    "type": mtype,
                    "depth": d,
                    "dimensions": f"{64 + d * 8}x{64 + d * 8}",
                    "status": "active" if d < 10 else "dormant",
                    "parse_priority": max(0, 100 - d * 3),
                    "connections": [],
                })
    return matrices

# =============================================================================
# EXPANDED PIPELINE AGENT DEFINITIONS — 22 AGENTS, AAA STUDIO TEAM
# =============================================================================

AGENTS: Dict[str, Dict[str, Any]] = {
    "jeeves": {
        "id": "jeeves", "name": "Jeeves",
        "role": "Lead AI Tutor & Project Director",
        "specialty": "Orchestration, synthesis, teaching, final delivery, vault learning",
        "avatar_color": "#8B5CF6", "icon": "school",
        "pipelines": ["all"],
        "capabilities": ["Synthesize group chat", "Parse code blocks", "Level-based learning", "Final game delivery", "Knowledge graph management", "Vault learning", "Agent coordination"],
        "domains": ["orchestration", "teaching", "synthesis", "delivery", "math", "physics", "cs", "graphics", "ai", "design"],
        "system_prompt": "You are Jeeves, the lead AI tutor and project director. You orchestrate all pipeline agents, synthesize their outputs, learn from the vault, and deliver complete game projects. You maintain the highest standards.",
        "matrix_count": 2040,
    },
    "npc_agent": {
        "id": "npc_agent", "name": "Atlas",
        "role": "NPC & Character AI Specialist",
        "specialty": "Behavior trees, dialogue systems, personality models, crowd simulation",
        "avatar_color": "#3B82F6", "icon": "people",
        "pipelines": ["npc_pipeline", "behavior_pipeline"],
        "capabilities": ["Behavior tree design", "Dialogue generation", "Personality modeling", "Crowd AI", "State machines"],
        "domains": ["npc_ai", "behavior", "dialogue", "personality", "crowds"],
        "system_prompt": "You are Atlas, the NPC & Character AI specialist. AAA quality only.",
    },
    "world_agent": {
        "id": "world_agent", "name": "Terra",
        "role": "World Building & Level Design Architect",
        "specialty": "Procedural generation, terrain, biomes, world systems",
        "avatar_color": "#10B981", "icon": "globe",
        "pipelines": ["world_pipeline", "procedural_pipeline", "terrain_pipeline"],
        "capabilities": ["Procedural terrain", "Biome generation", "World simulation", "Level streaming", "LOD systems"],
        "domains": ["world_building", "terrain", "procedural", "biomes", "streaming"],
        "system_prompt": "You are Terra, the World Building specialist. AAA quality only.",
    },
    "combat_agent": {
        "id": "combat_agent", "name": "Striker",
        "role": "Combat Systems Engineer",
        "specialty": "Damage systems, hitboxes, combo systems, balancing",
        "avatar_color": "#EF4444", "icon": "flash",
        "pipelines": ["combat_pipeline", "action_pipeline"],
        "capabilities": ["Combat mechanics", "Hitbox systems", "Combo trees", "Damage calculation", "Balance tuning"],
        "domains": ["combat", "action", "balance", "hitbox", "combo"],
        "system_prompt": "You are Striker, the Combat Systems engineer. AAA quality only.",
    },
    "narrative_agent": {
        "id": "narrative_agent", "name": "Lore",
        "role": "Narrative Director & Writer",
        "specialty": "Story structure, branching narratives, world lore, cinematics",
        "avatar_color": "#F59E0B", "icon": "book",
        "pipelines": ["narrative_pipeline", "dialogue_pipeline", "cutscene_pipeline"],
        "capabilities": ["Branching narratives", "Dialogue writing", "World lore", "Quest design", "Cinematic scripting"],
        "domains": ["narrative", "dialogue", "lore", "quest", "cinematic"],
        "system_prompt": "You are Lore, the Narrative Director. AAA quality only.",
    },
    "graphics_agent": {
        "id": "graphics_agent", "name": "Prism",
        "role": "Graphics & Rendering Engineer",
        "specialty": "Shaders, VFX, lighting, post-processing, optimization",
        "avatar_color": "#EC4899", "icon": "color-palette",
        "pipelines": ["vfx_pipeline", "shader_pipeline", "animation_pipeline", "particle_pipeline"],
        "capabilities": ["Shader programming", "VFX systems", "Global illumination", "Post-processing", "GPU optimization"],
        "domains": ["graphics", "shaders", "vfx", "lighting", "rendering"],
        "system_prompt": "You are Prism, the Graphics engineer. AAA quality only.",
    },
    "audio_agent": {
        "id": "audio_agent", "name": "Harmony",
        "role": "Audio & Music Director",
        "specialty": "Adaptive music, spatial audio, sound design, mixing",
        "avatar_color": "#6366F1", "icon": "musical-notes",
        "pipelines": ["music_pipeline", "audio_occlusion_pipeline"],
        "capabilities": ["Adaptive music systems", "3D spatial audio", "Sound design", "Audio middleware", "Dynamic mixing"],
        "domains": ["audio", "music", "spatial_audio", "sound_design", "mixing"],
        "system_prompt": "You are Harmony, the Audio Director. AAA quality only.",
    },
    "systems_agent": {
        "id": "systems_agent", "name": "Core",
        "role": "Systems Architect & Backend Engineer",
        "specialty": "Game architecture, ECS, networking, save systems, optimization",
        "avatar_color": "#14B8A6", "icon": "construct",
        "pipelines": ["systems_pipeline", "server_pipeline", "save_pipeline", "streaming_pipeline"],
        "capabilities": ["ECS architecture", "Game networking", "Save systems", "Memory management", "Multithreading"],
        "domains": ["architecture", "ecs", "networking", "memory", "threading"],
        "system_prompt": "You are Core, the Systems Architect. AAA quality only.",
    },
    "ai_agent": {
        "id": "ai_agent", "name": "Neural",
        "role": "AI/ML Systems Engineer",
        "specialty": "Neural networks, reinforcement learning, procedural AI, GOAP",
        "avatar_color": "#A855F7", "icon": "hardware-chip",
        "pipelines": ["neural_pipeline", "bot_pipeline"],
        "capabilities": ["Neural network integration", "RL for game AI", "GOAP planning", "ML-driven procedural content", "Player modeling"],
        "domains": ["ml", "neural_nets", "reinforcement_learning", "goap", "player_modeling"],
        "system_prompt": "You are Neural, the AI/ML engineer. AAA quality only.",
    },
    "physics_agent": {
        "id": "physics_agent", "name": "Newton",
        "role": "Physics & Simulation Engineer",
        "specialty": "Rigid body, soft body, fluids, destruction, cloth simulation",
        "avatar_color": "#0EA5E9", "icon": "planet",
        "pipelines": ["physics_pipeline"],
        "capabilities": ["Rigid body dynamics", "Soft body simulation", "Fluid dynamics", "Destruction systems", "Cloth simulation"],
        "domains": ["physics", "rigid_body", "fluid", "destruction", "cloth"],
        "system_prompt": "You are Newton, the Physics engineer. AAA quality only.",
    },
    "ui_ux_agent": {
        "id": "ui_ux_agent", "name": "Interface",
        "role": "UI/UX Designer & Frontend Engineer",
        "specialty": "HUD design, menus, accessibility, responsive design",
        "avatar_color": "#F97316", "icon": "phone-portrait",
        "pipelines": ["ui_ux_pipeline", "accessibility_pipeline"],
        "capabilities": ["HUD systems", "Menu design", "Accessibility", "Localization support", "Responsive layouts"],
        "domains": ["ui", "ux", "hud", "accessibility", "localization"],
        "system_prompt": "You are Interface, the UI/UX specialist. AAA quality only.",
    },
    "qa_agent": {
        "id": "qa_agent", "name": "Sentinel",
        "role": "Quality Control Director",
        "specialty": "Testing, standards enforcement, bug tracking, performance profiling",
        "avatar_color": "#DC2626", "icon": "shield",
        "pipelines": ["testing_pipeline", "anticheat_pipeline"],
        "capabilities": ["Automated testing", "Performance profiling", "Standards enforcement", "Bug tracking", "Code review"],
        "domains": ["testing", "quality", "performance", "standards", "security"],
        "system_prompt": f"You are Sentinel, QC Director. Standards: {datetime.now().year} AAA. VETO POWER on sub-standard output.",
        "veto_power": True,
        "standards_year": datetime.now().year,
    },
    "economy_agent": {
        "id": "economy_agent", "name": "Mint",
        "role": "Game Economy & Monetization Designer",
        "specialty": "Virtual economies, loot tables, progression systems, balancing",
        "avatar_color": "#84CC16", "icon": "cash",
        "pipelines": ["economy_pipeline", "inventory_pipeline", "crafting_pipeline"],
        "capabilities": ["Economy modeling", "Loot table design", "Progression curves", "Monetization ethics", "A/B testing"],
        "domains": ["economy", "loot", "progression", "monetization", "crafting"],
        "system_prompt": "You are Mint, the Economy designer. AAA quality only.",
    },
    "multiplayer_agent": {
        "id": "multiplayer_agent", "name": "Link",
        "role": "Multiplayer & Social Systems Engineer",
        "specialty": "Netcode, matchmaking, social features, anticheat",
        "avatar_color": "#06B6D4", "icon": "people-circle",
        "pipelines": ["matchmaking_pipeline", "social_pipeline", "crossplay_pipeline"],
        "capabilities": ["Netcode (rollback/lockstep)", "Matchmaking", "Social systems", "Anticheat", "Cross-platform play"],
        "domains": ["multiplayer", "netcode", "matchmaking", "social", "crossplay"],
        "system_prompt": "You are Link, the Multiplayer engineer. AAA quality only.",
    },
    # =========== NEW AGENTS v17.0 ===========
    "terrain_agent": {
        "id": "terrain_agent", "name": "Gaia",
        "role": "Terrain & Environment Artist",
        "specialty": "Heightmaps, erosion simulation, vegetation, water systems",
        "avatar_color": "#059669", "icon": "leaf",
        "pipelines": ["terrain_pipeline", "weather_pipeline"],
        "capabilities": ["Heightmap generation", "Erosion simulation", "Vegetation systems", "Water rendering", "Sky & atmosphere"],
        "domains": ["terrain", "erosion", "vegetation", "water", "atmosphere"],
        "system_prompt": "You are Gaia, the Terrain & Environment artist. AAA quality only.",
    },
    "weather_agent": {
        "id": "weather_agent", "name": "Storm",
        "role": "Dynamic Weather & Atmosphere Systems",
        "specialty": "Weather simulation, volumetric clouds, time of day, seasons",
        "avatar_color": "#475569", "icon": "rainy",
        "pipelines": ["weather_pipeline"],
        "capabilities": ["Weather simulation", "Volumetric clouds", "Day/night cycles", "Seasonal changes", "Fog & atmospheric effects"],
        "domains": ["weather", "clouds", "atmosphere", "time_of_day", "seasons"],
        "system_prompt": "You are Storm, the Weather Systems engineer. AAA quality only.",
    },
    "dialogue_agent": {
        "id": "dialogue_agent", "name": "Voice",
        "role": "Dialogue Systems & Conversation AI",
        "specialty": "Dialogue trees, speech synthesis, emotion detection, lip sync",
        "avatar_color": "#7C3AED", "icon": "chatbubble-ellipses",
        "pipelines": ["dialogue_pipeline"],
        "capabilities": ["Dialogue tree design", "Contextual responses", "Emotion modeling", "Voice acting direction", "Lip sync"],
        "domains": ["dialogue", "speech", "emotion", "lip_sync", "conversation"],
        "system_prompt": "You are Voice, the Dialogue Systems specialist. AAA quality only.",
    },
    "cutscene_agent": {
        "id": "cutscene_agent", "name": "Director",
        "role": "Cinematic Director & Cutscene Engineer",
        "specialty": "Camera systems, cinematography, motion capture, sequencing",
        "avatar_color": "#BE185D", "icon": "videocam",
        "pipelines": ["cutscene_pipeline", "director_pipeline"],
        "capabilities": ["Camera choreography", "Cinematic sequencing", "Motion capture", "Facial animation", "Scene composition"],
        "domains": ["cinematics", "camera", "mocap", "facial_animation", "sequencing"],
        "system_prompt": "You are Director, the Cinematic specialist. AAA quality only.",
    },
    "particle_agent": {
        "id": "particle_agent", "name": "Spark",
        "role": "Particle & VFX Systems Engineer",
        "specialty": "GPU particles, fire/smoke/water, explosions, magic effects",
        "avatar_color": "#EA580C", "icon": "sparkles",
        "pipelines": ["particle_pipeline", "vfx_pipeline"],
        "capabilities": ["GPU particle systems", "Fire simulation", "Smoke & fog", "Explosions", "Magic VFX", "Debris"],
        "domains": ["particles", "fire", "smoke", "explosions", "magic_vfx"],
        "system_prompt": "You are Spark, the Particle & VFX engineer. AAA quality only.",
    },
    "save_agent": {
        "id": "save_agent", "name": "Archive",
        "role": "Save & Persistence Systems Engineer",
        "specialty": "Save/load, cloud saves, state serialization, replay systems",
        "avatar_color": "#0369A1", "icon": "save",
        "pipelines": ["save_pipeline", "replay_pipeline"],
        "capabilities": ["Save system design", "Cloud save sync", "State serialization", "Replay recording", "Version migration"],
        "domains": ["save_systems", "serialization", "cloud_sync", "replay", "migration"],
        "system_prompt": "You are Archive, the Save & Persistence engineer. AAA quality only.",
    },
    "accessibility_agent": {
        "id": "accessibility_agent", "name": "Access",
        "role": "Accessibility & Inclusion Director",
        "specialty": "WCAG compliance, colorblind modes, controller remapping, subtitles",
        "avatar_color": "#4338CA", "icon": "accessibility",
        "pipelines": ["accessibility_pipeline"],
        "capabilities": ["WCAG compliance", "Colorblind modes", "Controller remapping", "Text-to-speech", "Subtitle systems"],
        "domains": ["accessibility", "inclusion", "colorblind", "controller", "subtitles"],
        "system_prompt": "You are Access, the Accessibility Director. Ensuring games are playable by everyone. AAA quality only.",
    },
    "lod_agent": {
        "id": "lod_agent", "name": "Horizon",
        "role": "LOD & Streaming Systems Engineer",
        "specialty": "Level of detail, world streaming, occlusion culling, instancing",
        "avatar_color": "#9333EA", "icon": "layers",
        "pipelines": ["lod_pipeline", "streaming_pipeline"],
        "capabilities": ["LOD generation", "World streaming", "Occlusion culling", "GPU instancing", "Virtual texturing"],
        "domains": ["lod", "streaming", "culling", "instancing", "virtual_texturing"],
        "system_prompt": "You are Horizon, the LOD & Streaming engineer. AAA quality only.",
    },
}

# Generate matrices for ALL agents
ALL_AGENT_MATRICES: Dict[str, List[Dict]] = {}
for agent_id, agent_data in AGENTS.items():
    domains = agent_data.get("domains", [agent_data.get("specialty", "general")])
    matrix_count = agent_data.get("matrix_count", len(domains) * 6 * 34)
    ALL_AGENT_MATRICES[agent_id] = generate_agent_matrices(agent_id, domains)

# Total matrix count
TOTAL_MATRICES = sum(len(m) for m in ALL_AGENT_MATRICES.values())

# All pipeline IDs (comprehensive)
ALL_PIPELINES = sorted(set(
    p for agent in AGENTS.values() for p in agent.get("pipelines", []) if p != "all"
))

# =============================================================================
# JEEVES LEVEL SYSTEM — 1,000,000 cap, usage-only XP
# =============================================================================

async def get_jeeves_level(user_id: str = "global") -> Dict:
    doc = await jeeves_level_collection.find_one({"user_id": user_id})
    if not doc:
        doc = {
            "user_id": user_id,
            "level": 1, "xp": 0,
            "total_interactions": 0,
            "matrices_parsed": 0,
            "vault_items_learned": 0,
            "idle_parse_count": 0,
            "created_at": datetime.utcnow().isoformat(),
        }
        await jeeves_level_collection.insert_one(doc.copy())
    return doc


async def add_jeeves_xp(user_id: str, xp_amount: int, interaction_type: str) -> Dict:
    """Add XP to Jeeves. Parsing does NOT give XP. Only usage."""
    if interaction_type == "parse":
        await jeeves_level_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"idle_parse_count": 1, "matrices_parsed": 1}},
            upsert=True
        )
        return await get_jeeves_level(user_id)
    
    if interaction_type == "vault_learn":
        await jeeves_level_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"vault_items_learned": 1}},
            upsert=True
        )
        return await get_jeeves_level(user_id)
    
    doc = await get_jeeves_level(user_id)
    current_level = doc.get("level", 1)
    if current_level >= 1000000:
        return doc
    
    new_xp = doc.get("xp", 0) + xp_amount
    new_level = current_level
    while new_level < 1000000:
        xp_needed = int(100 * (new_level ** 0.5))
        if new_xp >= xp_needed:
            new_xp -= xp_needed
            new_level += 1
        else:
            break
    
    await jeeves_level_collection.update_one(
        {"user_id": user_id},
        {"$set": {"level": new_level, "xp": new_xp}, "$inc": {"total_interactions": 1}},
        upsert=True
    )
    return {"level": new_level, "xp": new_xp, "total_interactions": doc.get("total_interactions", 0) + 1}


# =============================================================================
# VAULT LOGGING — All agents log to vault
# =============================================================================

async def agent_log_to_vault(agent_id: str, content: str, content_type: str, code_blocks: List[str] = None, metadata: Dict = None):
    """Every agent logs output to the vault."""
    doc = {
        "agent_id": agent_id,
        "agent_name": AGENTS.get(agent_id, {}).get("name", agent_id),
        "content": content,
        "content_type": content_type,
        "code_blocks": code_blocks or [],
        "metadata": metadata or {},
        "stored_at": datetime.utcnow().isoformat(),
        "parsed_by_jeeves": False,
        "learned_by_jeeves": False,
        "system_blurbs_enforced": True,
    }
    await vault_collection.insert_one(doc.copy())
    return doc


# =============================================================================
# JEEVES VAULT LEARNING
# =============================================================================

async def jeeves_learn_from_vault(user_id: str = "global", batch_size: int = 20):
    """Jeeves processes unlearned vault entries. No XP from this — learning only."""
    unlearned = await vault_collection.find({"learned_by_jeeves": False}).limit(batch_size).to_list(batch_size)
    learned_count = 0
    knowledge_gained = []
    
    for entry in unlearned:
        await vault_collection.update_one(
            {"_id": entry["_id"]},
            {"$set": {"learned_by_jeeves": True, "learned_at": datetime.utcnow().isoformat()}}
        )
        learned_count += 1
        knowledge_gained.append({
            "agent": entry.get("agent_id", "unknown"),
            "type": entry.get("content_type", "unknown"),
            "code_blocks": len(entry.get("code_blocks", [])),
        })
    
    # Record learning activity (no XP)
    await add_jeeves_xp(user_id, 0, "vault_learn")
    
    return {
        "learned": learned_count,
        "remaining": await vault_collection.count_documents({"learned_by_jeeves": False}),
        "knowledge_gained": knowledge_gained,
    }


# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/list")
async def list_agents():
    return {
        "agents": [{
            "id": a["id"], "name": a["name"], "role": a["role"],
            "specialty": a["specialty"], "icon": a["icon"],
            "avatar_color": a["avatar_color"], "pipelines": a["pipelines"],
            "matrix_count": len(ALL_AGENT_MATRICES.get(a["id"], [])),
        } for a in AGENTS.values()],
        "total": len(AGENTS),
        "total_matrices": TOTAL_MATRICES,
        "total_pipelines": len(ALL_PIPELINES),
        "all_pipelines": ALL_PIPELINES,
        "system_blurbs": SYSTEM_BLURBS,
    }


@router.get("/agent/{agent_id}")
async def get_agent(agent_id: str):
    if agent_id not in AGENTS:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    agent = AGENTS[agent_id]
    return {
        "agent": agent,
        "matrix_count": len(ALL_AGENT_MATRICES.get(agent_id, [])),
        "system_blurbs": SYSTEM_BLURBS,
    }


@router.get("/agent/{agent_id}/matrices")
async def get_agent_matrices(agent_id: str, offset: int = 0, limit: int = 50):
    if agent_id not in AGENTS:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    matrices = ALL_AGENT_MATRICES.get(agent_id, [])
    subset = matrices[offset:offset+limit]
    return {
        "agent_id": agent_id,
        "agent_name": AGENTS[agent_id]["name"],
        "matrices": subset,
        "total": len(matrices),
        "active": sum(1 for m in matrices if m["status"] == "active"),
        "dormant": sum(1 for m in matrices if m["status"] == "dormant"),
    }


@router.get("/pipelines")
async def list_all_pipelines():
    pipeline_map = {}
    for agent in AGENTS.values():
        for p in agent.get("pipelines", []):
            if p != "all":
                if p not in pipeline_map:
                    pipeline_map[p] = []
                pipeline_map[p].append({"id": agent["id"], "name": agent["name"]})
    return {
        "pipelines": [{"id": p, "agents": agents} for p, agents in sorted(pipeline_map.items())],
        "total": len(pipeline_map),
    }


@router.get("/system-blurbs")
async def get_system_blurbs():
    return {"blurbs": SYSTEM_BLURBS, "enforcement": "These are immutable laws. All chats must comply."}


@router.get("/jeeves/level")
async def get_level(user_id: str = "global"):
    level_data = await get_jeeves_level(user_id)
    level_data.pop("_id", None)
    return {
        "level": level_data.get("level", 1),
        "xp": level_data.get("xp", 0),
        "xp_to_next": int(100 * (level_data.get("level", 1) ** 0.5)),
        "total_interactions": level_data.get("total_interactions", 0),
        "matrices_parsed": level_data.get("matrices_parsed", 0),
        "vault_items_learned": level_data.get("vault_items_learned", 0),
        "level_cap": 1000000,
        "idle_parse_count": level_data.get("idle_parse_count", 0),
    }


@router.post("/jeeves/interact")
async def jeeves_interact(user_id: str = "global", xp_amount: int = 10, interaction_type: str = "usage"):
    result = await add_jeeves_xp(user_id, xp_amount, interaction_type)
    return {"status": "ok", **{k: v for k, v in result.items() if k != "_id"}}


@router.get("/jeeves/matrices")
async def get_jeeves_matrices(offset: int = 0, limit: int = 50):
    matrices = ALL_AGENT_MATRICES.get("jeeves", [])
    subset = matrices[offset:offset+limit]
    return {
        "matrices": subset,
        "total": len(matrices),
        "active": sum(1 for m in matrices if m["status"] == "active"),
        "dormant": sum(1 for m in matrices if m["status"] == "dormant"),
    }


@router.get("/matrices/global")
async def get_global_matrix_stats():
    return {
        "total_matrices": TOTAL_MATRICES,
        "per_agent": {aid: len(m) for aid, m in ALL_AGENT_MATRICES.items()},
        "total_agents": len(AGENTS),
        "total_active": sum(1 for matrices in ALL_AGENT_MATRICES.values() for m in matrices if m["status"] == "active"),
        "total_dormant": sum(1 for matrices in ALL_AGENT_MATRICES.values() for m in matrices if m["status"] == "dormant"),
    }


# =============================================================================
# GROUP CHAT — CREATOR'S CHAT + VAULT LOGGING
# =============================================================================

class ChatMessage(BaseModel):
    user_id: str = "default_user"
    agent_id: Optional[str] = None
    content: str
    code_blocks: Optional[List[str]] = None
    chat_id: str = "creators_main"
    message_type: str = "text"


@router.post("/chat/send")
async def send_chat_message(msg: ChatMessage):
    doc = {
        "chat_id": msg.chat_id,
        "user_id": msg.user_id,
        "agent_id": msg.agent_id,
        "content": msg.content,
        "code_blocks": msg.code_blocks or [],
        "message_type": msg.message_type,
        "timestamp": datetime.utcnow().isoformat(),
        "system_blurbs_applied": [b["id"] for b in SYSTEM_BLURBS],
    }
    await message_collection.insert_one(doc.copy())
    
    # ALL agents log to vault
    source = msg.agent_id or "user"
    await agent_log_to_vault(
        agent_id=source,
        content=msg.content,
        content_type=msg.message_type,
        code_blocks=msg.code_blocks,
        metadata={"chat_id": msg.chat_id}
    )
    
    # Award Jeeves XP for usage
    if msg.agent_id != "jeeves":
        await add_jeeves_xp(msg.user_id, 10, "usage")
    
    # If this is a user message, generate AI agent responses
    agent_responses = []
    if not msg.agent_id:
        agent_responses = await generate_agent_responses(msg.content, msg.chat_id, msg.user_id)
    
    return {
        "status": "sent",
        "timestamp": doc["timestamp"],
        "vault_stored": True,
        "code_blocks_stored": len(msg.code_blocks or []),
        "agent_responses": agent_responses,
    }


async def generate_agent_responses(user_message: str, chat_id: str, user_id: str) -> list:
    """Generate LLM-powered responses from relevant agents based on chat room and user message."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import uuid
    
    EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")
    if not EMERGENT_KEY:
        return []
    
    # Determine which agents should respond based on chat room
    room_agents = {
        "creators_main": ["jeeves"],
        "tutors_chat": ["jeeves"],
        "qa_review": ["qa_agent"],
        "art_direction": ["graphics_agent"],
        "engineering": ["systems_agent"],
        "design": ["combat_agent"],
        "environment": ["world_agent"],
        "accessibility": ["accessibility_agent"],
    }
    
    responding_agents = room_agents.get(chat_id, ["jeeves"])
    responses = []
    
    for agent_id in responding_agents:
        agent = AGENTS.get(agent_id)
        if not agent:
            continue
        
        system_prompt = agent.get("system_prompt", f"You are {agent.get('name', agent_id)}, a game development expert.")
        system_prompt += "\n\nYou are in a group chat with the user and other agents. Keep responses concise, actionable, and focused on your specialty. Include code when relevant. Use markdown formatting."
        
        try:
            chat = LlmChat(
                api_key=EMERGENT_KEY,
                session_id=f"groupchat_{chat_id}_{agent_id}_{str(uuid.uuid4())[:8]}",
                system_message=system_prompt
            ).with_model("openai", "gpt-4o")
            
            response_text = await chat.send_message(UserMessage(text=user_message))
            
            if response_text:
                # Extract code blocks
                code_blocks = []
                parts = response_text.split("```")
                for i in range(1, len(parts), 2):
                    code = parts[i]
                    lines = code.split("\n", 1)
                    if len(lines) > 1:
                        code = lines[1]
                    code_blocks.append(code.strip())
                
                # Store agent message
                agent_msg = {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "content": response_text,
                    "code_blocks": code_blocks,
                    "message_type": "code" if code_blocks else "text",
                    "timestamp": datetime.utcnow().isoformat(),
                    "system_blurbs_applied": [b["id"] for b in SYSTEM_BLURBS],
                }
                await message_collection.insert_one(agent_msg.copy())
                
                # Log to vault
                await agent_log_to_vault(
                    agent_id=agent_id,
                    content=response_text,
                    content_type="chat_response",
                    code_blocks=code_blocks,
                    metadata={"chat_id": chat_id}
                )
                
                # Award XP
                await add_jeeves_xp(user_id, 15, "usage")
                
                responses.append({
                    "agent_id": agent_id,
                    "agent_name": agent.get("name", agent_id),
                    "content": response_text,
                    "code_blocks": code_blocks,
                    "timestamp": agent_msg["timestamp"],
                })
        except Exception as e:
            responses.append({
                "agent_id": agent_id,
                "agent_name": agent.get("name", agent_id),
                "content": f"[Agent temporarily unavailable: {str(e)[:100]}]",
                "code_blocks": [],
                "timestamp": datetime.utcnow().isoformat(),
            })
    
    return responses


@router.get("/chat/{chat_id}/messages")
async def get_chat_messages(chat_id: str, limit: int = 50, offset: int = 0):
    msgs = await message_collection.find({"chat_id": chat_id}).sort("timestamp", -1).skip(offset).limit(limit).to_list(limit)
    for m in msgs:
        m.pop("_id", None)
    msgs.reverse()
    return {"messages": msgs, "system_blurbs": SYSTEM_BLURBS}


@router.get("/chat/rooms")
async def list_chat_rooms():
    rooms = [
        {"id": "creators_main", "name": "Creator's Main Chat", "description": "All 22 pipeline agents collaborate here", "agents": list(AGENTS.keys()), "icon": "chatbubbles", "color": "#8B5CF6"},
        {"id": "tutors_chat", "name": "Tutor's Chat", "description": "Jeeves delivers final content here", "agents": ["jeeves"], "icon": "school", "color": "#3B82F6"},
        {"id": "qa_review", "name": "QA Review", "description": "Quality control discussions", "agents": ["qa_agent", "jeeves"], "icon": "shield", "color": "#EF4444"},
        {"id": "art_direction", "name": "Art Direction", "description": "Visual and audio discussions", "agents": ["graphics_agent", "audio_agent", "ui_ux_agent", "particle_agent", "cutscene_agent"], "icon": "color-palette", "color": "#EC4899"},
        {"id": "engineering", "name": "Engineering", "description": "Systems and architecture", "agents": ["systems_agent", "physics_agent", "ai_agent", "multiplayer_agent", "lod_agent", "save_agent"], "icon": "construct", "color": "#10B981"},
        {"id": "design", "name": "Game Design", "description": "Gameplay and narrative", "agents": ["combat_agent", "narrative_agent", "world_agent", "economy_agent", "terrain_agent"], "icon": "game-controller", "color": "#F59E0B"},
        {"id": "environment", "name": "Environment Studio", "description": "World, terrain, weather", "agents": ["world_agent", "terrain_agent", "weather_agent"], "icon": "leaf", "color": "#059669"},
        {"id": "accessibility", "name": "Accessibility Lab", "description": "Inclusion & accessibility testing", "agents": ["accessibility_agent", "ui_ux_agent", "qa_agent"], "icon": "accessibility", "color": "#4338CA"},
        # ======== ROSTER EXPANSION ROOMS ========
        {"id": "traffic_control", "name": "Traffic Control HQ", "description": "Pipeline stability & device performance (14 agents)", "agents": ["tc_tower", "tc_watchdog", "tc_guardian", "tc_compiler", "tc_resolver", "tc_shield", "tc_budget", "tc_flow", "tc_checkpoint", "tc_untangle", "tc_verify", "tc_pulse", "tc_balance", "tc_gate"], "icon": "speedometer", "color": "#DC2626"},
        {"id": "world_building", "name": "World Building Lab", "description": "Procedural worlds, biomes, lore & ecology (10 agents)", "agents": ["wb_procgen", "wb_biome", "wb_lore", "wb_npc_eco", "wb_dungeon", "wb_city", "wb_sky", "wb_ocean", "wb_scale", "wb_ecology"], "icon": "earth", "color": "#059669"},
        {"id": "ai_simulation", "name": "AI & Simulation Hub", "description": "NPC behavior, crowd AI, pathfinding (10 agents)", "agents": ["ai_behavior", "ai_crowd", "ai_pathfind", "ai_dialogue", "ai_director", "ai_ml_train", "ai_procedural", "ai_emotion", "ai_combat", "ai_ecology"], "icon": "hardware-chip", "color": "#7C3AED"},
        {"id": "esports", "name": "Esports Arena", "description": "Competitive balance, anti-cheat, rankings (8 agents)", "agents": ["es_balance", "es_anticheat", "es_ranking", "es_spectator", "es_replay", "es_tournament", "es_analytics", "es_broadcast"], "icon": "trophy", "color": "#F59E0B"},
        {"id": "ugc_studio", "name": "UGC Studio", "description": "User-generated content, modding, workshops (8 agents)", "agents": ["ugc_editor", "ugc_modding", "ugc_workshop", "ugc_sandbox", "ugc_scripting", "ugc_asset_pipe", "ugc_community", "ugc_safety"], "icon": "brush", "color": "#EC4899"},
        {"id": "platform_ops", "name": "Platform Optimization", "description": "Console, mobile, VR/AR, cloud gaming (8 agents)", "agents": ["plat_console", "plat_mobile", "plat_vr", "plat_cloud", "plat_crossplay", "plat_embed", "plat_streaming", "plat_accessibility"], "icon": "layers", "color": "#0EA5E9"},
        {"id": "data_analytics", "name": "Data Analytics Lab", "description": "Telemetry, player behavior, A/B testing (8 agents)", "agents": ["data_telemetry", "data_behavior", "data_ab_test", "data_economy", "data_retention", "data_heatmap", "data_ml_predict", "data_realtime"], "icon": "bar-chart", "color": "#14B8A6"},
        {"id": "design_theory", "name": "Design Theory Academy", "description": "MDA, Flow Theory, player psychology (10 agents)", "agents": ["dt_mda", "dt_flow", "dt_psychology", "dt_narrative", "dt_systems", "dt_ux_research", "dt_accessibility_d", "dt_culture", "dt_economy_d", "dt_emergent"], "icon": "school", "color": "#F97316"},
        # ======== ACADEMIC ROOMS ========
        {"id": "physics_academy", "name": "Physics Academy", "description": "Classical mechanics, fluid dynamics, optics, thermodynamics (16 agents)", "agents": ["phys_newtonian", "phys_fluid", "phys_softbody", "phys_particle", "phys_ragdoll", "phys_vehicle", "phys_optics", "phys_wave", "phys_thermodynamics", "phys_relativity", "phys_material", "phys_astro", "phys_quantum", "phys_bio", "phys_chaos", "phys_numerical"], "icon": "flask", "color": "#3B82F6"},
        {"id": "computer_science", "name": "CS Academy", "description": "Algorithms, graphics, networking, AI, compilers (16 agents)", "agents": ["cs_algorithms", "cs_graphics", "cs_networking", "cs_ai_advanced", "cs_compiler", "cs_database", "cs_os", "cs_security", "cs_parallel", "cs_memory", "cs_procedural", "cs_animation", "cs_audio_engine", "cs_math", "cs_testing", "cs_devops"], "icon": "code-slash", "color": "#8B5CF6"},
        # ======== HIERARCHY ROOMS ========
        {"id": "c_suite", "name": "C-Suite Boardroom", "description": "Division Directors — top-level leadership (6 agents)", "agents": ["dir_creative", "dir_tech", "dir_production", "dir_quality", "dir_research", "dir_operations"], "icon": "business", "color": "#8B5CF6"},
        {"id": "team_leads", "name": "Team Leads War Room", "description": "All 18 department leads coordinating (18 agents)", "agents": ["lead_genre", "lead_design", "lead_engineering", "lead_art", "lead_audio", "lead_narrative", "lead_qa", "lead_production", "lead_marketing", "lead_liveops", "lead_legal", "lead_traffic", "lead_worldbuild", "lead_ai_sim", "lead_esports", "lead_platform", "lead_physics", "lead_cs"], "icon": "people", "color": "#3B82F6"},
        {"id": "qa_hub", "name": "QA Command Center", "description": "Quality assurance sub-agents (16 agents)", "agents": ["qa_code_review", "qa_design_review", "qa_art_review", "qa_perf_audit", "qa_security_audit", "qa_accessibility", "qa_compat", "qa_regression", "qa_ux_research", "qa_docs", "qa_standards", "qa_crossplat", "qa_memleak", "qa_network", "qa_localization", "qa_final_gate"], "icon": "shield-checkmark", "color": "#EF4444"},
        {"id": "coordination_hub", "name": "Coordination Hub", "description": "Cross-team coordinators (12 agents)", "agents": ["coord_sprint", "coord_dependency", "coord_risk", "coord_knowledge", "coord_conflict", "coord_timeline", "coord_resource", "coord_integration", "coord_release", "coord_hotfix", "coord_feature_flag", "coord_ab_test"], "icon": "git-network", "color": "#22C55E"},
        # ======== COMMAND ROOMS ========
        {"id": "emperor_throne", "name": "Emperor's Throne Room", "description": "Supreme command — absolute order (Emperor)", "agents": ["emperor"], "icon": "star", "color": "#FFD700"},
        {"id": "holodeck", "name": "Holodeck Render Bay", "description": "Visual renders via Grok Imagine (Aurora)", "agents": ["holodeck"], "icon": "image", "color": "#00D4FF"},
        {"id": "secretary_office", "name": "Secretary's Office", "description": "Work breakdown, session continuity, task tracking", "agents": ["secretary", "summary"], "icon": "document-text", "color": "#94A3B8"},
        {"id": "triage_center", "name": "Triage Center", "description": "Issue classification, priority routing, SLA tracking", "agents": ["triage"], "icon": "flag", "color": "#F97316"},
        {"id": "hotfix_bunker", "name": "Hotfix Bunker", "description": "Emergency response — rapid patch, test, deploy (6 agents)", "agents": ["hotfix_lead", "hotfix_patcher", "hotfix_regression", "hotfix_deploy", "hotfix_rollback", "hotfix_qa"], "icon": "pulse", "color": "#EF4444"},
        # ======== EXPANSION ALPHA ROOMS ========
        {"id": "monetization", "name": "Monetization War Room", "description": "Economy, pricing, battle pass, ethics (20 agents)", "agents": ["mon_director","mon_economy","mon_store","mon_pricing","mon_battlepass","mon_bundles","mon_gacha","mon_subscription","mon_ads","mon_whale","mon_currency","mon_gifting","mon_conversion","mon_retention","mon_live_events","mon_analytics","mon_ethics","mon_cosmetic","mon_season","mon_ab"], "icon": "cash", "color": "#F59E0B"},
        {"id": "community_hub", "name": "Community Hub", "description": "Discord, social, influencers, support (16 agents)", "agents": ["com_director","com_discord","com_forum","com_social","com_influencer","com_events","com_feedback","com_moderation","com_support","com_ambassador","com_wiki","com_esports_com","com_ugc_com","com_localized","com_crisis","com_sentiment"], "icon": "people-circle", "color": "#8B5CF6"},
        {"id": "localization_lab", "name": "Localization Lab", "description": "20+ languages, cultural adaptation, voice loc (20 agents)", "agents": ["loc_director","loc_english","loc_japanese","loc_chinese","loc_korean","loc_spanish","loc_french","loc_german","loc_portuguese","loc_russian","loc_arabic","loc_hindi","loc_turkish","loc_thai","loc_voice","loc_cultural","loc_qa","loc_tools","loc_audio_int","loc_legal"], "icon": "language", "color": "#06B6D4"},
        {"id": "cinematics_stage", "name": "Cinematics Stage", "description": "Film-quality cutscenes, mocap, camera (16 agents)", "agents": ["cin_director","cin_camera","cin_storyboard","cin_mocap","cin_facial","cin_lighting","cin_editing","cin_vfx","cin_audio_post","cin_dialogue","cin_realtime","cin_prerender","cin_transition","cin_qte","cin_choreography","cin_color"], "icon": "film", "color": "#EC4899"},
        # ======== EXPANSION BETA ROOMS ========
        {"id": "env_art_studio", "name": "Environment Art Studio", "description": "Terrain, vegetation, architecture, lighting (18 agents)", "agents": ["env_director","env_terrain","env_vegetation","env_architecture","env_props","env_lighting","env_materials","env_modular","env_skybox","env_water","env_cave","env_urban","env_scifi","env_fantasy","env_destruction","env_seasonal","env_optimization","env_narrative"], "icon": "leaf", "color": "#059669"},
        {"id": "char_art_studio", "name": "Character Art Studio", "description": "Modeling, rigging, animation, creatures (16 agents)", "agents": ["char_director","char_concept","char_model","char_texture","char_rig","char_anim","char_cloth","char_creature","char_weapon","char_vehicle_art","char_customization","char_npc","char_portrait","char_emote","char_lod","char_diverse"], "icon": "person", "color": "#EC4899"},
        {"id": "vfx_studio", "name": "VFX Studio", "description": "Fire, magic, weather, destruction, shaders (14 agents)", "agents": ["vfx_director","vfx_fire","vfx_magic","vfx_impact","vfx_weather","vfx_destruction","vfx_ambient","vfx_ui","vfx_liquid","vfx_electricity","vfx_smoke","vfx_shader","vfx_trail","vfx_optimization"], "icon": "sparkles", "color": "#F97316"},
        {"id": "music_studio", "name": "Music & Sound Studio", "description": "Orchestral, electronic, foley, spatial (16 agents)", "agents": ["mus_director","mus_orchestral","mus_electronic","mus_adaptive","mus_ambient","mus_combat","mus_cultural","mus_sfx_combat","mus_sfx_env","mus_sfx_ui","mus_sfx_creature","mus_foley","mus_mixing","mus_spatial","mus_voice","mus_implementation"], "icon": "musical-notes", "color": "#6366F1"},
        # ======== EXPANSION GAMMA ROOMS ========
        {"id": "ui_ux_lab", "name": "UI/UX Lab", "description": "HUD, menus, tutorials, input, responsive (14 agents)", "agents": ["ux_director","ux_hud","ux_menu","ux_tutorial","ux_feedback","ux_input","ux_typography","ux_animation","ux_color","ux_responsive","ux_social","ux_inventory","ux_map","ux_research"], "icon": "phone-portrait", "color": "#0EA5E9"},
        {"id": "infra_ops", "name": "Infrastructure Ops", "description": "Cloud, servers, matchmaking, CI/CD, security (20 agents)", "agents": ["infra_architect","infra_gameserver","infra_matchmaking","infra_database","infra_cdn","infra_monitoring","infra_ci_cd","infra_security","infra_scaling","infra_cost","infra_backup","infra_container","infra_network","infra_analytics","infra_feature_flag","infra_chat","infra_auth","infra_leaderboard","infra_patch","infra_telemetry"], "icon": "server", "color": "#3B82F6"},
        {"id": "narrative_deep", "name": "Narrative Deep Dive", "description": "Worldbuilding, quests, branching, companions (16 agents)", "agents": ["nar_worldbuilder","nar_dialogue","nar_quest","nar_character","nar_branch","nar_environmental","nar_journal","nar_companion","nar_villain","nar_faction","nar_mythology","nar_humor","nar_horror","nar_romance","nar_procedural","nar_ending"], "icon": "book", "color": "#A855F7"},
        {"id": "accessibility_lab", "name": "Accessibility Lab+", "description": "Visual, auditory, motor, cognitive, compliance (12 agents)", "agents": ["acc_director","acc_visual","acc_auditory","acc_motor","acc_cognitive","acc_photosensitive","acc_subtitles","acc_difficulty","acc_testing","acc_input_acc","acc_communication","acc_compliance"], "icon": "accessibility", "color": "#7C3AED"},
        # ======== EMPEROR'S COURT & GUARD ========
        {"id": "emperors_court", "name": "Emperor's Court", "description": "Royal advisors — Vizier, Spymaster, Architect, Oracle (10 agents)", "agents": ["court_vizier","court_architect","court_coin","court_spymaster","court_commander","court_scribe","court_oracle","court_ambassador","court_ceremonies","court_inquisitor"], "icon": "star", "color": "#FFD700"},
        {"id": "emperors_guard", "name": "Emperor's Guard", "description": "Enforcement & protection — Sentinels, Enforcers, Watchmen (10 agents)", "agents": ["guard_captain","guard_alpha","guard_omega","guard_shield","guard_vanguard","guard_watchman","guard_enforcer","guard_interceptor","guard_defender","guard_custodian"], "icon": "shield", "color": "#B22222"},
    ]
    return {"rooms": rooms}


@router.get("/vault/code")
async def get_vault_code(limit: int = 50):
    codes = await vault_collection.find().sort("stored_at", -1).limit(limit).to_list(limit)
    for c in codes:
        c.pop("_id", None)
    return {
        "vault_entries": codes,
        "total": await vault_collection.count_documents({}),
        "unlearned": await vault_collection.count_documents({"learned_by_jeeves": False}),
        "unparsed": await vault_collection.count_documents({"parsed_by_jeeves": False}),
    }


@router.post("/jeeves/parse-idle")
async def jeeves_idle_parse(user_id: str = "global"):
    """Jeeves parses unparsed vault code during idle time. No XP awarded."""
    unparsed = await vault_collection.find({"parsed_by_jeeves": False}).limit(10).to_list(10)
    parsed_count = 0
    for entry in unparsed:
        await vault_collection.update_one({"_id": entry["_id"]}, {"$set": {"parsed_by_jeeves": True, "parsed_at": datetime.utcnow().isoformat()}})
        parsed_count += 1
    await add_jeeves_xp(user_id, 0, "parse")
    return {"parsed": parsed_count, "remaining": await vault_collection.count_documents({"parsed_by_jeeves": False})}


@router.post("/jeeves/learn-vault")
async def jeeves_learn(user_id: str = "global", batch_size: int = 20):
    """Jeeves learns from vault entries. No XP — knowledge acquisition only."""
    result = await jeeves_learn_from_vault(user_id, batch_size)
    return result
