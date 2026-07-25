"""
core/routes_registry.py — Declarative router registration helper.

Replaces the ~625 lines of try/except + ``if X is not None: app.include_router(X)``
boilerplate that used to live in server.py.

★ Migration strategy
--------------------
Adding a new route module is now a single-line append to one of the two
lists below. The helper retains the same lazy-import + SKIPPED-on-failure
semantics that the old per-router try/except blocks had, so a broken
optional router can never bring down the whole boot.

    1. If the route module already declares ``APIRouter(prefix="/api/...")``
       internally → append to ``KNOWN_ROUTES``.
    2. If the route module declares a bare prefix (e.g. ``/health``) and
       relies on the mount to add ``/api`` → append to ``KNOWN_ROUTES_WITH_PREFIX``.

Why it's safe
-------------
* Same lazy ``importlib.import_module`` semantics as the old try/except blocks.
* Same SKIPPED-with-stderr-print fallback if a module fails to import.
* Routes are registered in the SAME order as declared (FastAPI behaviour
  preserved).
"""
from __future__ import annotations

import importlib
import sys
import time
from typing import List, Tuple, Union

from fastapi import FastAPI

#  A route entry is either ``(module_path, attribute_name)`` or
#  ``(module_path, attribute_name, url_prefix)``.
RouteEntry = Union[Tuple[str, str], Tuple[str, str, str]]


def register_routes(app: FastAPI, entries: List[RouteEntry]) -> dict:
    """
    Register each router in ``entries`` on the given FastAPI app.
    Returns a small report ``{"ok": N, "skipped": M, "skipped_names": [...]}``
    so callers (and the boot logger) can verify the result.
    """
    started = time.time()
    ok = 0
    skipped_names: List[str] = []
    for entry in entries:
        if len(entry) == 2:
            module_path, attr = entry  # type: ignore[misc]
            prefix = None
        elif len(entry) == 3:
            module_path, attr, prefix = entry  # type: ignore[misc]
        else:
            skipped_names.append(f"<malformed entry: {entry!r}>")
            continue
        try:
            mod = importlib.import_module(module_path)
            router = getattr(mod, attr, None)
            if router is None:
                skipped_names.append(f"{module_path} (attr {attr!r} missing)")
                continue
            if prefix:
                app.include_router(router, prefix=prefix)
            else:
                app.include_router(router)
            ok += 1
        except Exception as e:
            skipped_names.append(f"{module_path} ({type(e).__name__}: {e})")
            print(
                f"[BOOT] route import SKIPPED: {module_path} -> {type(e).__name__}: {e}",
                flush=True,
                file=sys.stderr,
            )
    elapsed_ms = int((time.time() - started) * 1000)
    print(
        f"[BOOT] routes_registry: registered={ok} skipped={len(skipped_names)} "
        f"dur_ms={elapsed_ms}",
        flush=True,
        file=sys.stderr,
    )
    return {"ok": ok, "skipped": len(skipped_names), "skipped_names": skipped_names}


