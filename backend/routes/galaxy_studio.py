"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  GALAXY STUDIO FACTORY v1.0                                                ║
║  ─────────────────────────────────────────────────────────────────────────  ║
║  Unified orchestrator merging:                                             ║
║    • Game Factory (52 genres, 200-step pipeline, 25,994 agents)            ║
║    • Jeeves Master Build (28,662 agents, 12-phase code generation)         ║
║    • Hyperscale Domains (300 domains, 2,400 specialists)                   ║
║    • MegaDomains (29 domains, 232 specialists)                             ║
║    • AAA Game Builder (phase tracking, agent activity)                     ║
║                                                                            ║
║  Single entry point: /api/galaxy-studio/*                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

★ DECOMPOSITION ROADMAP (2026-05) — slated for split into sub-package
─────────────────────────────────────────────────────────────────────
This file is 13k LOC and triggers a full WatchFiles reload on every edit.
The future shape is::

    routes/galaxy_studio/
        __init__.py        # re-exports `router` (no behavior change)
        _state.py          # shared in-memory state (agents, phases)
        builds.py          # POST /build, GET /builds, lifecycle
        vault.py           # GET/POST /vault/*
        pipeline.py        # 200-step pipeline endpoints
        hyperscale.py      # hyperscale domain endpoints
        agents.py          # /agents/* introspection

When splitting, the existing ``router`` instance below must remain the single
exported APIRouter, with each sub-module decorating it. This preserves the
``/api/galaxy-studio/*`` URL space and avoids touching server.py.

DO NOT split in a single PR — instead extract ONE sub-module at a time,
running ``pytest`` + ``curl /api/galaxy-studio/*`` between each step.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, AliasChoices
from core.exec_guard import code_execution_enabled, execution_disabled_response
from core.http_errors import internal_http_error
from typing import Optional, Union
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import uuid, os, json, zipfile, tempfile, subprocess, shutil
import time as _build_clock
import asyncio  # module-level (used by background build + expansion launchers)

load_dotenv()

router = APIRouter(prefix="/api/galaxy-studio", tags=["galaxy-studio"])

# Mount the catalog delegators sub-router EARLY (before the dynamic
# /pipeline/{build_id} route is defined below) so the STATIC /pipeline/catalog
# path wins route matching — Starlette resolves routes in registration order.
try:
    from routes.galaxy_studio_catalogs import router as _catalogs_router
    router.include_router(_catalogs_router)
except Exception as _cat_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] catalogs subrouter import SKIPPED: {type(_cat_err).__name__}: {_cat_err}", flush=True, file=_s.stderr)

# Manifest + Genres read-only endpoints (extracted Jun 2026 →
# routes/galaxy_studio_manifest.py). Mounted early so their static paths win.
try:
    from routes.galaxy_studio_manifest import router as _manifest_router
    router.include_router(_manifest_router)
except Exception as _man_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] manifest subrouter import SKIPPED: {type(_man_err).__name__}: {_man_err}", flush=True, file=_s.stderr)

# ═══════════════════════════════════════════════════════════════════════
# STATIC DATA CONSTANTS — extracted Jun 2026 → routes/galaxy_studio_constants.py
# (AGENT_MANIFEST, GALAXY_GENRES, TOTAL_GENRES, TOTAL_SUBGENRES, BUILD_PHASES,
#  SYNERGY_NETWORK). Re-imported here so existing references keep working.
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_constants import (
    AGENT_MANIFEST, GALAXY_GENRES, TOTAL_GENRES, TOTAL_SUBGENRES,
    BUILD_PHASES, SYNERGY_NETWORK,
)

# ═══════════════════════════════════════════════════════════════════════
# VAULT_DIR — canonical builds-vault directory (zip/apk staging lives under it).
# Sourced from core.build_vault so it tracks the SAME env-overridable, writable
# location the vault actually uses. Restores a name referenced by the
# /vault/zip-to-apk endpoint and imported by server.py (was undefined → would
# NameError at request time). Falls back gracefully if build_vault is absent.
# ═══════════════════════════════════════════════════════════════════════
try:
    from core.build_vault import BUILDS_ROOT as VAULT_DIR
except Exception:  # pragma: no cover — defensive fallback
    VAULT_DIR = os.environ.get("GALAXY_BUILDS_VAULT_DIR", "/app/backend/data/builds_vault")


def _safe_segment(value: str, *, what: str = "path") -> str:
    """Reject path traversal / absolute segments in user-supplied ids."""
    s = str(value or "").strip()
    if (
        not s
        or s in {".", ".."}
        or ".." in s
        or "/" in s
        or "\\" in s
        or s.startswith(("~", "/", "\\"))
    ):
        raise HTTPException(400, f"invalid {what}")
    return s


def _safe_slug(title: str, *, fallback: str = "game") -> str:
    """Derive a single-segment slug from a free-form title."""
    raw = (title or fallback).lower().replace(" ", "-")
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in raw)
    cleaned = cleaned.strip("-_")[:20] or fallback
    return _safe_segment(cleaned, what="slug")


def _resolve_under_dir(root: str, *parts: str) -> str:
    """Join under root; 400 if result escapes root."""
    root_r = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_r, *parts))
    if candidate != root_r and not candidate.startswith(root_r + os.sep):
        raise HTTPException(400, "path escapes sandbox")
    return candidate


# ═══════════════════════════════════════════════════════════════════════
# EXPANSION_PHASES — agent pipeline for the /expand (DLC / expansion pack) flow.
# Restores a name referenced by galaxy_expand() (was undefined → NameError 500
# whenever a user expanded a build). Each phase id is "exp_<keyword>" so it maps
# cleanly onto _get_phase_synergies()'s constellation table; `pct` is cumulative
# progress and `agents` the constellation headcount mobilised per phase.
# ═══════════════════════════════════════════════════════════════════════
EXPANSION_PHASES = [
    {"id": "exp_vision",      "name": "Expansion Vision & Scoping",   "agents": 85000,  "pct": 14},
    {"id": "exp_deep_design", "name": "Deep Design Integration",      "agents": 120000, "pct": 30},
    {"id": "exp_code_gen",    "name": "Content & Systems Codegen",    "agents": 210000, "pct": 52},
    {"id": "exp_art_audio",   "name": "Art & Audio Asset Expansion",  "agents": 140000, "pct": 68},
    {"id": "exp_narrative",   "name": "Narrative & Quest Expansion",  "agents": 160000, "pct": 84},
    {"id": "exp_qa_gauntlet", "name": "QA Gauntlet & Balancing",      "agents": 95000,  "pct": 95},
    {"id": "exp_production",  "name": "Production & Packaging",        "agents": 60000,  "pct": 100},
]



TOTAL_BATCHES = 10
PHASES_PER_BATCH = 10

# ── Re-export TOTAL_BATCHES from the canonical state module so any caller
#    that imports it from here keeps working. The actual SSOT is in
#    routes.galaxy_studio_state.TOTAL_BATCHES — keep them in sync.

# ═══════════════════════════════════════════════════════════════════════
# GLOBAL FILE BUDGET — HARD CEILING FOR A SINGLE BUILD
#
# ★ MEMORY-SAFE MODE (2026-04):
#   On small / 1 GB prod pods the previous 250 000-file ceiling could spike
#   RAM above the pod limit mid-build and cause silent OOM kills. We now
#   default to a much lower conservative budget and expose three env knobs
#   so the user can tune up if their pod has more headroom.
#
#   Env overrides (put in /app/backend/.env):
#     GALAXY_FILE_BUDGET        default 25000   max files per build
#     GALAXY_WORKERS            default 2       concurrent batch threads
#     GALAXY_MAX_FILE_BYTES     default 49152   per-file cap (48 KB)
#
# The ceiling is enforced:
#   (1) at the /create fusion-multiplier stamp,
#   (2) at the FLOOR PASS target calculation (after fusion mult),
#   (3) after every phase/batch harvest in _run_background_build_inner,
#   (4) at the start of every floor-pass chunk harvest loop.
# Anything that touches "files" must honour this constant.
# ═══════════════════════════════════════════════════════════════════════
GLOBAL_FILE_BUDGET = int(os.environ.get("GALAXY_FILE_BUDGET", "25000"))

# Add computed pct to each phase entry
for _i, _p in enumerate(BUILD_PHASES):
    _p["pct"] = round((_i + 1) / len(BUILD_PHASES) * 100)

# Build batch index: batch_num -> [phase_ids]
BUILD_BATCHES = {}
for _p in BUILD_PHASES:
    BUILD_BATCHES.setdefault(_p["batch"], []).append(_p["id"])

# Map phase_id -> batch_num (for fast lookup)
_PHASE_BATCH_MAP = {}
for _p in BUILD_PHASES:
    _PHASE_BATCH_MAP[_p["id"]] = _p["batch"]

# Map phase_id -> index in BUILD_PHASES
_PHASE_INDEX_MAP = {}
for _i, _p in enumerate(BUILD_PHASES):
    _PHASE_INDEX_MAP[_p["id"]] = _i

# Batch names for UI
BATCH_NAMES = {
    1: "Foundation",
    2: "Core Mechanics",
    3: "World & Environment",
    4: "Audio & Visual",
    5: "AI & Behavior",
    6: "Systems & Network",
    7: "Content & Depth",
    8: "Polish & Quality",
    9: "Testing & Security",
    10: "Final Assembly",
}

# ═══════════════════════════════════════════════════════════════════════
# IN-MEMORY BUILD STORE — Phase-3 (Feb 2026): the dicts now live in
# routes.galaxy_studio_state so sub-routers can share the SAME instance
# without circular imports. The names ``_builds`` / ``_active_runners``
# are kept as module-level bindings here for the ~250 existing callers
# inside this file — they're just aliases to the state module's objects.
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_state import _builds, _active_runners, _vault_entries  # noqa: E402

async def _save_build(build):
    try:
        from services.database import db as _db
        from core.databases import content_db as _cdb
        # Mongo has a 16MB BSON limit. Builds can accumulate 100k+ files that blow past that.
        # Strip `files` (the big blob) before saving — keep only metadata.
        # Also trim `phase_log`, `_bg_phase_log`, and `_bg_errors` which can grow unbounded
        # as phases accumulate — keep only the last 200 entries each (plenty for resume).
        # File contents can be re-generated on demand or are already cached in-memory/disk.
        # Strip all heavy in-memory-only fields so we rarely hit 16MB BSON.
        # `files` is the big blob; `_gen_cache` holds per-batch copies of the
        # same files; `_code_refs` holds 40 code snippets; `_nv_samples` and
        # `_gk_samples` are big narrative vault dumps. All regenerable.
        _heavy = {
            "files",
            "_gen_cache",
            "_code_refs",
            "_nv_samples",
            "_gk_samples",
            "_swarm_transcript",
            "_swarm_discourse",
            "_bg_deadline_monotonic",
        }
        save_doc = {k: v for k, v in build.items() if k not in _heavy}
        save_doc["_files_saved_separately"] = True
        save_doc["_file_count_at_save"] = len(build.get("files", {}))
        # Trim log arrays — preserve full arrays in RAM but store bounded versions to Mongo
        for log_key, cap in [("phase_log", 200), ("_bg_phase_log", 200), ("_bg_errors", 100)]:
            lst = save_doc.get(log_key)
            if isinstance(lst, list) and len(lst) > cap:
                save_doc[log_key] = lst[-cap:]
                save_doc[f"{log_key}_truncated_from"] = len(lst)
        # Trim any 'phases' entries that carry bulky inline content
        phases = save_doc.get("phases")
        if isinstance(phases, list):
            save_doc["phases"] = [
                {k: v for k, v in p.items() if k not in ("files_generated", "output", "raw_output")}
                for p in phases
            ]
        await _db.galaxy_builds.update_one({"build_id": build["build_id"]}, {"$set": save_doc}, upsert=True)
        # Keep galaxy_builds marked HOT so the cold-storage evictor never targets it.
        try:
            from core import cold_storage as _cs
            _cs.heat_touch("galaxy_builds", hydrate=False)
        except Exception:
            pass
        return True
    except Exception as e:
        # Callers that dispatch physical work require an acknowledged metadata write.
        msg = str(e)
        if "too large" in msg.lower() or "bson" in msg.lower():
            # BSON size fallback: save a minimal metadata-only copy
            try:
                from services.database import db as _db
                from core.databases import content_db as _cdb
                minimal = {
                    "build_id": build.get("build_id"),
                    "title": build.get("title"),
                    "genre": build.get("genre"),
                    "status": build.get("status"),
                    "current_phase": build.get("current_phase", 0),
                    "total_phases": build.get("total_phases", 100),
                    "file_count": build.get("file_count", 0),
                    "_bg_status": build.get("_bg_status"),
                    "_bg_started": build.get("_bg_started"),
                    "_bg_current_batch": build.get("_bg_current_batch", 0),
                    "_bg_last_batch_completed": build.get("_bg_last_batch_completed", 0),
                    "_bg_target_duration": build.get("_bg_target_duration", 15),
                    "_bg_total_batches": build.get("_bg_total_batches", 10),
                    "completed_at": build.get("completed_at"),
                    # Preserve phase status list (just id + status) so /status
                    # after a reload still reports completed_phases correctly.
                    "phases": [
                        {
                            "id": p.get("id"),
                            "name": p.get("name"),
                            "batch": p.get("batch"),
                            "agents": p.get("agents"),
                            "status": p.get("status", "pending"),
                            "completed_at": p.get("completed_at"),
                            "pct": p.get("pct", 0),
                        }
                        for p in (build.get("phases") or [])
                    ][:120],
                    "total_agents": build.get("total_agents", 0),
                    "agents_active": build.get("agents_active", 0),
                    "_bg_phase_log": (build.get("_bg_phase_log") or [])[-50:],
                    "_bg_errors": (build.get("_bg_errors") or [])[-10:],
                    "_bg_retries": build.get("_bg_retries", 0),
                    "_bg_fallbacks": build.get("_bg_fallbacks", 0),
                    "_bg_stop_requested": build.get("_bg_stop_requested", False),
                    "_bg_stop_reason": build.get("_bg_stop_reason"),
                    "_bg_stop_target": build.get("_bg_stop_target"),
                    "_bg_drain_pending": build.get("_bg_drain_pending", False),
                    "_vault_write_failed": build.get("_vault_write_failed", False),
                    "_bg_partial_artifacts": build.get("_bg_partial_artifacts", False),
                    "_minimal_save": True,
                }
                await _db.galaxy_builds.update_one(
                    {"build_id": build["build_id"]}, {"$set": minimal}, upsert=True,
                )
                print(f"[GALAXY _save_build] fell back to MINIMAL save for {build.get('build_id')}")
                return True
            except Exception as e2:
                print(f"[GALAXY _save_build] minimal save also failed: {e2}")
        print(f"[GALAXY _save_build] WARN: {type(e).__name__}")
        return False

def _normalize_build(doc: dict) -> dict:
    """Backfill required lifecycle keys on a build dict so the build pipeline
    never KeyErrors on a slimmed/legacy/edge-case copy.

    Background: build dicts can lose keys across (a) worker-pool slimmed copies,
    (b) backend restarts mid-build that resume via a minimal persisted doc, or
    (c) legacy docs saved before a schema field existed. `_advance_build` and
    the worker harvest read `current_phase`/`phases`/`total_phases` raw, so a
    missing key crashed the BACKGROUND runner (it self-recovered via a fallback,
    but burned 3 retries and spammed tracebacks). setdefault is additive and
    concurrency-safe — it only fills genuinely-absent keys and never overwrites
    real data, so well-formed builds are untouched.
    """
    if not isinstance(doc, dict):
        return doc
    doc.setdefault("files", {})            # stripped on save, restored empty
    doc.setdefault("current_phase", 0)     # ← the reported crash key
    doc.setdefault("total_phases", 100)
    doc.setdefault("phases", [])           # ← worker-harvest crash key
    doc.setdefault("status", "building")
    # ── Additional countermeasure backfills (2026-06) ──────────────────────
    # _advance_build / _generate_batch / fallback paths read these RAW. A
    # slimmed worker copy or legacy doc missing any of them crashed the
    # BACKGROUND runner (burned 3 retries + spammed tracebacks). setdefault is
    # additive + concurrency-safe → well-formed builds are untouched.
    doc.setdefault("title", "Untitled")
    doc.setdefault("genre", "rpg")
    doc.setdefault("subgenre", "")
    doc.setdefault("description", "")
    doc.setdefault("synergy_activations", [])   # ← .append() crash key
    doc.setdefault("agents_active", 0)
    doc.setdefault("file_count", 0)
    doc.setdefault("complexity", 7)
    if not doc.get("genre_info"):
        doc["genre_info"] = GALAXY_GENRES.get(doc.get("genre", "rpg")) or GALAXY_GENRES.get("rpg", {})
    return doc


async def _load_build(build_id: str):
    if build_id in _builds:
        return _normalize_build(_builds[build_id])
    try:
        from services.database import db as _db
        from core.databases import content_db as _cdb
        doc = await _db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 0})
        if doc:
            _normalize_build(doc)
            _builds[build_id] = doc
            # Keep the collection hot on every access so the evictor never re-freezes
            try:
                from core import cold_storage as _cs
                _cs.heat_touch("galaxy_builds", hydrate=False)
            except Exception:
                pass
            return doc
        # Fallback: try thawing if the collection was previously frozen
        try:
            from core import cold_storage as _cs
            _cs.thaw("galaxy_builds", mark_hot=True)
            doc = await _db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 0})
            if doc:
                _normalize_build(doc)
                _builds[build_id] = doc
                return doc
        except Exception:
            pass
    except Exception as e:
        print(f"[GALAXY _load_build] WARN: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════
# BUILD-FILE VAULT FLUSH — keeps in-memory file dict bounded
# ───────────────────────────────────────────────────────────────────────
# The file dict `build["files"]` used to accumulate indefinitely during
# generation (~90 KB of Python object per file), causing pod-OOM at scale.
# _flush_to_vault() streams whatever is currently in RAM to a zstd-compressed
# shard on disk (via core.build_vault) and then clears the dict, so the
# in-memory footprint never exceeds ~200 MB regardless of total file count.
#
# Call this after every file-producing step (phase, batch, chunk).
# file_count is sourced from the vault so it always reflects total.
# ═══════════════════════════════════════════════════════════════════════
# A reasonable chunk size: at 48 KB/file, 300 files = ~14 MB peak RAM.
# Env-configurable — drop lower on constrained pods, raise on beefy ones.
_VAULT_FLUSH_THRESHOLD = int(os.environ.get("GALAXY_FLUSH_EVERY", "300"))


def _flush_to_vault(build: dict, force: bool = False, threshold: int = _VAULT_FLUSH_THRESHOLD) -> int:
    """Persist a bounded pending file set; a failed write stops more generation.

    Keep the detached pending files available on failure. They are not silently
    discarded or enlarged by an unbounded fallback after durable storage fails.
    """
    files = build.get("files") or {}
    if not files or not force and len(files) < threshold:
        return 0
    bid = build.get("build_id")
    if not bid:
        raise GalaxyBuildStopped("build_identity_missing")
    if build.get("_vault_write_failed"):
        raise GalaxyBuildStopped(str(build.get("_bg_stop_reason") or "vault_write_failed"))
    snapshot = files
    build["files"] = {}
    try:
        from core import build_vault as _bv
        res = _bv.append_files(bid, dict(snapshot))
        build["file_count"] = int(res.get("file_count", 0))
        build["_vault_active"] = True
        build["_vault_file_count"] = int(res.get("file_count", 0))
        build["_vault_compressed_bytes"] = int(build.get("_vault_compressed_bytes", 0)) + int(
            res.get("compressed_bytes", 0)
        )
        return int(res.get("appended", 0))
    except Exception as exc:
        snapshot.update(build.get("files") or {})
        build["files"] = snapshot
        build["_vault_write_failed"] = True
        _mark_build_stop(build, "vault_write_failed")
        raise GalaxyBuildStopped("vault_write_failed") from exc


def _vault_total_files(build: dict) -> int:
    """file_count that reflects vault + in-memory pending (for /status)."""
    try:
        from core import build_vault as _bv
        bid = build.get("build_id")
        if bid:
            return _bv.get_file_count(bid) + len(build.get("files") or {})
    except Exception:
        pass
    return len(build.get("files") or {})


# Frontend ships humanised complexity values; map them to ints 0-10.
_COMPLEXITY_WORD_TO_INT = {
    'beginner': 2, 'basic': 2, 'simple': 2,
    'intermediate': 5, 'medium': 5, 'moderate': 5,
    'advanced': 7, 'complex': 7, 'hard': 7,
    'expert': 9, 'extreme': 9,
    'godlike': 10, 'maximum': 10, 'insane': 10, 'maximal': 10,
}


class CreateRequest(BaseModel):
    # Tolerant schema: the frontend ships several "human" forms of these
    # fields that older versions of the backend rejected with 422. The
    # validators below coerce them to the canonical internal form.
    model_config = ConfigDict(
        populate_by_name=True,        # accept both alias + python name
        extra='allow',                # never 422 on an unknown extra key
    )
    title: str
    genre: str
    subgenre: Optional[str] = None
    # ═══ Multi-genre / multi-subgenre fusion support ═══
    # When a user picks multiple genres (e.g. RPG + Tycoon + Open World) or
    # multiple subgenres, send them as lists. The primary `genre`/`subgenre`
    # above stays for backward compat and is treated as the "lead" genre.
    # Providing lists unlocks fusion mode — the build generator cycles through
    # all genres for each phase so the delivered game is a true hybrid, and
    # the floor-delivery multiplier scales with the genre count.
    genres: Optional[list[str]] = None
    subgenres: Optional[list[str]] = None
    description: str = ""
    # Frontend ships "beginner" / "intermediate" / "advanced" / "expert" /
    # "godlike" as strings; legacy clients send raw int 0-10. Accept both.
    complexity: Union[int, str] = 10
    age_target: str = "T"
    graphics_era: int = 7
    npc_density: int = 7
    sound_era: int = 7
    world_size: int = 7
    physics_realism: int = 7
    ai_complexity: int = 7
    lighting_engine: int = 7
    particle_effects: int = 7
    destruction_physics: int = 7
    narrative_branching: int = 7
    economy_complexity: int = 7
    multiplayer_max: int = 7
    weather_systems: int = 7
    day_night_cycle: int = 7
    animation_fluidity: int = 7
    post_processing: int = 7
    foliage_density: int = 7
    water_simulation: int = 7
    ui_minimalism: int = 7
    loot_variety: int = 7
    crafting_depth: int = 7
    dialog_depth: int = 7
    stealth_mechanics: int = 7
    vehicle_simulation: int = 7
    biome_diversity: int = 7
    faction_reputation: int = 7
    skill_system: int = 7
    gore_system: int = 7
    modding_support: int = 7
    # ═══ 2026-02 Animation controls ═══
    animation_style: str = "smooth"        # subtle|smooth|punchy|cinematic
    camera_effects: bool = True            # enables camera shake / zoom-on-hit
    # ═══ 2026-02 Story & Style pack ═══
    storyline_style: str = "heroic"        # heroic|tragedy|mystery|redemption|coming_of_age|comedy|cosmic_horror
    game_pace: str = "standard"            # slow_burn|standard|action_packed|breakneck
    difficulty_curve: str = "steady"       # gentle|steady|adaptive|punishing
    perspective: str = "third_person"      # first_person|third_person|isometric|top_down|side_scroll|vr
    combat_style: str = "action_rpg"       # realtime|turn_based|action_rpg|rhythm|tactical|none
    visual_style: str = "hand_painted"     # photoreal|cel_shaded|pixel_art|low_poly|voxel|hand_painted|anime
    game_tone: str = "epic"                # heroic|dark|humorous|melancholic|epic|cozy|unsettling
    progression_type: str = "open_world"   # linear|open_world|metroidvania|roguelike|sandbox|hub_and_spoke
    audio_mood: str = "orchestral"         # orchestral|synthwave|ambient|chiptune|rock|folk|silent
    # ═══ 2026-02 Locomotion ═══
    locomotion_depth: int = 5              # 0..10 — how many movement verbs to emit
    locomotion_style: str = "als"          # basic|tactical|parkour|als|gunplay|melee
    game_vision: str = ""
    # Frontend has historically used both `system_arch` and the canonical
    # `system_architecture`; accept either via alias.
    system_architecture: str = Field(
        default="",
        validation_alias=AliasChoices("system_architecture", "system_arch"),
    )
    world_laws: str = ""
    agent_instructions: str = ""
    scale: str = ""  # Natural language: "500,000 assets, 25GB game"
    target_files: int = 0  # 0 = auto/unlimited
    target_size_gb: float = 0  # 0 = auto
    # ═══ v2 Extended questionnaire — 100 additional customization sliders ═══
    # Sent as a flat {param_name: int 0-7} dict so the schema doesn't need 100 explicit fields
    # Tolerant: accept dict, JSON-string, or None (older clients send "").
    extra_params: Optional[Union[dict, str]] = None
    # ═══ v3 Game Era selector — tech/aesthetic tone ═══
    era_id: Optional[str] = None
    era_label: Optional[str] = None
    # Tolerant: frontend sometimes sends a number (e.g. 2026) and sometimes a
    # range string ("1985-2000"). Accept both and coerce downstream.
    era_year: Optional[Union[str, int]] = None
    # ═══ v5 "Era by Age" — target birth-year cohort (1985-2030, every year)
    # Lets users anchor a build to a specific year's tech/cultural sensibility
    # independent of the broader Game Era selector (Pong → Singularity).
    # Frontend sometimes sends this as `age_year` — accept either name.
    age_era_year: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("age_era_year", "age_year"),
    )
    # ═══ v6 Style pickers — 9 named-option selectors ═══
    # graphic_style, sound_style, music_style, design_style, cinematic_style,
    # director_style, dimension, asset_style, model_style. Sent as flat
    # {key: option_id} dict so the schema stays extensible.
    style_params: Optional[dict] = None
    # ═══ 2026-05-15 — Hyper-granular phase × axes matrices ═══════════════
    # Each is a nested dict of the form {phase_id: {axis_id: int}}. The
    # frontend Advanced mode lets users tune ~1,400 dials across these 9
    # tensors. We keep them flat-typed (Optional[dict]) so the schema is
    # extensible and no 422 ever bounces a build for an extra phase / axis.
    narrative_phases:     Optional[dict] = None  # 36 phases × 5 axes
    mechanics_matrix:     Optional[dict] = None  # 40 phases × 5 axes
    world_matrix:         Optional[dict] = None  # 36 phases × 5 axes
    art_matrix:           Optional[dict] = None  # 28 phases × 5 axes
    audio_matrix:         Optional[dict] = None  # 24 phases × 5 axes
    tech_matrix:          Optional[dict] = None  # 28 phases × 5 axes
    monetisation_matrix:  Optional[dict] = None  # 20 phases × 5 axes
    qa_matrix:            Optional[dict] = None  # 20 phases × 5 axes
    agent_matrix:         Optional[dict] = None  # 20 phases × 5 axes (ML / RAG dials)
    # ═══ 2026-05-15 — Second wave: 6 additional matrices (DBs · Styles · Mutation · Flair)
    vector_db_matrix:     Optional[dict] = None  # 31 phases × 5 axes (Pinecone, Weaviate, FAISS, HNSW, ColBERT, etc.)
    plagiarism_matrix:    Optional[dict] = None  # 32 phases × 5 axes (Moss, JPlag, CodeBERT, pHash, AST, stylometry)
    rdbms_matrix:         Optional[dict] = None  # 38 phases × 5 axes (Postgres, MySQL, normalization, sharding)
    styles_matrix:        Optional[dict] = None  # 31 phases × 5 axes (all style pickers as tunable dials)
    mutation_matrix:      Optional[dict] = None  # 27 phases × 5 axes (variation engine: drift, jitter, mutate)
    unique_flair_matrix:  Optional[dict] = None  # 29 phases × 5 axes (signature moves, easter eggs, secrets)
    # ═══ 2026-05-15 — Advanced ML execution config (Cross-Entropy / Fine-Tuning / ICL Log-Probs)
    ml_config:            Optional[dict] = None  # {loss_type, label_smoothing, focal_gamma, fine_tune_mode, lora_r, qlora_4bit, icl_logprobs_depth, self_consistency_k, mcts_depth}

    # ─── Tolerant input coercion ───────────────────────────────────────────
    @field_validator('complexity', mode='before')
    @classmethod
    def _coerce_complexity(cls, v):
        if v is None or v == '':
            return 10
        if isinstance(v, str):
            key = v.strip().lower()
            if key in _COMPLEXITY_WORD_TO_INT:
                return _COMPLEXITY_WORD_TO_INT[key]
            try:
                return int(float(key))
            except (TypeError, ValueError):
                return 10
        try:
            return int(v)
        except (TypeError, ValueError):
            return 10

    @field_validator('extra_params', mode='before')
    @classmethod
    def _coerce_extra_params(cls, v):
        # Accept dict (preferred), JSON string, empty string, or None.
        if v is None or v == '' or v == {}:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                import json as _json
                parsed = _json.loads(v)
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
        return None


class AdvanceRequest(BaseModel):
    build_id: str


class StartBuildRequest(BaseModel):
    build_id: str
    build_duration_minutes: int = Field(default=15, ge=1, le=60, strict=True)
    # ═══ v7 Galaxy Studio Settings — per-category emphasis weights (0.0-3.0) ═══
    # Each weight scales file output for phases in that category.
    # 0.0 = skip category, 1.0 = default, 2.0 = double, 3.0 = triple.
    # Categories map to BATCH_NAMES: foundation, core_mechanics, world, audio_visual,
    #   ai_behavior, systems_network, content_depth, polish_quality,
    #   testing_security, final_assembly.
    phase_weights: Optional[dict] = None


class ExpandRequest(BaseModel):
    build_id: str
    expansion_type: str = "content"  # content, systems, zones, enemies, items, all
    scale: str = ""  # Natural language scale for expansion
    description: str = ""  # What to expand
    target_new_files: int = 0  # 0 = auto


class ZipToApkRequest(BaseModel):
    build_id: str
    expo_token: str = ""


# ═══════════════════════════════════════════════════════════════════════
# SCALE PARSER — extracted 2026-06 → routes/galaxy_studio_scale.py
# (pure NL→scale translation; no state/DB). Imported here so /create +
# /expand keep their original call sites.
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_scale import _parse_scale, _scale_label


# ═══════════════════════════════════════════════════════════════════════
# CODE GENERATION ENGINE (Imported from jeeves_master_build)
# ═══════════════════════════════════════════════════════════════════════
from routes.jeeves_master_build import (
    _gen_app_json, _gen_package_json, _gen_eas_json, _gen_tsconfig,
    _gen_game_state, _gen_screen_intricate, _package_build as _jmb_package_build,
)


# ═══════════════════════════════════════════════════════════════════════
# STAGGERED BATCH GENERATION — 16 phases, every phase produces files
# Escalating complexity: foundation → mechanics → content → polish
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# PHASE → FUNCTION DISPATCH MAP
# Maps each phase_id to its generator function name
# ═══════════════════════════════════════════════════════════════════════
_TOTAL_BATCHES = 10


def _generate_batch(build: dict, batch_num: int) -> dict:
    """Generate files for ALL 10 phases within a batch (batch_num: 1-10).
    Each batch processes 10 phases simultaneously with triple-retry per phase
    and fallback generation. This is the core of the 10-batch architecture."""
    if "_gen_cache" not in build:
        build["_gen_cache"] = {}
    cache_key = f"batch_{batch_num}"
    if cache_key in build["_gen_cache"]:
        cached = build["_gen_cache"][cache_key]
        if isinstance(cached, dict) and len(cached) > 0:
            return cached

    # Code-library ref pull (from 32M-line snippet DB). CRITICAL: this runs
    # inside a worker thread (via _WORKER_POOL). Motor is bound to the MAIN
    # event loop — motor calls from a worker thread hang or raise "Future
    # attached to a different loop", blowing the 45s futures.result() timeout
    # and stalling the build at batch 1. Use sync PyMongo from worker threads
    # and keep Motor on the main thread only.
    try:
        import threading as _thr
        era_id = build.get("era_id") or ""
        genre = build.get("genre") or ""
        if _thr.current_thread() is _thr.main_thread():
            import asyncio as _asyncio
            # game_code_library lives in content_db (regenerable seed data)
            from core.databases import content_db as _cdb

            async def _pull_refs_async():
                q = {}
                if era_id: q["era"] = era_id
                if genre: q["genre"] = genre
                return await _asyncio.wait_for(
                    _cdb.game_code_library.find(q, {"_id": 0, "snippet_id": 1, "category": 1, "language": 1, "summary": 1, "code_template": 1}).limit(40).to_list(40),
                    timeout=3.0,
                )

            try:
                loop = _asyncio.get_event_loop()
                if loop.is_running():
                    refs = []
                else:
                    refs = loop.run_until_complete(_pull_refs_async())
            except RuntimeError:
                refs = _asyncio.run(_pull_refs_async())
        else:
            # Worker thread — use sync PyMongo via the shared funnel so we
            # never touch the main loop AND never spawn extra connection pools.
            from core.databases import get_sync_db
            _xdb = get_sync_db("content")  # read from content DB
            q = {}
            if era_id: q["era"] = era_id
            if genre: q["genre"] = genre
            refs = list(_xdb.game_code_library.find(q, {"_id": 0, "snippet_id": 1, "category": 1, "language": 1, "summary": 1, "code_template": 1}).limit(40))

        if refs:
            build["_code_refs"] = refs
            print(f"[GALAXY] Batch {batch_num}: pulled {len(refs)} code-library refs for era={era_id} genre={genre}")
    except Exception as e:
        print(f"[GALAXY] code-library ref pull skipped (non-fatal): {str(e)[:120]}")

    t = build["title"]
    g = build["genre"]
    batch_files = {}
    phase_ids = BUILD_BATCHES.get(batch_num, [])
    batch_name = BATCH_NAMES.get(batch_num, f"Batch {batch_num}")

    print(f"[GALAXY] ═══ BATCH {batch_num}/10: {batch_name} — Processing {len(phase_ids)} phases ═══")

    for phase_id in phase_ids:
        _check_build_resources(build)
        MAX_RETRIES = 3
        last_error = None
        phase_success = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                import time as _pt
                _pt_start = _pt.time()
                print(f"[GALAXY] B{batch_num} phase START: {phase_id} (attempt {attempt})", flush=True)
                phase_files = _call_phase_func(phase_id, build)
                _check_build_continuation(build)
                _pt_dt = _pt.time() - _pt_start
                print(f"[GALAXY] B{batch_num} phase DONE : {phase_id} in {_pt_dt:.2f}s files={len(phase_files) if phase_files else 0}", flush=True)
                if phase_files and len(phase_files) > 0:
                    batch_files.update(phase_files)
                    # Keep partial output available for the owner to retain
                    # on failure. Flush the batch once: vault counts describe
                    # appended records, so re-appending each phase here would
                    # double-count the same generated paths.
                    if not isinstance(build.get("files"), dict):
                        build["files"] = {}
                    build["files"].update(phase_files)
                    _check_build_resources(build)
                    phase_success = True
                    break
            except GalaxyBuildStopped:
                raise
            except Exception as e:
                import traceback, time as _time
                last_error = "phase_failed"
                traceback.print_exc()
                print(f"[GALAXY] Batch {batch_num} phase '{phase_id}' attempt {attempt}/{MAX_RETRIES} failed: {type(e).__name__}")
                if attempt < MAX_RETRIES:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    _time.sleep(backoff)

        if not phase_success:
            _check_build_continuation(build)
            build.setdefault("_bg_errors", []).append(
                {"batch": batch_num, "phase": phase_id, "error": "phase_generation_failed"}
            )
            build["_bg_errors"] = build["_bg_errors"][-100:]
            raise GalaxyBuildStopped("phase_generation_failed")

        # Cooperative GIL release between phases — this batch runs CPU-bound in
        # a worker thread; handing the GIL back here keeps the asyncio event
        # loop (HTTP, /status polling, hub initial-data load) responsive during
        # a live multi-minute build.
        try:
            import time as _gy
            _gy.sleep(0)
        except Exception:
            pass

    # Cache the full batch result — MASSIVE cap bump for AAA-scale volume.
    # Floor: every batch guarantees ≥ 600 files even if phase generation was
    # light; ceiling 10,000 per batch to allow AAA cranked-slider builds to
    # reach 100k+ total files without memory explosion.
    # BATCH_CAP/FLOOR tuned 16× bigger than original: BATCH_CAP lifted 2× on
    # top of the 4× tier (3000→12000→24000) so heavy builds can fill cap;
    # BATCH_FLOOR kept at 800 so 8-way parallel padding stays under ~3 GB
    # peak. The big scale-up happens in the SERIAL floor pass below which
    # reaches 96k+ files safely.
    # ═══ Apply per-category phase_weights from user settings (v7) ═══
    # User can dial any batch category from 0× (skip) to 3× (triple emphasis).
    # Maps directly to BATCH_NAMES keys (foundation, core_mechanics, etc.).
    weight = 1.0
    try:
        weights = build.get("phase_weights") or {}
        if isinstance(weights, dict):
            key = BATCH_NAMES.get(batch_num, "").lower().replace(" & ", "_").replace(" ", "_").replace("__", "_")
            # Try both snake_case and the raw batch number
            for k in (key, str(batch_num), BATCH_NAMES.get(batch_num, "")):
                if k in weights:
                    weight = float(weights[k]); break
    except Exception:
        weight = 1.0
    # Clamp for safety
    weight = max(0.0, min(3.0, weight))
    BATCH_CAP = 24000
    BATCH_FLOOR = int(800 * weight)      # 0 → skipped, 1.0 → 800, 2.0 → 1600
    if weight == 0.0:
        # Honor skip: emit a single marker file and return
        marker = {
            f"skipped/{BATCH_NAMES.get(batch_num, 'batch')}.md": (
                f"# Batch {batch_num} ({BATCH_NAMES.get(batch_num,'?')}) skipped by user (weight=0)\n"
            )
        }
        build["_gen_cache"][cache_key] = marker
        return marker
    _check_build_continuation(build)
    if batch_files:
        if len(batch_files) > BATCH_CAP:
            batch_files = dict(list(batch_files.items())[:BATCH_CAP])
        # Floor-padding — augment with synthetic-but-real expansion files
        if len(batch_files) < BATCH_FLOOR:
            deficit = BATCH_FLOOR - len(batch_files)
            batch_name = BATCH_NAMES.get(batch_num, f"batch_{batch_num}")
            pad = _generate_floor_padding(batch_num, t, g, batch_name, deficit)
            batch_files.update(pad)
            print(f"[GALAXY] Batch {batch_num} floor-padded with {len(pad)} extra files (deficit was {deficit})")
        build["_gen_cache"][cache_key] = batch_files
        print(f"[GALAXY] Batch {batch_num} complete: {len(batch_files)} files (cap={BATCH_CAP}, floor={BATCH_FLOOR})")
        # Heartbeat — watchdog reads this to detect zombie runners
        try:
            from datetime import datetime as _dt
            build["_bg_last_heartbeat"] = _dt.utcnow().isoformat()
        except Exception:
            pass
    return batch_files


# ═══════════════════════════════════════════════════════════════════════
# SYNTHETIC FILE PADDING — extracted 2026-06 → routes/galaxy_studio_padding.py
# (_expand_compact + _generate_floor_padding; pure/picklable so the spawn
# ProcessPoolExecutor can run _generate_floor_padding without re-importing
# this heavy module). Imported here so all original call sites keep working.
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_padding import _expand_compact, _generate_floor_padding


def _generate_fallback_files(batch_id: int, title: str, genre: str, phase_name: str, error: str) -> dict:
    """Emergency fallback generator — produces valid files even when phase function crashes.
    Massively expanded: 60 substantial modules instead of 5, so a single failed
    phase still contributes meaningfully to the AAA build."""
    files = {}
    prefix = f"fallback_phase_{batch_id}"
    domains = [
        "core", "entities", "systems", "combat", "ai", "ui", "hud", "menus",
        "audio", "music", "vfx", "shaders", "lighting", "physics", "particles",
        "save", "load", "network", "rpc", "matchmaking", "lobby", "chat",
        "input", "controller", "accessibility", "localization", "telemetry",
        "analytics", "achievements", "progression", "economy", "loot", "crafting",
        "quest", "dialogue", "narrative", "cinematic", "cutscene",
        "weather", "season", "mod_api", "anti_cheat", "leaderboard",
        "store", "dlc", "live_ops", "events", "tutorial", "onboarding",
        "dungeon", "world_gen", "biome", "ecosystem",
        "camera", "animation", "ragdoll", "ik", "mocap_binding",
        "tools", "debug", "profiler", "tests",
    ]
    safe_phase = (phase_name or "phase").lower().replace(' ', '_')
    for i in range(60):
        domain = domains[i % len(domains)]
        name = f"{prefix}_{domain}_{i:03d}"
        desc = f"Fallback {domain} module #{i} for {phase_name} — auto-recovered from: {(error or 'unknown')[:100]}"
        try:
            content = (
                f"// ═══ {title} — FALLBACK: {phase_name} — {domain} #{i} ═══\n"
                f"// Auto-generated fallback after phase failure. Genre: {genre}\n"
                f"// Original error: {(error or 'none')[:200]}\n\n"
                + _expand_massive(name, desc, title, genre, "fallback")
            )
        except Exception:
            content = (
                f"// {title} — {phase_name} fallback #{i}\n"
                f"export const M{i} = {{ genre: '{genre}', domain: '{domain}' }};\n"
            )
        files[f"fallback/{safe_phase}/{domain}/{name}.ts"] = content
    files[f"fallback/{safe_phase}/RECOVERY_LOG.md"] = (
        f"# {title} — {phase_name} Recovery Log\n\n"
        f"## Phase: {batch_id}\n"
        f"## Status: RECOVERED via fallback\n"
        f"## Error: {(error or 'none')[:500]}\n"
        f"## Files Generated: 5 fallback modules\n"
        f"## Timestamp: {datetime.utcnow().isoformat()}\n"
    )
    return files


def _run_batch_for_phase(build: dict, batch_num: int) -> int:
    """Run a full batch (10 phases) and merge files into the build.
    Returns count of new files added."""
    new_count = 0
    batch_files = _generate_batch(build, batch_num)
    if batch_files:
        build["files"].update(batch_files)
        new_count = len(batch_files)
    build["file_count"] = len(build["files"])
    # Stream this batch to the on-disk vault — keeps RAM bounded.
    try:
        _flush_to_vault(build)
    except Exception as _flush_error:
        print(f"[GALAXY] vault flush failed: {_flush_error}", flush=True)

    # ═══ SWARM DISCOURSE — 200 agents debate the batch's context ═══
    # Non-fatal: failures never block file generation.
    try:
        from core.discourse_engine import simulate as _simulate_discourse
        ctx = {
            "genre": build.get("genre"),
            "subgenre": build.get("subgenre"),
            "era_id": build.get("era_id"),
            "era_year": build.get("era_year"),
            "engine": build.get("engine"),
            "style": build.get("style"),
            "mood": build.get("mood"),
            "seed": build.get("build_id"),
            "tags": [build.get("title", "")],
        }
        record = _simulate_discourse(
            build_id=build.get("build_id", "unknown"),
            phase=f"batch_{batch_num}",
            game_ctx=ctx,
            rounds=2,
            persist=True,
        )
        # Persist discourse highlights INTO the build's generated files so the
        # knowledge makes it into the final game package.
        discourse_md = (
            f"# Swarm Discourse — Batch {batch_num}\n\n"
            f"**Participants:** {len(record['participants'])} specialist agents across "
            f"{len({p['category'] for p in record['participants']})} categories.\n\n"
            f"**Unique flair tags:** {', '.join(record['unique_flair_tags'])}\n\n"
            "## Transcript\n\n" +
            "\n".join(f"- **R{t['round']}** {t['text']}" for t in record["transcript"])
        )
        build["files"][f"docs/swarm_discourse/batch_{batch_num}.md"] = discourse_md
        # Track lightweight summary on the build record itself
        build.setdefault("swarm_discourse_summary", []).append({
            "batch": batch_num,
            "participants": [p["id"] for p in record["participants"]],
            "flair": record["unique_flair_tags"],
            "highlight": record.get("highlight", ""),
        })
        build["file_count"] = len(build["files"])
        new_count += 1

        # ═══ PLATOON CHAIN — every phase gets 5-agent platoon with handoffs ═══
        try:
            from core.platoons import chain_for_batch, force_participation_sweep
            # Derive phase_ids for this batch (10 phases × 10 batches)
            phases_per_batch = 10
            phase_ids = [f"b{batch_num:02d}_p{i+1:02d}" for i in range(phases_per_batch)]
            chain = chain_for_batch(build.get("build_id", "unknown"), batch_num, ctx,
                                    phase_ids=phase_ids, rounds=2, size=5)
            platoon_md = (
                f"# Platoon Chain — Batch {batch_num}\n\n"
                f"**Phases:** {chain['phase_count']}  |  **Unique agents seated:** {chain['unique_agents_seated']}  |  "
                f"**Total transcript lines:** {chain['total_transcript_lines']}\n\n"
                "## Phase platoons (chained by handoff)\n\n" +
                "\n".join(
                    f"- **{p['phase_id']}** (rot={p['rotation_idx']}) seats: {', '.join(p['member_codes'])}  →  handoff: _{p['handoff_head']}_"
                    for p in chain['phase_platoons']
                )
            )
            build["files"][f"docs/platoons/batch_{batch_num}_chain.md"] = platoon_md
            build["file_count"] = len(build["files"])
            new_count += 1
            # On the final batch, sweep any silent agents for 100% coverage
            if batch_num >= 10:
                sweep = force_participation_sweep(build.get("build_id", "unknown"), ctx)
                build["files"][f"docs/platoons/coverage_sweep.md"] = (
                    f"# Coverage Sweep\n\n**Swept agents:** {sweep['swept']}  —  "
                    f"All agents in roster now have at least one platoon seat in this build.\n"
                )
                build["file_count"] = len(build["files"])
                new_count += 1
        except Exception as _pe:
            print(f"[GALAXY][platoons] skipped (batch {batch_num}): {_pe}")

        # ═══ LAYERED LEGION DISCOURSE — 3-tier network every 3rd batch ═══
        # Teams → Legion council → Full Swarm chorus. Heavier, so periodic.
        if batch_num % 3 == 1:
            try:
                from core.legion_discourse import simulate_network as _simulate_legion
                leg = _simulate_legion(
                    build_id=build.get("build_id", "unknown"),
                    phase=f"legion_batch_{batch_num}",
                    game_ctx=ctx,
                    seat_limit=999,               # FULL TOTALITY — entire team joins
                    max_full_swarm_voices=1000,   # FULL TOTALITY — all 482 agents
                    persist=True,
                )
                legion_md = (
                    f"# Layered Legion Discourse — Batch {batch_num}\n\n"
                    f"**Teams:** {leg['layers']['team_count']}  |  "
                    f"**Legion council seats:** {leg['layers']['legion']['seats']}  |  "
                    f"**Full-swarm voices sampled:** {leg['layers']['full_swarm']['voices_sampled']}  "
                    f"(total agents: {leg['layers']['full_swarm']['census']['total_agents']})\n\n"
                    f"**Legion synthesis:** {leg['layers']['legion']['synthesis']}\n\n"
                    f"**Final flair:** {', '.join(leg['layers']['full_swarm']['final_flair'])}\n\n"
                    f"**Chant:** {leg['layers']['full_swarm']['chant']}\n\n"
                    "## Team consensuses\n\n" +
                    "\n".join(f"- **{t['category']}** ({t['seats']} seats): {t['consensus']}"
                             for t in leg['layers']['teams'][:20])
                )
                build["files"][f"docs/legion_discourse/legion_batch_{batch_num}.md"] = legion_md
                build["file_count"] = len(build["files"])
                new_count += 1
            except Exception as _le:
                print(f"[GALAXY][legion] skipped (batch {batch_num}): {_le}")
    except Exception as _e:
        # Discourse is decorative enhancement; never block a build.
        print(f"[GALAXY][swarm] discourse skipped (batch {batch_num}): {_e}")

    return new_count


# ═══════════════════════════════════════════════════════════════════════
# NARRATIVE VAULT INJECTION — pulls from 200+ specialized topic DBs + 6
# core storyline libraries + Era-by-Age year profile. The swarm uses the
# emitted files in later phases to drive original, non-derivative stories.
# ═══════════════════════════════════════════════════════════════════════
def _gen_narrative_vault_docs(build: dict, title: str, genre: str, genre_info: dict) -> dict:
    """Synchronous narrative doc generator. Reads vault via a short-lived
    motor client so the sync phase_vision flow stays self-contained.
    Returns `{path: content}` for write-through into the build files."""
    out: dict = {}
    try:
        import asyncio
        from core import narrative_vault as _nv
        from core import narrative_vault_specialized as _nvs

        # Normalize the genre to a vault bucket
        g = (genre or "").lower()
        # Strip common suffixes so variants match buckets
        bucket = g
        for alias, target in [("mmorpg", "mmo"), ("fps", "fps"), ("tps", "tps"),
                              ("turn_based_strategy", "tactics"), ("four_x", "strategy"),
                              ("grand_strategy", "strategy"), ("city_builder", "tycoon"),
                              ("soulslike", "action_rpg"), ("metroidvania", "metroidvania"),
                              ("roguelike", "roguelike"), ("roguelite", "roguelite")]:
            if g == alias:
                bucket = target
                break

        # Pull the v6 style params if present
        style_params = build.get("style_params") or {}

        try:
            import threading as _thr
            if _thr.current_thread() is not _thr.main_thread():
                # Worker thread — motor is bound to main loop and will hang.
                # Use the in-memory static seed fallback below.
                samples = {}
            else:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Running inside async context — use run_coroutine_threadsafe
                    # Fallback: skip DB sampling, use only static seeds.
                    samples = {}
                else:
                    samples = loop.run_until_complete(_fetch_vault_samples(bucket))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                samples = loop.run_until_complete(_fetch_vault_samples(bucket))
            finally:
                loop.close()
        except Exception:
            samples = {}

        # Always also include a static snapshot from the in-memory seeds so
        # narrative files are never empty even on a cold-start DB.
        pw_seeds = _nv.PLAYWRIGHT_SEEDS.get(bucket, [])
        if not pw_seeds:
            # cross-seed fallback
            all_seeds = [s for lst in _nv.PLAYWRIGHT_SEEDS.values() for s in lst]
            pw_seeds = all_seeds[:8]

        # ── 1. MASTER story bible ──
        ey = build.get("age_era_year")
        era_profile = build.get("age_era_profile") or {}
        story_bible_lines = [
            f"# {title} — Narrative Vault Seed",
            f"## Genre bucket: `{bucket}` (source genre: `{genre}`)",
            f"## Era-by-Age target year: **{ey if ey else 'unset'}**",
            f"## Era anchor: {era_profile.get('anchor', '—')}",
            f"## Flavor tags: {', '.join(era_profile.get('flavor_tags', []))}",
            "",
            "> The swarm MUST deviate by at least one variation axis from any",
            "> canonical plot seed listed below. Use the specialized topics as",
            "> raw material; combine three or more for each major story beat.",
            "",
            "## Canonical playwright seeds (DO NOT clone — differentiate from)",
        ]
        for (ref_title, ref_plot) in pw_seeds[:12]:
            story_bible_lines.append(f"- **{ref_title}** — {ref_plot}")
        story_bible_lines.extend([
            "",
            "## Quest archetype menu (pick 3-5 non-adjacent for mains, 8+ for sides)",
        ])
        for q in _nv.QUEST_SEEDS[:18]:
            story_bible_lines.append(f"- **{q['archetype']}**: beats {q['beats']}, twists {q['twist_pool']}")
        story_bible_lines.extend([
            "",
            "## Story arc structures (choose one primary + one contrapuntal)",
        ])
        for a in _nv.STORY_ARC_SEEDS[:10]:
            story_bible_lines.append(f"- **{a['name']}**: {a['beats']}")
        story_bible_lines.extend([
            "",
            "## Storytelling techniques (require 4 minimum to be woven in)",
        ])
        for tech in _nv.STORYTELLING_SEEDS[:14]:
            story_bible_lines.append(f"- **{tech['technique']}**: {tech['usage']}")
        story_bible_lines.extend([
            "",
            "## Narration voices (pick 1 primary, 1 interlude voice for contrast)",
        ])
        for n in _nv.NARRATION_SEEDS[:10]:
            story_bible_lines.append(f"- **{n['narrator']}** ({n['pacing']}/{n['tone']}): \"{n['hook']}\"")
        out["docs/NARRATIVE_VAULT_BIBLE.md"] = "\n".join(story_bible_lines) + "\n"

        # ── 2. Specialized topic digest (from DB or static fallback) ──
        if samples:
            lines = [f"# {title} — Specialized Topic Digest", "## Pulled from 200+ vaults\n"]
            for topic, rows in samples.items():
                if not rows:
                    continue
                lines.append(f"### {topic.replace('_', ' ').title()}")
                for r in rows:
                    lines.append(f"- {r}")
                lines.append("")
            out["docs/SPECIALIZED_TOPIC_DIGEST.md"] = "\n".join(lines) + "\n"
        else:
            # Fallback: compile a smaller digest from the static seed dict
            fallback_lines = [f"# {title} — Specialized Topic Digest (static)", ""]
            picks = ["character_archetypes", "villain_archetypes", "kingdoms",
                     "cities", "magic_systems", "themes", "tones", "main_quests",
                     "mystery_types", "cultural_customs", "dialogue_one_liners",
                     "art_palettes", "factions", "artifacts", "historical_events"]
            for topic in picks:
                seeds = _nvs.SPECIALIZED_TOPICS.get(topic, [])
                if not seeds:
                    continue
                fallback_lines.append(f"### {topic.replace('_', ' ').title()}")
                for s in seeds[:8]:
                    fallback_lines.append(f"- {s}")
                fallback_lines.append("")
            out["docs/SPECIALIZED_TOPIC_DIGEST.md"] = "\n".join(fallback_lines) + "\n"

        # ── 3. Agent directive — narrative differentiation mandate ──
        out["docs/NARRATIVE_DIFFERENTIATION_MANDATE.md"] = f"""# {title} — Narrative Differentiation Mandate

The swarm (1,473,844 agents) is directed to produce a **unique, original** storyline.
Before any narrative payload is written to disk, the Playwright sub-swarm must:

1. Check the proposed plot fingerprint against `playwright_library` via
   `check_originality(db, synopsis, '{bucket}')`.
2. If similarity ≥ 0.75, apply the returned `suggested_axis` mutation
   (gender-flip, tone-inversion, setting-swap, antagonist-reveal-shift,
   scale-escalation, or time-period-shift) and re-check.
3. Weave in **at least three** specialized topics from the digest above.
4. Ensure the narrator voice, story-arc shape, and storytelling techniques
   listed in `NARRATIVE_VAULT_BIBLE.md` are all present.
5. Respect the Era-by-Age year ({ey if ey else 'unset'}) — pick palette,
   sound hardware, and UX idioms that match the flavor tags.
6. Engage in discourse across the mesh. Any phase that fails to produce
   a unique fingerprint must loop back to the Ghost + Seraphim layers
   for an authored mutation pass.
"""

        # ── 4. Swarm-consumable JSON (compact form for agent prompts) ──
        import json as _json
        swarm_feed = {
            "build_id": build.get("build_id"),
            "title": title,
            "genre_bucket": bucket,
            "age_era_year": ey,
            "era_anchor": era_profile.get("anchor"),
            "era_flavor": era_profile.get("flavor_tags", []),
            "style_params": style_params,
            "canonical_refs": [{"title": pt, "plot": pp} for (pt, pp) in pw_seeds[:10]],
            "quest_menu": [q["archetype"] for q in _nv.QUEST_SEEDS],
            "arc_menu": [a["name"] for a in _nv.STORY_ARC_SEEDS],
            "technique_menu": [t["technique"] for t in _nv.STORYTELLING_SEEDS],
            "specialized_picks": {k: v for k, v in list((samples or {}).items())[:12]},
            "mandate": "Differentiate or re-spin. Originality threshold 0.75.",
        }
        out["docs/swarm_narrative_feed.json"] = _json.dumps(swarm_feed, indent=2)

        # ── 5. Style Manifest — surfaces v6 style pickers to every phase ──
        if style_params:
            sm_lines = [
                f"# {title} — Style Manifest",
                "## v6 named-option pickers — apply consistently across all phases.",
                "",
                "| Slider | Selected option |",
                "|---|---|",
            ]
            pretty_map = {
                "graphic_style": "Graphic Style",
                "sound_style": "Sound Style",
                "music_style": "Music Style",
                "design_style": "Design Style",
                "cinematic_style": "Cinematic Style",
                "director_style": "Director Style",
                "dimension": "Dimension",
                "asset_style": "Asset Style",
                "model_style": "Model Style",
            }
            for key in ["graphic_style", "sound_style", "music_style", "design_style",
                        "cinematic_style", "director_style", "dimension",
                        "asset_style", "model_style"]:
                val = style_params.get(key, "—")
                sm_lines.append(f"| **{pretty_map.get(key, key)}** | `{val}` |")
            sm_lines.extend([
                "",
                "## Implementation notes for the swarm",
                "- **Graphic** drives material/shader choice, palette, and VFX sensibility.",
                "- **Sound** drives SFX authoring (foley vs. synthesized vs. chiptune).",
                "- **Music** drives score instrumentation, key/mode, and tempo envelope.",
                "- **Design** drives UI vocabulary, spatial composition, typographic choice.",
                "- **Cinematic** drives cutscene framing, pacing, lens, and edit rhythm.",
                "- **Director** is the overarching auteur sensibility — resolves ties.",
                "- **Dimension** drives engine/pipeline (2D sprite, 2.5D, full 3D PBR, etc.).",
                "- **Asset** drives prop / environment authoring (hand-painted, PBR, voxel…).",
                "- **Model** drives character proportion & rigging (chibi, heroic, realistic).",
                "",
                "When two sliders conflict (e.g. Graphic=pixel_16bit + Dimension=3d_rtx),",
                "resolve toward the **Director** style intent and log the decision in the",
                "swarm discourse ledger for traceability.",
            ])
            out["docs/STYLE_MANIFEST.md"] = "\n".join(sm_lines) + "\n"

    except Exception:
        out["docs/NARRATIVE_VAULT_BIBLE.md"] = f"# {title} — Narrative Vault\n\n(vault injection unavailable)\n"
    return out


async def _fetch_vault_samples(bucket: str) -> dict:
    """Async helper to sample the specialized_vault for a handful of topics."""
    try:
        from services.database import db as _db
        from core.databases import content_db as _cdb
        from core.narrative_vault_specialized import sample_specialized_context
        return await sample_specialized_context(_db, bucket, topics=[
            "character_archetypes", "villain_archetypes", "kingdoms", "cities",
            "magic_systems", "themes", "tones", "main_quests", "mystery_types",
            "cultural_customs", "dialogue_one_liners", "art_palettes", "factions",
            "artifacts", "historical_events", "atmosphere_descriptors",
        ], per_topic=4)
    except Exception:
        return {}


async def _fetch_game_knowledge_samples(bucket: str, topic_hints: list | None = None) -> dict:
    """Async helper to sample the 500-vault game_knowledge collection."""
    try:
        from services.database import db as _db
        from core.databases import content_db as _cdb
        from core.game_knowledge_vault import sample_game_knowledge_for_agents
        return await sample_game_knowledge_for_agents(
            _db, genre=bucket, topic_hints=topic_hints, per_topic=3, topic_count=28
        )
    except Exception:
        return {}


def _gen_game_knowledge_docs(build: dict, title: str, genre: str) -> dict:
    """Sync wrapper that produces docs from the 500 Game Knowledge Vaults.

    Mirrors `_gen_narrative_vault_docs`: runs a short-lived event loop,
    falls back to the static in-process topic dict when the DB isn't warm.
    Writes:
      - docs/GAME_KNOWLEDGE_VAULT.md (human-readable digest across 28 topics)
      - docs/swarm_game_knowledge_feed.json (agent-consumable compact feed)
      - docs/AGENTS_NO_LAZY_MANDATE.md (mandate forcing every phase to cite ≥3 topics)
    Also stashes `build["_gk_context"]` so downstream phases can surface it.
    """
    out: dict = {}
    try:
        import asyncio
        import json as _json
        from core import game_knowledge_vault as _gkv

        g = (genre or "").lower()
        bucket = g
        for alias, target in [("mmorpg", "mmo"), ("turn_based_strategy", "tactics"),
                              ("four_x", "strategy"), ("grand_strategy", "strategy"),
                              ("city_builder", "tycoon"), ("soulslike", "action_rpg")]:
            if g == alias:
                bucket = target
                break

        # Try to sample from DB (works when called from a worker thread)
        samples: dict = {}
        try:
            import threading as _thr
            if _thr.current_thread() is not _thr.main_thread():
                # Worker thread — motor is bound to main loop and will hang.
                # Use the in-memory static seed fallback below.
                samples = {}
            else:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    samples = {}
                else:
                    samples = loop.run_until_complete(_fetch_game_knowledge_samples(bucket))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                samples = loop.run_until_complete(_fetch_game_knowledge_samples(bucket))
            finally:
                loop.close()
        except Exception:
            samples = {}

        # Static fallback: hand-pick 24 topics from the in-memory vault
        static_topic_picks = [
            "engine_architectures", "rendering_pipelines", "physics_engines",
            "animation_systems", "ai_decision_models", "pathing_systems",
            "damage_models", "combo_systems", "inventory_systems",
            "progression_systems", "currency_systems", "loot_tables",
            "hud_layouts", "menu_patterns", "accessibility_options",
            "core_loop_patterns", "flow_state_design", "difficulty_systems",
            "save_systems", "live_ops_cadences", "revenue_models",
            "platform_profiles", "audio_spatialization", "adaptive_music_systems",
        ]

        # Build combined knowledge map (prefer DB samples, else static seeds)
        knowledge_map: dict = {}
        for topic in static_topic_picks:
            if topic in samples and samples[topic]:
                knowledge_map[topic] = list(samples[topic])[:6]
            else:
                seeds = _gkv.GAME_KNOWLEDGE_TOPICS.get(topic, [])
                if seeds:
                    knowledge_map[topic] = list(seeds)[:6]

        # ── 1. Human-readable digest ──
        ts = _gkv.topic_summary()
        lines = [
            f"# {title} — Game Knowledge Vault",
            f"## Genre bucket: `{bucket}` (source genre: `{genre}`)",
            f"## Vault scale: {ts.get('total_topics', 0)} topics × {ts.get('genres', 0)} genres × {ts.get('axes', 0)} axes "
            f"(~{ts.get('estimated_rows_at_target_6', 0):,} canonical rows)",
            "",
            "> Every phase of the swarm MUST cite **at least three** topics from this",
            "> vault in its generated modules or the file is considered *lazy* and",
            "> will be rewritten by the Ghost layer. No lazy agents allowed.",
            "",
        ]
        for topic, seeds in knowledge_map.items():
            lines.append(f"### {topic.replace('_', ' ').title()}")
            for s in seeds:
                lines.append(f"- {s}")
            lines.append("")
        out["docs/GAME_KNOWLEDGE_VAULT.md"] = "\n".join(lines) + "\n"

        # ── 2. Swarm-consumable JSON feed ──
        feed = {
            "build_id": build.get("build_id"),
            "title": title,
            "genre_bucket": bucket,
            "vault_scale": ts,
            "topics": knowledge_map,
            "variation_axes": list(_gkv.VARIATION_AXES),
            "mandate": "Reference ≥3 topics per generated module; no lazy agents.",
        }
        out["docs/swarm_game_knowledge_feed.json"] = _json.dumps(feed, indent=2)

        # ── 3. No-lazy-agents mandate ──
        out["docs/AGENTS_NO_LAZY_MANDATE.md"] = (
            f"# {title} — No Lazy Agents Mandate\n\n"
            f"The 500-DB Game Knowledge Vault is wired to every phase.\n\n"
            f"## Hard rules for every sub-swarm (1,473,844 agents)\n\n"
            f"1. Every generated code file must **cite ≥3 topics** from\n"
            f"   `docs/GAME_KNOWLEDGE_VAULT.md` in its doc header.\n"
            f"2. Every phase README must include a *Knowledge Applied* section\n"
            f"   listing the topics used, e.g. `progression_systems, loot_tables, adaptive_music_systems`.\n"
            f"3. Failure to cite triggers a Ghost-layer rewrite pass.\n"
            f"4. The vault is canonical — do not duplicate seeds verbatim;\n"
            f"   mutate along one of the {len(_gkv.VARIATION_AXES)} variation axes.\n"
            f"5. Mandatory variation axes: {', '.join(list(_gkv.VARIATION_AXES)[:8])}, …\n\n"
            f"## Summary of source\n- File: `core/game_knowledge_vault.py`\n"
            f"- Collection: `game_knowledge_vault` (PROTECTED from cold storage)\n"
            f"- Topic count: {ts.get('total_topics', 0)}\n"
        )

        # ── 4. Stash context for downstream phases ──
        try:
            build["_gk_context"] = {
                "bucket": bucket,
                "topic_count": len(knowledge_map),
                "topic_keys": list(knowledge_map.keys()),
                "axes": list(_gkv.VARIATION_AXES)[:12],
            }
        except Exception:
            pass
    except Exception:
        out["docs/GAME_KNOWLEDGE_VAULT.md"] = (
            f"# {title} — Game Knowledge Vault\n\n(vault injection unavailable)\n"
        )
    return out


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: VISION & CONCEPT — Design doc, config, project setup
# Minimum 200 pages (10,000+ lines) of foundational code
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# PHASE & MUTATION GENERATORS — extracted Jun 2026 → routes/galaxy_studio_phases.py
# Re-imported so _call_phase_func's globals() dispatch + external callers keep working.
# (Imported AFTER the data-tables/helpers above so the _gs proxy resolves at call time.)
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_phases import (  # noqa: F401,E402
    _extract_active_mutations, _gen_all_mutation_permutations, _gen_animation_pattern_file, _gen_mutation_combo_module,
    _gen_mutation_module, _gen_mutation_operator_module, _gen_mutation_permutation_engine, _gen_mutation_permutation_registry,
    _mut_camel, _phase_ai_behavior, _phase_ambiance, _phase_animations_pack,
    _phase_architecture, _phase_assets, _phase_backend, _phase_balancing,
    _phase_cinematics, _phase_compilation, _phase_complexity, _phase_cutscenes,
    _phase_easter_eggs, _phase_engine, _phase_enhancement, _phase_environment,
    _phase_fine_tuning, _phase_framework, _phase_frontend, _phase_gameplay,
    _phase_generic, _phase_graphics, _phase_immersion, _phase_intricacy,
    _phase_locomotion_pack, _phase_lore, _phase_mechanics, _phase_menu,
    _phase_middleware, _phase_music, _phase_networking, _phase_permutations,
    _phase_physics_math, _phase_plot_intrigue, _phase_polish, _phase_psychology,
    _phase_scope, _phase_settings, _phase_sfx, _phase_sota,
    _phase_sound, _phase_story_style_pack, _phase_system, _phase_testing,
    _phase_tutorial, _phase_vfx, _phase_vision, _phase_world_gen,
    _PHASE_FUNC_MAP,
)


def _call_phase_func(phase_id: str, build: dict) -> dict:
    """Call the appropriate generator function for a phase_id.
    
    ★ HARDENING LAYER (2026-04-20) ★
    Every path is wrapped in try/except so a bug, missing DB, malformed
    build dict, or thread-unsafe global NEVER crashes the pipeline.
    Guaranteed contract:
      • Always returns a dict[str, str]
      • Always returns at least a stub file on catastrophic failure
      • Never raises — the outer pipeline trusts this to be total.
    """
    # ── Input guard ─────────────────────────────────────────────────
    try:
        t = build.get("title") or "Untitled"
        g = build.get("genre") or "rpg"
        gi = build.get("genre_info") or {}
        v = build.get("game_vision", "")
        sy = build.get("system_architecture", "")
        la = build.get("world_laws", "")
        ins = build.get("agent_instructions", "")
        sc = build.get("scale_info") or {}
        m = sc.get("multiplier", 1) if isinstance(sc, dict) else 1
        complexity = build.get("complexity", "moderate")
        age_target = build.get("age_target", "teen")
    except Exception as _ig:
        print(f"[GALAXY _call_phase_func] input guard triggered: {_ig}")
        return _generate_fallback_files(0, "Untitled", "rpg", phase_id, f"input_guard: {_ig}")

    # ── Phase spec lookup ───────────────────────────────────────────
    phase_info = None
    try:
        for p in BUILD_PHASES:
            if p.get("id") == phase_id:
                phase_info = p
                break
    except Exception:
        phase_info = None
    if phase_info is None:
        phase_info = {"id": phase_id, "name": phase_id, "agents": 50000, "batch": 1}

    # ── Primary path: dedicated function ────────────────────────────
    func_name = _PHASE_FUNC_MAP.get(phase_id)
    if func_name:
        func = globals().get(func_name)
        if func is not None:
            try:
                if func_name == "_phase_vision":
                    result = func(build, t, g, gi, v, sy, la, ins, complexity, age_target)
                elif func_name == "_phase_scope":
                    result = func(build, t, g, gi, v, sy, la, ins, m)
                elif func_name == "_phase_networking":
                    result = func(build, t, g, m, v, sy, la, ins)
                elif func_name == "_phase_permutations":
                    result = func(build, t, g, m)
                else:
                    result = func(build, t, g)
                # Contract check
                if isinstance(result, dict) and result:
                    return result
                print(f"[GALAXY phase][{phase_id}] dedicated returned empty — falling back to generic")
            except Exception as _pe:
                print(f"[GALAXY phase][{phase_id}] dedicated FAILED: {_pe} — falling back to generic")

    # ── Secondary path: generic generator ───────────────────────────
    try:
        result = _phase_generic(build, t, g, phase_info)
        if isinstance(result, dict) and result:
            return result
        print(f"[GALAXY phase][{phase_id}] generic returned empty — using fallback stub")
    except Exception as _ge:
        print(f"[GALAXY phase][{phase_id}] generic FAILED: {_ge} — using fallback stub")

    # ── Tertiary path: fallback files (guaranteed to work) ──────────
    try:
        return _generate_fallback_files(phase_info.get("batch", 0), t, g, phase_info.get("name", phase_id),
                                         "phase_all_paths_failed")
    except Exception as _fe:
        # Final safety net — even the fallback generator failed.
        print(f"[GALAXY phase][{phase_id}] fallback FAILED: {_fe} — returning stub")
        return {
            f"stubs/{phase_id}/emergency_stub.ts": (
                f"// Emergency stub for phase '{phase_id}' — all generators failed.\n"
                f"// title={t} genre={g}\n"
                f"export const _emergency_{phase_id.replace('-', '_')} = {{\n"
                f"  phase: '{phase_id}',\n"
                f"  status: 'emergency_fallback',\n"
                f"  title: '{t}',\n"
                f"  genre: '{g}',\n"
                f"  error: 'all_phase_generators_failed',\n"
                f"}};\n"
            )
        }


def _expand_for_scale(files: dict, title: str, genre: str, multiplier: int, vision: str, systems: str, laws: str, instructions: str):
    """Dynamically expand file count based on scale multiplier. NO LIMITS. 10x MINIMUM."""
    
    # ═══ ENEMIES — massively expanded ═══
    enemy_types = [
        "Goblin", "Skeleton", "Dragon", "Demon", "Wraith", "Golem", "Spider", "Wolf",
        "Bandit", "Necromancer", "Lich", "Ogre", "Troll", "Vampire", "Werewolf", "Elemental",
        "Hydra", "Phoenix", "Chimera", "Minotaur", "Medusa", "Kraken", "Griffin", "Basilisk",
        "Wyvern", "DarkKnight", "Gargoyle", "Imp", "Succubus", "Balrog", "Beholder", "MindFlayer",
        "Doppelganger", "Shade", "Revenant", "DeathKnight", "BoneGolem", "FleshGolem", "IronGolem",
        "StormElemental", "FrostElemental", "FireElemental", "EarthElemental", "VoidElemental",
        "ShadowAssassin", "PlagueDoctor", "BloodMage", "RuneGuardian", "CrystalSentinel",
        "TreeAncient", "SeaSerpent", "SandWurm", "ThunderBird", "DireWolf", "GiantSpider",
        "PoisonDrake", "FrostDrake", "FireDrake", "VoidDrake", "StormDrake",
    ]
    max_tiers = min(multiplier // 5 + 1, 200)
    for enemy in enemy_types:
        for tier in range(1, max_tiers + 1):
            files[f"entities/enemies/{enemy.lower()}/{enemy}Tier{tier}.ts"] = _gen_entity_file(f"{enemy}Tier{tier}", "enemy", title, genre)

    # ═══ ALLIES / NPCs — new category ═══
    ally_types = [
        "Paladin", "Cleric", "Bard", "Ranger", "Druid", "Monk", "Sorcerer", "Warlock",
        "Barbarian", "Fighter", "Rogue", "Wizard", "Artificer", "BloodHunter", "Mystic",
        "Merchant", "Blacksmith", "Alchemist", "Innkeeper", "QuestGiver", "TrainerNPC",
        "GuardCaptain", "TownCrier", "Librarian", "SageNPC", "StableKeeper", "Ferryman",
        "MysticOracle", "DungeonGuide", "ArenaChampion", "GuildLeader",
    ]
    max_ally_tiers = min(multiplier // 10 + 1, 50)
    for ally in ally_types:
        for tier in range(1, max_ally_tiers + 1):
            files[f"entities/allies/{ally.lower()}/{ally}Tier{tier}.ts"] = _gen_entity_file(f"{ally}Tier{tier}", "ally", title, genre)

    # ═══ BOSSES — dedicated boss files ═══
    boss_types = [
        "DragonKing", "LichEmperor", "DemonLord", "VoidTitan", "StormGod",
        "FrostQueen", "FlameEmpress", "ShadowPrince", "PlagueKing", "CrystalArchon",
        "WorldSerpent", "MoonBeast", "SunAvatar", "AbyssalLeviathin", "CosmicHorror",
        "MechanicalOverlord", "NatureAvatar", "TimeWarden", "FateWeaver", "ChaosSovereign",
    ]
    max_boss_tiers = min(multiplier // 10 + 1, 30)
    for boss in boss_types:
        for tier in range(1, max_boss_tiers + 1):
            files[f"entities/bosses/{boss.lower()}/{boss}Tier{tier}.ts"] = _gen_entity_file(f"{boss}Tier{tier}", "boss", title, genre)

    # ═══ WEAPONS — all types × quality tiers ═══
    weapons = [
        "Sword", "Axe", "Bow", "Staff", "Dagger", "Mace", "Spear", "Crossbow",
        "Wand", "Shield", "Greatsword", "Katana", "Scythe", "Flail", "Halberd", "Whip",
        "Rapier", "WarHammer", "Glaive", "Trident", "Javelin", "Sling", "Chakram", "Claw",
        "Fist", "Musket", "Blunderbuss", "Cannon", "BattleAxe", "MorningStar", "Pike", "Lance",
    ]
    qualities = ["Rusty", "Common", "Refined", "Superior", "Masterwork", "Legendary", "Mythic", "Divine", "Cosmic", "Apocalyptic"]
    for weapon in weapons:
        for quality in qualities:
            files[f"data/weapons/{quality.lower()}_{weapon.lower()}.ts"] = _gen_weapon_data(f"{quality}{weapon}", title, genre)

    # ═══ BIOMES — zones × tiers ═══
    biomes = [
        "Forest", "Desert", "Tundra", "Swamp", "Mountain", "Ocean", "Volcano", "Cave",
        "Jungle", "Plains", "Ruins", "Dungeon", "Castle", "Skylands", "Abyss", "Crystal",
        "Graveyard", "Library", "Arena", "Garden", "Factory", "Temple", "Prison", "Sewer",
        "Clocktower", "Observatory", "Laboratory", "Marketplace", "Harbor", "Battlefield",
        "Nursery", "Throne", "Crypt", "Catacomb", "Mine", "Quarry", "Oasis", "Glacier",
        "Reef", "Archipelago", "Canyon", "Mesa", "Steppe", "Savanna", "Mangrove", "Bayou",
        "Taiga", "Peat", "Caldera", "Geyser",
    ]
    max_zone_tiers = min(multiplier // 10 + 1, 100)
    for biome in biomes:
        for tier in range(1, max_zone_tiers + 1):
            files[f"world/biomes/{biome.lower()}/{biome}Tier{tier}.ts"] = _gen_biome_file(f"{biome}Tier{tier}", title, genre)

    # ═══ ITEM SETS — complete equipment sets ═══
    item_sets = [
        "DragonSlayer", "ShadowDancer", "HolyAvenger", "StormBringer", "FrostWarden",
        "PlagueBringer", "VoidWalker", "SunKnight", "MoonPriest", "StarForged",
        "BloodBound", "IronWill", "CrystalHeart", "FlameWrath", "NatureGuard",
        "ArcaneScholar", "DeathBringer", "LightBearer", "ChaosCrown", "OrderShield",
    ]
    equipment_slots = ["Helm", "Chest", "Legs", "Boots", "Gloves", "Cape", "Ring", "Amulet", "Belt", "Pauldrons", "Bracers", "Weapon"]
    for set_name in item_sets:
        for piece in equipment_slots:
            files[f"data/sets/{set_name.lower()}/{set_name}{piece}.ts"] = _gen_weapon_data(f"{set_name}{piece}", title, genre)

    # ═══ SKILLS — per class × tier ═══
    classes = ["Warrior", "Mage", "Ranger", "Rogue", "Cleric", "Paladin", "Necromancer", "Druid",
               "Bard", "Monk", "Warlock", "Sorcerer", "Berserker", "Assassin", "Templar", "Shaman"]
    max_skill_tiers = min(multiplier // 20 + 1, 30)
    for cls in classes:
        for tier in range(1, max_skill_tiers + 1):
            files[f"data/skills/{cls.lower()}/{cls}SkillTier{tier}.ts"] = _gen_data_file(f"{cls.lower()}_skills_tier_{tier}", f"{cls} class skills tier {tier} with abilities, passives, ultimates", title, genre)

    # ═══ ASSET MANIFESTS — for extreme scale ═══
    if multiplier > 10:
        asset_categories = ["textures", "models", "sounds", "animations", "particles",
                           "materials", "prefabs", "scripts", "shaders", "configs"]
        manifests_per_cat = min(multiplier // 50 + 1, 200)
        for cat in asset_categories:
            for batch in range(manifests_per_cat):
                files[f"assets/manifests/{cat}_batch_{batch:04d}.json"] = _gen_asset_manifest(cat, batch, title, genre, multiplier)


def _build_description_block(title: str, genre: str, vision: str, systems: str, laws: str, instructions: str) -> str:
    """Build a rich description block that gets injected into every generated file."""
    parts = [f"// ═══ {title} — Galaxy Studio Factory ═══"]
    parts.append(f"// Genre: {genre} | 1,444,700 agents | 15 synergy links")
    if vision:
        parts.append(f"// GAME VISION: {vision[:200]}")
    if systems:
        parts.append(f"// SYSTEM ARCHITECTURE: {systems[:200]}")
    if laws:
        parts.append(f"// WORLD LAWS: {laws[:200]}")
    if instructions:
        parts.append(f"// AGENT INSTRUCTIONS: {instructions[:200]}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL CODE AMPLIFIER — Ensures EVERY file reaches 30,000+ lines / 1MB+
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# AAA CODE-GENERATORS — extracted Jun 2026 → routes/galaxy_studio_codegen.py
# Re-imported here so every existing reference (and external importers like
# routes.galaxy_studio_state._amplify) keeps working unchanged.
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_codegen import (  # noqa: F401
    MAX_GAME_FILE_BYTES, _amplify, _amplify_uncapped, _cap_file_size,
    _expand_massive, _expand_massive_uncapped, _gen_ai_behavior_tree, _gen_animation_hook,
    _gen_asset_manifest, _gen_audio_hook, _gen_babel_config, _gen_biome_file,
    _gen_camera_hook, _gen_color_utils, _gen_combat_store, _gen_combat_types,
    _gen_component_aaa, _gen_constants, _gen_data_file, _gen_design_directives,
    _gen_design_doc, _gen_entity_file, _gen_entity_store, _gen_eslint_config,
    _gen_formatters, _gen_game_loop_hook, _gen_helpers, _gen_input_hook,
    _gen_inventory_hook, _gen_inventory_store, _gen_inventory_types, _gen_layout_code,
    _gen_logic_aaa, _gen_math_utils, _gen_metro_config, _gen_network_hook,
    _gen_network_store, _gen_network_types, _gen_networking_code, _gen_physics_hook,
    _gen_procgen_code, _gen_screen_aaa, _gen_shader_code, _gen_test_file,
    _gen_types, _gen_ui_store, _gen_ui_types, _gen_validators,
    _gen_weapon_data, _gen_world_store, _gen_world_types, hash,
)


def _create_build(title: str, genre: str, subgenre: str, description: str, complexity: int = 10, game_vision: str = "", system_architecture: str = "", world_laws: str = "", agent_instructions: str = "", scale: str = "", target_files: int = 0, target_size_gb: float = 0, age_target: str = "T", graphics_era: int = 7, npc_density: int = 7, sound_era: int = 7, world_size: int = 7, physics_realism: int = 7, ai_complexity: int = 7, lighting_engine: int = 7, particle_effects: int = 7, destruction_physics: int = 7, narrative_branching: int = 7, economy_complexity: int = 7, multiplayer_max: int = 7, weather_systems: int = 7, day_night_cycle: int = 7, animation_fluidity: int = 7, post_processing: int = 7, foliage_density: int = 7, water_simulation: int = 7, ui_minimalism: int = 7, loot_variety: int = 7, crafting_depth: int = 7, dialog_depth: int = 7, stealth_mechanics: int = 7, vehicle_simulation: int = 7, biome_diversity: int = 7, faction_reputation: int = 7, skill_system: int = 7, gore_system: int = 7, modding_support: int = 7, animation_style: str = "smooth", camera_effects: bool = True, storyline_style: str = "heroic", game_pace: str = "standard", difficulty_curve: str = "steady", perspective: str = "third_person", combat_style: str = "action_rpg", visual_style: str = "hand_painted", game_tone: str = "epic", progression_type: str = "open_world", audio_mood: str = "orchestral", locomotion_depth: int = 5, locomotion_style: str = "als") -> dict:
    """Create a new Galaxy Studio build with rich descriptions and scale parsing."""
    
    # Enforce SOTA Directive
    if complexity < 7:
        complexity = 7  # Advanced games standardized as minimum outcome
    
    sota_prefix = f"""[SOTA DIRECTIVE ACTIVE: GOD-TIER AAA STATUS]
- 10 Levels of Complexity Engaged (Current Level: {complexity}).
- Whisper protocols and synergy networks synchronized for maximum inter-agent communication.
- Output MUST exceed standard pipelines. Real algorithms, fluid mechanics, and deep lore generation required.
"""
    agent_instructions = sota_prefix + "\n" + agent_instructions
    genre_info = GALAXY_GENRES.get(genre)
    if not genre_info:
        genre = "rpg"
        genre_info = GALAXY_GENRES["rpg"]

    # Parse scale from natural language + explicit targets
    scale_info = _parse_scale(scale, target_files, target_size_gb)

    build_id = str(uuid.uuid4())[:12]
    build = {
        "build_id": build_id,
        "title": title,
        "genre": genre,
        "subgenre": subgenre,
        "genre_info": genre_info,
        "description": description or f"A {genre_info['name']} game called {title}",
        "complexity": complexity,
        "age_target": age_target,
        "graphics_era": graphics_era,
        "npc_density": npc_density,
        "sound_era": sound_era,
        "world_size": world_size,
        "physics_realism": physics_realism,
        "ai_complexity": ai_complexity,
        "lighting_engine": lighting_engine,
        "particle_effects": particle_effects,
        "destruction_physics": destruction_physics,
        "narrative_branching": narrative_branching,
        "economy_complexity": economy_complexity,
        "multiplayer_max": multiplayer_max,
        "weather_systems": weather_systems,
        "day_night_cycle": day_night_cycle,
        "animation_fluidity": animation_fluidity,
        "animation_style": animation_style,
        "camera_effects": camera_effects,
        # ═══ 2026-02 Story & Style ═══
        "storyline_style": storyline_style,
        "game_pace": game_pace,
        "difficulty_curve": difficulty_curve,
        "perspective": perspective,
        "combat_style": combat_style,
        "visual_style": visual_style,
        "game_tone": game_tone,
        "progression_type": progression_type,
        "audio_mood": audio_mood,
        # ═══ 2026-02 Locomotion ═══
        "locomotion_depth": locomotion_depth,
        "locomotion_style": locomotion_style,
        "post_processing": post_processing,
        "foliage_density": foliage_density,
        "water_simulation": water_simulation,
        "ui_minimalism": ui_minimalism,
        "loot_variety": loot_variety,
        "crafting_depth": crafting_depth,
        "dialog_depth": dialog_depth,
        "stealth_mechanics": stealth_mechanics,
        "vehicle_simulation": vehicle_simulation,
        "biome_diversity": biome_diversity,
        "faction_reputation": faction_reputation,
        "skill_system": skill_system,
        "gore_system": gore_system,
        "modding_support": modding_support,
        "game_vision": game_vision,
        "system_architecture": system_architecture,
        "world_laws": world_laws,
        "agent_instructions": agent_instructions,
        "scale": scale,
        "scale_info": scale_info,
        # Echo the explicit target from the scale-parser so /status can
        # return target_files directly without recomputing.
        "target_files": int(scale_info.get("target_files", 0) or 0),
        "status": "building",
        "current_phase": 0,
        "phases": [],
        "total_agents": AGENT_MANIFEST["total"]["agents"],
        "agents_active": 0,
        "synergy_activations": [],
        "files": {},
        "file_count": 0,
        "eas_build_id": None,
        "eas_build_status": None,
        "download_url": None,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    }

    # Initialize phases
    for p in BUILD_PHASES:
        build["phases"].append({
            "id": p["id"],
            "name": p["name"],
            "agents": p["agents"],
            "pct": p["pct"],
            "icon": p["icon"],
            "color": p["color"],
            "status": "pending",
            "started_at": None,
            "completed_at": None,
        })

    _builds[build_id] = build
    return build


async def _advance_build(build_id: str) -> dict:
    """Generate one durable batch under the same physical admission rules."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if _build_has_live_work(build_id):
        raise HTTPException(409, "Build already owns live work; poll its status.")
    if _any_build_has_live_work():
        raise HTTPException(429, "Another build owns the generation slot.")
    if build.get("_bg_stop_requested"):
        raise HTTPException(409, "Build was stopped; explicitly start it to resume generation.")
    current_phase_idx = max(0, int(build.get("current_phase", 0)))
    phases = build.get("phases") or []
    if current_phase_idx >= len(BUILD_PHASES):
        if phases and all(phase.get("status") == "completed" for phase in phases):
            return build
        raise HTTPException(409, "Build progress has no verified completed phase set.")
    current_batch = BUILD_PHASES[current_phase_idx]["batch"]
    owner = asyncio.current_task()
    _active_runners.add(build_id)
    _background_tasks[build_id] = owner
    build["status"] = "building"
    build["_bg_status"] = "running"
    build["_bg_current_batch"] = current_batch
    build["_bg_started"] = datetime.utcnow().isoformat()
    build["_bg_last_heartbeat"] = build["_bg_started"]
    build["_bg_deadline_monotonic"] = _build_clock.monotonic() + 180.0
    try:
        await _await_build_io(build, _check_build_resources, build)
        await _save_build_required(build)
        future = _track_build_future(
            build_id, _WORKER_POOL.submit(_safe_generate_batch, build_id, current_batch)
        )
        batch, files, error = await _await_build_future(build, future)
        if batch != current_batch or error or not isinstance(files, dict) or not files:
            raise GalaxyBuildStopped(error or "batch_empty_output")
        build.setdefault("files", {}).update(files)
        await _await_build_io(build, _flush_to_vault, build, True)
        files.clear()
        build.get("_gen_cache", {}).pop(f"batch_{current_batch}", None)
        _check_build_continuation(build)
        phase_ids = BUILD_BATCHES.get(current_batch, [])
        for phase_id in phase_ids:
            index = _PHASE_INDEX_MAP.get(phase_id, -1)
            if 0 <= index < len(phases):
                phases[index]["status"] = "completed"
                phases[index]["completed_at"] = datetime.utcnow().isoformat()
        build["current_phase"] = (
            max((_PHASE_INDEX_MAP.get(pid, 0) for pid in phase_ids), default=current_phase_idx) + 1
        )
        build["_bg_last_batch_completed"] = current_batch
        build.setdefault("_bg_phase_log", []).append(
            {
                "batch": current_batch,
                "status": "success",
                "source": "worker",
                "completed_at": datetime.utcnow().isoformat(),
                "file_count": build["file_count"],
            }
        )
        if (
            build["current_phase"] >= len(BUILD_PHASES)
            and phases
            and all(phase.get("status") == "completed" for phase in phases)
        ):
            build["status"] = "completed"
            build["_bg_status"] = "completed"
            build["completed_at"] = datetime.utcnow().isoformat()
        else:
            build["_bg_status"] = "manual"
        await _save_build_required(build)
        return build
    except asyncio.CancelledError:
        _mark_build_stop(build, "runner_cancelled", failed=False)
        raise
    except Exception as exc:
        reason = exc.reason if isinstance(exc, GalaxyBuildStopped) else "batch_generation_failed"
        _mark_build_stop(build, reason)
        raise HTTPException(503, f"Build stopped: {reason}. Partial artifacts are retained.") from None
    finally:
        build["_bg_drain_pending"] = _physical_build_workers(build_id) > 0
        await _drain_build_workers(build_id)
        build["_bg_drain_pending"] = False
        build.pop("_bg_deadline_monotonic", None)
        if build.get("_bg_stop_requested"):
            build["_gen_cache"] = {}
            build["status"] = build.get("_bg_stop_target", "failed")
            build["_bg_status"] = build["status"]
            build["_bg_partial_artifacts"] = bool(build.get("_vault_active") or build.get("files"))
        try:
            await _save_build(build)
        finally:
            _active_runners.discard(build_id)
            if _background_tasks.get(build_id) is owner:
                _background_tasks.pop(build_id, None)


def _get_phase_synergies(phase_id: str) -> list:
    """Get which synergy links activate for a given phase."""
    # Phase-to-constellation mapping
    phase_constellations = {
        "vision": ["mega", "hyper"],
        "deep_design": ["hyper", "mega", "quantum"],
        "quantum_core": ["quantum", "hexa"],
        "game_factory": ["hexa", "hyper", "mega", "quantum"],
        "code_gen": ["hexa", "pipeline", "quantum"],
        "art_audio": ["hexa", "hyper"],
        "narrative": ["mega", "hexa", "quantum"],
        "qa_gauntlet": ["pipeline", "hexa", "hyper", "quantum"],
        "marketing": ["mega", "deploy"],
        "platform": ["deploy", "hexa", "pipeline"],
        "production": ["pipeline", "deploy", "hexa"],
        "compilation": ["deploy", "hexa", "pipeline", "quantum", "hyper", "mega"],
    }
    active_constellations = phase_constellations.get(phase_id, ["hexa"])
    activated = []
    for link in SYNERGY_NETWORK["links"]:
        if link["from"] in active_constellations or link["to"] in active_constellations:
            activated.append({
                "from": link["from"],
                "to": link["to"],
                "strength": link["strength"],
                "desc": link["desc"],
            })
    return activated


async def _package_build(build_id: str) -> str:
    """Package build files into downloadable ZIP.
    Reads directly from the on-disk build-vault shards (streaming, no
    full-RAM copy) so we can package 250k-file builds without OOM."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(400, "Build not found")

    safe_id = _safe_segment(build_id, what="build_id")
    slug = _safe_slug(build.get("title") or "game")
    zip_dir = _resolve_under_dir("/tmp/galaxy_studio", safe_id)
    os.makedirs(zip_dir, exist_ok=True)
    zip_path = _resolve_under_dir(zip_dir, f"{slug}-game.zip")

    # Prefer streaming from the vault when present — this is the ONLY path
    # that works for massive builds (files no longer in RAM).
    from core import build_vault as _bv
    vault_count = _bv.get_file_count(build_id)
    mem_files = build.get("files") or {}
    if vault_count == 0 and not mem_files:
        raise HTTPException(400, "No files to package")

    # Compress on a worker thread — zipping 10k+ files with DEFLATE is CPU-heavy
    # and previously blocked the event loop at build completion (the last blip).
    def _build_zip():
        written = set()
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            # 1) stream vault shards (newest wins on duplicates)
            for path, content in _bv.iter_files(build_id):
                if path in written:
                    continue
                _zip_write_file(zf, f"{slug}/{path}", content)
                written.add(path)
            # 2) any in-memory files not yet flushed
            for path, content in mem_files.items():
                if path in written:
                    continue
                _zip_write_file(zf, f"{slug}/{path}", content)
                written.add(path)
    await asyncio.to_thread(_build_zip)

    return zip_path


# ═══════════════════════════════════════════════════════════════════════
# BINARY-SAFE FILE HELPERS
# ═══════════════════════════════════════════════════════════════════════
_BINARY_PREFIX = "__BINARY_BASE64__"

def _zip_write_file(zf, archive_path: str, content: str):
    """Write a file to a ZipFile, handling binary base64-encoded content."""
    import base64
    if isinstance(content, str) and content.startswith(_BINARY_PREFIX):
        zf.writestr(archive_path, base64.b64decode(content[len(_BINARY_PREFIX):]))
    else:
        zf.writestr(archive_path, content)

def _disk_write_file(full_path: str, content: str):
    """Write a file to disk, handling binary base64-encoded content."""
    import base64
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if isinstance(content, str) and content.startswith(_BINARY_PREFIX):
        with open(full_path, 'wb') as f:
            f.write(base64.b64decode(content[len(_BINARY_PREFIX):]))
    else:
        with open(full_path, 'w') as f:
            f.write(content)

# ═══════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# MOVED (Jun 2026): /manifest + /genres extracted → galaxy_studio_manifest.py
# (read static data from galaxy_studio_constants.py); mounted near top of file.
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# MOVED (Jun 2026): /capabilities/catalog, /pipeline/catalog, /datasets/catalog
# delegators were extracted → routes/galaxy_studio_catalogs.py and mount on
# their original public paths via include_router near the end of this file.
# (No stub here — a decorated stub would shadow the sub-router's real route.)
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# AGENT ONCE-OVER (/agents/once-over, /agents/once-over/last) was extracted in
# Jun 2026 → routes/galaxy_studio_agents.py (self-contained, no build state).
# VAULT ADMIN (/admin/vault/stats, /admin/vault/prune) was extracted in Jun
# 2026 → routes/galaxy_studio_vault_admin.py. Both mount on their original
# public paths via include_router near the end of this file.
# ═══════════════════════════════════════════════════════════════════════


@router.post("/create")
async def create_build(req: CreateRequest):
    """Start a Galaxy Studio build with all 1,444,700 agents, rich descriptions, and scale parsing."""
    build = _create_build(
        req.title, req.genre, req.subgenre or "", req.description, req.complexity,
        req.game_vision, req.system_architecture, req.world_laws, req.agent_instructions,
        req.scale, req.target_files, req.target_size_gb, req.age_target,
        req.graphics_era, req.npc_density, req.sound_era, req.world_size, req.physics_realism, req.ai_complexity, req.lighting_engine, req.particle_effects, req.destruction_physics, req.narrative_branching, req.economy_complexity, req.multiplayer_max, req.weather_systems, req.day_night_cycle, req.animation_fluidity, req.post_processing, req.foliage_density, req.water_simulation, req.ui_minimalism, req.loot_variety, req.crafting_depth, req.dialog_depth, req.stealth_mechanics, req.vehicle_simulation, req.biome_diversity, req.faction_reputation, req.skill_system, req.gore_system, req.modding_support,
        req.animation_style, req.camera_effects,
        req.storyline_style, req.game_pace, req.difficulty_curve,
        req.perspective, req.combat_style, req.visual_style,
        req.game_tone, req.progression_type, req.audio_mood,
        req.locomotion_depth, req.locomotion_style
    )
    # Store any extra_params (new v2 sliders) on the build for phase generators to use
    extra = getattr(req, "extra_params", None) or {}
    if isinstance(extra, dict) and extra:
        build["extra_params"] = extra
    # ═══ v3: Stamp Game Era onto build ═══
    if req.era_id:
        build["era_id"] = req.era_id
        build["era_label"] = req.era_label or ""
        build["era_year"] = req.era_year or ""
    # ═══ v5: Era-by-Age (year 1985-2030). Swarm uses this to pick year-specific
    # hardware/cultural vocabulary, palettes, and UX idioms that match the
    # target cohort memory (e.g. 1995 = PS1 polygons, 2015 = live-service).
    if req.age_era_year:
        try:
            yr = max(1985, min(2030, int(req.age_era_year)))
            build["age_era_year"] = yr
            # Persist a flavor profile for phase generators
            from core.narrative_vault_specialized import build_era_year_profile
            build["age_era_profile"] = build_era_year_profile(yr)
        except Exception as _ee:
            print(f"[GALAXY] age_era_year coercion failed: {_ee}")
    # ═══ v6: Style pickers — graphic/sound/music/design/cinematic/director/
    # dimension/asset/model. Stamped onto build for phase-generator consumption.
    sp = getattr(req, "style_params", None) or {}
    if isinstance(sp, dict) and sp:
        # Sanitize: only keep str→str entries, cap at ~30 keys
        clean = {str(k): str(v)[:64] for k, v in list(sp.items())[:30]
                 if isinstance(k, str) and isinstance(v, (str, int, float))}
        if clean:
            build["style_params"] = clean
    # ═══ v4: Multi-genre / multi-subgenre fusion ═══
    # When the user picks multiple genres (e.g. RPG + Tycoon + Open World),
    # the primary `genre` stays the "lead" (for backward-compat code paths)
    # while the fused list unlocks hybrid generation + boosted delivery floor
    # (every added genre bumps the target file count 30 % up, capped at 3.0 ×).
    primary_genre = build["genre"]
    primary_sub = build.get("subgenre") or ""
    seen_g: set = set()
    genres_fused: list = []
    for g in [primary_genre, *(list(req.genres or []))]:
        gg = (g or "").strip()
        if gg and gg not in seen_g:
            seen_g.add(gg); genres_fused.append(gg)
    seen_s: set = set()
    subs_fused: list = []
    for s in [primary_sub, *(list(req.subgenres or []))]:
        ss = (s or "").strip()
        if ss and ss not in seen_s:
            seen_s.add(ss); subs_fused.append(ss)
    build["genres"] = genres_fused
    build["subgenres"] = subs_fused
    build["fusion_count"] = len(genres_fused)
    build["is_fusion"] = len(genres_fused) > 1
    # ★ FUSION SIZE GUARD (2026-02 hotfix) ★
    # Previously the multiplier climbed to 3.0× which — when applied AFTER the
    # 250k floor-pass ceiling — silently produced builds targeting up to
    # 750k files and OOM-killed the pod (surfaced to the UI as 502/520 at
    # "initializing"). Per user directive: "limit fusion increase on size,
    # keep 250,000 files limit". We now:
    #   (a) cap the multiplier at 1.6× (so fusion still consumes a LARGER
    #       share of the 250k budget but can't blow past it), and
    #   (b) re-clamp floor_target to 250,000 AFTER the multiplier is applied
    #       (see MASSIVE-DELIVERY FLOOR PASS below).
    build["fusion_multiplier"] = min(1.6, 1.0 + 0.12 * max(0, len(genres_fused) - 1)) if build["is_fusion"] else 1.0
    # ═══ 2026-05-15 — Hyper-granular matrices (9 tensors). Stamp onto the
    # build doc so phase generators + AgentKnowledgeRAG can ground every
    # batch against the user's exact dial settings. We deep-copy and sanitise
    # to avoid storing surprising non-numeric values inside the tensor.
    def _sanitise_matrix(m):
        if not isinstance(m, dict):
            return None
        out: dict = {}
        for phase_id, axes in list(m.items())[:64]:
            if not isinstance(phase_id, str) or not isinstance(axes, dict):
                continue
            inner: dict = {}
            for axis_id, val in list(axes.items())[:16]:
                if not isinstance(axis_id, str):
                    continue
                try:
                    inner[axis_id] = int(val)
                except (TypeError, ValueError):
                    continue
            if inner:
                out[phase_id[:48]] = inner
        return out or None

    matrices_payload = {
        "narrative_phases":    _sanitise_matrix(getattr(req, "narrative_phases", None)),
        "mechanics_matrix":    _sanitise_matrix(getattr(req, "mechanics_matrix", None)),
        "world_matrix":        _sanitise_matrix(getattr(req, "world_matrix", None)),
        "art_matrix":          _sanitise_matrix(getattr(req, "art_matrix", None)),
        "audio_matrix":        _sanitise_matrix(getattr(req, "audio_matrix", None)),
        "tech_matrix":         _sanitise_matrix(getattr(req, "tech_matrix", None)),
        "monetisation_matrix": _sanitise_matrix(getattr(req, "monetisation_matrix", None)),
        "qa_matrix":           _sanitise_matrix(getattr(req, "qa_matrix", None)),
        "agent_matrix":        _sanitise_matrix(getattr(req, "agent_matrix", None)),
        # 2026-05-15 — second wave matrices (DBs · Styles · Mutation · Flair)
        "vector_db_matrix":    _sanitise_matrix(getattr(req, "vector_db_matrix", None)),
        "plagiarism_matrix":   _sanitise_matrix(getattr(req, "plagiarism_matrix", None)),
        "rdbms_matrix":        _sanitise_matrix(getattr(req, "rdbms_matrix", None)),
        "styles_matrix":       _sanitise_matrix(getattr(req, "styles_matrix", None)),
        "mutation_matrix":     _sanitise_matrix(getattr(req, "mutation_matrix", None)),
        "unique_flair_matrix": _sanitise_matrix(getattr(req, "unique_flair_matrix", None)),
    }
    matrix_dial_count = 0
    for k, v in matrices_payload.items():
        if v:
            build[k] = v
            matrix_dial_count += sum(len(axes) for axes in v.values())
    if matrix_dial_count:
        build["matrix_dial_count"] = matrix_dial_count
        build["matrix_keys"] = [k for k, v in matrices_payload.items() if v]
    # ═══ Advanced ML execution config — derive from agent_matrix or explicit ml_config
    ml_cfg_raw = getattr(req, "ml_config", None)
    agent_mtx  = matrices_payload.get("agent_matrix") or {}
    derived_ml: dict = {}
    # Cross-Entropy customization (CE loss · label smoothing · focal)
    if "loss_ce" in agent_mtx:
        derived_ml["ce_loss_weight"] = agent_mtx["loss_ce"].get("weight", 7)
        derived_ml["ce_temperature"] = round(agent_mtx["loss_ce"].get("temperature", 7) / 10.0, 2)
    if "loss_label_smooth" in agent_mtx:
        derived_ml["label_smoothing"] = round(agent_mtx["loss_label_smooth"].get("weight", 0) / 100.0, 3)
    if "loss_focal" in agent_mtx:
        derived_ml["focal_gamma"] = round(agent_mtx["loss_focal"].get("weight", 2) / 4.0, 2)
    # Fine-tuning execution (DPO / ORPO / KTO + LoRA / QLoRA)
    pref_modes = []
    for pref_key, pref_name in [("pref_dpo", "DPO"), ("pref_orpo", "ORPO"), ("pref_kto", "KTO")]:
        if pref_key in agent_mtx and agent_mtx[pref_key].get("weight", 0) >= 5:
            pref_modes.append(pref_name)
    if pref_modes:
        derived_ml["preference_finetune"] = pref_modes
    if "lora_r" in agent_mtx:
        # weight 0-10 → r ∈ {4,8,16,32,64}
        weight = agent_mtx["lora_r"].get("weight", 7)
        derived_ml["lora_r"] = [4, 8, 16, 32, 64][min(4, weight // 2)]
    if "qlora_4bit" in agent_mtx:
        derived_ml["qlora_4bit"] = agent_mtx["qlora_4bit"].get("weight", 0) >= 5
    # In-Context Learning Log-Probs depth + Self-Consistency + MCTS
    if "icl_logprobs" in agent_mtx:
        derived_ml["icl_logprobs_depth"] = agent_mtx["icl_logprobs"].get("context_depth", 7)
        derived_ml["icl_samples"]        = agent_mtx["icl_logprobs"].get("samples", 8)
    if "icl_self_consistency" in agent_mtx:
        derived_ml["self_consistency_k"] = agent_mtx["icl_self_consistency"].get("samples", 8)
    if "icl_mcts" in agent_mtx:
        derived_ml["mcts_depth"] = agent_mtx["icl_mcts"].get("context_depth", 5)
    # Merge with explicit ml_config (explicit wins on conflict)
    if isinstance(ml_cfg_raw, dict):
        for k, v in ml_cfg_raw.items():
            if isinstance(k, str) and k[:48]:
                derived_ml[k[:48]] = v
    if derived_ml:
        build["ml_config"] = derived_ml
    # ═══ Persist immediately so build never vanishes before first batch save ═══
    await _save_build(build)
    scale_info = build.get("scale_info", {})
    return {
        "build_id": build["build_id"],
        "title": build["title"],
        "genre": build["genre"],
        "genres": build.get("genres", [build["genre"]]),
        "subgenre": build.get("subgenre"),
        "subgenres": build.get("subgenres", []),
        "fusion_count": build.get("fusion_count", 1),
        "is_fusion": bool(build.get("is_fusion")),
        "fusion_multiplier": build.get("fusion_multiplier", 1.0),
        "status": build["status"],
        "total_phases": len(BUILD_PHASES),
        "total_agents": build["total_agents"],
        "synergy_network": SYNERGY_NETWORK,
        "scale": {
            "label": scale_info.get("scale_label", "UNLIMITED"),
            "target_files": scale_info.get("target_files", 0),
            "target_size_gb": scale_info.get("target_size_gb", 0),
            "multiplier": scale_info.get("multiplier", 1),
        },
        "descriptions_received": {
            "game_vision": bool(build["game_vision"]),
            "system_architecture": bool(build["system_architecture"]),
            "world_laws": bool(build["world_laws"]),
            "agent_instructions": bool(build["agent_instructions"]),
        },
        "message": f"Galaxy Studio build started — SCALE: {scale_info.get('scale_label', 'UNLIMITED')}. {AGENT_MANIFEST['total']['agents']} agents mobilized with {sum(1 for v in [build['game_vision'], build['system_architecture'], build['world_laws'], build['agent_instructions']] if v)} description directives across {SYNERGY_NETWORK['total_links']} synergy links.",
    }


@router.post("/advance")
async def advance_build(req: AdvanceRequest):
    """Advance build to the next BATCH (10 phases at once)."""
    build = await _advance_build(req.build_id)
    idx = build.get("current_phase", 0)
    completed_phases = [p for p in build["phases"] if p["status"] == "completed"]
    current = build["phases"][idx] if idx < len(build["phases"]) else build["phases"][-1]

    # Determine current batch
    current_batch = (idx // PHASES_PER_BATCH) + 1 if idx < len(BUILD_PHASES) else TOTAL_BATCHES
    batch_name = BATCH_NAMES.get(min(current_batch, TOTAL_BATCHES), "Complete")

    return {
        "build_id": build["build_id"],
        "status": build["status"],
        "current_phase": idx,
        "total_phases": len(BUILD_PHASES),
        "current_batch": min(current_batch, TOTAL_BATCHES),
        "total_batches": TOTAL_BATCHES,
        "batch_name": batch_name,
        "progress_pct": current.get("pct", 100),
        "agents_active": build["agents_active"],
        "completed_phases": len(completed_phases),
        "latest_phase": completed_phases[-1] if completed_phases else None,
        "file_count": build["file_count"],
        "synergy_activations": build["synergy_activations"][-1] if build["synergy_activations"] else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# BACKGROUND BUILD — 10-batch architecture (100 phases in 10 steps)
# Each batch processes 10 phases; only durable results advance completion.
# Frontend polls GET /status/{build_id} on interval. No rapid POST calls.
# ═══════════════════════════════════════════════════════════════════════
_background_tasks: dict = {}


class GalaxyBuildStopped(RuntimeError):
    """An actual build boundary stopped dispatch; partial artifacts are retained."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _mark_build_stop(build: dict, reason: str, *, failed: bool = True) -> None:
    if not build.get("_bg_stop_requested"):
        build["_bg_stop_reason"] = reason
        build["_bg_stop_target"] = "failed" if failed else "cancelled"
    build["_bg_stop_requested"] = True
    build["_bg_status"] = "stopping"
    build["_bg_error"] = build.get("_bg_stop_reason", reason)


def _check_build_continuation(build: dict) -> None:
    if build.get("_bg_stop_requested"):
        raise GalaxyBuildStopped(str(build.get("_bg_stop_reason") or "build_stopped"))
    deadline = build.get("_bg_deadline_monotonic")
    if isinstance(deadline, (int, float)) and _build_clock.monotonic() >= deadline:
        _mark_build_stop(build, "build_deadline_exceeded")
        raise GalaxyBuildStopped("build_deadline_exceeded")


def _check_build_resources(build: dict) -> None:
    """Blocking resource probes run in workers, never on the async loop."""
    _check_build_continuation(build)
    if _memory_check("build admission") == "hard":
        _mark_build_stop(build, "memory_limit_reached")
        raise GalaxyBuildStopped("memory_limit_reached")
    location = os.path.abspath(VAULT_DIR)
    while not os.path.isdir(location) and location != os.path.dirname(location):
        location = os.path.dirname(location)
    try:
        if shutil.disk_usage(location).free < 64 * 1024 * 1024:
            raise OSError("artifact storage headroom exhausted")
    except OSError:
        _mark_build_stop(build, "artifact_storage_unavailable")
        build["_vault_write_failed"] = True
        raise GalaxyBuildStopped("artifact_storage_unavailable") from None
    _check_build_continuation(build)


async def _save_build_required(build: dict) -> None:
    if await _save_build(build) is not True:
        _mark_build_stop(build, "build_metadata_unavailable")
        raise GalaxyBuildStopped("build_metadata_unavailable")


# ═══ WORKER THREAD POOL — admitted physical generation and vault I/O ═══
# The owner submits one generation result at a time and retains its native
# future through cancellation. Extra pool capacity also serves vault I/O.
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future
import threading

_MAX_WORKERS = int(os.environ.get("GALAXY_WORKERS", "2"))  # default 2 (OOM-safe; bump to 8 on big pods)
_WORKER_POOL = ThreadPoolExecutor(
    max_workers=_MAX_WORKERS,
    thread_name_prefix="galaxy-studio-worker",
)
_worker_stats = {
    "total_submitted": 0,
    "total_completed": 0,
    "total_failed": 0,
    "active": 0,
    "max_workers": _MAX_WORKERS,
}
_worker_lock = threading.Lock()
_build_worker_futures: dict[str, set[Future]] = {}


def _track_build_future(build_id: str, future: Future) -> Future:
    with _worker_lock:
        _build_worker_futures.setdefault(build_id, set()).add(future)

    def settled(done: Future) -> None:
        with _worker_lock:
            pending = _build_worker_futures.get(build_id)
            if pending is not None:
                pending.discard(done)
                if not pending:
                    _build_worker_futures.pop(build_id, None)

    future.add_done_callback(settled)
    return future


def _physical_build_workers(build_id: str) -> int:
    with _worker_lock:
        return sum(not future.done() for future in _build_worker_futures.get(build_id, ()))


def _build_has_live_work(build_id: str) -> bool:
    task = _background_tasks.get(build_id)
    return bool(
        (task is not None and not task.done())
        or _physical_build_workers(build_id)
        or build_id in _active_runners
    )


def _any_build_has_live_work() -> bool:
    if _active_runners or any(task is not None and not task.done() for task in _background_tasks.values()):
        return True
    with _worker_lock:
        return any(not future.done() for pending in _build_worker_futures.values() for future in pending)


async def _drain_build_workers(build_id: str) -> None:
    """Cancellation cannot release a slot while native futures still execute."""
    while True:
        with _worker_lock:
            pending = tuple(future for future in _build_worker_futures.get(build_id, ()) if not future.done())
        if not pending:
            return
        for future in pending:
            future.cancel()  # only queued work can be cancelled; running work drains
        waiter = asyncio.gather(*(asyncio.wrap_future(future) for future in pending), return_exceptions=True)
        while not waiter.done():
            try:
                await asyncio.shield(waiter)
            except asyncio.CancelledError:
                continue


async def _await_build_future(build: dict, future: Future, *, maximum_seconds: float = 180.0):
    _check_build_continuation(build)
    remaining = max(
        0.001,
        float(build.get("_bg_deadline_monotonic", _build_clock.monotonic() + maximum_seconds))
        - _build_clock.monotonic(),
    )
    wrapped = asyncio.wrap_future(future)
    wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    try:
        result = await asyncio.wait_for(asyncio.shield(wrapped), timeout=min(maximum_seconds, remaining))
    except asyncio.TimeoutError:
        _mark_build_stop(build, "worker_deadline_exceeded")
        raise GalaxyBuildStopped("worker_deadline_exceeded") from None
    _check_build_continuation(build)
    return result


async def _await_build_io(build: dict, operation, *args):
    """Vault mutations retain native custody even if their async waiter leaves."""
    future = _track_build_future(build["build_id"], _WORKER_POOL.submit(operation, *args))
    wrapped = asyncio.wrap_future(future)
    wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.shield(wrapped)


async def _request_build_stop(build_id: str, reason: str, *, failed: bool = True) -> dict | None:
    build = await _load_build(build_id)
    if not build:
        return None
    if build.get("status") == "completed" and not _build_has_live_work(build_id):
        return build
    _mark_build_stop(build, reason, failed=failed)
    live = _build_has_live_work(build_id)
    build["_bg_drain_pending"] = live
    if not live:
        build["status"] = build.get("_bg_stop_target", "failed")
        build["_bg_status"] = build["status"]
        build["_bg_stopped_at"] = datetime.utcnow().isoformat()
    await _save_build(build)
    return build


# ── Process pool for the CPU-bound FLOOR PASS ────────────────────────────
# The floor pass generates the bulk of a build's files (10k+). Run in WORKER
# THREADS it holds the GIL and briefly starves the asyncio event loop at peak
# (one short blip per build). A spawn-based ProcessPoolExecutor runs that pure,
# stateless generator (_generate_floor_padding: primitives in → dict out) in a
# SEPARATE process with its own GIL, so the API process stays fully responsive.
# Lazy-created on first use (never forks the FastAPI process at import/startup)
# and falls back to the thread pool if a process pool can't be created/submitted.
import multiprocessing as _mp
_USE_PROC_POOL = os.environ.get("GALAXY_PROC_POOL", "1") == "1"
_PROC_WORKERS = int(os.environ.get("GALAXY_PROC_WORKERS", "2"))
_PROC_POOL = None
_PROC_POOL_LOCK = threading.Lock()
_PROC_POOL_FAILED = False


def _get_proc_pool():
    """Lazily build a spawn ProcessPoolExecutor; returns None → caller uses threads."""
    global _PROC_POOL, _PROC_POOL_FAILED
    if not _USE_PROC_POOL or _PROC_POOL_FAILED:
        return None
    if _PROC_POOL is None:
        with _PROC_POOL_LOCK:
            if _PROC_POOL is None and not _PROC_POOL_FAILED:
                try:
                    _PROC_POOL = ProcessPoolExecutor(
                        max_workers=_PROC_WORKERS,
                        mp_context=_mp.get_context("spawn"),
                    )
                    print(f"[GALAXY] process pool ready (spawn, {_PROC_WORKERS} workers)")
                except Exception as _ppe:
                    _PROC_POOL_FAILED = True
                    print(f"[GALAXY] process pool unavailable → thread fallback: {_ppe}")
                    return None
    return _PROC_POOL


def _submit_floor_chunk(params):
    """Submit one floor-padding chunk to the process pool (thread fallback)."""
    pool = _get_proc_pool()
    if pool is not None:
        try:
            return pool.submit(_generate_floor_padding, *params)
        except Exception as _se:
            print(f"[GALAXY] proc submit failed → thread fallback: {_se}")
    return _WORKER_POOL.submit(_generate_floor_padding, *params)


# ═══════════════════════════════════════════════════════════════════════
# MEMORY WATCHDOG + WORKER COOLDOWN — extracted 2026-06 →
# routes/galaxy_studio_resilience.py (pure, self-contained back-pressure
# helpers; no build state / DB / circular import). Imported here so the
# worker loop + _safe_generate_batch keep their original call sites. See
# that module for full docs + env knobs (GALAXY_RSS_SOFT_MB / HARD_MB /
# WATCHDOG / WORKER_COOLDOWN_MS / BATCH_PAUSE_MS).
# ═══════════════════════════════════════════════════════════════════════
from routes.galaxy_studio_resilience import (
    _RSS_SOFT_MB, _RSS_HARD_MB, _WATCHDOG_ON,
    _WORKER_COOLDOWN_MS, _BATCH_PAUSE_MS,
    _malloc_trim, _get_rss_mb, _worker_cooldown, _memory_check,
)


def _safe_generate_batch(build_id: str, batch_num: int) -> tuple:
    """One tracked worker result. Resource failures are failures, not stubs."""
    with _worker_lock:
        _worker_stats["active"] += 1
        _worker_stats["total_submitted"] += 1
    try:
        build = _builds.get(build_id)
        if not build:
            raise GalaxyBuildStopped("build_identity_missing")
        _check_build_resources(build)
        files = _generate_batch(build, batch_num) or {}
        _check_build_continuation(build)
        with _worker_lock:
            _worker_stats["total_completed"] += 1
        return batch_num, files, None
    except Exception as exc:
        with _worker_lock:
            _worker_stats["total_failed"] += 1
        return batch_num, {}, exc.reason if isinstance(exc, GalaxyBuildStopped) else "batch_generation_failed"
    finally:
        with _worker_lock:
            _worker_stats["active"] = max(0, _worker_stats["active"] - 1)


async def _run_background_build(build_id: str, duration_minutes: int = 15, resume_from_batch: int = 1):
    """Retain task and physical worker ownership through stop and durable drain."""
    current = asyncio.current_task()
    previous = _background_tasks.get(build_id)
    if previous is not None and previous is not current and not previous.done():
        return
    _background_tasks[build_id] = current
    _active_runners.add(build_id)
    build = None
    cancelled = False
    try:
        build = await _load_build(build_id)
        if not build:
            return
        if type(duration_minutes) is not int or not 1 <= duration_minutes <= 60:
            raise GalaxyBuildStopped("build_duration_invalid")
        budget = duration_minutes * 60.0
        started = build.get("_bg_started")
        if started:
            try:
                original = datetime.fromisoformat(started)
                if original.tzinfo is None:
                    original = original.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - original).total_seconds()
                if elapsed < -5.0:
                    raise ValueError("build clock moved backwards")
                budget = max(0.0, budget - max(0.0, elapsed))
            except (ValueError, TypeError):
                raise GalaxyBuildStopped("build_clock_unavailable") from None
        build["_bg_deadline_monotonic"] = _build_clock.monotonic() + budget
        await _run_background_build_inner(build, build_id, duration_minutes, resume_from_batch)
    except asyncio.CancelledError:
        cancelled = True
        if build is not None:
            _mark_build_stop(build, "runner_cancelled", failed=False)
    except Exception as exc:
        if build is not None:
            _mark_build_stop(
                build, exc.reason if isinstance(exc, GalaxyBuildStopped) else "background_runner_failed"
            )
    finally:
        if build is not None:
            build["_bg_drain_pending"] = _physical_build_workers(build_id) > 0
        await _drain_build_workers(build_id)
        try:
            if build is not None:
                build.pop("_bg_deadline_monotonic", None)
                build["_bg_floor_in_progress"] = False
                if build.get("_bg_stop_requested"):
                    build["_gen_cache"] = {}
                    try:
                        if not build.get("_vault_write_failed"):
                            await _await_build_io(build, _flush_to_vault, build, True)
                        from core import build_vault as _bv

                        preserved = await _await_build_io(build, _bv.preserve_on_failure, build_id)
                        build["_vault_preserved"] = bool(preserved)
                    except Exception:
                        build["_vault_preserved"] = bool(build.get("_vault_active"))
        except asyncio.CancelledError:
            cancelled = True
        finally:
            # A second cancellation during a vault write still cannot free
            # the build slot before that physical mutation finishes.
            await _drain_build_workers(build_id)
            try:
                if build is not None:
                    build["_bg_drain_pending"] = False
                    if build.get("_bg_stop_requested"):
                        build["status"] = build.get("_bg_stop_target", "failed")
                        build["_bg_status"] = build["status"]
                        build["_bg_stopped_at"] = datetime.utcnow().isoformat()
                        build.pop("completed_at", None)
                        build.pop("_bg_completed", None)
                        build["_bg_partial_artifacts"] = bool(
                            build.get("_vault_active") or build.get("files")
                        )
                    await _save_build(build)
            finally:
                _active_runners.discard(build_id)
                if _background_tasks.get(build_id) is current:
                    _background_tasks.pop(build_id, None)
    if cancelled:
        raise asyncio.CancelledError


async def _run_background_build_inner(
    build: dict, build_id: str, duration_minutes: int = 15, resume_from_batch: int = 1
):
    """Dispatch bounded serial work; completion follows actual durable results."""
    _check_build_continuation(build)
    build["_bg_status"] = "running"
    build["status"] = "building"
    build.setdefault("_bg_started", datetime.utcnow().isoformat())
    build["_bg_target_duration"] = duration_minutes
    build["_bg_total_batches"] = TOTAL_BATCHES
    build.setdefault("_bg_phase_log", [])
    build.setdefault("_bg_errors", [])
    build.setdefault("_bg_retries", 0)
    build.setdefault("_bg_fallbacks", 0)
    build["_bg_prefetch_mode"] = "single-physical-worker"
    await _save_build_required(build)
    for batch_num in range(max(1, resume_from_batch), TOTAL_BATCHES + 1):
        _check_build_continuation(build)
        await _await_build_io(build, _check_build_resources, build)
        build["_bg_current_batch"] = batch_num
        build["_bg_last_heartbeat"] = datetime.utcnow().isoformat()
        future = _track_build_future(build_id, _WORKER_POOL.submit(_safe_generate_batch, build_id, batch_num))
        actual_batch, files, error = await _await_build_future(build, future)
        if actual_batch != batch_num or error or not isinstance(files, dict) or not files:
            raise GalaxyBuildStopped(error or "batch_empty_output")
        build.setdefault("files", {}).update(files)
        await _await_build_io(build, _flush_to_vault, build, True)
        files.clear()
        build.get("_gen_cache", {}).pop(f"batch_{batch_num}", None)
        _check_build_continuation(build)
        for phase_id in BUILD_BATCHES.get(batch_num, []):
            index = _PHASE_INDEX_MAP.get(phase_id, -1)
            if 0 <= index < len(build["phases"]):
                build["phases"][index]["status"] = "completed"
                build["phases"][index]["completed_at"] = datetime.utcnow().isoformat()
        last_index = (
            max(
                (_PHASE_INDEX_MAP.get(phase, 0) for phase in BUILD_BATCHES.get(batch_num, [])),
                default=build.get("current_phase", 0),
            )
            + 1
        )
        build["current_phase"] = max(build.get("current_phase", 0), last_index)
        build["_bg_last_batch_completed"] = batch_num
        build["_bg_phase_log"].append(
            {
                "batch": batch_num,
                "name": BATCH_NAMES.get(batch_num),
                "status": "success",
                "file_count": build["file_count"],
                "completed_at": datetime.utcnow().isoformat(),
                "attempts": 1,
                "source": "worker",
            }
        )
        await _save_build_required(build)
        if build["file_count"] >= GLOBAL_FILE_BUDGET and batch_num < TOTAL_BATCHES:
            raise GalaxyBuildStopped("artifact_file_budget_exhausted")
        await asyncio.to_thread(_worker_cooldown, context=f"after-batch-{batch_num}")

    # Preserve the existing requested delivery floor while keeping physical
    # custody and at most one small unharvested result. No RAM fallback on I/O
    # failure and no further submissions until a durable append is confirmed.
    complexity = int(build.get("complexity", 60) or 60)
    floor_target = max(50000, 50000 + (complexity - 50) * 2500)
    sliders = [
        build.get(key, 0)
        for key in (
            "graphics_era",
            "world_size",
            "ai_complexity",
            "physics_realism",
            "narrative_branching",
            "multiplayer_max",
        )
    ]
    if any(int(value or 0) >= 8 for value in sliders):
        floor_target += 75000
    if all(int(value or 0) >= 9 for value in sliders):
        floor_target += 125000
    fusion = max(1.0, min(1.6, float(build.get("fusion_multiplier", 1.0) or 1.0)))
    floor_target = min(int(floor_target * fusion), GLOBAL_FILE_BUDGET)
    from core import build_vault as _bv

    current_files = await asyncio.to_thread(_bv.get_file_count, build_id)
    deficit = max(0, floor_target - current_files)
    genres = build.get("genres") or [build.get("genre", "rpg")]
    if not isinstance(genres, list) or not 1 <= len(genres) <= 16:
        raise GalaxyBuildStopped("build_genres_invalid")
    build["_bg_floor_target"] = floor_target
    build["_bg_floor_in_progress"] = deficit > 0
    serial = 0
    while deficit > 0:
        _check_build_continuation(build)
        await _await_build_io(build, _check_build_resources, build)
        count = min(128, deficit)
        genre = genres[serial % len(genres)]
        params = (
            99 + serial,
            build.get("title", "Game"),
            genre,
            f"AAA_Delivery_Floor[{genre}]#{serial}",
            count,
        )
        future = _track_build_future(build_id, _submit_floor_chunk(params))
        extra = await _await_build_future(build, future, maximum_seconds=180.0)
        if not isinstance(extra, dict) or not extra:
            raise GalaxyBuildStopped("floor_generation_failed")
        # The one pending chunk remains owned by the build if its durable
        # append fails; no further generation follows a storage failure.
        build.setdefault("files", {}).update(extra)
        previous_count = current_files
        await _await_build_io(build, _flush_to_vault, build, True)
        current_files = int(build.get("_vault_file_count", 0))
        if current_files <= previous_count:
            raise GalaxyBuildStopped("floor_no_durable_progress")
        extra.clear()
        deficit = max(0, floor_target - current_files)
        serial += 1
        build["_bg_last_heartbeat"] = datetime.utcnow().isoformat()
        if serial % 4 == 0 or not deficit:
            await _save_build_required(build)
        await asyncio.sleep(0)
    build["_bg_floor_in_progress"] = False
    _check_build_continuation(build)
    await _await_build_io(build, _flush_to_vault, build, True)
    if not build.get("phases") or any(phase.get("status") != "completed" for phase in build["phases"]):
        raise GalaxyBuildStopped("build_phases_incomplete")
    build["file_count"] = await asyncio.to_thread(_bv.get_file_count, build_id)
    build["status"] = "completed"
    build["_bg_status"] = "completed"
    build["_bg_completed"] = datetime.utcnow().isoformat()
    build["completed_at"] = build["_bg_completed"]
    await _save_build_required(build)
    build["_gen_cache"] = {}
    # Packaging and pruning are separate owner actions. Completion does not
    # silently allocate a second copy or delete another build's artifacts.


@router.post("/force-complete/{build_id}")
async def force_complete_build(build_id: str, background_tasks: BackgroundTasks):
    """Compatibility stop endpoint; client clocks cannot attest completed work."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if build.get("status") == "completed" and not _build_has_live_work(build_id):
        return {"build_id": build_id, "status": "already_completed", "file_count": build.get("file_count", 0)}
    build = await _request_build_stop(build_id, "operator_stop_requested", failed=False)
    return {
        "build_id": build_id,
        "status": build["_bg_status"],
        "file_count": build.get("file_count", 0),
        "partial_artifacts": bool(build.get("_vault_active") or build.get("files")),
        "drain_pending": _build_has_live_work(build_id),
        "message": "Stop requested. Completed artifacts are retained; the build slot remains held until physical work drains.",
    }


# ═══════════════════════════════════════════════════════════════════════
# Code Library (32M virtual lines) — agent knowledge base
# All swarm agents reference the `game_code_library` Mongo collection for
# canonical patterns, snippets, and era-appropriate code templates.
# ═══════════════════════════════════════════════════════════════════════
_code_library_seed_lock: bool = False


async def _ensure_code_library_seeded():
    """Idempotent — triggers the seeder once if the collection is empty."""
    global _code_library_seed_lock
    if _code_library_seed_lock:
        return
    _code_library_seed_lock = True
    try:
        from core.databases import content_db as _cdb
        from seeds.game_code_library_seed import seed_game_code_library
        # ★ FIX 2026-02: seed into content_db (where game_code_library lives
        # per the routing config), not core_db.
        result = await seed_game_code_library(_cdb)
        print(f"[GALAXY CodeLibrary] Seed result: {result}")
    except Exception as e:
        print(f"[GALAXY CodeLibrary] Seed error (non-fatal): {e}")
    # Intentionally keep lock engaged until process restart — avoids repeat attempts


# ═══════════════════════════════════════════════════════════════════════════
# Code-library endpoints (/code-library/stats, /code-library/search) were
# extracted in Feb 2026 (Phase-3 decomposition) → routes/galaxy_studio_code_library.py.
# They mount on the SAME public paths via include_router below. The seeder
# (_ensure_code_library_seeded) stays in this file because it has many
# internal helper dependencies; the sub-router calls it via lazy import.
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_code_library import router as _cl_router
    router.include_router(_cl_router)
except Exception as _cl_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] code-library subrouter import SKIPPED: {type(_cl_err).__name__}: {_cl_err}", flush=True, file=_s.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Phase-4 sub-router mounts (Feb 2026): Flair, ML-config, Mega-DBs.
# Each module is pure (no in-memory build state, no circular imports). They
# mount on the SAME public paths as the originals so existing clients keep
# working unchanged.
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_flair import router as _flair_router
    router.include_router(_flair_router)
except Exception as _fl_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] flair subrouter import SKIPPED: {type(_fl_err).__name__}: {_fl_err}", flush=True, file=_s.stderr)

try:
    from routes.galaxy_studio_ml_config import router as _mlc_router
    router.include_router(_mlc_router)
except Exception as _mlc_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] ml-config subrouter import SKIPPED: {type(_mlc_err).__name__}: {_mlc_err}", flush=True, file=_s.stderr)

try:
    from routes.galaxy_studio_mega_dbs import router as _mega_router
    router.include_router(_mega_router)
except Exception as _mega_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] mega-dbs subrouter import SKIPPED: {type(_mega_err).__name__}: {_mega_err}", flush=True, file=_s.stderr)

# ═══════════════════════════════════════════════════════════════════════════
# Phase-6 sub-router mounts (Feb 2026): Pipeline, Files, Admin.
# These access parent helpers (_generate_batch_files, _amplify,
# _package_build, _worker_*, _background_tasks) via galaxy_studio_state
# lazy proxies so module-load order is irrelevant.
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_pipeline import router as _pipe_router
    router.include_router(_pipe_router)
except Exception as _pipe_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] pipeline subrouter import SKIPPED: {type(_pipe_err).__name__}: {_pipe_err}", flush=True, file=_s.stderr)

try:
    from routes.galaxy_studio_files import router as _files_router
    router.include_router(_files_router)
except Exception as _files_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] files subrouter import SKIPPED: {type(_files_err).__name__}: {_files_err}", flush=True, file=_s.stderr)

try:
    from routes.galaxy_studio_admin import router as _admin_router
    router.include_router(_admin_router)
except Exception as _admin_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] admin subrouter import SKIPPED: {type(_admin_err).__name__}: {_admin_err}", flush=True, file=_s.stderr)

try:
    from routes.galaxy_studio_meta import router as _meta_router
    router.include_router(_meta_router)
except Exception as _meta_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] meta subrouter import SKIPPED: {type(_meta_err).__name__}: {_meta_err}", flush=True, file=_s.stderr)


# ─── /agent-db-manifest extracted → routes/galaxy_studio_meta.py

# ───────────────────────────────────────────────────────────────────────
# Phase-7 (Feb 2026): tiny back-compat shim for inline call-sites that
# still reference ``_save_vault_entry``. The canonical helper now lives
# in ``galaxy_studio_state.py``; we re-bind the name here so existing
# fire-and-forget call-sites inside this file (auto-archive,
# /vault/zip-to-apk, etc.) keep working without touching every caller.
# ───────────────────────────────────────────────────────────────────────
from routes.galaxy_studio_state import save_vault_entry as _save_vault_entry  # noqa: E402,F401
# ─── Flair endpoints extracted → routes/galaxy_studio_flair.py
#     (see include_router() block near end of file).

# ─── ML-config endpoints extracted → routes/galaxy_studio_ml_config.py
#     (see include_router() block near end of file).


# ─── Mega-DBs + db-status + bootstrap extracted → routes/galaxy_studio_mega_dbs.py
#     (see include_router() block near end of file).


# ─── Workers + resumable + my-builds + admin-status extracted →
#     routes/galaxy_studio_admin.py (see include_router() block near end).
@router.post("/start-build")
async def start_background_build(req: StartBuildRequest):
    """Start a full background build within a bounded execution budget.
    Frontend should poll GET /status/{build_id} every 5-10 seconds.

    ★ HARDENED INIT (2026-04-20) ★
    Before returning, we STAMP the build doc with `_bg_status='running'`,
    `_bg_started`, and an empty-but-present file_count so the first
    /status poll from the frontend always sees a sensible state — never
    the confusing `_bg_status: null` + no progress combo that made the UI
    feel like it never initialized.
    """
    import asyncio
    try:
        build = await _load_build(req.build_id)
    except Exception as _lerr:
        raise internal_http_error("Failed to load build", _lerr) from None
    if not build:
        raise HTTPException(404, "Build not found")

    # Don't restart if already running (idempotent)
    if _build_has_live_work(req.build_id):
        return {
            "build_id": req.build_id,
            "status": "already_running",
            "message": "Build is already in progress. Poll GET /status/{build_id} for updates.",
        }

    # ═══ MEMORY + CONCURRENCY GUARD ═══
    # Reject new builds ONLY if we're actively generating. A Mongo doc with
    # status="building" doesn't count — after a pod restart the runner is
    # gone and the doc is just a zombie. Only live _background_tasks with
    # unfinished work count. This is the fix for the "2 builds already
    # running" 429 errors users hit after any pod recycle.
    try:
        import psutil as _ps
        mem_pct = _ps.virtual_memory().percent
    except Exception:
        mem_pct = 0

    # Count ACTUALLY running tasks only
    live_runners = 0
    for _bid, _tsk in list(_background_tasks.items()):
        try:
            if _tsk is not None and not _tsk.done():
                live_runners += 1
            else:
                # Clean up done tasks so they don't linger
                _background_tasks.pop(_bid, None)
        except Exception:
            pass
    live_runners = max(live_runners, len(_active_runners))
    with _worker_lock:
        live_runners = max(
            live_runners,
            sum(any(not future.done() for future in pending) for pending in _build_worker_futures.values()),
        )
    # Also mark any in-memory build docs whose runner is gone as "lost" so
    # the UI can render them accurately, and they stop blocking new starts.
    stale_marked = 0
    for _bid, _b in list(_builds.items()):
        if (_b.get("status") == "building"
                and _bid not in _background_tasks
                and _bid not in _active_runners):
            _b["_bg_status"] = _b.get("_bg_status") or "lost"
            _b["_runner_lost"] = True
            stale_marked += 1
    if stale_marked:
        print(f"[GALAXY start-build] reclassified {stale_marked} zombie builds as lost")

    if mem_pct > 88:
        raise HTTPException(
            status_code=503,
            detail=f"Pod memory at {mem_pct:.0f}% — refusing to start new build to avoid OOM. Wait for current builds to finish and retry.",
        )
    # Per-build RAM peaks at ~1.5–2 GB and the memory watchdog HARD-freezes
    # file generation at the cgroup ceiling (~2 GB on this pod). Running more
    # than ONE build at a time reliably pushes past that ceiling and wedges
    # every build in a freeze/retry loop that also starves the HTTP event
    # loop. So we hard-cap to a SINGLE live build; concurrent requests get a
    # clear 429 telling them to wait. (Single-builder design — see FLOOR PASS.)
    if live_runners >= 1:
        raise HTTPException(
            status_code=429,
            detail=f"A build is already running ({live_runners} active). This pod runs one build at a time to stay within memory limits — wait for it to finish, then retry.",
        )

    preflight = {
        key: value
        for key, value in build.items()
        if key not in {"_bg_stop_requested", "_bg_deadline_monotonic"}
    }
    try:
        await asyncio.to_thread(_check_build_resources, preflight)
    except GalaxyBuildStopped as exc:
        raise HTTPException(503, f"Build admission refused: {exc.reason}.") from None
    # No await between the final custody check and reserving the slot.
    if _build_has_live_work(req.build_id):
        return {"build_id": req.build_id, "status": "already_running"}
    if _any_build_has_live_work():
        raise HTTPException(429, "Another build owns the generation slot.")
    _active_runners.add(req.build_id)
    # ═══ STAMP INITIAL STATE ═══
    # This is the fix for "build doesn't initialize" — we pre-set the status
    # fields so the UI's first poll sees `_bg_status=running`, not None.
    for key in (
        "_bg_stop_requested",
        "_bg_stop_reason",
        "_bg_stop_target",
        "_bg_drain_pending",
        "_bg_deadline_monotonic",
        "_vault_write_failed",
        "_bg_error",
        "completed_at",
        "_bg_completed",
    ):
        build.pop(key, None)
    build["status"] = "building"
    build["_bg_status"] = "running"
    build["_bg_current_batch"] = 0
    build["_bg_last_batch_completed"] = 0
    build["current_phase"] = 0
    for phase in build.get("phases", []):
        phase["status"] = "pending"
        phase["started_at"] = None
        phase["completed_at"] = None
    build["_bg_total_batches"] = TOTAL_BATCHES
    build["_bg_target_duration"] = req.build_duration_minutes
    build["_bg_started"] = datetime.utcnow().isoformat()
    build["_bg_last_heartbeat"] = datetime.utcnow().isoformat()
    build["_bg_phase_log"] = []
    build["_bg_errors"] = build.get("_bg_errors", [])
    build["_bg_retries"] = build.get("_bg_retries", 0)
    build["_bg_fallbacks"] = build.get("_bg_fallbacks", 0)
    build["file_count"] = build.get("file_count", 0)
    if not isinstance(build.get("files"), dict):
        build["files"] = {}
    try:
        await _save_build_required(build)
    except asyncio.CancelledError:
        _mark_build_stop(build, "admission_cancelled", failed=False)
        build["status"] = "cancelled"
        build["_bg_status"] = "cancelled"
        _active_runners.discard(req.build_id)
        raise
    except GalaxyBuildStopped:
        build["status"] = "failed"
        build["_bg_status"] = "failed"
        _active_runners.discard(req.build_id)
        raise HTTPException(503, "Durable build metadata is unavailable; no worker was started.") from None

    # ═══ LAUNCH BACKGROUND RUNNER ═══
    # Stash user-supplied phase_weights on the build doc so the generator
    # can scale file output per category.
    if req.phase_weights and isinstance(req.phase_weights, dict):
        clean_weights = {}
        for k, v in req.phase_weights.items():
            try:
                fv = float(v)
                # clamp to [0, 3] — prevents abuse / runaway builds
                clean_weights[str(k)] = max(0.0, min(3.0, fv))
            except Exception:
                continue
        if clean_weights:
            build["phase_weights"] = clean_weights
            print(f"[GALAXY start-build] applied phase_weights for {req.build_id}: {clean_weights}")

    # Wrap the create_task itself in try/except so even a catastrophic
    # asyncio failure doesn't leave the user staring at a dead UI.
    try:
        task = asyncio.create_task(
            _run_background_build(req.build_id, req.build_duration_minutes)
        )
        _background_tasks[req.build_id] = task
    except Exception as _tke:
        _active_runners.discard(req.build_id)
        # Restore status so frontend knows something went wrong
        build["_bg_status"] = "failed"
        build["status"] = "failed"
        build["_bg_error"] = "task_creation_failed"
        try:
            await _save_build(build)
        except Exception as _save_error:
            print(f"[GALAXY] failed-status save failed: {_save_error}", flush=True)
        raise internal_http_error("Failed to launch build task", _tke) from None

    # ═══ AUTO-SCHEDULE THE SWARM DAG ═══
    # Kicking off a build also fires the Hierarchical Swarm Planner's async
    # execution: it plans the director→leads→platoons→workers DAG for the
    # canonical build ladder and runs the real platoons wave-by-wave on a
    # background thread. Non-fatal — a build never blocks on the swarm.
    swarm_job_id = None
    try:
        from core import swarm_scheduler as _sched
        swarm_job_id = _sched.start_async("build", build_id=req.build_id)
    except Exception as _swe:
        print(f"[GALAXY start-build] swarm auto-schedule skipped (non-fatal): {_swe}")

    return {
        "build_id": req.build_id,
        "status": "started",
        "bg_status": "running",
        "swarm_job_id": swarm_job_id,
        "swarm_poll_url": (f"/api/galaxy-studio/swarm/planner/job/{swarm_job_id}" if swarm_job_id else None),
        "duration_minutes": req.build_duration_minutes,
        "total_phases": len(BUILD_PHASES),
        "total_batches": TOTAL_BATCHES,
        "batch_names": BATCH_NAMES,
        "poll_url": f"/api/galaxy-studio/status/{req.build_id}",
        "poll_interval_seconds": 5,
        "message": f"Build started. {len(BUILD_PHASES)} phases in {TOTAL_BATCHES} batches within a {req.build_duration_minutes}-minute execution budget. Poll status for progress.",
    }


@router.get("/status/{build_id}")
async def get_status(build_id: str):
    """Get full build status. Primary endpoint for frontend polling during background builds."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    # Inspection does not create/release work. The bounded watchdog owns
    # orphan admission; live futures remain authoritative through physical drain.
    runner_live = _build_has_live_work(build_id)

    phase_idx = max(0, min(int(build.get("current_phase", 0)), len(BUILD_PHASES) - 1))
    completed_phases = [
        p for p in build.get("phases", []) if isinstance(p, dict) and p.get("status") == "completed"
    ]

    # ── AUTHORITATIVE FILE COUNT (cached 2s) ──
    # build["file_count"] is set in many places to len(build["files"]) which
    # is the in-memory dict. _flush_to_vault() resets that dict to {} after
    # streaming to disk, so build["file_count"] often shows 0 mid-build
    # even though the vault has thousands of files. Derive from vault total
    # + in-memory pending, but cache for 2s so concurrent /status polls
    # don't read the manifest on every hit (manifest reads can race with
    # concurrent shard appends → slow polls).
    try:
        import time as _t
        now = _t.time()
        last_check = build.get("_file_count_last_check", 0)
        if now - last_check > 2.0:
            build["_file_count_last_check"] = now
            authoritative_count = await asyncio.to_thread(_vault_total_files, build)
            if authoritative_count > 0:
                build["file_count"] = authoritative_count
            build["_file_count_last_check"] = now
    except Exception:
        pass

    # Time is a budget display only; actual durable phases determine progress.
    bg_progress = None
    if build.get("_bg_started"):
        try:
            started = datetime.fromisoformat(build["_bg_started"])
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
            target = max(1, int(build.get("_bg_target_duration", 15))) * 60
            bg_progress = {
                "elapsed_seconds": round(elapsed),
                "target_seconds": target,
                "elapsed_formatted": f"{int(elapsed // 60)}m {int(elapsed % 60)}s",
                "remaining_formatted": f"{max(0, int((target - elapsed) // 60))}m {max(0, int((target - elapsed) % 60))}s",
                "time_pct": min(100, round(elapsed / target * 100)),
            }
        except (ValueError, TypeError, OverflowError):
            pass

    # Determine current batch
    current_batch = (build.get("current_phase", 0) // PHASES_PER_BATCH) + 1 if build.get("current_phase", 0) < len(BUILD_PHASES) else TOTAL_BATCHES
    batch_name = BATCH_NAMES.get(min(current_batch, TOTAL_BATCHES), "Complete")

    # ── LIVE FILE PREVIEW ──
    # Cheap glance at the most-recent files this build has generated.
    # We surface up to 12 paths so the UI can render a marquee of recently
    # generated files without doing a full /files/{build_id} fetch.
    recent_files: list[dict] = []
    try:
        in_mem = build.get("files") or {}
        if in_mem:
            # Python dicts preserve insertion order — grab the tail.
            tail_keys = list(in_mem.keys())[-12:]
            for k in tail_keys:
                v = in_mem[k]
                recent_files.append({
                    "path": k,
                    "size": len(v) if isinstance(v, (str, bytes)) else 0,
                    "ext": k.rsplit(".", 1)[-1] if "." in k else "txt",
                })
    except Exception:
        recent_files = []

    # ── Frontend-friendly aliases & summaries ──
    # The triage test expected several conventional fields (`progress_percent`,
    # `target_files`, `phase_label`, `eta_seconds`, `errors`). Provide them
    # as first-class keys without breaking the existing payload shape.
    progress_percent = round(len(completed_phases) * 100 / max(1, len(build.get("phases") or [])))
    if build.get("status") != "completed":
        progress_percent = min(99, progress_percent)
    progress_pct = progress_percent
    eta_seconds = None
    if bg_progress:
        eta_seconds = max(0, bg_progress["target_seconds"] - bg_progress["elapsed_seconds"])
    phase_label = BUILD_PHASES[phase_idx].get("name") if phase_idx < len(BUILD_PHASES) else "Complete"

    return {
        "build_id": build["build_id"],
        "title": build["title"],
        "genre": build["genre"],
        "status": build["status"],
        "bg_status": build.get("_bg_status", "manual"),
        "execution": {
            "runner_live": runner_live,
            "physical_workers": _physical_build_workers(build_id),
            "stop_requested": bool(build.get("_bg_stop_requested")),
            "stop_reason": build.get("_bg_stop_reason"),
            "drain_pending": bool(build.get("_bg_drain_pending")),
            "partial_artifacts": bool(build.get("_vault_active") or build.get("files")),
            "unflushed_files": len(build.get("files") or {}),
            "storage_failed": bool(build.get("_vault_write_failed")),
        },
        "current_phase": build.get("current_phase", 0),
        "total_phases": len(BUILD_PHASES),
        "current_batch": min(current_batch, TOTAL_BATCHES),
        "total_batches": TOTAL_BATCHES,
        "batch_name": batch_name,
        "batch_names": BATCH_NAMES,
        "progress_pct": progress_pct,
        "progress_percent": progress_percent,  # 0-100 overall
        "phase_label": phase_label,  # e.g. "Codegen", "Polish"
        "phase": phase_idx,  # alias for current_phase
        "target_files": build.get("target_files", build.get("file_count", 0)),
        "eta_seconds": eta_seconds,  # null if not background
        "errors": build.get("_bg_errors", []),  # alias of redundancy.error_details (full list)
        "total_agents": build["total_agents"],
        "agents_active": build["agents_active"],
        "phases": build["phases"],
        "file_count": build["file_count"],
        "completed_phases": len(completed_phases),
        "latest_phase": completed_phases[-1] if completed_phases else None,
        "phase_log": build.get("_bg_phase_log", []),
        "bg_progress": bg_progress,
        "bg_current_batch": build.get("_bg_current_batch", 0),
        "recent_files": recent_files,
        # Redundancy health info
        "redundancy": {
            "retries": build.get("_bg_retries", 0),
            "fallbacks": build.get("_bg_fallbacks", 0),
            "errors": len(build.get("_bg_errors", [])),
            "error_details": build.get("_bg_errors", [])[-3:],  # Last 3 errors
            "health": (
                "excellent"
                if build.get("_bg_fallbacks", 0) == 0
                else "recovered" if build.get("_bg_fallbacks", 0) < 5 else "degraded"
            ),
        },
    }


# ─── Files + download + download-apk extracted → routes/galaxy_studio_files.py
#     (see include_router() block near end of file).
@router.post("/deploy/{build_id}")
async def deploy_build(build_id: str, expo_token: Optional[str] = None):
    """Deploy game — triggers EAS build or provides ZIP."""
    if not code_execution_enabled():
        return execution_disabled_response("Galaxy Studio deployment")

    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
        


    if not build["files"]:
        raise HTTPException(400, "No code files. Complete build first.")

    # Package to disk
    safe_id = _safe_segment(build_id, what="build_id")
    zip_path = _package_build(safe_id)
    slug = _safe_slug(build["title"])
    project_dir = _resolve_under_dir("/tmp/galaxy_studio_projects", safe_id)
    os.makedirs(project_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(project_dir)

    subdirs = [d for d in os.listdir(project_dir) if d not in {".", ".."}]
    actual_dir = _resolve_under_dir(project_dir, subdirs[0]) if subdirs else project_dir

    token = expo_token or os.environ.get("EXPO_TOKEN", "")
    if not token:
        return {
            "build_id": build_id,
            "status": "zip_ready",
            "message": "ZIP package ready for download. Provide EXPO_TOKEN for APK compilation.",
            "zip_url": f"/api/galaxy-studio/download/{build_id}",
            "file_count": build["file_count"],
            "instructions": [
                "1. Download the ZIP from the download URL",
                "2. Extract and cd into the project",
                "3. Run: npm install",
                "4. Run: npx expo start",
                "5. For APK: npx eas-cli build --platform android --profile preview",
            ],
        }

    # Trigger EAS Build
    env = os.environ.copy()
    env["EXPO_TOKEN"] = token
    try:
        # Initialize git repo (required by EAS)
        subprocess.run(["git", "init"], cwd=actual_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "add", "."], cwd=actual_dir, capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "Galaxy Studio Factory build"], cwd=actual_dir, capture_output=True, env={**env, "GIT_AUTHOR_NAME": "Galaxy Studio", "GIT_AUTHOR_EMAIL": "build@galaxy.studio", "GIT_COMMITTER_NAME": "Galaxy Studio", "GIT_COMMITTER_EMAIL": "build@galaxy.studio"}, timeout=15)

        # Install dependencies
        subprocess.run(["npm", "install", "--legacy-peer-deps"], cwd=actual_dir, capture_output=True, timeout=120)

        # Fix app.json — remove invalid projectId so eas init can set a real one
        app_json_path = _resolve_under_dir(actual_dir, "app.json")
        if os.path.exists(app_json_path):
            with open(app_json_path, 'r') as f:
                app_config = json.load(f)
            # Remove the invalid "auto" projectId
            if "expo" in app_config and "extra" in app_config["expo"]:
                if "eas" in app_config["expo"]["extra"]:
                    app_config["expo"]["extra"]["eas"].pop("projectId", None)
            with open(app_json_path, 'w') as f:
                json.dump(app_config, f, indent=2)

        # Initialize EAS project (--force creates new project if needed)
        subprocess.run(
            ["eas", "init", "--non-interactive", "--force"],
            cwd=actual_dir, env=env, capture_output=True, text=True, timeout=60,
        )

        # Git commit after eas init updates app.json with projectId
        subprocess.run(["git", "add", "."], cwd=actual_dir, capture_output=True, timeout=10)
        subprocess.run(
            ["git", "commit", "-m", "eas init"],
            cwd=actual_dir, capture_output=True,
            env={**env, "GIT_AUTHOR_NAME": "Galaxy Studio", "GIT_AUTHOR_EMAIL": "build@galaxy.studio", "GIT_COMMITTER_NAME": "Galaxy Studio", "GIT_COMMITTER_EMAIL": "build@galaxy.studio"},
            timeout=15,
        )

        result = subprocess.run(
            ["eas", "build", "--platform", "android", "--profile", "preview", "--non-interactive", "--no-wait", "--json"],
            cwd=actual_dir, env=env, capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            try:
                eas_output = json.loads(result.stdout)
                eas_build_id = eas_output[0].get("id", "") if isinstance(eas_output, list) else eas_output.get("id", "")
                build["eas_build_id"] = eas_build_id
                build["eas_build_status"] = "building"
                return {
                    "build_id": build_id,
                    "eas_build_id": eas_build_id,
                    "status": "building",
                    "message": "EAS Build triggered! APK compiling in the cloud.",
                }
            except json.JSONDecodeError:
                return {"build_id": build_id, "status": "submitted", "message": "Build submitted to EAS."}
        else:
            return {
                "build_id": build_id,
                "status": "zip_ready",
                "message": "EAS Build failed. ZIP download available.",
                "error": result.stderr[:500],
                "zip_url": f"/api/galaxy-studio/download/{build_id}",
            }
    except Exception:
        return {
            "build_id": build_id,
            "status": "zip_ready",
            "message": "EAS build failed",
            "zip_url": f"/api/galaxy-studio/download/{build_id}",
        }


# ─── /domains extracted → routes/galaxy_studio_meta.py
def _vault_save(build_id: str, vault_type: str, title: str, file_path: str, extra: dict = {}) -> dict:
    """Save a file to the vault."""
    safe_id = _safe_segment(build_id, what="build_id")
    vault_id = f"{vault_type}_{safe_id}_{int(datetime.utcnow().timestamp())}"
    # Constrain vault artifact paths to known sandboxes (CodeQL path-injection).
    real = os.path.realpath(file_path)
    allowed = (
        os.path.realpath(VAULT_DIR),
        os.path.realpath("/tmp/galaxy_studio"),
        os.path.realpath("/tmp/galaxy_studio_projects"),
        os.path.realpath("/tmp/galaxy_projects"),
    )
    if not any(real == r or real.startswith(r + os.sep) for r in allowed):
        raise HTTPException(400, "path escapes vault sandbox")
    file_path = real
    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    entry = {
        "vault_id": vault_id,
        "type": vault_type,
        "build_id": safe_id,
        "title": title,
        "filename": os.path.basename(file_path),
        "path": file_path,
        "size_bytes": size,
        "size_human": _format_bytes(size),
        "created_at": datetime.utcnow().isoformat(),
        **extra,
    }
    _vault_entries[vault_id] = entry
    return entry


def _format_bytes(b: int) -> str:
    if b >= 1e9: return f"{b/1e9:.2f} GB"
    if b >= 1e6: return f"{b/1e6:.2f} MB"
    if b >= 1e3: return f"{b/1e3:.2f} KB"
    return f"{b} B"


# ═══════════════════════════════════════════════════════════════════════
# PIPELINE BATCH FILE RETRIEVAL — Paginated, on-demand generation
# ═══════════════════════════════════════════════════════════════════════

def _generate_batch_files(build: dict, batch: int, batch_size: int = 5000) -> dict:
    """Generate files for a specific batch. Uses FULL AAA generators for EVERY file.
    Supports 1M+ total files via procedural expansion with HYPERDENSE code."""
    genre = build["genre"]
    title = build["title"]
    scale_info = build.get("scale_info", {})
    multiplier = scale_info.get("multiplier", 1)
    
    # Batch 0: Core files (configs, stores, utils, types, hooks, screens, components, logic)
    if batch == 0:
        return dict(build.get("files", {}))
    
    # Subsequent batches: Procedural expansion with FULL generators
    offset = (batch - 1) * batch_size  # batch 1 starts at procedural index 0
    files = {}
    global_idx = 0
    
    entity_types = [
        "Goblin", "Skeleton", "Dragon", "Demon", "Wraith", "Golem", "Spider", "Wolf",
        "Bandit", "Necromancer", "Lich", "Ogre", "Troll", "Vampire", "Werewolf", "Elemental",
        "Hydra", "Phoenix", "Chimera", "Minotaur", "Medusa", "Kraken", "Griffin", "Basilisk",
        "Orc", "Imp", "Shade", "Revenant", "Gargoyle", "Harpy", "Centaur", "Cyclops",
        "Wyvern", "Djinn", "Naga", "Treant", "Mushroom", "Slime", "Rat", "Bat",
        "Bear", "Boar", "Deer", "Eagle", "Serpent", "Scorpion", "Beetle", "Wasp",
        "Crab", "Shark", "Whale", "Turtle", "Frog", "Lizard", "Crow", "Owl",
    ]
    weapon_types = [
        "Sword", "Axe", "Bow", "Staff", "Dagger", "Mace", "Spear", "Crossbow",
        "Wand", "Shield", "Greatsword", "Katana", "Scythe", "Flail", "Halberd", "Whip",
        "Rapier", "Claymore", "Longbow", "Shortbow", "Trident", "Hammer", "Pike", "Sickle",
    ]
    biome_types = [
        "Forest", "Desert", "Tundra", "Swamp", "Mountain", "Ocean", "Volcano", "Cave",
        "Jungle", "Plains", "Ruins", "Dungeon", "Castle", "Skylands", "Abyss", "Crystal",
        "Meadow", "Glacier", "Wasteland", "Marsh", "Canyon", "Reef", "Caldera", "Cavern",
    ]
    item_types = ["HealthPotion", "ManaPotion", "StaminaElixir", "Antidote", "FireBomb", "IceShard",
                  "LightningRod", "ShadowCloak", "HolyWater", "PoisonVial", "TeleportScroll", "ReviveStone",
                  "StrengthRing", "WisdomAmulet", "SpeedBoots", "ShieldCharm", "LuckToken", "ExpOrb"]
    skill_types = ["Fireball", "IceBlast", "ThunderStrike", "HealingWave", "ShadowStep", "HolySmite",
                   "PoisonCloud", "WindSlash", "EarthQuake", "WaterTorrent", "NecroBlast", "ArcaneMissile",
                   "Berserk", "Stealth", "Taunt", "Block", "Parry", "Dodge", "Sprint", "Meditate"]
    
    def _emit(path: str, content: str) -> bool:
        nonlocal global_idx, files
        if global_idx >= offset and global_idx < offset + batch_size:
            files[path] = content
        global_idx += 1
        return len(files) >= batch_size
    
    # ═══ Entity variants using FULL _gen_entity_file (120+ lines each) ═══
    max_tiers = min(multiplier // 10 + 1, 200)
    for tier in range(1, max_tiers + 1):
        for base in entity_types:
            vname = f"{base}Tier{tier}"
            if _emit(f"entities/{base.lower()}/{vname}.ts", _gen_entity_file(vname, "enemy", title, genre)):
                return files
    
    # ═══ Weapon variants using FULL _gen_weapon_data (130+ lines each) ═══
    qualities = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine", "Cosmic"]
    for qi, quality in enumerate(qualities):
        for base in weapon_types:
            wname = f"{quality}{base}"
            if _emit(f"data/weapons/{base.lower()}/{wname}.ts", _gen_weapon_data(wname, title, genre)):
                return files
    
    # ═══ Zone files using FULL _gen_biome_file (100+ lines each) ═══
    max_zone_tiers = min(multiplier // 50 + 1, 100)
    for tier in range(1, max_zone_tiers + 1):
        for base in biome_types:
            zname = f"{base}Zone{tier}"
            if _emit(f"world/zones/{base.lower()}/{zname}.ts", _gen_biome_file(zname, title, genre)):
                return files
    
    # ═══ Items using FULL _gen_data_file (200+ lines each) ═══
    max_item_tiers = min(multiplier // 100 + 1, 50)
    for tier in range(1, max_item_tiers + 1):
        for base in item_types:
            iname = f"{base}Tier{tier}"
            if _emit(f"data/items/{base.lower()}/{iname}.ts", _gen_data_file(iname, f"{base} tier {tier} item data", title, genre)):
                return files
    
    # ═══ Skills using FULL _gen_data_file (200+ lines each) ═══
    max_ranks = min(multiplier // 200 + 1, 30)
    for rank in range(1, max_ranks + 1):
        for base in skill_types:
            sname = f"{base}Rank{rank}"
            if _emit(f"data/skills/{base.lower()}/{sname}.ts", _gen_data_file(sname, f"{base} rank {rank} skill data", title, genre)):
                return files
    
    # ═══ Asset manifests for extreme scale ═══
    if multiplier > 100:
        asset_cats = ["textures", "models", "sounds", "animations", "particles", "materials", "ui_sprites", "icons", "skyboxes", "terrain"]
        manifests_per_cat = min(multiplier // 500 + 1, 200)
        for cat in asset_cats:
            for mb in range(manifests_per_cat):
                if _emit(f"assets/manifests/{cat}/batch_{mb:06d}.json", json.dumps({
                    "category": cat, "batch": mb, "count": min(multiplier, 10000),
                    "assets": [{"id": f"{cat}_{mb}_{i:08d}", "size": hash(f"{cat}{mb}{i}") % 10000000 + 1000} for i in range(min(500, multiplier))]
                })): return files
    
    return files


def _get_total_file_count(build: dict) -> int:
    """Calculate total file count including procedural expansion.
    Must stay in sync with _generate_batch_files AND _expand_for_scale."""
    scale_info = build.get("scale_info", {})
    multiplier = scale_info.get("multiplier", 10)
    target = scale_info.get("target_files", 0)
    
    base_count = len(build.get("files", {}))
    
    # Must match _generate_batch_files exactly:
    # enemy entity_types(56) × max_tiers
    max_tiers = min(multiplier // 10 + 1, 200)
    entity_count = max_tiers * 56
    # weapon_types(24) × qualities(8)
    weapon_count = 8 * 24
    # biome_types(24) × max_zone_tiers
    max_zone_tiers = min(multiplier // 50 + 1, 100)
    zone_count = max_zone_tiers * 24
    # item_types(18) × max_item_tiers
    max_item_tiers = min(multiplier // 100 + 1, 50)
    item_count = max_item_tiers * 18
    # skill_types(20) × max_ranks
    max_ranks = min(multiplier // 200 + 1, 30)
    skill_count = max_ranks * 20
    # asset manifests
    asset_count = 0
    if multiplier > 100:
        asset_cats = 10  # matches _generate_batch_files
        manifests_per_cat = min(multiplier // 500 + 1, 200)
        asset_count = asset_cats * manifests_per_cat
    
    total = base_count + entity_count + weapon_count + zone_count + item_count + skill_count + asset_count
    
    # If user requested a target, report that
    if target > 0:
        return max(total, target)
    return total


# ═══════════════════════════════════════════════════════════════════════
# PIPELINE BATCH RETRIEVAL ENDPOINT
# ═══════════════════════════════════════════════════════════════════════

# ─── Pipeline endpoints extracted → routes/galaxy_studio_pipeline.py
#     (see include_router() block near end of file).
def _generate_expansion_files(build: dict, exp_type: str, exp_desc: str, exp_multiplier: int) -> dict:
    """Generate REAL expansion files through the agent code generators.
    Uses the same AAA generators as the main build — screens, components, logic, AI, data, shaders, procgen, networking."""
    title = build["title"]
    genre = build["genre"]
    genre_info = build.get("genre_info", GALAXY_GENRES.get(genre, GALAXY_GENRES["rpg"]))
    vision = build.get("game_vision", "")
    existing_files = set(build.get("files", {}).keys())
    new_files = {}

    # ═══ EXPANSION SCREENS — new areas, dungeons, game modes ═══
    expansion_screens = {
        "content": [
            "ExpansionHubScreen", "NewWorldScreen", "DLCQuestLogScreen",
            "NewBiomeScreen", "ExpansionStoryScreen", "BonusDungeonScreen",
            "ExpansionShopScreen", "NewArenaScreen", "RaidLobbyScreen",
            "EndgameScreen", "NewGamePlusScreen", "ChallengeRunScreen",
        ],
        "systems": [
            "MountCombatScreen", "SiegeScreen", "NavalBattleScreen",
            "PoliticsScreen", "ProfessionScreen", "CompanionScreen",
            "WeatherBattleScreen", "TransmogrifyScreen", "RuneForgeScreen",
        ],
        "zones": [
            "AbyssalDeepScreen", "FrozenWastesScreen", "BurningDesertScreen",
            "HauntedForestScreen", "CrystalCavesScreen", "FloatingIslandsScreen",
            "CorruptedLandsScreen", "ElderWoodsScreen", "MoltenCoreScreen",
            "StarfallPeakScreen", "VoidRealmScreen", "AncientRuinsScreen",
        ],
        "enemies": [
            "BossGalleryScreen", "BestiaryScreen", "EliteChallengeScreen",
            "BountyBoardScreen", "MonsterHuntScreen", "WorldBossTrackerScreen",
        ],
        "items": [
            "SetCollectionScreen", "RuneLibraryScreen", "LegendaryForgeScreen",
            "TransmogClosetScreen", "GemcuttingScreen", "ArtifactMuseumScreen",
        ],
    }
    target_screens = []
    if exp_type == "all":
        for cat_screens in expansion_screens.values():
            target_screens.extend(cat_screens)
    else:
        target_screens = expansion_screens.get(exp_type, expansion_screens["content"])

    for scr in target_screens:
        path = f"expansions/screens/{scr}.tsx"
        if path not in existing_files:
            new_files[path] = _gen_screen_aaa(scr, f"{title} — {exp_desc}", genre)

    # ═══ EXPANSION COMPONENTS — new UI elements ═══
    expansion_components = {
        "content": [
            ("ExpansionBanner", f"DLC banner with expansion title '{exp_desc}', unlock status, progress tracker, animated reveal"),
            ("QuestChainTracker", "multi-quest chain with branching paths, completion markers, reward preview, chapter system"),
            ("NewWorldMap", "expansion world map with fog reveal, fast travel, danger zones, collectible markers, region completion"),
            ("DLCRewardPopup", "expansion-exclusive reward display with animated unbox, rarity effects, stat comparison, equip prompt"),
            ("StoryRecap", "narrative recap with chapter summaries, choice highlights, character relationship changes, timeline view"),
            ("ExpansionLeaderboard", "DLC-specific leaderboard with speed runs, challenge scores, boss kill times, collectible rankings"),
        ],
        "systems": [
            ("MountCombatHUD", "mounted combat overlay with lance aim, charge meter, trample zone, dismount warning, mount health"),
            ("SiegeControls", "siege engine controls with aim, power, ammo types, wall integrity, troop deployment, rally points"),
            ("NavalWheel", "ship helm control with wind direction, sail management, cannon aim, boarding hooks, crew status"),
            ("ProfessionWorkbench", "crafting profession UI with recipe mastery, specialization tree, experiment mode, discovery log"),
            ("CompanionPanel", "companion management with loyalty meter, skill equip, personality traits, conversation starters, gift system"),
            ("WeatherGauge", "weather combat indicator with elemental advantages, forecast, terrain effects, ability modifiers"),
        ],
        "zones": [
            ("ZoneTransition", "seamless zone transition with loading vignette, environment preview, danger warning, level recommendation"),
            ("BiomeHazardIndicator", "environmental hazard display with damage type, safe zones, timer, resistance requirements"),
            ("ExplorationProgress", "zone exploration tracker with discovered areas, hidden secrets, completion percentage, reward thresholds"),
            ("ZoneEventBanner", "dynamic zone event announcement with timer, reward preview, difficulty, player count, teleport option"),
        ],
        "enemies": [
            ("BossPhaseIndicator", "multi-phase boss UI with phase HP, mechanic warnings, enrage timer, DPS check, weak points"),
            ("EliteModifiers", "elite enemy modifier display with affix icons, danger rating, loot bonus, special mechanics"),
            ("BountyTarget", "bounty target card with location, reward, difficulty, time remaining, hunter count, tracking compass"),
            ("MonsterCodex", "monster encyclopedia entry with lore, weaknesses, drop table, kill count, strategies, artwork"),
        ],
        "items": [
            ("SetBonusDisplay", "equipment set bonus UI with active pieces, next threshold, full set preview, stat breakdown"),
            ("RuneSocket", "rune socketing interface with compatibility check, stat preview, removal cost, combination bonuses"),
            ("LegendaryTooltip", "legendary item tooltip with unique lore, proc effect, equip comparison, upgrade path, transmog preview"),
            ("ArtifactPowerTree", "artifact power tree with unlockable nodes, resource cost, synergy paths, prestige levels"),
        ],
    }
    target_components = []
    if exp_type == "all":
        for cat_comps in expansion_components.values():
            target_components.extend(cat_comps)
    else:
        target_components = expansion_components.get(exp_type, expansion_components["content"])

    for comp_name, comp_desc in target_components:
        path = f"expansions/components/{comp_name}.tsx"
        if path not in existing_files:
            new_files[path] = _gen_component_aaa(comp_name, comp_desc, title, genre)

    # ═══ EXPANSION LOGIC SYSTEMS — real game logic through agent generators ═══
    expansion_logic = {
        "content": [
            ("expansionQuestEngine", f"expansion quest system for '{exp_desc}' with new quest chains, world-state triggers, reputation gates, branching outcomes, retroactive completion, DLC-exclusive rewards, cross-expansion references"),
            ("expansionProgressionEngine", "expansion-level progression with level cap increase, prestige talents, paragon points, mastery tracks, catch-up mechanics, veteran rewards, seasonal integration"),
            ("expansionEconomySystem", "DLC economy with new currency, inflation controls, exclusive merchants, cross-economy trading, gold sinks, expansion-only auction categories"),
            ("newGamePlusManager", "NG+ system with difficulty scaling, carried stats, locked/unlocked items, new enemy variants, alternate story paths, bonus objectives"),
        ],
        "systems": [
            ("mountCombatEngine", "mounted combat with lance physics, charge momentum, trample area damage, dismount grapple, mount abilities, jousting tournaments, mount armor system"),
            ("siegeWarfareEngine", "siege system with destructible walls, catapult trajectory, battering ram physics, boiling oil, ladder climbing, troop morale, siege timer, resource logistics"),
            ("navalCombatEngine", "naval combat with broadside volleys, wind physics, boarding mechanics, crew management, ship damage model, repair stations, treasure raids, fleet formations"),
            ("politicsEngine", "political system with faction influence, elections, law proposals, diplomacy negotiations, trade agreements, war declarations, espionage, propaganda"),
            ("professionEngine", "crafting professions with mastery tiers, specialization branches, recipe experimentation, gathering bonuses, work orders, guild commissions, rare discoveries"),
            ("companionAIEngine", "companion AI with loyalty system, personality matrix, conversation memory, gift preferences, combat behavior trees, skill learning, relationship events"),
            ("weatherCombatEngine", "weather combat effects with elemental amplification, terrain modifiers, visibility reduction, movement penalties, ability restrictions, seasonal events"),
            ("runeForgeEngine", "rune crafting system with socket types, rune combinations, power scaling, ancient rune discovery, corruption risk, purification, legendary rune quests"),
        ],
        "zones": [
            ("zoneGeneratorExpansion", "procedural zone expansion with biome blending, danger scaling, resource placement, secret rooms, environmental puzzles, traversal challenges, dynamic events"),
            ("worldEventOrchestrator", "world event system with zone invasion, treasure hunts, boss spawns, faction wars, environmental disasters, celestial events, community goals"),
            ("environmentHazardEngine", "environmental hazard system with damage zones, safe corridors, hazard timers, resistance checks, environmental puzzles, traversal mechanics"),
        ],
        "enemies": [
            ("expansionBossEngine", "expansion boss system with multi-phase encounters, new mechanics, desperation moves, adds management, environmental interactions, mythic difficulty, achievement challenges"),
            ("eliteAffixEngine", "elite enemy affixes with stackable modifiers, synergy combinations, player counters, loot bonus scaling, difficulty ratings, affix immunity crafting"),
            ("bountySystem", "bounty hunting system with target generation, tracking mechanics, reward tiers, reputation gains, hunter rankings, rare bounties, community hunts"),
            ("monsterEvolutionEngine", "enemy evolution system with adaptive difficulty, player-reactive mutations, environmental adaptations, pack behaviors, boss transformations"),
        ],
        "items": [
            ("setEquipmentEngine", "equipment set system with set bonuses, piece tracking, transmog integration, set completion rewards, ancient sets, set upgrade paths, socket inheritance"),
            ("legendaryProcEngine", "legendary proc system with unique effects, internal cooldowns, power scaling, synergy with abilities, visual effects, sound design triggers"),
            ("artifactPowerEngine", "artifact system with power trees, unlock progression, prestige resets, ancient knowledge, artifact quests, corruption/purification, ultimate abilities"),
            ("gemcraftingEngine", "gemcrafting system with gem tiers, combination recipes, socket matching, stat amplification, gem destruction, perfect cuts, legendary gems"),
        ],
    }
    target_logic = []
    if exp_type == "all":
        for cat_logic in expansion_logic.values():
            target_logic.extend(cat_logic)
    else:
        target_logic = expansion_logic.get(exp_type, expansion_logic["content"])

    for logic_name, logic_desc in target_logic:
        path = f"expansions/logic/{logic_name}.ts"
        if path not in existing_files:
            new_files[path] = _gen_logic_aaa(logic_name, logic_desc, title, genre)

    # ═══ EXPANSION AI BEHAVIOR TREES — new enemy/NPC behaviors ═══
    expansion_ai = {
        "content": [
            ("bt_expansion_boss_phase1", f"Expansion boss phase 1 for '{exp_desc}': summon_adds→area_denial→combo_attack→vulnerable_window→heal→phase_transition"),
            ("bt_expansion_boss_phase2", f"Expansion boss phase 2: enraged_state→devastating_slam→chase_player→execute_combo→desperation_heal→final_stand"),
            ("bt_expansion_npc_questgiver", "Expansion NPC: check_prerequisites→offer_quest→provide_lore→give_hint→react_to_progress→celebrate_completion→unlock_next"),
        ],
        "enemies": [
            ("bt_dread_knight", "DreadKnight AI: dark_charge→shield_bash→death_sweep→summon_undead→heal_from_kills→phase2_transform→shadow_realm"),
            ("bt_void_walker", "VoidWalker AI: teleport→void_eruption→reality_tear→dimension_shift→void_prison→collapse_reality→desperation"),
            ("bt_plague_bearer", "PlagueBearer AI: spread_plague→summon_swarm→poison_zone→mutate→consume_adds→pandemic→death_cloud"),
            ("bt_frost_wyrm", "FrostWyrm AI: ice_breath→tail_sweep→freeze_ground→blizzard→aerial_dive→frost_nova→glacial_tomb"),
            ("bt_abyssal_horror", "AbyssalHorror AI: tentacle_slam→fear_aura→consume→deep_dive→tsunami→madness_pulse→kraken_form"),
        ],
        "systems": [
            ("bt_companion_combat", "Companion combat AI: assess_threat→position_optimal→use_ability→protect_player→heal_ally→revive→retreat_when_low"),
            ("bt_siege_defender", "Siege defender AI: man_walls→pour_oil→fire_arrows→repair_gate→rally_troops→call_reinforcements→last_stand"),
            ("bt_naval_crew", "Naval crew AI: man_cannons→repair_hull→board_enemy→defend_ship→adjust_sails→brace_impact→abandon_ship"),
        ],
    }
    target_ai = []
    if exp_type == "all":
        for cat_ai in expansion_ai.values():
            target_ai.extend(cat_ai)
    else:
        target_ai = expansion_ai.get(exp_type, expansion_ai.get("content", []))

    for ai_name, ai_desc in target_ai:
        path = f"expansions/ai/{ai_name}.ts"
        if path not in existing_files:
            new_files[path] = _gen_ai_behavior_tree(ai_name, ai_desc, title, genre)

    # ═══ EXPANSION DATA FILES — new databases ═══
    expansion_data = {
        "content": [
            ("expansion_quests_database", f"Expansion quest database for '{exp_desc}' with 100+ quests across 10 chains, objectives, rewards, prerequisites, voice acting triggers, cutscene references"),
            ("expansion_items_database", "Expansion items with 200+ new items across weapons, armor, consumables, materials, legendary sets, unique effects, upgrade paths"),
            ("expansion_npcs_database", "New NPCs with backstories, dialogue trees, schedules, relationships, quest involvement, merchant inventories, voice profiles"),
        ],
        "enemies": [
            ("expansion_enemies_database", "Expansion enemies with 50+ new types, stats, abilities, loot tables, behavior profiles, spawn conditions, elite variants"),
            ("expansion_boss_database", "Expansion bosses with phases, mechanics, enrage timers, loot tables, achievement conditions, mythic variants, cinematics"),
        ],
        "zones": [
            ("expansion_zones_database", "New zones with biome data, resource nodes, enemy spawns, NPC placements, secrets, events, traversal challenges"),
            ("expansion_worldevents_database", "World events with triggers, phases, rewards, community goals, participation tracking, rare spawn conditions"),
        ],
        "items": [
            ("expansion_sets_database", "Equipment set definitions with pieces, bonuses, ancient variants, transmog appearances, upgrade materials, lore entries"),
            ("expansion_runes_database", "Rune definitions with types, combinations, power levels, socket requirements, legendary runes, corruption effects"),
        ],
    }
    target_data = []
    if exp_type == "all":
        for cat_data in expansion_data.values():
            target_data.extend(cat_data)
    else:
        target_data = expansion_data.get(exp_type, expansion_data.get("content", []))

    for data_name, data_desc in target_data:
        path = f"expansions/data/{data_name}.ts"
        if path not in existing_files:
            new_files[path] = _gen_data_file(data_name, data_desc, title, genre)

    # ═══ EXPANSION SHADERS — new visual effects ═══
    if exp_type in ("all", "zones", "content"):
        expansion_shaders = [
            ("void_distortion", "Void zone visual distortion with reality tears, dimension bleed, chromatic aberration, temporal ghosting"),
            ("corruption_spread", "Corruption visual effect with spreading tendrils, ground decay, particle dissolution, color desaturation"),
            ("abyssal_fog", "Deep abyss fog with bioluminescent particles, pressure distortion, light absorption, creature shadows"),
            ("frost_crystallize", "Freeze effect with ice crystal growth, surface frost, breath vapor, light refraction through ice"),
            ("volcanic_heat", "Heat haze with magma glow, ember particles, thermal distortion, lava surface animation"),
        ]
        for shader_name, shader_desc in expansion_shaders:
            path = f"expansions/shaders/{shader_name}.glsl"
            if path not in existing_files:
                new_files[path] = _gen_shader_code(shader_name, shader_desc, title, genre)

    # ═══ EXPANSION PROCGEN — new procedural content ═══
    if exp_type in ("all", "zones", "content"):
        expansion_procgen = [
            ("expansion_dungeon_gen", "Expansion dungeon generator with new room templates, trap types, puzzle rooms, boss arenas, secret passages, themed decorations"),
            ("expansion_encounter_gen", "DLC encounter generator with new enemy compositions, ambush patterns, elite packs, environmental hazards, boss gauntlets"),
            ("expansion_lore_gen", "Expansion lore generator with new history, factions, mythology, ancient texts, prophecies, character backstories"),
        ]
        for pg_name, pg_desc in expansion_procgen:
            path = f"expansions/procgen/{pg_name}.ts"
            if path not in existing_files:
                new_files[path] = _gen_procgen_code(pg_name, pg_desc, title, genre)

    # ═══ EXPANSION NETWORKING — multiplayer expansion content ═══
    if exp_type in ("all", "systems", "content"):
        expansion_net = [
            ("expansion_sync", "Expansion state sync with new entity types, expansion-specific channels, cross-server events, DLC ownership validation"),
            ("raid_coordinator", "Raid coordination with boss sync, mechanic broadcasts, damage aggregation, loot distribution, wipe detection"),
        ]
        for net_name, net_desc in expansion_net:
            path = f"expansions/networking/{net_name}.ts"
            if path not in existing_files:
                new_files[path] = _gen_networking_code(net_name, net_desc, title, genre)

    # ═══ 4X CODEBASE EXPANSION — Scale entities/zones/weapons/items to 4X base ═══
    # The expansion MUST add at least 4X the base file count
    base_file_count = len(build.get("files", {}))
    target_expansion_files = base_file_count * 4
    handcrafted_count = len(new_files)  # Files already generated above

    # ─── TIER CALCULATION: ensure enough tiers to hit 4X ───
    # With default multiplier 10: tiers = max(16, 10) = 16
    tier_base = max(16, exp_multiplier)

    # ═══ CATEGORY 1: Expansion enemies — 60 types × tier_base tiers ═══
    exp_enemies = [
        "DreadKnight", "VoidWalker", "PlagueBearer", "StormCaller", "ShadowLord",
        "FrostWyrm", "MoltenGolem", "ElderTreent", "AbyssalHorror", "CelestialGuard",
        "ChronoWraith", "BloodAncient", "CrystalSentinel", "ShadowPhoenix", "TidalLord",
        "DoomBringer", "SoulReaper", "FleshWeaver", "BoneLord", "AshStalker",
        "VenomQueen", "ThunderKing", "IceEmpress", "FireEmperor", "NatureSovereign",
        "VoidTitan", "ChaosDragon", "OrderGolem", "TimeWraith", "SpaceBender",
        "BlightKing", "CorruptSeer", "PurgeAngel", "FallenPaladin", "DarkDruid",
        "StormGiant", "FrostGiant", "FireGiant", "MountainGiant", "SeaGiant",
        "PhantomAssassin", "GhostShip", "UndeadDragon", "LichKing", "DeathPriest",
        "PlagueRat", "VenomSpider", "AcidSlime", "CrystalGolem", "ObsidianSentinel",
        "SkyWyrm", "DeepDiver", "SandWorm", "JungleHunter", "TundraWolf",
        "LavaElemental", "IceElemental", "StormElemental", "VoidElemental", "ArcaneElemental",
    ]
    for enemy in exp_enemies:
        for tier in range(1, tier_base + 1):
            path = f"expansions/entities/{enemy.lower()}/{enemy}Tier{tier}.ts"
            if path not in existing_files:
                new_files[path] = _gen_entity_file(f"{enemy}Tier{tier}", "enemy", title, genre)

    # ═══ CATEGORY 2: Expansion biomes — 50 zones × tier_base tiers ═══
    exp_biomes = [
        "AbyssalDeep", "FrozenWastes", "BurningDesert", "HauntedForest", "CrystalCaves",
        "FloatingIslands", "CorruptedLands", "ElderWoods", "MoltenCore", "StarfallPeak",
        "VoidRift", "AncientLibrary", "DragonNest", "ShadowRealm", "CelestialGarden",
        "BlightedMarsh", "ThunderPeaks", "SunkenCity", "ForgottenTemple", "ObsidianFortress",
        "GlacialCavern", "VolcanicCaldera", "CoralReef", "CrystalForest", "MechanicalCity",
        "DreamRealm", "NightmarePlane", "MirrorWorld", "ChaosDimension", "OrderSanctum",
        "TimeLoop", "SpaceStation", "UnderDark", "OverWorld", "BetweenRealms",
        "PrimordialSoup", "ElderTreeHollow", "GiantBoneyard", "DragonGraveyard", "GodsThrone",
        "WorldEdge", "CoreOfPlanet", "MoonSurface", "SunTemple", "StarBridge",
        "VoidBreach", "RealityTear", "DimensionGate", "TimeFracture", "SpaceFold",
    ]
    for biome in exp_biomes:
        for tier in range(1, tier_base + 1):
            path = f"expansions/zones/{biome.lower()}/{biome}Tier{tier}.ts"
            if path not in existing_files:
                new_files[path] = _gen_biome_file(f"{biome}Tier{tier}", title, genre)

    # ═══ CATEGORY 3: Expansion weapons — 32 types × 10 qualities ═══
    exp_weapons = [
        "VoidBlade", "FrostScythe", "PlagueDagger", "StormHammer",
        "ShadowBow", "AbyssalStaff", "DragonSpear", "CelestialWand",
        "ChaosSword", "OrderShield", "TimeAxe", "SpaceLance",
        "BlightMace", "PurgeHalberd", "DoomFlail", "HopeRapier",
        "CrimsonKatana", "AzureGreatsword", "EmeraldCrossbow", "GoldenWhip",
        "ObsidianTrident", "CrystalSickle", "RunePike", "SoulChakram",
        "DarkClaw", "LightFist", "StormMusket", "VoidCannon",
        "PrimalSling", "ArcaneOrb", "NatureStaff", "DeathScythe",
    ]
    exp_qualities = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine", "Cosmic", "Apocalyptic", "Transcendent"]
    for weapon in exp_weapons:
        for quality in exp_qualities:
            path = f"expansions/data/weapons/{quality.lower()}_{weapon.lower()}.ts"
            if path not in existing_files:
                new_files[path] = _gen_weapon_data(f"{quality}{weapon}", title, genre)

    # ═══ CATEGORY 4: Expansion item sets — 30 sets × 12 pieces ═══
    exp_sets = [
        "VoidWalker", "FrostGuard", "PlagueBringer", "StormBorn", "ShadowDancer",
        "DragonSlayer", "CelestialKnight", "AbyssalLord", "NatureSage", "ChaosMaster",
        "TimeWeaver", "SpaceRanger", "BlightKing", "PurgeAngel", "DoomBringer",
        "HopeBearer", "CrimsonFury", "AzureWisdom", "EmeraldGuard", "GoldenOrder",
        "ObsidianWill", "CrystalMind", "RuneForged", "SoulBound", "DarkPact",
        "LightSworn", "StormCaller", "VoidBreaker", "PrimalRage", "ArcaneEcho",
    ]
    exp_pieces = ["Helm", "Chest", "Legs", "Boots", "Gloves", "Cape", "Ring", "Amulet", "Belt", "Pauldrons", "Bracers", "Weapon"]
    for set_name in exp_sets:
        for piece in exp_pieces:
            path = f"expansions/data/sets/{set_name.lower()}/{set_name}{piece}.ts"
            if path not in existing_files:
                new_files[path] = _gen_weapon_data(f"{set_name}{piece}", title, genre)

    # ═══ CATEGORY 5: Expansion classes/skills — 16 classes × tier_base tiers ═══
    exp_classes = ["Warrior", "Mage", "Ranger", "Rogue", "Cleric", "Paladin", "Necromancer", "Druid",
                   "Bard", "Monk", "Warlock", "Sorcerer", "Berserker", "Assassin", "Templar", "Shaman"]
    for cls in exp_classes:
        for tier in range(1, tier_base + 1):
            path = f"expansions/data/skills/{cls.lower()}/{cls}SkillTier{tier}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{cls.lower()}_exp_skills_tier_{tier}", f"Expansion {cls} skills tier {tier}", title, genre)

    # ═══ CATEGORY 6: Expansion armor — 32 types × 10 materials ═══
    exp_armors = [
        "VoidPlate", "FrostMail", "PlagueShroud", "StormGuard",
        "ShadowLeather", "AbyssalRobe", "DragonScale", "CelestialSilk",
        "ChaosWeave", "OrderIron", "TimeCloth", "SpaceFiber",
        "BlightHide", "PurgePlate", "DoomChain", "HopeBarrier",
        "CrimsonBrigandine", "AzureVestment", "EmeraldCuirass", "GoldenAegis",
        "ObsidianCarapace", "CrystalLattice", "RunePlate", "SoulShroud",
        "DarkWraps", "LightArmor", "StormCoat", "VoidMantle",
        "PrimalHide", "ArcaneTunic", "NatureWard", "DeathCloak",
    ]
    exp_materials = ["Iron", "Steel", "Mithril", "Adamantine", "Orichalcum", "Starmetal", "Voidstone", "Dragonbone", "Celestium", "Primordium"]
    for armor in exp_armors:
        for material in exp_materials:
            path = f"expansions/data/armors/{material.lower()}_{armor.lower()}.ts"
            if path not in existing_files:
                new_files[path] = _gen_weapon_data(f"{material}{armor}", title, genre)

    # ═══ CATEGORY 7: Expansion abilities — 60 abilities × 8 ranks ═══
    exp_abilities = [
        "Fireball", "IceStorm", "LightningBolt", "ShadowStrike", "HolySmite",
        "PoisonCloud", "EarthQuake", "WindSlash", "WaterSurge", "VoidPulse",
        "DragonBreath", "PhoenixFlame", "FrostNova", "ThunderClap", "NatureWrath",
        "DeathCoil", "LifeBloom", "ArcaneMissile", "ChaosOrb", "OrderBeam",
        "TimeWarp", "SpaceRend", "BlightWave", "PurgeLight", "DoomRay",
        "HealingTouch", "ShieldWall", "BerserkerRage", "StealthField", "SummonMinion",
        "MeteorShower", "Tsunami", "Tornado", "Avalanche", "Eruption",
        "SoulDrain", "MindControl", "Petrify", "Banish", "Resurrect",
        "Shockwave", "Impale", "Cleave", "Backstab", "HolyNova",
        "CursePlague", "BlessCourage", "Entangle", "Silence", "Polymorph",
        "ChainLightning", "RainOfFire", "BlizzardStorm", "VoidEruption", "SolarFlare",
        "LunarEclipse", "TidalWave", "Sandstorm", "GravityWell", "DimensionDoor",
    ]
    exp_ranks = ["Novice", "Apprentice", "Adept", "Expert", "Master", "Grandmaster", "Legendary", "Transcendent"]
    for ability in exp_abilities:
        for rank in exp_ranks:
            path = f"expansions/data/abilities/{ability.lower()}/{rank.lower()}_{ability.lower()}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{rank}_{ability}", f"{rank}-rank {ability} ability with scaling damage, cooldown, mana cost, special effects, synergies, and combo chains", title, genre)

    # ═══ CATEGORY 8: NPC profiles — 50 NPCs × 5 role variants ═══
    exp_npcs = [
        "ElderSage", "MysteriousStranger", "BlacksmithMaster", "ThievesGuild",
        "RoyalAdvisor", "DesertNomad", "ForestGuardian", "SeaCaptain",
        "MountainHermit", "CityMayor", "TempleHigh", "LibraryKeeper",
        "BountyHunter", "TravelingMerchant", "WarVeteran", "YoungApprentice",
        "AncientDragon", "GhostSpirit", "DemonLord", "AngelGuardian",
        "PirateCaptain", "NinjaAssassin", "GladChampion", "ArenaMaster",
        "AlchemistSage", "RunesmithElder", "BeastTamer", "SkyPilot",
        "UndergroundKing", "SwampWitch", "DesertPrincess", "NorthernKing",
        "SouthernEmpress", "EasternMonk", "WesternGunslinger", "IslandChief",
        "VoidProphet", "TimeKeeper", "SpaceNavigator", "DreamWalker",
        "NightmareHunter", "SoulCollector", "FateWeaver", "LuckBringer",
        "DeathsHand", "LifeSpring", "WarHorn", "PeaceMaker",
        "ChaosAgent", "OrderEnforcer",
    ]
    exp_npc_roles = ["Questgiver", "Merchant", "Trainer", "Companion", "Antagonist"]
    for npc in exp_npcs:
        for role in exp_npc_roles:
            path = f"expansions/data/npcs/{npc.lower()}/{npc}{role}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{npc}_{role}", f"NPC {npc} as {role} with dialogue trees, schedules, relationships, quest hooks, and merchant inventories", title, genre)

    # ═══ CATEGORY 9: Quest scripts — 40 quest chains × 6 stages ═══
    exp_quest_chains = [
        "MainStory", "DarkProphecy", "AncientEvil", "LostKingdom", "DragonWar",
        "VoidIncursion", "TimeParadox", "ShadowConspiracy", "DivineRetribution", "PlagueOrigin",
        "FrostbornLegacy", "DesertMystery", "OceanDepths", "SkyFortress", "UndergroundEmpire",
        "GhostShipCurse", "DragonEggHunt", "AncientRelicSearch", "ForgottenGods", "DemonGates",
        "AngelFall", "KnightTrial", "MageTower", "RogueGuild", "BarbarianHorde",
        "ElvenExodus", "DwarfMine", "OrcInvasion", "UndeadPlague", "ElementalChaos",
        "CosmicAlignment", "DimensionRift", "WorldTreeWilt", "SunMoonEclipse", "StarFall",
        "DreamInvasion", "NightmareWake", "SoulHarvest", "FateChain", "FinalStand",
    ]
    exp_quest_stages = ["Prologue", "Act1", "Act2", "Climax", "Resolution", "Epilogue"]
    for quest in exp_quest_chains:
        for stage in exp_quest_stages:
            path = f"expansions/data/quests/{quest.lower()}/{quest}{stage}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{quest}_{stage}", f"Quest chain '{quest}' stage '{stage}' with objectives, dialogue triggers, reward tables, branching outcomes, and world-state changes", title, genre)

    # ═══ CATEGORY 10: Level designs — 30 levels × 5 difficulty modes ═══
    exp_levels = [
        "TutorialVillage", "DarkForest", "CrystalMine", "VolcanicRift", "FrozenLake",
        "AncientTemple", "SunkenRuins", "SkyTower", "DesertOasis", "SwampLabyrinth",
        "DragonLair", "DemonFortress", "AngelicSanctum", "VoidNexus", "TimeCitadel",
        "SpaceStation", "UnderworldCavern", "CloudCastle", "MushroomGrove", "MechanicalFactory",
        "PirateIsland", "NinjaDojo", "GladiatorArena", "WizardAcademy", "ThievesHideout",
        "KingsThrone", "EmpressPalace", "MonkMonastery", "BarbarianCamp", "FinalBattlefield",
    ]
    exp_difficulties = ["Normal", "Hard", "Nightmare", "Inferno", "Mythic"]
    for level in exp_levels:
        for diff in exp_difficulties:
            path = f"expansions/data/levels/{level.lower()}/{level}{diff}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{level}_{diff}", f"Level '{level}' at {diff} difficulty with enemy placements, traps, rewards, secrets, boss encounters, and environment hazards", title, genre)

    # ═══ CATEGORY 11: Sound design — 30 categories × 8 variants ═══
    exp_sound_categories = [
        "AmbientForest", "AmbientDungeon", "AmbientCity", "AmbientOcean", "AmbientDesert",
        "CombatSword", "CombatMagic", "CombatBow", "CombatExplosion", "CombatImpact",
        "MusicBattle", "MusicExploration", "MusicBoss", "MusicVictory", "MusicDefeat",
        "UIClick", "UIHover", "UIOpen", "UIClose", "UINotification",
        "FootstepStone", "FootstepGrass", "FootstepWater", "FootstepSand", "FootstepMetal",
        "WeatherRain", "WeatherThunder", "WeatherWind", "WeatherSnow", "WeatherSandstorm",
    ]
    exp_sound_variants = ["Variant1", "Variant2", "Variant3", "Variant4", "Variant5", "Variant6", "Variant7", "Variant8"]
    for sound in exp_sound_categories:
        for variant in exp_sound_variants:
            path = f"expansions/data/sounds/{sound.lower()}/{sound}{variant}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{sound}_{variant}", f"Sound design specification for {sound} {variant} with waveform, frequency, duration, envelope, spatial settings, and mix parameters", title, genre)

    # ═══ CATEGORY 12: Particle effects — 20 effects × 8 variants ═══
    exp_particles = [
        "FireBlast", "IceShatter", "LightningStrike", "HealingAura", "PoisonCloud",
        "ExplosionSmoke", "TeleportFlash", "LevelUpGlow", "LootSparkle", "DamageNumbers",
        "BloodSplatter", "WaterSplash", "DustCloud", "LeafFall", "SnowDrift",
        "MagicCircle", "RuneGlow", "SoulWisp", "VoidTear", "StarTrail",
    ]
    for particle in exp_particles:
        for variant in exp_sound_variants:
            path = f"expansions/data/particles/{particle.lower()}/{particle}{variant}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"{particle}_{variant}", f"Particle effect {particle} {variant} with emitter config, physics, color gradient, lifetime, spawn rate, collision, and LOD settings", title, genre)

    # ═══ SAFEGUARD: Guarantee 4X target is met ═══
    # If we're still short, generate additional procedural filler files
    current_count = len(new_files)
    if current_count < target_expansion_files:
        deficit = target_expansion_files - current_count
        filler_categories = [
            ("animations", "animation state machine with blend trees, transitions, IK targets, root motion"),
            ("configs", "configuration preset with gameplay tuning parameters, balance values, difficulty curves"),
            ("tests", "comprehensive test suite with unit tests, integration tests, edge cases, mocks"),
            ("localization", "localization strings with translations, pluralization, RTL support, formatting"),
            ("achievements", "achievement definition with conditions, rewards, progress tracking, display data"),
            ("tutorials", "tutorial step with highlight targets, instruction text, validation, skip logic"),
        ]
        filler_idx = 0
        while len(new_files) < target_expansion_files:
            cat_name, cat_desc = filler_categories[filler_idx % len(filler_categories)]
            path = f"expansions/{cat_name}/generated_{filler_idx:05d}.ts"
            if path not in existing_files:
                new_files[path] = _gen_data_file(f"gen_{cat_name}_{filler_idx}", f"{cat_desc} — procedurally generated expansion file #{filler_idx}", title, genre)
            filler_idx += 1
            if filler_idx > target_expansion_files * 2:
                break  # Safety valve

    return new_files


@router.post("/expand")
async def expand_game(req: ExpandRequest):
    """Expand a completed game in the BACKGROUND (4X codebase multiplier).

    Re-queries the agent expansion pipeline and generates 4X the base game's
    files. The heavy generation used to run synchronously (~50s) and tripped the
    30s request-duration cap → client 504 even though the server finished. It is
    now a background job: this returns immediately with status 'running'; poll
    GET /expand/status/{build_id} for progress + the final result."""
    build = await _load_build(req.build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    if build["status"] != "completed":
        raise HTTPException(400, "Build must be completed before expansion")

    # Don't double-launch if an expansion is already in flight for this build.
    existing = build.get("_expansion")
    if existing and existing.get("status") == "running":
        return {
            "build_id": req.build_id,
            "expansion_status": "running",
            "poll_url": f"/api/galaxy-studio/expand/status/{req.build_id}",
            "phases_total": existing.get("phases_total", len(EXPANSION_PHASES)),
            "files_before": existing.get("files_before", 0),
            "message": "An expansion is already running for this build.",
        }

    # Use the build's own scale multiplier so expansion matches scale (fast).
    build_multiplier = build.get("scale_info", {}).get("multiplier", 10)
    expansion_scale = _parse_scale(req.scale, req.target_new_files, 0)
    exp_multiplier = max(expansion_scale.get("multiplier", 1), build_multiplier)
    exp_type = req.expansion_type
    exp_desc = req.description or f"Expansion pack for {build['title']}"
    pre_count = _vault_total_files(build)

    # Seed expansion job state so a poll right after launch sees "running".
    build["_expansion"] = {
        "status": "running",
        "expansion_type": exp_type,
        "description": exp_desc,
        "scale": expansion_scale,
        "multiplier": exp_multiplier,
        "started_at": datetime.utcnow().isoformat(),
        "phases_total": len(EXPANSION_PHASES),
        "phases_completed": 0,
        "files_added": 0,
        "files_before": pre_count,
        "total_files": pre_count,
        "error": None,
    }
    await _save_build(build)

    # Launch the heavy work in the background; return immediately.
    asyncio.create_task(
        _run_expansion_bg(req.build_id, exp_type, exp_desc, exp_multiplier, expansion_scale)
    )

    return {
        "build_id": req.build_id,
        "expansion_status": "running",
        "poll_url": f"/api/galaxy-studio/expand/status/{req.build_id}",
        "phases_total": len(EXPANSION_PHASES),
        "files_before": pre_count,
        "message": (
            f"Expansion '{exp_desc}' started — generating files across "
            f"{len(EXPANSION_PHASES)} phases in the background. "
            f"Poll /expand/status/{req.build_id} for progress."
        ),
    }


async def _run_expansion_bg(build_id: str, exp_type: str, exp_desc: str,
                            exp_multiplier: int, expansion_scale: dict):
    """Background worker for /expand. Runs the synergy pipeline, then the heavy
    (sync, CPU-bound) file generation in a thread executor so the event loop
    stays responsive, and records the result on build['_expansion']."""
    try:
        build = await _load_build(build_id)
        if not build:
            return
        exp = build.get("_expansion") or {}

        # ═══ RUN EXPANSION THROUGH AGENT PIPELINE (fast) ═══
        synergy_activations = []
        expansion_phases_log = []
        agents_mobilized = 0
        for phase in EXPANSION_PHASES:
            phase_synergies = _get_phase_synergies(phase["id"].replace("exp_", ""))
            synergy_activations.append({
                "phase": phase["id"], "name": phase["name"], "agents": phase["agents"],
                "links_activated": len(phase_synergies), "synergies": phase_synergies[:5],
            })
            agents_mobilized += phase["agents"]
            expansion_phases_log.append({
                "id": phase["id"], "name": phase["name"], "agents": phase["agents"],
                "pct": phase["pct"], "status": "completed",
                "timestamp": datetime.utcnow().isoformat(),
            })
            exp["phases_completed"] = exp.get("phases_completed", 0) + 1

        # ═══ GENERATE EXPANSION FILES — offload sync CPU work to a thread ═══
        loop = asyncio.get_event_loop()
        new_files = await loop.run_in_executor(
            None, _generate_expansion_files, build, exp_type, exp_desc, exp_multiplier,
        )

        # ═══ PERSIST EXPANSION FILES TO VAULT (survives restarts) ═══
        pre_count = exp.get("files_before", _vault_total_files(build))
        try:
            from core import build_vault as _bv
            _bv.append_files(build_id, new_files)
        except Exception as _ve:
            print(f"[GALAXY expand-bg] vault append failed (memory-only): {_ve}")
            if not isinstance(build.get("files"), dict):
                build["files"] = {}
            build["files"].update(new_files)
        build["file_count"] = _vault_total_files(build)

        total_new_lines = sum(c.count('\n') + 1 for c in new_files.values() if isinstance(c, str))
        total_new_bytes = sum(len(c.encode('utf-8')) if isinstance(c, str) else len(c) for c in new_files.values())

        # Track expansion history
        if "expansions" not in build:
            build["expansions"] = []
        build["expansions"].append({
            "type": exp_type, "description": exp_desc, "scale": expansion_scale,
            "files_added": len(new_files), "files_before": pre_count,
            "files_after": build["file_count"], "phases_completed": len(EXPANSION_PHASES),
            "agents_mobilized": agents_mobilized, "synergy_activations": len(synergy_activations),
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Categorize new files
        categories = {}
        for fpath in new_files.keys():
            parts = fpath.split("/")
            cat = parts[1] if len(parts) > 1 else "root"
            categories[cat] = categories.get(cat, 0) + 1

        exp.update({
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "files_added": len(new_files),
            "total_files": build["file_count"],
            "total_new_lines": total_new_lines,
            "total_new_bytes": total_new_bytes,
            "total_new_size_human": _format_bytes(total_new_bytes),
            "agents_mobilized": agents_mobilized,
            "synergy_activations": len(synergy_activations),
            "file_categories": categories,
            "phases": expansion_phases_log,
            "total_expansions": len(build["expansions"]),
            "message": (
                f"Expansion '{exp_desc}' completed — {len(new_files)} new files "
                f"({_format_bytes(total_new_bytes)}, {total_new_lines} lines) generated by "
                f"{agents_mobilized:,} agents across {len(EXPANSION_PHASES)} phases. "
                f"Total: {build['file_count']} files."
            ),
        })
        build["_expansion"] = exp
        await _save_build(build)
        print(f"[GALAXY expand-bg] DONE {build_id}: +{len(new_files)} files → {build['file_count']} total")
    except Exception as e:
        try:
            b = await _load_build(build_id)
            if b is not None:
                ex = b.get("_expansion") or {}
                ex.update({"status": "failed", "error": "expansion failed",
                           "completed_at": datetime.utcnow().isoformat()})
                b["_expansion"] = ex
                await _save_build(b)
        except Exception:
            pass
        print(f"[GALAXY expand-bg] FAILED for {build_id}: {e}")


@router.get("/expand/status/{build_id}")
async def expand_status(build_id: str):
    """Poll the background expansion job for a build. Returns status
    'none' | 'running' | 'completed' | 'failed' plus progress/result fields."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    exp = build.get("_expansion")
    if not exp:
        return {"build_id": build_id, "status": "none"}
    return {"build_id": build_id, **exp}


# ═══════════════════════════════════════════════════════════════════════
# ZIP VAULT — Generate, store, list, download ZIPs (LEGACY HEADER, see below)
# ═══════════════════════════════════════════════════════════════════════
#
# Phase-6 (Feb 2026): The ``POST /vault/zip/{build_id}`` endpoint was
# extracted into ``routes/galaxy_studio_vault.py`` alongside the read
# endpoints. The APK build endpoint (``POST /vault/zip-to-apk/{id}``)
# stays in this module because it owns the EAS subprocess wiring +
# app.json templating that aren't worth dragging out as proxies.


# ═══════════════════════════════════════════════════════════════════════════
# Vault READ + ZIP-WRITE endpoints were extracted in Feb 2026 (Phase-5 +
# Phase-6 decomposition) → routes/galaxy_studio_vault.py.
# They mount on the SAME public paths via include_router below. The APK
# build endpoint (/vault/zip-to-apk/{id}) remains in this file because it
# has deeper helper dependencies (EAS subprocess, _disk_write_file,
# app.json templating).
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_vault import router as _vault_router
    router.include_router(_vault_router)
except Exception as _vt_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] vault subrouter import SKIPPED: {type(_vt_err).__name__}: {_vt_err}", flush=True, file=_s.stderr)


# ═══════════════════════════════════════════════════════════════════════
# APK VAULT — Full ZIP → APK flow via EAS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/vault/zip-to-apk/{build_id}")
async def vault_zip_to_apk(build_id: str, req: ZipToApkRequest):
    """Package game files + trigger an EAS APK build — as a BACKGROUND job.

    The packaging pipeline (ZIP all files → npm install → eas init → eas build)
    can take several MINUTES and used to run synchronously, tripping the 30s
    request-duration cap (client 504 while the server kept working). It now
    returns immediately with apk_status 'running'; poll
    GET /vault/apk-status/{build_id} for stage progress + the final result
    (download_url, eas_build_id). Once packaging finishes, the existing
    /eas-status/{build_id} endpoint tracks the EAS cloud build.
    """
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")

    from core import build_vault as _bv
    vault_count = _bv.get_file_count(build_id)
    mem_files = build.get("files") or {}
    if vault_count == 0 and not mem_files:
        raise HTTPException(400, "No files. Complete build first.")

    # Don't double-launch if packaging is already in flight.
    existing = build.get("_apk")
    if existing and existing.get("status") == "running":
        return {
            "build_id": build_id,
            "apk_status": "running",
            "poll_url": f"/api/galaxy-studio/vault/apk-status/{build_id}",
            "stage": existing.get("stage"),
            "message": "Packaging is already running for this build.",
        }

    token = req.expo_token or os.environ.get("EXPO_TOKEN", "")
    if not token:
        from dotenv import load_dotenv
        load_dotenv()
        token = os.environ.get("EXPO_TOKEN", "")
    slug = _safe_slug(build.get("title") or "build", fallback="build")

    build["_apk"] = {
        "status": "running",
        "stage": "queued",
        "has_token": bool(token),
        "started_at": datetime.utcnow().isoformat(),
        "error": None,
        "result": None,
    }
    await _save_build(build)

    asyncio.create_task(_run_apk_bg(build_id, token, slug))

    return {
        "build_id": build_id,
        "apk_status": "running",
        "poll_url": f"/api/galaxy-studio/vault/apk-status/{build_id}",
        "stage": "queued",
        "message": (
            "APK packaging started in the background"
            + (" (EAS cloud compile)." if token else " — ZIP only (no EXPO_TOKEN).")
            + f" Poll /vault/apk-status/{build_id} for progress."
        ),
    }


def _apk_pipeline_sync(build: dict, build_id: str, token: str, slug: str, prog: dict):
    """Pure-sync packaging pipeline (ZIP + EAS subprocess chain). Runs inside a
    thread executor so the event loop stays free. Mutates `prog['stage']` as it
    advances and collects vault entries into prog['_entries'] for the async
    wrapper to persist. Returns the result dict."""
    from core import build_vault as _bv
    mem_files = build.get("files") or {}
    entries = prog.setdefault("_entries", [])

    # ─── Stream the ZIP from vault ────────────────────────────────────
    prog["stage"] = "zipping"
    safe_id = _safe_segment(build_id, what="build_id")
    safe_slug = _safe_slug(slug, fallback="build")
    zip_filename = f"{safe_slug}-{safe_id[:8]}.zip"
    zip_path = _resolve_under_dir(VAULT_DIR, "zips", zip_filename)
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    written_paths: set[str] = set()
    total_files = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for vp, vc in _bv.iter_files(build_id):
            if vp in written_paths:
                continue
            try:
                _zip_write_file(zf, f"{slug}/{vp}", vc)
                written_paths.add(vp); total_files += 1
            except Exception:
                continue
        for vp, vc in mem_files.items():
            if vp in written_paths:
                continue
            try:
                _zip_write_file(zf, f"{slug}/{vp}", vc)
                written_paths.add(vp); total_files += 1
            except Exception:
                continue

    zip_entry = _vault_save(safe_id, "zip", build.get("title", "game"), zip_path, {
        "file_count": total_files, "genre": build.get("genre", "unknown"),
    })
    entries.append(zip_entry)
    prog["stage"] = "zip_ready"

    result = {
        "build_id": build_id,
        "vault_id": zip_entry["vault_id"],
        "status": "zip_ready",
        "filename": zip_filename,
        "size": zip_entry["size_human"],
        "size_bytes": zip_entry["size_bytes"],
        "file_count": total_files,
        "download_url": f"/api/galaxy-studio/vault/download/{zip_entry['vault_id']}",
        "message": f"ZIP ready: {zip_filename} ({zip_entry['size_human']})",
    }

    if token:
        try:
            project_dir = _resolve_under_dir("/tmp/galaxy_studio_projects", safe_id)
            actual_dir = _resolve_under_dir(project_dir, safe_slug)
            os.makedirs(actual_dir, exist_ok=True)

            prog["stage"] = "materializing"
            files_written = 0
            try:
                for vpath, vcontent in _bv.iter_files(build_id):
                    if not isinstance(vcontent, str):
                        continue
                    full_path = os.path.join(actual_dir, vpath)
                    try:
                        _disk_write_file(full_path, vcontent); files_written += 1
                    except Exception:
                        continue
            except Exception as _ve:
                print(f"[APK] vault stream failed ({_ve}); falling back to memory")
            for path, content in (build.get("files") or {}).items():
                full_path = os.path.join(actual_dir, path)
                if os.path.exists(full_path):
                    continue
                try:
                    _disk_write_file(full_path, content); files_written += 1
                except Exception:
                    continue
            print(f"[APK] materialised {files_written} files into {actual_dir}")
            if files_written < 5:
                raise RuntimeError(
                    f"APK packaging aborted: only {files_written} files materialised from vault. "
                    f"Build may have failed silently. Re-run /vault/zip to verify file count first."
                )

            env = os.environ.copy(); env["EXPO_TOKEN"] = token
            git_env = {**env, "GIT_AUTHOR_NAME": "Galaxy Studio", "GIT_AUTHOR_EMAIL": "build@galaxy.studio", "GIT_COMMITTER_NAME": "Galaxy Studio", "GIT_COMMITTER_EMAIL": "build@galaxy.studio"}

            subprocess.run(["git", "init"], cwd=actual_dir, capture_output=True, timeout=10)
            subprocess.run(["git", "add", "."], cwd=actual_dir, capture_output=True, timeout=10)
            subprocess.run(["git", "commit", "-m", "Galaxy Studio Factory build"], cwd=actual_dir, capture_output=True, env=git_env, timeout=15)

            prog["stage"] = "npm_install"
            subprocess.run(["npm", "install", "--legacy-peer-deps"], cwd=actual_dir, capture_output=True, timeout=120)

            app_json_path = _resolve_under_dir(actual_dir, "app.json")
            if os.path.exists(app_json_path):
                with open(app_json_path, 'r') as f:
                    app_config = json.load(f)
                if "expo" in app_config:
                    if "extra" in app_config["expo"] and "eas" in app_config["expo"]["extra"]:
                        app_config["expo"]["extra"]["eas"].pop("projectId", None)
                with open(app_json_path, 'w') as f:
                    json.dump(app_config, f, indent=2)

            prog["stage"] = "eas_init"
            subprocess.run(["eas", "init", "--non-interactive", "--force"], cwd=actual_dir, env=env, capture_output=True, text=True, timeout=60)
            subprocess.run(["git", "add", "."], cwd=actual_dir, capture_output=True, timeout=10)
            subprocess.run(["git", "commit", "-m", "eas init"], cwd=actual_dir, capture_output=True, env=git_env, timeout=15)

            prog["stage"] = "eas_build"
            eas_result = subprocess.run(
                ["eas", "build", "--platform", "android", "--profile", "preview", "--non-interactive", "--no-wait", "--json"],
                cwd=actual_dir, env=env, capture_output=True, text=True, timeout=180,
            )

            if eas_result.returncode == 0:
                try:
                    eas_output = json.loads(eas_result.stdout)
                    eas_build_id = eas_output[0].get("id", "") if isinstance(eas_output, list) else eas_output.get("id", "")
                    apk_entry = _vault_save(build_id, "apk", build["title"], "", {
                        "eas_build_id": eas_build_id, "status": "building",
                        "genre": build["genre"], "file_count": len(build.get("files") or {}),
                        "era_id": build.get("era_id"), "era_label": build.get("era_label"),
                    })
                    entries.append(apk_entry)
                    build["eas_build_id"] = eas_build_id
                    build["eas_build_status"] = "building"
                    result["apk_status"] = "building"
                    result["apk_vault_id"] = apk_entry.get("vault_id")
                    result["eas_build_id"] = eas_build_id
                    result["apk_message"] = f"APK build triggered on EAS! Track at expo.dev. Build ID: {eas_build_id}"
                    result["status"] = "apk_building"
                except json.JSONDecodeError:
                    result["apk_status"] = "submitted"
                    result["apk_message"] = "Build submitted to EAS."
            else:
                result["apk_status"] = "eas_error"
                result["apk_error"] = eas_result.stderr[:500] if eas_result.stderr else "EAS build failed"
                result["apk_message"] = "EAS build failed. ZIP is available for download."
        except Exception:
            result["apk_status"] = "error"
            result["apk_error"] = "apk_build_failed"
            result["apk_message"] = "APK build error. ZIP available."
    else:
        try:
            apk_entry = _vault_save(build_id, "apk", build["title"], "", {
                "status": "no_token", "genre": build["genre"],
                "file_count": len(build.get("files") or {}),
                "era_id": build.get("era_id"), "era_label": build.get("era_label"),
                "note": "Fallback placeholder — set EXPO_TOKEN in backend/.env to enable real EAS cloud compile.",
            })
            entries.append(apk_entry)
            result["apk_status"] = "no_token"
            result["apk_vault_id"] = apk_entry.get("vault_id")
            result["apk_message"] = "No EXPO_TOKEN configured. Add token in backend/.env and restart backend for real EAS cloud compile."
        except Exception:
            result["apk_status"] = "no_token"
            result["apk_message"] = "No EXPO_TOKEN available. ZIP created for manual APK build."

    return result


async def _run_apk_bg(build_id: str, token: str, slug: str):
    """Background worker for /vault/zip-to-apk. Offloads the blocking ZIP + EAS
    subprocess pipeline to a thread, persists vault entries, and records the
    final result on build['_apk']."""
    try:
        build = await _load_build(build_id)
        if not build:
            return
        apk_state = build.get("_apk") or {}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _apk_pipeline_sync, build, build_id, token, slug, apk_state,
        )
        # Persist collected vault entries (zip + apk) to Mongo.
        for ent in apk_state.pop("_entries", []) or []:
            try:
                await _save_vault_entry(ent)
            except Exception as se:
                print(f"[APK vault save] {se}")
        apk_state.update({
            "status": "completed",
            "stage": "done",
            "completed_at": datetime.utcnow().isoformat(),
            "result": result,
        })
        build["_apk"] = apk_state
        await _save_build(build)
        print(f"[GALAXY apk-bg] DONE {build_id}: {result.get('apk_status')} ({result.get('file_count')} files)")
    except Exception as e:
        try:
            b = await _load_build(build_id)
            if b is not None:
                st = b.get("_apk") or {}
                st.update({"status": "failed", "error": "apk_packaging_failed",
                           "completed_at": datetime.utcnow().isoformat()})
                st.pop("_entries", None)
                b["_apk"] = st
                await _save_build(b)
        except Exception:
            pass
        print(f"[GALAXY apk-bg] FAILED for {build_id}: {e}")


@router.get("/vault/apk-status/{build_id}")
async def vault_apk_status(build_id: str):
    """Poll the background APK packaging job. Returns status
    'none' | 'running' | 'completed' | 'failed', the current `stage`, and (when
    completed) the full `result` (download_url, eas_build_id, apk_status...)."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    apk = build.get("_apk")
    if not apk:
        return {"build_id": build_id, "status": "none"}
    out = {k: v for k, v in apk.items() if k != "_entries"}
    out["build_id"] = build_id
    return out


@router.get("/jobs/active")
async def galaxy_active_jobs():
    """Lightweight cross-build scan of in-memory builds for any RUNNING
    background job (expansion or APK packaging). Powers the home Galaxy-tile
    badge so progress is visible without opening the modal. In-memory only —
    running jobs keep their build hot, so this reliably reflects live work."""
    jobs = []
    try:
        # ── LIVE FILE-GENERATION BUILDS ──
        # _active_runners is the AUTHORITATIVE set of builds whose runner is
        # currently generating files (the runner adds its id on start, removes
        # it on finish). This is independent of whether the in-memory _builds
        # cache happens to hold the doc, so it never misses a live build nor
        # counts a post-restart zombie. This is the long phase users wait on,
        # so surface it on the home badge + banner.
        for bid in list(_active_runners):
            _tsk = _background_tasks.get(bid)
            if _tsk is not None and _tsk.done() and not _physical_build_workers(bid):
                continue
            b = {}
            try:
                _cand = _builds.get(bid)
                if isinstance(_cand, dict):
                    b = _cand
            except Exception:
                b = {}
            # Skip builds already finalized (e.g. via force-complete) even if
            # the runner is still winding down — they must not keep /jobs/active
            # (and the hub banner) lit or hold the single-build slot.
            if not _build_has_live_work(bid):
                continue
            phases = b.get("phases") or []
            done = sum(1 for p in phases if isinstance(p, dict) and p.get("status") == "completed")
            jobs.append(
                {
                    "build_id": bid,
                    "title": b.get("title") or str(bid)[:8],
                    "kind": "build",
                    "stage": (
                        "stopping; draining physical work"
                        if b.get("_bg_stop_requested")
                        else f"phase {done}/{len(phases) or 100}"
                    ),
                    "files": b.get("file_count", 0),
                }
            )

        # ── POST-BUILD EXPANSION / APK PACKAGING JOBS (in-memory state) ──
        for bid, b in list(_builds.items()):
            if not isinstance(b, dict):
                continue
            title = b.get("title") or str(bid)[:8]
            exp = b.get("_expansion")
            if isinstance(exp, dict) and exp.get("status") == "running":
                jobs.append({
                    "build_id": bid, "title": title, "kind": "expand",
                    "stage": f"pipeline {exp.get('phases_completed', 0)}/{exp.get('phases_total', 7)}",
                })
            apk = b.get("_apk")
            if isinstance(apk, dict) and apk.get("status") == "running":
                jobs.append({
                    "build_id": bid, "title": title, "kind": "apk",
                    "stage": apk.get("stage") or "packaging",
                })
    except Exception as e:
        print(f"[GALAXY jobs/active] WARN: {e}")
    return {"ok": True, "count": len(jobs), "jobs": jobs}


# ═══════════════════════════════════════════════════════════════════════════
#  SELF-HEAL ENDPOINTS — resurrect a lost/stuck build + watchdog health
#  (added at end of file so route table isn't re-ordered by accident)
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Watchdog/diagnose/resurrect/force-advance endpoints were extracted in
# Feb 2026 (Phase-4 decomposition) → routes/galaxy_studio_watchdog.py.
# They mount on the SAME public paths via include_router below and use
# the shared state (_builds, _active_runners) + lazy proxies from
# galaxy_studio_state — no circular import.
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_watchdog import router as _wd_router
    router.include_router(_wd_router)
except Exception as _wd_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] watchdog subrouter import SKIPPED: {type(_wd_err).__name__}: {_wd_err}", flush=True, file=_s.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# EAS CONNECTION STATUS — lets the frontend show "EAS live" in the UI and
# detect when the real compile path is ready. Replaces the old MOCKED flow.
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# EAS proxy endpoints (/eas/whoami, /eas/build-status/{id}) were extracted
# in Feb 2026 (Phase-2 decomposition) → routes/galaxy_studio_eas.py.
# They mount on the SAME public paths via include_router below.
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_eas import (
        router as _eas_router,
        eas_build_status,  # re-exported for `galaxy_eas_status` below
    )
    router.include_router(_eas_router)
except Exception as _eas_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] EAS subrouter import SKIPPED: {type(_eas_err).__name__}: {_eas_err}", flush=True, file=_s.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Agent Once-Over (/agents/once-over, /agents/once-over/last) and Vault Admin
# (/admin/vault/stats, /admin/vault/prune) endpoints were extracted in Jun 2026
# (decomposition continuation) → routes/galaxy_studio_agents.py and
# routes/galaxy_studio_vault_admin.py. Both are self-contained (no in-memory
# build state) and mount on the SAME public paths via include_router below.
# ═══════════════════════════════════════════════════════════════════════════
try:
    from routes.galaxy_studio_agents import router as _agents_router
    router.include_router(_agents_router)
except Exception as _ag_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] agents subrouter import SKIPPED: {type(_ag_err).__name__}: {_ag_err}", flush=True, file=_s.stderr)

try:
    from routes.galaxy_studio_vault_admin import router as _vault_admin_router
    router.include_router(_vault_admin_router)
except Exception as _va_err:  # pragma: no cover — defensive
    import sys as _s
    print(f"[GALAXY] vault-admin subrouter import SKIPPED: {type(_va_err).__name__}: {_va_err}", flush=True, file=_s.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# JEEVES → GALAXY STUDIO MERGE (2026-04-20)
# Consolidates the old /api/jeeves-master/* build endpoints into a single
# /api/galaxy-studio/* namespace so there are no orphaned routes. The two
# routes below preserve the frontend's existing call signatures so no UI
# regression is needed. The legacy router remains file-resident for safety
# but should not be registered by server.py anymore.
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/compile/{build_id}")
async def galaxy_compile_build(build_id: str, expo_token: Optional[str] = None):
    """Real EAS cloud compile for a Galaxy Studio build.

    Replaces /api/jeeves-master/compile/{build_id}. Uses the same real
    (non-mocked) flow: git init → npm install → eas init → eas build
    --platform android --profile preview --non-interactive --no-wait.
    """
    if not code_execution_enabled():
        return execution_disabled_response("Galaxy Studio EAS compilation")

    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if not build.get("files"):
        raise HTTPException(400, "No code files generated yet. Complete build first.")

    # Lazy import so we don't pull subprocess/zipfile unless needed
    import subprocess as _sp, json as _json, os as _os, zipfile as _zf
    from datetime import datetime as _dt
    from dotenv import load_dotenv as _ld
    try:
        _ld()
    except Exception as _dotenv_error:
        print(f"[GALAXY] dotenv load failed: {_dotenv_error}", flush=True)

    token = expo_token or _os.environ.get("EXPO_TOKEN", "")
    if not token:
        return {
            "build_id": build_id,
            "status": "no_token",
            "message": "EXPO_TOKEN missing. Set it in /app/backend/.env and restart.",
        }

    # Package the build into a ZIP + extract to /tmp project dir
    safe_id = _safe_segment(build_id, what="build_id")
    project_dir = _resolve_under_dir("/tmp/galaxy_projects", safe_id)
    _os.makedirs(project_dir, exist_ok=True)
    try:
        zip_path = _resolve_under_dir("/tmp/galaxy_projects", f"{safe_id}.zip")
        with _zf.ZipFile(zip_path, "w", _zf.ZIP_DEFLATED) as zf:
            for path, content in (build.get("files") or {}).items():
                if isinstance(content, str):
                    zf.writestr(path, content)
        with _zf.ZipFile(zip_path, "r") as zf:
            zf.extractall(project_dir)
        subdirs = [d for d in _os.listdir(project_dir) if _os.path.isdir(_os.path.join(project_dir, d)) and d not in {".", ".."}]
        actual_dir = _resolve_under_dir(project_dir, subdirs[0]) if subdirs else project_dir
    except Exception as pe:
        print(f"[GALAXY] ZIP extract failed: {type(pe).__name__}", flush=True)
        return {"build_id": build_id, "status": "package_error", "message": "zip_extract_failed"}

    env = _os.environ.copy()
    env["EXPO_TOKEN"] = token
    git_env = {
        **env,
        "GIT_AUTHOR_NAME": "Galaxy Studio",
        "GIT_AUTHOR_EMAIL": "build@galaxy.studio",
        "GIT_COMMITTER_NAME": "Galaxy Studio",
        "GIT_COMMITTER_EMAIL": "build@galaxy.studio",
    }
    try:
        _sp.run(["git", "init"], cwd=actual_dir, capture_output=True, timeout=10)
        _sp.run(["git", "add", "."], cwd=actual_dir, capture_output=True, timeout=15)
        _sp.run(["git", "commit", "-m", "Galaxy Studio build"],
                cwd=actual_dir, capture_output=True, env=git_env, timeout=20)
        npm_res = _sp.run(
            ["npm", "install", "--legacy-peer-deps", "--no-audit", "--no-fund"],
            cwd=actual_dir, capture_output=True, text=True, timeout=240,
        )
        # Sanitise app.json (strip placeholder projectId)
        app_json_path = _resolve_under_dir(actual_dir, "app.json")
        if _os.path.exists(app_json_path):
            try:
                with open(app_json_path) as f:
                    app_config = _json.load(f)
                if "expo" in app_config and "extra" in app_config["expo"]:
                    app_config["expo"]["extra"].get("eas", {}).pop("projectId", None)
                with open(app_json_path, "w") as f:
                    _json.dump(app_config, f, indent=2)
            except Exception as _app_config_error:
                print(f"[GALAXY] app.json update failed: {_app_config_error}", flush=True)
        _sp.run(["eas", "init", "--non-interactive", "--force"],
                cwd=actual_dir, env=env, capture_output=True, text=True, timeout=90)
        _sp.run(["git", "add", "."], cwd=actual_dir, capture_output=True, timeout=15)
        _sp.run(["git", "commit", "-m", "eas init"],
                cwd=actual_dir, capture_output=True, env=git_env, timeout=20)
        eas_res = _sp.run(
            ["eas", "build", "--platform", "android", "--profile", "preview",
             "--non-interactive", "--no-wait", "--json"],
            cwd=actual_dir, env=env, capture_output=True, text=True, timeout=300,
        )
        if eas_res.returncode != 0:
            return {
                "build_id": build_id, "status": "eas_error",
                "message": "EAS build submit failed.",
                "eas_stderr": (eas_res.stderr or "")[-600:],
                "npm_stderr": (npm_res.stderr or "")[-400:] if npm_res.returncode != 0 else "",
            }
        eas_build_id = ""
        try:
            out = _json.loads(eas_res.stdout)
            eas_build_id = (out[0] if isinstance(out, list) else out).get("id", "")
        except _json.JSONDecodeError:
            pass
        build["eas_build_id"] = eas_build_id
        build["eas_build_status"] = "building"
        build["eas_started_at"] = _dt.utcnow().isoformat()
        await _save_build(build)
        return {
            "build_id": build_id,
            "eas_build_id": eas_build_id,
            "status": "building",
            "message": "Galaxy Studio cloud compile triggered on Expo EAS.",
            "expo_dashboard": f"https://expo.dev/accounts/galaxystudio/builds/{eas_build_id}" if eas_build_id else None,
        }
    except _sp.TimeoutExpired:
        return {"build_id": build_id, "status": "timeout", "message": "EAS step timed out"}
    except Exception:
        return {"build_id": build_id, "status": "error", "message": "EAS build failed"}


@router.get("/eas-status/{build_id}")
async def galaxy_eas_status(build_id: str):
    """Poll the status of a Galaxy Studio EAS cloud build. Replaces
    /api/jeeves-master/eas-status/{build_id}. Accepts a GALAXY build_id
    (not the raw EAS build id) and resolves through build['eas_build_id']."""
    build = await _load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    eas_id = build.get("eas_build_id") or ""
    if not eas_id:
        return {
            "build_id": build_id,
            "eas_build_id": None,
            "status": build.get("eas_build_status", "not_submitted"),
            "message": "EAS build not triggered yet. Call POST /compile/{build_id} first.",
        }
    # Delegate to the real EAS proxy
    try:
        return await eas_build_status(eas_id)  # type: ignore[name-defined]
    except Exception:
        return {"build_id": build_id, "eas_build_id": eas_id, "status": "error", "error": "EAS status check failed"}


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-EVICT completed builds from in-memory cache to prevent memory growth.
# Runs every 5 minutes; evicts any build whose status is in {completed, failed,
# aborted} and whose last_touch is older than 15 minutes. The Mongo doc is
# kept so /files and /status still work after eviction (re-loaded on demand).
# ═══════════════════════════════════════════════════════════════════════════

import threading as _evict_thr
import time as _evict_time

def _evict_stale_builds_loop():
    while True:
        try:
            _evict_time.sleep(300)  # 5 min
            now = _evict_time.time()
            evicted = 0
            for bid in list(_builds.keys()):
                b = _builds.get(bid) or {}
                status = b.get("status", "")
                if status not in ("completed", "failed", "aborted", "cancelled"):
                    continue
                if _build_has_live_work(bid) or b.get("_vault_write_failed") or b.get("files"):
                    continue  # never evict live custody or the only copy of unflushed artifacts
                touch = b.get("_last_touch") or b.get("completed_at") or b.get("_bg_started")
                try:
                    if isinstance(touch, str):
                        from datetime import datetime as __dt
                        touch_ts = __dt.fromisoformat(touch).timestamp()
                    else:
                        touch_ts = float(touch or 0)
                except Exception:
                    touch_ts = now  # keep if unparseable
                if now - touch_ts > 900:  # 15 min old
                    _builds.pop(bid, None)
                    _background_tasks.pop(bid, None)
                    _active_runners.discard(bid)
                    evicted += 1
            if evicted:
                print(f"[GALAXY] evict: removed {evicted} stale builds from memory")
        except Exception as _ee:
            print(f"[GALAXY] evict error: {_ee}")

_evict_thread = _evict_thr.Thread(target=_evict_stale_builds_loop, daemon=True, name="galaxy-evict")
_evict_thread.start()
