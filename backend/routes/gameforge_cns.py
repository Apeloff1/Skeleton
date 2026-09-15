"""
routes/gameforge_cns.py — GameForge CNS "Zaibatsu" integration surface.

Additive merge (per the Zaibatsu Deployment Guide): the existing app stays the
base; the vendored ``backend/gameforge/`` package is mounted here under a single
``/api/gameforge`` umbrella so every sub-router is reachable through the k8s
``/api/*`` ingress (the package's native prefixes like ``/exocortex`` are not).

ALL imports are defensive: if any Zaibatsu module fails to load, this router
still registers with a degraded ``/health`` report instead of crashing boot.
Runtime module selection is intentionally avoided: every executable import path
below is statically declared and reviewable.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge", tags=["gameforge-cns"])

_MOUNTED: list[str] = []
_FAILED: dict[str, str] = {}


# ── Mount every Zaibatsu sub-router under /api/gameforge ──────────────────────
def _diaries_router():
    from gameforge.api.diaries import router as subrouter

    return subrouter


def _scim_router():
    from gameforge.api.scim import router as subrouter

    return subrouter


def _personal_logs_router():
    from gameforge.api.personal_logs import router as subrouter

    return subrouter


def _calendar_router():
    from gameforge.api.calendar_api import router as subrouter

    return subrouter


def _neuro_router():
    from gameforge.api.neuro_api import router as subrouter

    return subrouter


def _decade_router():
    from gameforge.api.decade_logs_api import router as subrouter

    return subrouter


def _coherence_router():
    from gameforge.api.coherence_api import router as subrouter

    return subrouter


def _math_router():
    from gameforge.api.math_api import router as subrouter

    return subrouter


def _exocortex_router():
    from gameforge.api.exocortex_api import router as subrouter

    return subrouter


def _security_router():
    from gameforge.api.security_api import router as subrouter

    return subrouter


_SUBROUTERS: list[tuple[str, Callable[[], APIRouter]]] = [
    ("diaries", _diaries_router),
    ("scim", _scim_router),
    ("logs", _personal_logs_router),
    ("calendar", _calendar_router),
    ("neuro", _neuro_router),
    ("decade", _decade_router),
    ("coherence", _coherence_router),
    ("math", _math_router),
    ("exocortex", _exocortex_router),
    ("security", _security_router),
]

for _label, _loader in _SUBROUTERS:
    try:
        router.include_router(_loader())
        _MOUNTED.append(_label)
    except Exception as e:  # noqa: BLE001 — degrade, never crash boot
        _FAILED[_label] = f"{type(e).__name__}: {e}"[:160]


@router.get("/rooms")
async def gameforge_rooms(limit: int = 20):
    """Room registry summary — total count (now 1000) + a capability sample."""
    from gameforge.rooms.full_room_registry import all_rooms

    rooms = all_rooms()
    sample = [
        {
            "room_id": k,
            **{
                kk: v.get(kk)
                for kk in ("division", "api_access", "mcp_access", "concurrent_query")
            },
        }
        for k, v in list(rooms.items())[: max(1, min(limit, 100))]
    ]
    concurrent = sum(1 for v in rooms.values() if v.get("concurrent_query"))
    return {
        "total": len(rooms),
        "concurrent_query_capable": concurrent,
        "sample": sample,
    }


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


# Static activation dispatch. Each callable contains a fixed import path so request
# data can never select a Python module or attribute to execute.
def _run_cns_execution_cycle() -> Any:
    from gameforge.cns_execution_orchestrator import run_full_cns_cycle

    return run_full_cns_cycle()


def _run_full_cns_activation() -> Any:
    from gameforge.integration.full_cns_integration_layer import FullCNSIntegrationLayer

    return FullCNSIntegrationLayer().activate_full_cns()


def _run_system_health_check() -> Any:
    from gameforge.cns_full_integration_layer import CNSFullIntegrationLayer

    return CNSFullIntegrationLayer().run_full_system_health_check()


def _run_begin_cns_activation() -> Any:
    from gameforge.bootstrap.begin_cns_activation import BeginCNSActivation

    return BeginCNSActivation().run()


_ACTIVATION_STEPS: list[tuple[str, Callable[[], Any]]] = [
    ("cns_execution_cycle", _run_cns_execution_cycle),
    ("full_cns_activation", _run_full_cns_activation),
    ("system_health_check", _run_system_health_check),
    ("begin_cns_activation", _run_begin_cns_activation),
]


@router.post("/activate")
async def gameforge_activate():
    """Activate the explicitly approved CNS execution + bootstrap engines.

    Each step runs in a worker thread and is fully guarded — a failing engine is
    reported, never crashes the request. Import targets are static and reviewable.
    """
    import asyncio as _aio

    results: dict = {}
    for name, runner in _ACTIVATION_STEPS:
        try:
            out = await _aio.wait_for(_aio.to_thread(runner), timeout=25)
            results[name] = {"ok": True, "result": _trim(out)}
        except Exception as e:  # noqa: BLE001
            results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:180]}
    activated = sum(1 for r in results.values() if r["ok"])
    return {
        "activated": activated,
        "total": len(_ACTIVATION_STEPS),
        "status": "live" if activated else "degraded",
        "engines": results,
    }


# Static architecture probes. Returning the imported module makes each import a
# real, used expression while retaining defensive per-module reporting.
def _probe_observability() -> Any:
    from gameforge.enterprise import observability

    return observability


def _probe_hybrid_rag_engine() -> Any:
    from gameforge.exocortex.agentic import hybrid_rag_engine

    return hybrid_rag_engine


def _probe_vector_shard_manager() -> Any:
    from gameforge.exocortex.agentic import vector_shard_manager

    return vector_shard_manager


def _probe_latent_metrics_table() -> Any:
    from gameforge.exocortex.agentic import latent_metrics_table

    return latent_metrics_table


def _probe_database_architecture() -> Any:
    from gameforge.persistence import marathon_store

    return marathon_store


def _probe_dspy_pipeline() -> Any:
    from gameforge.exocortex.agentic import dspy_game_creation_pipeline

    return dspy_game_creation_pipeline


def _probe_grok_thinking() -> Any:
    from gameforge.exocortex.agentic import grok_thinking

    return grok_thinking


def _probe_mcp_connectors() -> Any:
    from gameforge.exocortex.agentic import mcp_connectors

    return mcp_connectors


def _probe_jeeves_zaibatsu() -> Any:
    from gameforge.exocortex.zaibatsu import jeeves_zaibatsu

    return jeeves_zaibatsu


_ARCHITECTURE_PROBES: dict[str, Callable[[], Any]] = {
    "observability": _probe_observability,
    "hybrid_rag_engine": _probe_hybrid_rag_engine,
    "vector_shard_manager": _probe_vector_shard_manager,
    "latent_metrics_table": _probe_latent_metrics_table,
    "database_architecture": _probe_database_architecture,
    "dspy_pipeline": _probe_dspy_pipeline,
    "grok_thinking": _probe_grok_thinking,
    "mcp_connectors": _probe_mcp_connectors,
    "jeeves_zaibatsu": _probe_jeeves_zaibatsu,
}


@router.get("/architecture")
async def gameforge_architecture():
    """Item 31 — report availability of statically approved Zaibatsu modules."""
    report: dict = {}
    for name, probe in _ARCHITECTURE_PROBES.items():
        try:
            probe()
            report[name] = "live"
        except Exception as e:  # noqa: BLE001
            report[name] = f"unavailable: {type(e).__name__}"
    live = sum(1 for v in report.values() if v == "live")
    return {"live": live, "total": len(_ARCHITECTURE_PROBES), "modules": report}


@router.get("/status")
async def gameforge_status():
    """Which Zaibatsu sub-systems mounted successfully."""
    from gameforge.version import __codename__, __version__

    return {
        "codename": __codename__,
        "version": __version__,
        "mounted": _MOUNTED,
        "mounted_count": len(_MOUNTED),
        "failed": _FAILED,
        "cockpit": "/api/gameforge/cockpit",
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