# ───────────────────────────────────────────────────────────────────────
# KNOWN_ROUTES — modules whose APIRouter already includes "/api/..." in
# its prefix declaration. They are mounted WITHOUT any extra prefix.
# ───────────────────────────────────────────────────────────────────────
KNOWN_ROUTES: List[RouteEntry] = [
    # ── Phase-1 (Feb 2026): v19.0+ subsystem routers ────────────────────
    ("routes.resilience_forge",                 "router"),
    ("routes.sentinel_array",                   "router"),
    ("routes.game_mechanics_nexus",             "router"),
    ("routes.game_factory_quantum_core",        "router"),
    ("routes.jeeves_game_builder",              "router"),
    ("routes.game_deployment_pipeline",         "router"),
    ("routes.game_domains_mega_expansion",      "router"),
    ("routes.game_domains_hyperscale",          "router"),
    # ── Galaxy Studio & Swarm ───────────────────────────────────────────
    ("routes.galaxy_studio",                    "router"),
    ("routes.global_search",                    "router"),
    ("routes.swarm_hub",                        "router"),
    ("routes.swarm_cold_legion",                "router"),
    ("routes.swarm_planner",                    "router"),
    ("routes.item_foundry",                     "router"),
    ("routes.vault_gdd",                        "router"),
    ("routes.asset_forge",                      "router"),
    ("routes.eras",                             "router"),
    ("routes.forge_registry",                   "router"),
    ("routes.final_build",                      "router"),
    ("routes.construct_forge",                  "router"),
    ("routes.universal_forge",                  "router"),
    ("routes.tool_forge",                       "router"),
    ("routes.systems_forge",                    "router"),
    ("routes.galaxy_studio_axes",               "router"),
    ("routes.build_ledger",                     "router"),
    ("routes.text_gamefile",                    "router"),
    ("routes.stage_builder",                    "router"),
    ("routes.build_journey",                    "router"),
    ("routes.storage",                          "router"),
    ("routes.refine_gates",                     "router"),
    ("routes.gamefile_pipeline",                "router"),
    ("routes.churn",                            "router"),
    ("routes.orchestrator",                     "router"),
    ("routes.provenance",                       "router"),
    ("routes.director",                         "router"),
    ("routes.gameforge_cns",                    "router"),
    ("routes.gameforge_studio",                 "router"),
    ("routes.gameforge_map",                    "router"),
    ("routes.gameforge_knowledge",              "router"),
    ("routes.gameforge_build",                  "router"),
    ("routes.gameforge_runtime",                "router"),
    ("routes.gameforge_planning",               "router"),
    ("routes.gameforge_jury",                   "router"),
    ("routes.gameforge_tools",                  "router"),
    ("routes.gameforge_coverage",               "router"),
    ("routes.gameforge_workflow",               "router"),
    ("routes.prood",                            "router"),
    ("routes.omega_conductor",                  "router"),
    ("routes.lafs",                             "router"),
    ("routes.agent_swarm",                      "router"),
    ("routes.ops_scheduler",                    "router"),
    ("routes.jeeves_compose",                   "router"),
    ("routes.jeeves_media",                     "router"),
    ("routes.gameforge_auth",                   "router"),
    ("routes.nexus",                            "router"),
    # ── Quality-of-life / engagement routers ────────────────────────────
    ("routes.spaced_repetition",                "router"),
    ("routes.daily_challenges",                 "router"),
    ("routes.ai_reader",                        "router"),
    ("routes.pomodoro",                         "router"),
    ("routes.adaptive_difficulty",              "router"),
    ("routes.enhancements",                     "router"),
    ("routes.code_playground",                  "router"),
    ("routes.gamification",                     "router"),
    ("routes.language_classes",                 "router"),
    ("routes.agent_knowledge",                  "router"),
    ("routes.coding_dictionary",                "router"),
    ("routes.rosetta_challenge",                "router"),
    ("routes.leaderboards",                     "router"),
    ("routes.anticheat",                        "router"),
    ("routes.llm_router",                       "router"),
    ("routes.design_spec",                      "router"),
    ("routes.discourse",                        "router"),
    ("routes.playable_discovery",               "router"),
    ("routes.playable_board",                   "router"),
    ("routes.playable",                         "router"),
    ("routes.playable_edit",                    "router"),
    ("routes.playable_artwire",                 "router"),
    ("routes.playable_pipeline",                "router"),
    ("routes.game_kb",                          "router"),
    ("routes.game_modes",                       "router"),
    ("routes.snowball_bigwins",                 "router"),
    ("routes.snowball",                         "router"),
    ("routes.snowball_audit",                   "router"),
    ("routes.snowball_improve",                 "router"),
    ("routes.agent_logs",                       "router"),
    ("routes.canon_rag",                        "router"),
    ("routes.canon_graph",                      "router"),
    ("routes.groupchat",                        "router"),
    ("routes.photoreal",                        "router"),
    ("routes.playable_kbwire",                  "router"),
    ("routes.playable_sentience",               "router"),
    ("routes.playable_aesthetics",              "router"),
    ("routes.playable_physics",                 "router"),
    ("routes.playable_factions_wire",           "router"),
    ("routes.playable_polish",                  "router"),
    ("routes.faction_sim",                      "router"),
    ("routes.playable_derive",                  "router"),
    ("routes.playable_cover",                   "router"),
    ("routes.playable_repair",                  "router"),
    ("routes.collections",                      "router"),
    ("routes.marketplace",                      "router"),
    ("routes.tournaments",                      "router"),
    ("routes.liveops",                          "router"),
    ("routes.ops",                              "router"),
    ("routes.governance",                       "router"),
    ("routes.creator_prefs",                    "router"),
    ("routes.creator_economy",                  "router"),
    ("routes.share",                            "router"),
    ("routes.worldforge",                       "router"),
    ("routes.worldforge_publish",               "router"),
    ("routes.agent_memory",                     "router"),
    ("routes.asset_genesis",                    "router"),
    ("routes.multiplayer_scaffold",             "router"),
    ("routes.snowball_wins",                    "router"),
    # ── Rewired orphaned game-build routers (bare paths → /api/game-router mount) ──
    ("routes.game_router_build",                "router", "/api/game-router"),
    ("routes.game_router_competitor",           "router", "/api/game-router"),
    ("routes.game_router_layers",               "router", "/api/game-router"),
    # ── Reconnected orphaned game-building & knowledge features (were dead code) ──
    ("routes.game_systems_pipeline",            "router"),
    ("routes.jeeves_master_build",              "router"),
    ("routes.knowledge_updater",                "router"),
    ("routes.vfx_materials_pipeline",           "router"),

    # ── Phase-2 (Feb 2026): engine + pipeline routers (self-prefixed) ───
    ("routes.world_engine",                     "router"),
    ("routes.narrative_engine",                 "router"),
    ("routes.logic_engine",                     "router"),
    ("routes.physics_engine",                   "router"),
    ("routes.math_engine",                      "router"),
    ("routes.cs_engine",                        "router"),
    ("routes.hybrid_pipeline",                  "router"),
    ("routes.sota_extended",                    "router"),
    ("routes.learning_engine",                  "router"),
    ("routes.immersive_learning",               "router"),
    ("routes.reading_time",                     "router"),
    ("routes.logscraper",                       "router"),
    ("routes.quiz_bank",                        "router"),
    ("routes.reading_curriculum",               "router"),
    ("routes.jeeves_eq",                        "router"),
    ("routes.export_github",                    "router"),
    ("routes.ai_toolkit_enhanced",              "router"),
    ("routes.synergy",                          "router"),
    # ── Jeeves persona / voice / tutor ─────────────────────────────────
    ("routes.jeeves_hyperion",                  "router"),
    ("routes.jeeves_voice",                     "router"),
    ("routes.immersive_tutor",                  "router"),
    ("routes.jeeves_synergy",                   "router"),
    ("routes.npc_pipeline",                     "router"),
    ("routes.game_logic_pipeline",              "router"),
    ("routes.animation_pipeline",               "router"),
    ("routes.jeeves_core",                      "router"),
    ("routes.jeeves_persona",                   "router"),
    # ── World / behaviour / testing pipelines ──────────────────────────
    ("routes.world_management_pipeline",        "router"),
    ("routes.behaviour_npc_memory_pipeline",    "router"),
    ("routes.testing_qa_pipeline",              "router"),
    ("routes.interactive_narrative_pipeline",   "router"),
    ("routes.server_backend_pipeline",          "router"),
    ("routes.economy_pipeline",                 "router"),
    ("routes.world_models_pipeline",            "router"),
    ("routes.neural_rendering_pipeline",        "router"),
    ("routes.action_gameplay_pipeline",         "router"),
    ("routes.director_pipeline",                "router"),
    ("routes.hardware_optimization_pipeline",   "router"),
    ("routes.monetization_pipeline",            "router"),
    ("routes.bot_persona_pipeline",             "router"),
    ("routes.ai_bible_enhanced",                "router"),
    # ── Academy / curriculum / camera ──────────────────────────────────
    ("routes.academy_v3",                       "router"),
    ("routes.reading_content",                  "router"),
    ("routes.git_operations",                   "router"),
    ("routes.camera_director",                  "router"),
    ("routes.physics_pipeline",                 "router"),
    ("routes.sorting_vault",                    "router"),
    ("routes.camera_academy",                   "router"),
    ("routes.jeeves_camera",                    "router"),
    ("routes.language_academy",                 "router"),
    ("routes.jeeves_languages",                 "router"),
    ("routes.class_progress",                   "router"),
    ("routes.math_academy",                     "router"),
    ("routes.pipeline_agents",                  "router"),
    ("routes.quality_control",                  "router"),
    # ── Game factory / studio / armor ──────────────────────────────────
    ("routes.game_factory",                     "router"),
    ("routes.studio_api",                       "router"),
    ("routes.overheat_system",                  "router"),
    ("routes.performance_armor",                "router"),
]


