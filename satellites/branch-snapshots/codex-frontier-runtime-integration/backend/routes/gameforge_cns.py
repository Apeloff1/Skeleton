"""
routes/gameforge_cns.py — GameForge CNS "Zaibatsu" integration surface.

Additive merge (per the Zaibatsu Deployment Guide): the existing app stays the
base; the vendored ``backend/gameforge/`` package is mounted here under a single
``/api/gameforge`` umbrella so every sub-router is reachable through the k8s
``/api/*`` ingress (the package's native prefixes like ``/exocortex`` are not).

ALL imports are defensive: if any Zaibatsu module fails to load, this router
still registers with a degraded ``/health`` report instead of crashing boot.
"""
from __future__ import annotations

from pathlib import Path

import asyncio

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge", tags=["gameforge-cns"])

_MOUNTED: list[str] = []
_FAILED: dict[str, str] = {}

# ── Mount every Zaibatsu sub-router under /api/gameforge ──────────────────────
_SUBROUTERS = [
    ("gameforge.api.diaries",         "diaries"),
    ("gameforge.api.scim",            "scim"),
    ("gameforge.api.personal_logs",   "logs"),
    ("gameforge.api.calendar_api",    "calendar"),
    ("gameforge.api.neuro_api",       "neuro"),
    ("gameforge.api.decade_logs_api", "decade"),
    ("gameforge.api.coherence_api",   "coherence"),
    ("gameforge.api.math_api",        "math"),
    ("gameforge.api.exocortex_api",   "exocortex"),
    ("gameforge.api.security_api",    "security"),
]
for _mod_path, _label in _SUBROUTERS:
    try:
        _mod = __import__(_mod_path, fromlist=["router"])
        router.include_router(_mod.router)
        _MOUNTED.append(_label)
    except Exception as e:  # noqa: BLE001 — degrade, never crash boot
        _FAILED[_label] = f"{type(e).__name__}: {e}"[:160]


@router.get("/rooms")
async def gameforge_rooms(limit: int = 20):
    """Room registry summary — total count (now 1000) + a capability sample."""
    from gameforge.rooms.full_room_registry import all_rooms
    rooms = all_rooms()
    sample = [{"room_id": k, **{kk: v.get(kk) for kk in
              ("division", "api_access", "mcp_access", "concurrent_query")}}
              for k, v in list(rooms.items())[:max(1, min(limit, 100))]]
    concurrent = sum(1 for v in rooms.values() if v.get("concurrent_query"))
    return {"total": len(rooms), "concurrent_query_capable": concurrent, "sample": sample}


class RoomQuery(BaseModel):
    mcp_queries: list[str] = []
    api_targets: list[dict] = []
    sources: list[str] | None = None


@router.post("/rooms/{room_id}/query")
async def gameforge_room_query(room_id: str, body: RoomQuery):
    """A room fans MCP queries + external API targets out CONCURRENTLY.
    External HTTP is gated by GAMEFORGE_ENABLE_EXTERNAL_APIS (inward-focused default)."""
    from gameforge.rooms.full_room_registry import all_rooms
    from gameforge.rooms.room_api_gateway import query_concurrent
    if room_id not in all_rooms():
        return JSONResponse({"error": f"unknown room '{room_id}'"}, status_code=404)
    return await query_concurrent(room_id, body.mcp_queries, body.api_targets, body.sources)


class BroadcastQuery(BaseModel):
    query: str
    max_rooms: int = 50
    concurrency: int = 32
    sources: list[str] | None = None


@router.post("/rooms/broadcast")
async def gameforge_broadcast(body: BroadcastQuery):
    """CNS-wide thought — dispatch ONE query across many rooms CONCURRENTLY
    (bounded by a semaphore) and aggregate the mesh's answers."""
    from gameforge.rooms.full_room_registry import all_rooms
    from gameforge.rooms.room_api_gateway import query_concurrent
    rooms = list(all_rooms().keys())
    targets = rooms[: max(1, min(body.max_rooms, 1000))]
    sem = asyncio.Semaphore(max(1, min(body.concurrency, 128)))

    async def _one(rid: str):
        async with sem:
            return await query_concurrent(rid, [body.query], [], body.sources)

    results = await asyncio.gather(*[_one(r) for r in targets])
    ok = sum(1 for r in results if r["ok"])
    return {
        "query": body.query,
        "total_rooms": len(rooms),
        "rooms_queried": len(targets),
        "ok_rooms": ok,
        "concurrency": sem._value if hasattr(sem, "_value") else body.concurrency,
        "aggregate_sample": results[:10],
    }


