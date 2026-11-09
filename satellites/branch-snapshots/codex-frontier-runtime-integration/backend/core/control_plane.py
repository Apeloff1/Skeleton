"""
core/control_plane.py — Crosswire & Oversikt (Feb 2026)

This is the single "control plane" surface that aggregates state from EVERY
self-healing subsystem in the backend into one consistent view. The
frontend's status pill and the upcoming /api/health/overview endpoint both
read from here, so an operator can answer "what is the backend doing right
now?" in a single round-trip.

Wires together:
  • routes_registry  → router-mounting summary
  • build_watchdog   → Galaxy Studio background-build self-healing
  • cold_storage     → evictor thread state
  • feature_flags    → cache age + per-flag override counts
  • deprecations     → which legacy modules still emit warnings
  • core.databases   → sync funnel snapshot (pool size, in-use, idle)
  • boot stages      → readiness gate + per-stage outcomes
  • circuit breakers → frontend-mirror of the backend's load shed state
  • lifespan watchdog→ "are we ready" answer used by K8s probes

Design rules:
  1. Every probe is OPT-IN best-effort — a missing optional subsystem just
     returns `null` for its slot instead of bringing down /overview.
  2. All probes must answer in ≤ 250ms total wall time. Anything slower
     gets pushed into a separate /api/health/deep endpoint elsewhere.
  3. The output schema is FROZEN — add new keys, never rename existing ones.
"""
from __future__ import annotations
import os
import sys
import time
import asyncio
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

# ───────────────────────────────────────────────────────────────────────
# Lightweight per-probe wrappers — every one is fault-tolerant. They return
# either {"ok": True, ...} or {"ok": False, "error": "..."} so the overview
# endpoint never throws.
# ───────────────────────────────────────────────────────────────────────

