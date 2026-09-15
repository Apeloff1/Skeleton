"""
routes/galaxy_studio_meta.py — Meta / introspection sub-router.

Extracted from routes/galaxy_studio.py (Phase-7, Feb 2026). Hosts pure-read
endpoints that document the agent-swarm wiring and global domain
overview. No in-memory build state, no parent helpers.

  GET /agent-db-manifest  — which Mongo collections each agent swarm uses
  GET /domains            — unified domain overview (Mega + Hyperscale)

Mounted via parent ``router.include_router(...)`` so public paths
``/api/galaxy-studio/agent-db-manifest`` and ``/api/galaxy-studio/domains``
remain unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["galaxy-studio"])


@router.get("/agent-db-manifest")
async def agent_db_manifest():
    """Documents which Mongo collections every agent swarm is wired to.
    Includes the 200 mega-asset collections (games, mechanics, descriptors,
    models, renders, sprites, sounds, voices, names, graphics, ambiance,
    retention)."""
    try:
        from seeds.mega_game_db_seed import (
            MEGA_COLLECTIONS, MEGA_CATEGORIES, TOTAL_MEGA_COLLECTIONS,
        )
        mega_names = [n for n, _ in MEGA_COLLECTIONS]
        mega_cats  = list(MEGA_CATEGORIES.keys())
        mega_count = TOTAL_MEGA_COLLECTIONS
    except Exception:
        mega_names, mega_cats, mega_count = [], [], 0
    manifest = {
        "galaxy_agents": {
            "swarm":       "Galaxy Studio",
            "count":       28_894,
            "collections": ["galaxy_builds", "galaxy_vault", "game_code_library", "academy_tracks", "bible_entries"] + mega_names,
            "role":        "Primary game-generation swarm. Reads canonical code + bibles + 200 mega-asset DBs, writes builds + vault.",
        },
        "jeeves_agents": {
            "swarm":       "Jeeves Master Build",
            "count":       28_662,
            "collections": ["jeeves_builds", "galaxy_vault", "game_code_library", "rosetta_stone", "hyperscale_references"] + mega_names,
            "role":        "APK compilation + polish swarm. Reads code lib + translation + 200 mega-asset DBs, writes jeeves_builds + vault.",
        },
        "vee_agents": {
            "swarm":       "AgentVEE (Virtual Execution Environment)",
            "count":       1_444_700,
            "collections": ["game_code_library", "galaxy_builds", "jeeves_builds", "academy_tracks", "bible_entries", "hyperscale_references", "rosetta_stone"] + mega_names,
            "role":        "Massively parallel virtual swarm. Reads everything (including all 200 mega-DBs), drives simulated build phases.",
        },
        "outcall_agents": {
            "swarm":       "OutcallManager (Offline LLM synth)",
            "count":       512,
            "collections": ["game_code_library", "rosetta_stone", "hyperscale_references"],
            "role":        "Intercepts external LLM calls. Falls back to local canonical answers when APIs unreachable.",
        },
        "vault_agents": {
            "swarm":       "Vault Custodians",
            "count":       128,
            "collections": ["galaxy_vault", "galaxy_builds", "jeeves_builds"],
            "role":        "Archive and deliver ZIPs / APKs. Indexes every completed build.",
        },
        "compiler_agents": {
            "swarm":       "EAS Compiler",
            "count":       64,
            "collections": ["galaxy_vault", "galaxy_builds", "jeeves_builds"],
            "role":        "Drives EAS cloud compilation + fallback mock APK generation.",
        },
    }
    total_agents     = sum(g["count"]              for g in manifest.values())
    all_collections  = sorted({c for g in manifest.values() for c in g["collections"]})
    return {
        "manifest":           manifest,
        "total_agents":       total_agents,
        "total_connections":  sum(len(g["collections"]) for g in manifest.values()),
        "collections":        all_collections,
        "collection_count":   len(all_collections),
        "mega_db_count":      mega_count,
        "mega_categories":    mega_cats,
    }


@router.get("/domains")
async def get_domains():
    """Get unified domain overview (MegaDomains + Hyperscale)."""
    try:
        return {
            "hyperscale":         {"domains": 300, "specialists": 2_400, "expertise_areas": 19_200},
            "mega":               {"domains":  29, "specialists":   232, "synergy_links":      99},
            "total_domains":      329,
            "total_specialists":  2_632,
        }
    except Exception:
        return {"hyperscale": {"domains": 300}, "mega": {"domains": 29}, "total_domains": 329}