# ───────────────────────────────────────────────────────────────────────
# KNOWN_ROUTES_WITH_PREFIX — modules whose APIRouter declares a bare
# (non-/api) prefix and rely on the mount to inject "/api". Migrated from
# the original lines 7980-8170 of server.py.
# ───────────────────────────────────────────────────────────────────────
KNOWN_ROUTES_WITH_PREFIX: List[RouteEntry] = [
    ("routes.health",                       "router", "/api"),
    ("routes.feature_flags",                "router", "/api"),
    ("routes.observability_v2",             "router", "/api"),
    ("routes.boot",                         "router", "/api"),
    ("routes.expo_flaps",                   "router", "/api"),
    ("routes.bible",                        "router", "/api"),
    ("routes.compiler",                     "router", "/api"),
    ("routes.hub",                          "router", "/api"),
    ("routes.ai",                           "router", "/api"),
    ("routes.ai_pipeline",                  "router", "/api"),
    ("routes.curriculum",                   "router", "/api"),
    ("routes.vault",                        "router", "/api"),
    ("routes.build_pipeline",               "router", "/api"),
    ("routes.apk_inspector",                "router", "/api"),
    ("routes.telemetry",                    "router", "/api"),
    ("routes.code_to_app_pipeline",         "router", "/api"),
    ("routes.dna_preview_router",           "router", "/api"),
    ("routes.image_generation",             "router", "/api"),
    ("routes.ai_debugger",                  "router", "/api"),
    ("routes.music_pipeline",               "router", "/api"),
    ("routes.interactive_education",        "router", "/api"),
    ("routes.jeeves_tutor",                 "router", "/api"),
    ("routes.masterclass",                  "router", "/api"),
    ("routes.asset_pipeline",               "router", "/api"),
    ("routes.game_genres",                  "router", "/api"),
    ("routes.ai_log_vault",                 "router", "/api"),
    ("routes.multi_agent",                  "router", "/api"),
    ("routes.sota_2026",                    "router", "/api"),
    ("routes.code_intelligence",            "router", "/api"),
    ("routes.collaboration",                "router", "/api"),
    ("routes.intelligence_collab",          "router", "/api"),
    # ── Phase-6 (Feb 2026): server.py monolith decomposition ────────────
    ("routes.compiler_tools",               "router", "/api"),
    ("routes.hub_tools",                    "router", "/api"),
]


