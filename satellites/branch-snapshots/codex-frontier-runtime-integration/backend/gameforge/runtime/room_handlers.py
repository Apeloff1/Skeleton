from __future__ import annotations
from typing import Dict, Any


ROOM_SPECIALTIES: Dict[str, Dict[str, Any]] = {
    "game_engine": {"title": "Game Engine Core", "focus": "Loops, subsystems, determinism"},
    "physics_core": {"title": "Physics", "focus": "Integrators, collision, constraints"},
    "entity_component_system": {"title": "ECS", "focus": "Data-oriented layout, queries, jobs"},
    "rendering": {"title": "Rendering", "focus": "Passes, materials, GPU sync"},
    "shader_system": {"title": "Shaders", "focus": "HLSL/GLSL, variants, permutations"},
    "animation": {"title": "Animation", "focus": "Skeleton, blend trees, retarget"},
    "audio": {"title": "Audio", "focus": "Buses, spatialization, mix"},
    "ai_navigation": {"title": "AI Navigation", "focus": "Navmesh, steering, perception"},
    "networking": {"title": "Networking", "focus": "Replication, prediction, interest"},
    "serialization": {"title": "Serialization", "focus": "Binary layouts, versioning"},
    "tools_pipeline": {"title": "Tools Pipeline", "focus": "Asset import, cooks, validation"},
    "scripting_core": {"title": "Scripting", "focus": "Bindings, sandbox, hot-reload"},
}


class RoomHandlerRegistry:
    def __init__(self, specialties: Dict[str, Dict[str, Any]] | None = None):
        self.specialties = specialties or dict(ROOM_SPECIALTIES)

    def frame(self, room_id: str, prompt: str) -> str:
        spec = self.specialties.get(room_id) or {"title": room_id, "focus": "general"}
        return (
            f"[{spec['title']}]\nFocus: {spec['focus']}\n\n{prompt}"
        )

    def list_rooms(self):
        return [
            {"room_id": k, "title": v.get("title"), "focus": v.get("focus")}
            for k, v in self.specialties.items()
        ]

# --- Zaibatsu: auto specialty stubs for full registry -------------------
try:
    from gameforge.rooms.full_room_registry import all_rooms as _ALL_ROOMS

    for _rid, _meta in _ALL_ROOMS().items():
        if _rid not in ROOM_SPECIALTIES:
            ROOM_SPECIALTIES[_rid] = {
                "division": _meta.get("division", "Other"),
                "role": _meta.get("role", ""),
                "handler": "generic",
                "zaibatsu": True,
            }
except Exception:
    pass
