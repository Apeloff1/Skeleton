"""
Galaxy Studio — Manifest & Genres sub-router.

Extracted from routes/galaxy_studio.py (Jun 2026, decomposition continuation).
Two read-only endpoints that surface static catalog data. They import their
data directly from routes/galaxy_studio_constants.py (NOT from galaxy_studio),
so this module is fully decoupled and import-safe.

Mounted from routes/galaxy_studio.py via ``router.include_router(...)`` WITHOUT
an additional prefix so the public paths stay identical:
  - /api/galaxy-studio/manifest
  - /api/galaxy-studio/genres
"""

from __future__ import annotations
from fastapi import APIRouter

from routes.galaxy_studio_constants import (
    AGENT_MANIFEST, GALAXY_GENRES, TOTAL_GENRES, TOTAL_SUBGENRES,
    BUILD_PHASES, SYNERGY_NETWORK,
)

# Sub-router — NO prefix so the parent's "/api/galaxy-studio" prefix applies.
router = APIRouter(tags=["galaxy-studio"])


@router.get("/manifest")
async def get_manifest():
    """Get the full Galaxy Studio agent manifest and stats."""
    return {
        "name": "Galaxy Studio Factory",
        "version": "3.0 — UNLIMITED",
        "agents": AGENT_MANIFEST,
        "total_agents": AGENT_MANIFEST["total"]["agents"],
        "total_genres": TOTAL_GENRES,
        "total_subgenres": TOTAL_SUBGENRES,
        "total_phases": len(BUILD_PHASES),
        "phases": BUILD_PHASES,
        "synergy_network": SYNERGY_NETWORK,
        "capabilities": {
            "file_limit": "NONE — Unlimited files",
            "size_limit": "NONE — Unlimited size",
            "scale_parsing": True,
            "aaa_references": ["Elden Ring", "GTA", "Cyberpunk", "Red Dead", "Zelda", "God of War", "Skyrim"],
            "code_density": "HYPERDENSE — Real algorithms, not templates",
            "file_categories": ["screens", "components", "logic", "shaders", "ai", "data", "networking", "procgen", "entities", "world", "tests", "hooks", "types", "utils", "store"],
        },
    }


@router.get("/genres")
async def get_genres():
    """Get all genres with their sub-genres."""
    genres = []
    for key, g in GALAXY_GENRES.items():
        genres.append({
            "id": key,
            "name": g["name"],
            "icon": g["icon"],
            "color": g["color"],
            "desc": g["desc"],
            "screens": g["screens"],
            "components": g["components"],
            "logic_files": g["logic_files"],
            "subgenres": g["subgenres"],
            "subgenre_count": len(g["subgenres"]),
        })
    return {
        "genres": genres,
        "total_genres": TOTAL_GENRES,
        "total_subgenres": TOTAL_SUBGENRES,
    }


__all__ = ["router", "get_manifest", "get_genres"]
