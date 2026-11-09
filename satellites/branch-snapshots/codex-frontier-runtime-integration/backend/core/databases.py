"""
core/databases.py — Centralized MongoDB database handles.

The app uses THREE logical databases on the same MongoDB cluster/URL so that
the Emergent `[MONGODB_MIGRATE]` step only moves the small user-facing DB on
deploy. The other two are rebuilt from code on boot.

  • core_db     (= DB_NAME)              — user/app state. Migrated to prod.
  • content_db  (= DB_NAME + "_content") — regenerable seed content. SKIPPED by MIGRATE.
  • swarm_db    (= DB_NAME + "_swarm")   — hyperscale agent scratch data. SKIPPED by MIGRATE.

Which collections live where is declared in ``COLLECTION_MAP`` at the bottom of
this file so the routing is explicit and trivial to audit.

Usage
-----
    from core.databases import core_db, content_db, swarm_db
    await content_db.reading_library.find({}).to_list(100)

For code that doesn't know up-front which DB a collection lives in, use the
``collection()`` helper which routes by name:

    from core.databases import collection
    coll = collection("reading_library")   # returns content_db.reading_library
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# Load env so MONGO_URL / DB_NAME are available when this module is imported
# before server.py (e.g. from a standalone script).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME: str = os.environ.get("DB_NAME", "galaxy_studio_db")

CORE_DB_NAME: str = _DB_NAME
CONTENT_DB_NAME: str = f"{_DB_NAME}_content"
SWARM_DB_NAME: str = f"{_DB_NAME}_swarm"

# Single shared async client for all three logical databases.
# ★ DEPLOYMENT FIX (2026-02): K8s liveness/readiness probes were timing out
# because Motor was attempting eager SRV DNS resolution at module import time
# in cold containers. `connect=False` defers all I/O until first operation, and
# aggressive timeouts ensure failures fast-fail to JSON 5xx instead of hanging
# the event loop. The values below preserve normal operation while keeping
# import-time work essentially zero.
client: AsyncIOMotorClient = AsyncIOMotorClient(
    MONGO_URL,
    maxPoolSize=100,
    minPoolSize=0,                       # don't pre-warm pool at startup
    maxIdleTimeMS=45000,
    serverSelectionTimeoutMS=5000,       # fail fast on bad DNS / unreachable
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
    retryReads=True,
    connect=False,                        # ★ defer connect until first op
    appname="codedock-backend",
)

core_db: AsyncIOMotorDatabase = client[CORE_DB_NAME]
content_db: AsyncIOMotorDatabase = client[CONTENT_DB_NAME]
swarm_db: AsyncIOMotorDatabase = client[SWARM_DB_NAME]

# ─────────────────────────────────────────────────────────────────────────────
# SYNC FUNNEL (2026-05 architecture refactor — P2)
# ─────────────────────────────────────────────────────────────────────────────
# Several non-async modules (agent_ledger, cold_storage, discourse_engine,
# legion_discourse, platoons, whisper_network, collection_agents) previously
# instantiated their OWN pymongo.MongoClient with identical options, creating
# 7 separate connection pools per pod.
#
# ``get_sync_client()`` and ``get_sync_db()`` provide a SINGLE shared pymongo
# client + database handle. Modules should migrate one at a time::
#
#     from core.databases import get_sync_db
#     _db = get_sync_db()
#     col = _db["my_collection"]
#
# The client is lazily created on first call — module-import time stays
# zero-cost (critical for the K8s readiness probe).
_sync_client = None      # type: ignore[var-annotated]
#  Lock guarding the lazy-init of `_sync_client`. Created at module import
#  time which is SAFE here because ``threading.Lock`` does not need an event
#  loop (unlike asyncio.Lock — see core/api_middleware.py for the lazy
#  asyncio-lock pattern).
import threading as _threading  # noqa: E402  (kept near its only consumer)
_sync_client_lock = _threading.Lock()


def get_sync_client():
    """Return the single shared synchronous pymongo MongoClient.

    Thread-safe lazy init using the double-checked locking idiom. The fast
    path (already-initialised) is lock-free; only the first concurrent
    callers contend for the lock to perform the single instantiation.
    Subsequent callers share the same pool (default 100 connections).
    """
    global _sync_client
    if _sync_client is None:
        with _sync_client_lock:
            #  Re-check INSIDE the lock — another thread may have raced us
            #  and already created the client.
            if _sync_client is None:
                from pymongo import MongoClient  # local import keeps module-load fast
                _sync_client = MongoClient(
                    MONGO_URL,
                    maxPoolSize=100,
                    minPoolSize=0,
                    maxIdleTimeMS=45000,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=20000,
                    retryWrites=True,
                    retryReads=True,
                    connect=False,
                    appname="codedock-backend-sync",
                )
    return _sync_client


def get_sync_db(db_name: str | None = None):
    """Return a synchronous pymongo database handle.

    Defaults to the core DB (``DB_NAME``). Pass ``"content"`` or ``"swarm"``
    to target one of the other logical databases.
    """
    name = db_name or CORE_DB_NAME
    if name == "content":
        name = CONTENT_DB_NAME
    elif name == "swarm":
        name = SWARM_DB_NAME
    return get_sync_client()[name]

# ─────────────────────────────────────────────────────────────────────────────
# COLLECTION ROUTING
# ─────────────────────────────────────────────────────────────────────────────
# Any collection listed under CONTENT_COLLECTIONS or SWARM_COLLECTIONS lives in
# the corresponding extra database. Everything else defaults to core_db. Prefix
# matches (`*_suffix`) are supported with the second (tuple) form.

# Exact-name content collections (regenerable seed data):
CONTENT_COLLECTIONS: set[str] = {
    "reading_library",
    "bugfix_library",
    "specialized_vault",
    "game_knowledge_vault",
    "unique_flair",
    "game_code_library",
    # ─── Narrative-vault family (populated by core/narrative_vault.py) ───
    "narrative_vault",
    "narrative_libraries",
    "playwright_library",
    "narration_library",
    "quest_library",
    "mission_library",
    "story_arc_library",
    "storytelling_library",
    "game_knowledge_plan",
    # ─── Rosetta family (populated by seeds/rosetta_stone_seed.py) ───
    "rosetta_stone",
    # ─── Hyperscale/reference family (populated by seed_runner.py) ───
    "hyperscale_references",
    "hyperscale_bibles",
    "complexity_reference",
    "tech_glossary",
    "workaround_library",
    # ─── Agent-knowledge family ───
    "patch_notes",
    "patch_notes_curated",
    "github_code_refs",
    "code_synthesis_templates",
    "code_diagnostics_rules",
    "procgen_recipes",
    "content_catalogues",
    "game_design_patterns",
    "game_balance_curves",
    "engine_api_schemas",
    "gamestate_schemas",
    "qa_oracles",
    "ai_generative_weights",
    "build_recipes",
    # ─── Agent-knowledge sub-collections (populated by lifespan kicks) ───
    "academic_frameworks",
    "age_era_reference",
    "agnostic_content_index",
    "asset_engine_theft",
    "ast_detection",
    "audio_dsp",
    "code_similarity_logic",
    "cognitive_psychographics",
    "deep_lore",
    "director_pacing",
    "ecosystems_biology",
    "emotional_dialogue",
    "game_playing_logic_clones",
    "historical_meta",
    "input_haptics",
    "legal_compliance",
    "linting_formatters",
    "mechanic_legal_paradox",
    "physics_materials_sim",
    "publishing_assets",
    "reading_library_content",
    "reading_library_quiz",
    "scraper_jobs",
    "security_crypto",
    "stylometric_fingerprint",
    "training_recipes",
    "variation_mutation",
    "visual_juice",
    # ─── Note on academy/quiz/catalog data ─────────────────────────────────
    # The following collections (academy_tracks, academy_subjects,
    # interactive_quizzes, achievements_catalog, bible_entries, knowledge_*,
    # algo_challenges, language_classes) STAY in core_db. They are written
    # by seeds/seed_runner.py and read by routes/academy_v3.py via the
    # `core_db` handle directly (`_db.<name>`). Routing them to content_db
    # would orphan ~30 read paths and break the Academy UI. They are small
    # (~22 MB combined) and core_db remains well under the 50 MB safe budget
    # for the Emergent [MONGODB_MIGRATE] Atlas step.
}

# Prefix-matched content collections (mega game DB: 200 collections × 3000 docs):
# All prefixes below ARE actively populated by seeds/mega_game_db_seed.py.
CONTENT_PREFIXES: tuple[str, ...] = (
    "ambiance_",      # 16 collections × 3000 = 48,000 docs
    "descriptors_",   # 20 × 3000 = 60,000
    "games_",         # 16 × 3000 = 48,000
    "graphics_",      # 16 × 3000 = 48,000
    "mechanics_",     # 20 × 3000 = 60,000
    "models_",        # 20 × 3000 = 60,000
    "names_",         # 16 × 3000 = 48,000
    "renders_",       # 16 × 3000 = 48,000
    "retention_",     # 12 × 3000 = 36,000
    "sounds_",        # 16 × 3000 = 48,000
    "sprites_",       # 16 × 3000 = 48,000
    "voices_",        # 16 × 3000 = 48,000
    "bugfix_",        # bugfix_mega, bugfix_complete, etc.
    # ─────────────────────────────────────────────────────────────────
    # ★ FORWARD-DECLARED PREFIXES (reserved for future expansion).
    # No seeder exists yet. Any future collection created with these
    # prefixes will automatically route to content_db (not core_db).
    # Listed last so it's clear they're forward-looking, not omissions.
    # ─────────────────────────────────────────────────────────────────
    "ai_patterns_",
    "bosses_",
    "enemies_",
    "factions_",
    "loot_",
    "lore_",
    "npcs_",
    "puzzles_",
    "quests_",
    "worldgen_",
)

# Hyperscale / swarm collections (agent scratch, ledgers are still user-scoped
# so they stay in core_db; this is really for hyperscale volumes only).
SWARM_COLLECTIONS: set[str] = set()
SWARM_PREFIXES: tuple[str, ...] = (
    "hyperscale_",
    "swarm_",
)


def which_db(collection_name: str) -> AsyncIOMotorDatabase:
    """Return the logical database that owns the given collection."""
    if collection_name in CONTENT_COLLECTIONS or collection_name.startswith(CONTENT_PREFIXES):
        return content_db
    if collection_name in SWARM_COLLECTIONS or collection_name.startswith(SWARM_PREFIXES):
        return swarm_db
    return core_db


def collection(name: str):
    """Return the Motor collection handle, auto-routed to the correct DB."""
    return which_db(name)[name]


__all__ = [
    "client",
    "core_db",
    "content_db",
    "swarm_db",
    "CORE_DB_NAME",
    "CONTENT_DB_NAME",
    "SWARM_DB_NAME",
    "CONTENT_COLLECTIONS",
    "CONTENT_PREFIXES",
    "SWARM_COLLECTIONS",
    "SWARM_PREFIXES",
    "which_db",
    "collection",
]