# ───────────────────────────────────────────────────────────────────────
# Stage A4 — LOGICAL ROUTE-TREE GROUPING
# ───────────────────────────────────────────────────────────────────────
# Rather than physically relocating 284 route modules (68 of which import
# each other), the route tree is grouped *logically* by module-name prefix.
# ``route_group_summary()`` classifies every declared route into one of these
# buckets and reports the counts — giving an auditable, package-like view of
# the API surface without risking a fragile cross-import reshuffle.
ROUTE_GROUPS: List[Tuple[str, Tuple[str, ...]]] = [
    ("gameforge", ("routes.gameforge",)),
    ("prood",     ("routes.prood", "routes.churn", "routes.orchestrator", "routes.provenance")),
    ("omega",     ("routes.omega",)),
    ("lafs",      ("routes.lafs",)),
    ("jeeves",    ("routes.jeeves",)),
    ("agents",    ("routes.agent", "routes.multi_agent", "routes.pipeline_agents", "routes.swarm", "routes.groupchat")),
    ("playable",  ("routes.playable", "routes.game_kb", "routes.game_modes", "routes.snowball", "routes.canon")),
    ("worldforge", ("routes.worldforge", "routes.asset_genesis", "routes.faction")),
    ("engines",   ("routes.world_engine", "routes.narrative_engine", "routes.logic_engine",
                   "routes.physics_engine", "routes.math_engine", "routes.cs_engine")),
    ("pipelines", ("routes.",)),  # any *_pipeline caught below via suffix
    ("academy",   ("routes.academy", "routes.curriculum", "routes.reading", "routes.language",
                   "routes.math_academy", "routes.class_")),
    ("infra",     ("routes.health", "routes.boot", "routes.telemetry", "routes.observability",
                   "routes.feature_flags", "routes.ops", "routes.governance", "routes.storage")),
]


