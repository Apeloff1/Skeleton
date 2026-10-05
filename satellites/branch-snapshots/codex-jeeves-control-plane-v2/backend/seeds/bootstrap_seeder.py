"""
Bootstrap seeder — ensures every collection that agents/routes depend on exists
and contains at least a minimum set of reference data.

Called once on startup AND exposed via GET /api/galaxy-studio/bootstrap-dbs so
the frontend can trigger a re-verify at any time.

Covers:
  • tutorial_progress — canonical tutorial templates (was empty)
  • galaxy_vault — seed one system entry so the collection exists for agents
  • jeeves_builds — same
  • galaxy_build_archive — index for completed builds
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger("GalaxyStudio.BootstrapSeeder")

TUTORIAL_TEMPLATES = [
    # (slug, title, total_steps, category)
    ("galaxy-studio-intro", "Galaxy Studio — Full Walkthrough", 12, "game_creation"),
    ("galaxy-studio-era-picker", "Mastering the Game Era Selector", 6, "game_creation"),
    ("galaxy-studio-sliders-129", "The 129-Slider Deep Dive", 10, "game_creation"),
    ("jeeves-master-build", "Jeeves Master Build — APK Delivery", 8, "compilation"),
    ("vault-tour", "Vault — Storage & Download", 5, "storage"),
    ("code-library-search", "Agent-Facing Code Library (32M lines)", 7, "agents"),
    ("presets-quickstart", "Quick Start Templates", 4, "game_creation"),
    ("rosetta-stone-basics", "Rosetta Stone — Language Pivots", 9, "language"),
    ("academy-tracks", "Academy Tracks — Multi-Year Curricula", 11, "education"),
    ("knowledge-bibles", "Knowledge Bibles — Deep-Dive Reading", 8, "education"),
    ("assessments-intro", "Assessments — How They Work", 6, "education"),
    ("achievements-intro", "Achievements & Streaks", 5, "gamification"),
    ("adaptive-learning", "Adaptive Learning Paths", 7, "education"),
    ("study-paths", "Building Your Own Study Path", 6, "education"),
    ("leaderboards", "Leaderboards & Social", 4, "gamification"),
    ("offline-mode", "Offline-First — Works Without Internet", 5, "system"),
    ("outcall-manager", "OutcallManager — LLM Fallback", 6, "agents"),
    ("agent-swarms", "The 1.5M-Agent Swarm Explained", 8, "agents"),
    ("pomodoro", "Pomodoro Focus Timer", 4, "productivity"),
    ("cheatsheets", "Cheatsheets Library", 5, "reference"),
]


async def seed_tutorial_progress(db) -> dict:
    """Seed tutorial_progress if empty."""
    try:
        existing = await db.tutorial_progress.count_documents({}, limit=1)
    except Exception as e:
        log.warning(f"tutorial_progress count failed: {e}")
        existing = 0
    if existing:
        return {"tutorial_progress": "already_seeded", "docs": existing}

    try:
        await db.tutorial_progress.create_index("slug", unique=True)
        await db.tutorial_progress.create_index("category")
    except Exception:
        pass

    now = datetime.utcnow().isoformat()
    import uuid
    docs = []
    for slug, title, steps, category in TUTORIAL_TEMPLATES:
        docs.append({
            "id": f"tut-{slug}-{uuid.uuid4().hex[:8]}",
            "slug": slug,
            "title": title,
            "category": category,
            "total_steps": steps,
            "current_step": 0,
            "completed": False,
            "started_at": None,
            "completed_at": None,
            "system_template": True,
            "description": f"Canonical walkthrough: {title}",
            "created_at": now,
        })
    try:
        await db.tutorial_progress.insert_many(docs, ordered=False)
    except Exception as e:
        log.warning(f"tutorial_progress insert failed: {e}")
    return {"tutorial_progress": "seeded", "docs": len(docs)}


async def bootstrap_agent_collections(db) -> dict:
    """Create tombstone docs so agent-facing collections exist and are queryable."""
    now = datetime.utcnow().isoformat()
    results = {}
    targets = [
        ("galaxy_vault", {"vault_id": "SYSTEM_BOOTSTRAP", "type": "bootstrap", "title": "Galaxy Vault initialized", "size_human": "0 B", "size_bytes": 0, "created_at": now, "metadata": {"system": True}}),
        ("jeeves_builds", {"build_id": "SYSTEM_BOOTSTRAP", "title": "Jeeves Bootstrap", "status": "bootstrap", "created_at": now, "system": True}),
        ("galaxy_build_archive", {"archive_id": "SYSTEM_BOOTSTRAP", "title": "Archive Index", "created_at": now, "system": True}),
    ]
    for coll_name, tombstone in targets:
        try:
            existing = await db[coll_name].count_documents({}, limit=1)
            if existing == 0:
                await db[coll_name].insert_one(tombstone)
                results[coll_name] = "bootstrapped"
            else:
                results[coll_name] = f"ok ({existing})"
        except Exception as e:
            results[coll_name] = f"err: {str(e)[:80]}"
    return results


async def bootstrap_all(db) -> dict:
    """One-shot bootstrap — safe to call multiple times (idempotent)."""
    result = {"timestamp": datetime.utcnow().isoformat()}
    try:
        result.update(await seed_tutorial_progress(db))
    except Exception as e:
        result["tutorial_progress_error"] = str(e)[:200]
    try:
        result["agent_collections"] = await bootstrap_agent_collections(db)
    except Exception as e:
        result["agent_collections_error"] = str(e)[:200]
    return result