def _trim(out):
    """Keep activation responses small + JSON-safe."""
    if isinstance(out, (dict, list)):
        s = str(out)
        return out if len(s) < 1500 else {"summary": s[:1500] + "…"}
    return str(out)[:800]


@router.post("/activate")
async def gameforge_activate():
    """Activate the newly-merged CNS execution + bootstrap engines so they become
    LIVE capabilities (not dormant modules). Each step runs in a worker thread and
    is fully guarded — a failing engine is reported, never crashes the request."""
    import asyncio as _aio
    steps = [
        ("cns_execution_cycle", "gameforge.cns_execution_orchestrator", "run_full_cns_cycle", None),
        ("full_cns_activation", "gameforge.integration.full_cns_integration_layer", "FullCNSIntegrationLayer", "activate_full_cns"),
        ("system_health_check", "gameforge.cns_full_integration_layer", "CNSFullIntegrationLayer", "run_full_system_health_check"),
        ("begin_cns_activation", "gameforge.bootstrap.begin_cns_activation", "BeginCNSActivation", "run"),
    ]

    def _one(mod: str, attr: str, method):
        m = __import__(mod, fromlist=[attr])
        obj = getattr(m, attr)
        return getattr(obj(), method)() if method else obj()

    results: dict = {}
    for name, mod, attr, method in steps:
        try:
            out = await _aio.wait_for(_aio.to_thread(_one, mod, attr, method), timeout=25)
            results[name] = {"ok": True, "result": _trim(out)}
        except Exception as e:  # noqa: BLE001
            results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:180]}
    activated = sum(1 for r in results.values() if r["ok"])
    return {"activated": activated, "total": len(steps),
            "status": "live" if activated else "degraded", "engines": results}


@router.get("/architecture")
async def gameforge_architecture():
    """Item 31 — prove the core Zaibatsu architectural additions are LIVE by
    importing each subsystem module and reporting availability."""
    modules = {
        "observability":        "gameforge.enterprise.observability",
        "hybrid_rag_engine":    "gameforge.exocortex.agentic.hybrid_rag_engine",
        "vector_shard_manager": "gameforge.exocortex.agentic.vector_shard_manager",
        "latent_metrics_table": "gameforge.exocortex.agentic.latent_metrics_table",
        "database_architecture": "gameforge.persistence.marathon_store",
        "dspy_pipeline":        "gameforge.exocortex.agentic.dspy_game_creation_pipeline",
        "grok_thinking":        "gameforge.exocortex.agentic.grok_thinking",
        "mcp_connectors":       "gameforge.exocortex.agentic.mcp_connectors",
        "jeeves_zaibatsu":      "gameforge.exocortex.zaibatsu.jeeves_zaibatsu",
    }
    report: dict = {}
    for name, path in modules.items():
        try:
            __import__(path)
            report[name] = "live"
        except Exception as e:  # noqa: BLE001
            report[name] = f"unavailable: {type(e).__name__}"
    live = sum(1 for v in report.values() if v == "live")
    return {"live": live, "total": len(modules), "modules": report}


@router.get("/status")
async def gameforge_status():
    """Which Zaibatsu sub-systems mounted successfully."""
    from gameforge.version import __version__, __codename__
    return {
        "codename": __codename__, "version": __version__,
        "mounted": _MOUNTED, "mounted_count": len(_MOUNTED),
        "failed": _FAILED, "cockpit": "/api/gameforge/cockpit",
    }


@router.get("/cockpit", response_class=HTMLResponse)
async def gameforge_cockpit():
    """Serve the Zaibatsu command-center cockpit (inward-focused)."""
    p = Path(__file__).resolve().parent.parent / "gameforge" / "api" / "cockpit.html"
    if p.exists():
        return HTMLResponse(p.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>GameForge cockpit not found</h1>", status_code=404)


@router.get("/health")
async def gameforge_health():
    """Lightweight coherence/health check across the merged CNS (Item: deploy_ready).
    Runs the Zaibatsu init in-process and reports room + engine status. Guarded so
    a heavy/partial system reports 'degraded' rather than erroring."""
    report: dict = {"ok": True, "mounted": _MOUNTED, "failed": _FAILED}
    try:
        from gameforge.rooms.full_room_registry import all_rooms
        report["rooms"] = len(all_rooms())
    except Exception as e:  # noqa: BLE001
        report["ok"] = False
        report["rooms_error"] = f"{type(e).__name__}: {e}"[:160]
    if _FAILED:
        report["ok"] = False
    status = 200 if report["ok"] else 207
    return JSONResponse(report, status_code=status)
