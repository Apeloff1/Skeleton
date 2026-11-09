from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RoomStyleAssignment:
    room_id: str
    room_name: str
    description: str
    tier_2: str
    tier_3: str
    tier_4: str
    domain_tags: List[str]


ROOM_ASSIGNMENTS: Dict[str, RoomStyleAssignment] = {
    "game_engine": RoomStyleAssignment(
        "game_engine", "Game Engine Core", "Main loop and subsystem orchestration",
        "niklas_frykholm", "john_carmack", "casey_muratori",
        ["engine", "architecture"],
    ),
    "entity_component_system": RoomStyleAssignment(
        "entity_component_system", "ECS", "Data-oriented entity systems",
        "mike_acton", "niklas_frykholm", "casey_muratori",
        ["ecs", "dod"],
    ),
    "physics_core": RoomStyleAssignment(
        "physics_core", "Physics", "Simulation core",
        "john_carmack", "fabian_giesen", "casey_muratori",
        ["physics", "math"],
    ),
    "rendering": RoomStyleAssignment(
        "rendering", "Rendering", "Frame graph and passes",
        "fabian_giesen", "niklas_frykholm", "john_carmack",
        ["graphics", "gpu"],
    ),
    "shader_system": RoomStyleAssignment(
        "shader_system", "Shaders", "Shader variants and pipelines",
        "fabian_giesen", "john_carmack", "niklas_frykholm",
        ["shaders", "gpu"],
    ),
    "networking": RoomStyleAssignment(
        "networking", "Networking", "Replication and prediction",
        "john_carmack", "casey_muratori", "niklas_frykholm",
        ["net", "replication"],
    ),
    "tools_pipeline": RoomStyleAssignment(
        "tools_pipeline", "Tools Pipeline", "Asset cooks and validation",
        "niklas_frykholm", "jonathan_blow", "casey_muratori",
        ["tools", "assets"],
    ),
    "ai_navigation": RoomStyleAssignment(
        "ai_navigation", "AI Navigation", "Navmesh and steering",
        "andrej_karpathy", "john_carmack", "casey_muratori",
        ["ai", "nav"],
    ),
    "serialization": RoomStyleAssignment(
        "serialization", "Serialization", "Binary layouts and versioning",
        "fabian_giesen", "casey_muratori", "mike_acton",
        ["io", "formats"],
    ),
    "scripting_core": RoomStyleAssignment(
        "scripting_core", "Scripting", "Bindings and sandbox",
        "jonathan_blow", "casey_muratori", "niklas_frykholm",
        ["script", "vm"],
    ),
}


# Extended from full_room_registry engine set
for _rid, _meta in {
    "audio_engine": ("Audio Engine", "Mixer and DSP", "casey_muratori", "fabian_giesen", "niklas_frykholm", ["audio"]),
    "animation_rig": ("Animation", "Skeletal systems", "niklas_frykholm", "casey_muratori", "john_carmack", ["anim"]),
    "input_system": ("Input", "Device abstraction", "casey_muratori", "john_carmack", "niklas_frykholm", ["input"]),
    "memory_allocator": ("Memory", "Arenas and pools", "casey_muratori", "mike_acton", "fabian_giesen", ["memory"]),
    "job_system": ("Jobs", "Task graph", "mike_acton", "casey_muratori", "niklas_frykholm", ["jobs"]),
    "platform_android": ("Android", "S20 shell", "john_carmack", "casey_muratori", "niklas_frykholm", ["mobile"]),
    "level_design": ("Level Design", "Spaces", "jonathan_blow", "casey_muratori", "john_carmack", ["levels"]),
    "procedural_gen": ("PCG", "Generators", "andrej_karpathy", "jonathan_blow", "john_carmack", ["pcg"]),
    "ci_cd_room": ("CI/CD", "Pipelines", "niklas_frykholm", "casey_muratori", "john_carmack", ["ci"]),
}.items():
    if _rid not in ROOM_ASSIGNMENTS:
        ROOM_ASSIGNMENTS[_rid] = RoomStyleAssignment(
            _rid, _meta[0], _meta[1], _meta[2], _meta[3], _meta[4], _meta[5]
        )


def assignment_for(room_id: str) -> Optional[RoomStyleAssignment]:
    return ROOM_ASSIGNMENTS.get(room_id)


def coder_for_tier(room_id: str, tier: str) -> Optional[str]:
    a = ROOM_ASSIGNMENTS.get(room_id)
    if not a:
        return None
    return {
        "tier_2": a.tier_2,
        "tier_3": a.tier_3,
        "tier_4": a.tier_4,
        "standard": None,
    }.get(tier)