def group_of(module_path: str) -> str:
    """Classify a ``routes.xyz`` module path into a logical group name."""
    if module_path.endswith("_pipeline"):
        return "pipelines"
    for name, prefixes in ROUTE_GROUPS:
        if name == "pipelines":
            continue
        if any(module_path.startswith(p) for p in prefixes):
            return name
    return "other"


def route_group_summary() -> dict:
    """Return ``{group_name: [module, ...]}`` over all declared routes."""
    summary: dict[str, list[str]] = {}
    for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX):
        mod = entry[0]
        summary.setdefault(group_of(mod), []).append(mod)
    return {g: sorted(mods) for g, mods in sorted(summary.items())}


def register_known_routes(app: FastAPI) -> dict:
    """Register every router declared in this module. Mounts the prefixed
    routers FIRST (so their /api/* paths are visible to OpenAPI before the
    self-prefixed routers add their own /api/* paths)."""
    r1 = register_routes(app, KNOWN_ROUTES_WITH_PREFIX)
    r2 = register_routes(app, KNOWN_ROUTES)
    combined = {
        "ok": r1["ok"] + r2["ok"],
        "skipped": r1["skipped"] + r2["skipped"],
        "skipped_names": r1["skipped_names"] + r2["skipped_names"],
        # Stage A4 — logical route-tree grouping (no physical file moves; 68
        # route modules cross-import each other so grouping is expressed as a
        # classifier rather than a package reshuffle).
        "groups": route_group_summary(),
    }
    # ★ Surface the report on /api/health/registry. Best-effort — the
    # diagnostic endpoint is optional, so a missing module never fails boot.
    try:
        from routes.registry_health import record_registry_report, router as _rh_router
        record_registry_report(combined)
        app.include_router(_rh_router, prefix="/api")
    except Exception:
        pass
    # ★ Mount the central control plane (oversikt) — adds
    #   /api/health/overview and /api/health/redundancies.
    try:
        from core.control_plane import router as _cp_router
        app.include_router(_cp_router, prefix="/api")
    except Exception:
        pass
    return combined


__all__ = [
    "RouteEntry",
    "register_routes",
    "register_known_routes",
    "KNOWN_ROUTES",
    "KNOWN_ROUTES_WITH_PREFIX",
    "ROUTE_GROUPS",
    "group_of",
    "route_group_summary",
]