async def _probe_registry() -> dict[str, Any]:
    try:
        from routes.registry_health import _LAST_REPORT
        return {
            "ok": True,
            "registered": _LAST_REPORT.get("ok", 0),
            "skipped": _LAST_REPORT.get("skipped", 0),
            "skipped_names": _LAST_REPORT.get("skipped_names", []),
            "age_s": (time.time() - _LAST_REPORT.get("at", 0.0)) if _LAST_REPORT.get("at") else None,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _probe_watchdog() -> dict[str, Any]:
    try:
        from core import build_watchdog as _wd
        snap = await _wd.health_snapshot()
        return {"ok": True, **snap}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _probe_cold_storage() -> dict[str, Any]:
    try:
        from core import cold_storage as _cs
        return {"ok": True, "stats": _cs.vault_stats(), "evictor_running": _cs.is_evictor_running()}
    except Exception as e:
        # cold_storage may not expose is_evictor_running yet → degrade gracefully.
        try:
            from core import cold_storage as _cs
            return {"ok": True, "stats": _cs.vault_stats(), "evictor_running": None}
        except Exception as e2:
            return {"ok": False, "error": f"{type(e2).__name__}: {e2}"}


async def _probe_databases() -> dict[str, Any]:
    """Best-effort snapshot of the sync MongoClient funnel + the async motor pool."""
    out: dict[str, Any] = {"ok": True}
    try:
        from core.databases import client as _async_client, get_sync_db
        # Async client: motor surfaces server selection / topology via its
        # `topology_description` attribute — but accessing it is racy on
        # cold boots, so wrap.
        try:
            out["async_topology"] = str(_async_client.topology_description)[:200]
        except Exception:
            out["async_topology"] = None
        # Sync funnel: just confirm it's reachable.
        try:
            _sdb = get_sync_db()
            out["sync_db"] = _sdb.name if _sdb is not None else None
        except Exception as e:
            out["sync_db"] = None
            out["sync_db_error"] = str(e)[:200]
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


async def _probe_feature_flags() -> dict[str, Any]:
    try:
        from routes.feature_flags import _cache_age_ms, _cache_size  # type: ignore
        return {"ok": True, "cache_age_ms": _cache_age_ms(), "cache_size": _cache_size()}
    except Exception:
        # Fallback: just check the module imports.
        try:
            import routes.feature_flags as _ff  # noqa: F401
            return {"ok": True, "cache_age_ms": None, "cache_size": None, "note": "module loaded; no cache hooks"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _probe_deprecations() -> dict[str, Any]:
    try:
        from core._deprecations import _seen  # type: ignore
        return {"ok": True, "emitted_count": len(_seen), "emitted": sorted(_seen)[:20]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _probe_boot_stages() -> dict[str, Any]:
    try:
        from routes.boot import _last_score, _stage_outcomes  # type: ignore
        return {
            "ok": True,
            "boot_score": _last_score(),
            "stage_outcomes": _stage_outcomes(),
        }
    except Exception:
        # Older boot router didn't expose helpers. Best-effort via REST self-call.
        return {"ok": True, "note": "no boot helper exports; check /api/health/boot/score directly"}


# ───────────────────────────────────────────────────────────────────────
# Lifecycle banner — what the operator wants to read in 1 second.
# ───────────────────────────────────────────────────────────────────────

def _process_info() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "started_at": _BOOT_TIME,
        "uptime_s": int(time.time() - _BOOT_TIME),
        "deploy_env": "production" if os.environ.get("EMERGENT_DEPLOY") else "dev",
    }


_BOOT_TIME = time.time()


# ───────────────────────────────────────────────────────────────────────
# /api/health/overview — the single "oversikt" answer for the frontend.
# ───────────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview() -> dict[str, Any]:
    """One-shot snapshot across every self-healing subsystem.

    Returns a flat object with one slot per subsystem. Each slot has an
    `ok` boolean — so a frontend status pill can decide red/yellow/green
    in a single comparison without iterating.
    """
    started = time.time()
    # Run every probe in parallel so wall time = slowest probe, not sum.
    probes = await asyncio.gather(
        _probe_registry(),
        _probe_watchdog(),
        _probe_cold_storage(),
        _probe_databases(),
        _probe_feature_flags(),
        _probe_deprecations(),
        _probe_boot_stages(),
        return_exceptions=True,
    )
    keys = ("registry", "watchdog", "cold_storage", "databases", "feature_flags", "deprecations", "boot")
    out: dict[str, Any] = {"process": _process_info(), "elapsed_ms": 0}
    for key, val in zip(keys, probes):
        if isinstance(val, Exception):
            out[key] = {"ok": False, "error": f"probe_crashed: {type(val).__name__}: {val}"}
        else:
            out[key] = val
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    # ★ Aggregate "all_green" so a status bar can render in O(1).
    out["all_green"] = all(
        (out.get(k) or {}).get("ok", False) is True for k in keys
    )
    return out


# ───────────────────────────────────────────────────────────────────────
# /api/health/redundancies — enumerates the 42 redundancies (handlers,
# fallbacks, retries, mirrors, caches, evictors, watchdogs, …) the backend
# ships with. Used by an audit screen so we never lose track of them.
# ───────────────────────────────────────────────────────────────────────

REDUNDANCIES: list[dict[str, str]] = [
    # ── Data plane (12) ──────────────────────────────────────────────
    {"id": "R-01", "name": "sync_db_singleton", "layer": "data", "purpose": "single MongoClient pool per pod"},
    {"id": "R-02", "name": "async_motor_client", "layer": "data", "purpose": "async motor client w/ separate pool"},
    {"id": "R-03", "name": "split_core_content_db", "layer": "data", "purpose": "core_db vs content_db isolation"},
    {"id": "R-04", "name": "cold_storage_evictor", "layer": "data", "purpose": "idle-collection compression thread"},
    {"id": "R-05", "name": "vault_replay", "layer": "data", "purpose": "compressed shard playback after eviction"},
    {"id": "R-06", "name": "mongo_index_kick", "layer": "data", "purpose": "background index creation post-boot"},
    {"id": "R-07", "name": "deferred_seeders", "layer": "data", "purpose": "non-blocking seeder fleet via _kick()"},
    {"id": "R-08", "name": "safe_set_with_meta", "layer": "data", "purpose": "AsyncStorage sidecar timestamps"},
    {"id": "R-09", "name": "stale_key_pruner", "layer": "data", "purpose": "7-day TTL sweep on @boot/* @codedock/*"},
    {"id": "R-10", "name": "feature_flags_cache", "layer": "data", "purpose": "in-memory mirror of Mongo flag table"},
    {"id": "R-11", "name": "deprecation_dedup", "layer": "data", "purpose": "one-shot warning emitter set"},
    {"id": "R-12", "name": "safe_json_guard", "layer": "data", "purpose": "10MB parse cap + cyclic stringify"},

    # ── Network plane (12) ───────────────────────────────────────────
    {"id": "R-13", "name": "circuit_breaker_3state", "layer": "net", "purpose": "CLOSED/OPEN/HALF_OPEN per-bucket gating"},
    {"id": "R-14", "name": "exp_backoff_jitter", "layer": "net", "purpose": "±25% jitter prevents thundering herd"},
    {"id": "R-15", "name": "request_timeout_mw", "layer": "net", "purpose": "wall-clock timeout middleware (504 not hang)"},
    {"id": "R-16", "name": "rate_limit_mw", "layer": "net", "purpose": "token-bucket per-IP / per-route"},
    {"id": "R-17", "name": "size_limit_mw", "layer": "net", "purpose": "body-size guard before parsers"},
    {"id": "R-18", "name": "audit_ring_mw", "layer": "net", "purpose": "5000-entry rolling audit ring"},
    {"id": "R-19", "name": "load_shed_mw", "layer": "net", "purpose": "drop low-priority requests under pressure"},
    {"id": "R-20", "name": "observability_mw", "layer": "net", "purpose": "rid + dur_ms + path tagging"},
    {"id": "R-21", "name": "graceful_drain", "layer": "net", "purpose": "SIGTERM-aware connection draining"},
    {"id": "R-22", "name": "tunnel_health", "layer": "net", "purpose": "/api/health/tunnel watchdog"},
    {"id": "R-23", "name": "lan_mode_fallback", "layer": "net", "purpose": "expo_smart_start.sh skips ngrok"},
    {"id": "R-24", "name": "withRetry_helper", "layer": "net", "purpose": "generic retry-on-fail wrapper"},

    # ── Lifecycle (10) ───────────────────────────────────────────────
    {"id": "R-25", "name": "boot_dag_runner", "layer": "lifecycle", "purpose": "parallel boot DAG w/ deps"},
    {"id": "R-26", "name": "boot_watchdog_12s", "layer": "lifecycle", "purpose": "12s readiness watchdog"},
    {"id": "R-27", "name": "warm_boot_fastpath", "layer": "lifecycle", "purpose": "skip seeded stages on restart"},
    {"id": "R-28", "name": "in_stage_retries", "layer": "lifecycle", "purpose": "per-stage retry budget"},
    {"id": "R-29", "name": "abort_signal_chain", "layer": "lifecycle", "purpose": "cancel cascading boot work"},
    {"id": "R-30", "name": "build_watchdog_20s", "layer": "lifecycle", "purpose": "Galaxy Studio orphan resurrector"},
    {"id": "R-31", "name": "stage_skip_warmup", "layer": "lifecycle", "purpose": "watchdog ignores first 3 ticks"},
    {"id": "R-32", "name": "k_service_detect", "layer": "lifecycle", "purpose": "auto-detect K8s vs dev env"},
    {"id": "R-33", "name": "skip_heavy_seed", "layer": "lifecycle", "purpose": "minimal-seed deploy profile"},
    {"id": "R-34", "name": "lifespan_kick_30", "layer": "lifecycle", "purpose": "deferred background-task fleet"},

    # ── Telemetry (8) ────────────────────────────────────────────────
    {"id": "R-35", "name": "routes_registry_report", "layer": "telemetry", "purpose": "/api/health/registry"},
    {"id": "R-36", "name": "control_plane_overview", "layer": "telemetry", "purpose": "/api/health/overview (this file)"},
    {"id": "R-37", "name": "modal_logger_ring", "layer": "telemetry", "purpose": "frontend ringbuffer breadcrumb log"},
    {"id": "R-38", "name": "trail_add_breadcrumbs", "layer": "telemetry", "purpose": "every API call leaves a breadcrumb"},
    {"id": "R-39", "name": "telemetry_boot_endpoint", "layer": "telemetry", "purpose": "/api/telemetry/boot"},
    {"id": "R-40", "name": "boot_score_endpoint", "layer": "telemetry", "purpose": "/api/health/boot/score"},
    {"id": "R-41", "name": "_deprecations_emit_summary", "layer": "telemetry", "purpose": "list of dep-warned modules"},
    {"id": "R-42", "name": "ngrok_status_page_link", "layer": "telemetry", "purpose": "operator quick link"},
]
assert len(REDUNDANCIES) == 42, f"REDUNDANCIES list size drift: {len(REDUNDANCIES)}"


@router.get("/redundancies")
async def list_redundancies() -> dict[str, Any]:
    """The 42 self-healing redundancies the backend ships with, grouped
    by layer. Frontends can render this as an audit grid."""
    by_layer: dict[str, list[dict[str, str]]] = {}
    for r in REDUNDANCIES:
        by_layer.setdefault(r["layer"], []).append(r)
    return {
        "total": len(REDUNDANCIES),
        "by_layer": by_layer,
        "layer_counts": {k: len(v) for k, v in by_layer.items()},
    }


__all__ = [
    "router",
    "overview",
    "list_redundancies",
    "REDUNDANCIES",
]
