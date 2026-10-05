"""
Galaxy Studio — Agent Once-Over sub-router.

Extracted from routes/galaxy_studio.py (Jun 2026, decomposition continuation)
so the 12k-LOC monolith shrinks and the cross-subsystem diagnostics cadence can
be tested / iterated independently.

This module is fully self-contained: it probes each specialist subsystem's
public HTTP endpoint over the internal base URL and consolidates the results.
It does NOT touch any of the in-memory build state owned by the main
galaxy_studio module, so the extraction is safe and side-effect-free.

Mounted from routes/galaxy_studio.py via ``router.include_router(...)`` WITHOUT
an additional prefix so the public paths stay identical
(``/api/galaxy-studio/agents/once-over`` and ``.../agents/once-over/last``).
"""

from __future__ import annotations
import os
import time
import asyncio

import httpx
from fastapi import APIRouter

# Sub-router — NO prefix so the parent's "/api/galaxy-studio" prefix applies.
router = APIRouter(tags=["galaxy-studio"])

# Last report cached in-process (survives across /last calls, resets on reload).
_LAST_ONCE_OVER: dict = {}

# Ring buffer of compact run summaries for the frontend health sparkline.
# Backed by MongoDB (collection below) so the trend survives backend restarts;
# the in-process list is just a hot cache that is hydrated lazily on first read.
_ONCE_OVER_HISTORY: list = []
_HISTORY_CAP = 30
_HISTORY_COLLECTION = "galaxy_agent_once_over_history"
_history_hydrated = False


def _history_col():
    """Async Motor handle for the persisted once-over trend (auto-routed DB)."""
    from core.databases import collection
    return collection(_HISTORY_COLLECTION)


async def _hydrate_history() -> None:
    """Load the most-recent runs from MongoDB into the in-process cache once."""
    global _history_hydrated
    if _history_hydrated:
        return
    try:
        cur = _history_col().find({}, {"_id": 0}).sort("ran_at", -1).limit(_HISTORY_CAP)
        docs = await cur.to_list(length=_HISTORY_CAP)
        # Stored newest-first; expose oldest → newest for the sparkline.
        _ONCE_OVER_HISTORY[:] = list(reversed(docs))
    except Exception:
        # Non-fatal: fall back to the empty in-memory buffer.
        pass
    _history_hydrated = True


async def _persist_history(entry: dict) -> None:
    """Append one run to MongoDB and trim to the most-recent _HISTORY_CAP."""
    try:
        col = _history_col()
        await col.insert_one(dict(entry))
        # Trim: keep only the newest _HISTORY_CAP documents.
        cutoff = await col.find({}, {"_id": 0, "ran_at": 1}).sort("ran_at", -1) \
            .skip(_HISTORY_CAP).limit(1).to_list(length=1)
        if cutoff:
            await col.delete_many({"ran_at": {"$lt": cutoff[0]["ran_at"]}})
    except Exception:
        pass  # non-fatal — in-memory cache still serves the trend this session

# (agent label, probe path) — curated specialist subsystems on this platform.
_ONCE_OVER_AGENTS = [
    ("core_health",          "/api/health"),
    ("boot_score",           "/api/health/boot/score"),
    ("feature_flags",        "/api/feature-flags/health"),
    ("sentinel_array",       "/api/sentinel-array/status"),
    ("resilience_forge",     "/api/resilience-forge/status"),
    ("swarm_overview",       "/api/galaxy-studio/swarm/overview"),
    ("swarm_cold_stats",     "/api/galaxy-studio/swarm/cold/stats"),
    ("legion_discourse",     "/api/galaxy-studio/swarm/discourse/legion/stats"),
    ("agent_knowledge",      "/api/knowledge/stats"),
    ("coding_dictionary",    "/api/dictionary/stats"),
    ("capabilities",         "/api/galaxy-studio/capabilities/catalog"),
    ("gamedev_pipeline",     "/api/galaxy-studio/pipeline/catalog"),
    ("agent_datasets",       "/api/galaxy-studio/datasets/catalog"),
    ("leaderboards",         "/api/leaderboards/boards"),
    ("daily_challenge",      "/api/daily/challenge"),
    ("galaxy_manifest",      "/api/galaxy-studio/manifest"),
]


async def _probe_agent(client, label: str, path: str, base: str) -> dict:
    """Probe one agent endpoint with up to 3 redundant attempts."""
    last_err = None
    for attempt in range(1, 4):
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{base}{path}", timeout=8.0)
            dur = round((time.perf_counter() - t0) * 1000, 1)
            ok = 200 <= r.status_code < 300
            finding = "ok" if ok else f"http_{r.status_code}"
            return {
                "agent": label, "path": path, "ok": ok, "status": r.status_code,
                "latency_ms": dur, "attempts": attempt, "finding": finding,
            }
        except Exception as e:  # network/timeout — retry (redundancy)
            last_err = str(e)
            continue
    return {
        "agent": label, "path": path, "ok": False, "status": 0,
        "latency_ms": None, "attempts": 3, "finding": f"unreachable: {last_err}",
    }


@router.post("/agents/once-over")
async def agents_once_over():
    """Run a consecutive once-over (cadence) across ALL specialised agents.
    Each subsystem is probed in sequence with redundant retries and isolated
    error handling. Returns a consolidated health/review report."""
    base = os.environ.get("INTERNAL_BASE_URL", "http://localhost:8001")
    t0 = time.perf_counter()
    async with httpx.AsyncClient() as client:
        # Probe ALL agents CONCURRENTLY. Previously this ran sequentially with a
        # 0.05s cadence + per-agent retries, which summed to ~50-60s through the
        # K8s ingress and tripped the 30s gateway timeout (504). asyncio.gather
        # collapses the wall-clock to ~max(single probe); it also preserves input
        # order, so `results` still lines up with _ONCE_OVER_AGENTS.
        results = list(await asyncio.gather(*[
            _probe_agent(client, label, path, base)
            for label, path in _ONCE_OVER_AGENTS
        ]))
    total = len(results)
    healthy = sum(1 for r in results if r["ok"])
    lats = [r["latency_ms"] for r in results if r["latency_ms"] is not None]
    report = {
        "ok": True,
        "ran_at": int(time.time()),
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
        "total_agents": total,
        "healthy": healthy,
        "degraded": total - healthy,
        "health_pct": round(100.0 * healthy / total, 1) if total else 0.0,
        "avg_latency_ms": round(sum(lats) / len(lats), 1) if lats else None,
        "results": results,
        "blockers": [r["agent"] for r in results if not r["ok"]],
    }
    global _LAST_ONCE_OVER
    _LAST_ONCE_OVER = report
    # Append a compact summary to the trend buffer (for the sparkline) and
    # persist it to MongoDB so the trend survives backend restarts.
    await _hydrate_history()
    entry = {
        "ran_at": report["ran_at"],
        "health_pct": report["health_pct"],
        "healthy": report["healthy"],
        "total_agents": report["total_agents"],
        "avg_latency_ms": report["avg_latency_ms"],
    }
    _ONCE_OVER_HISTORY.append(entry)
    if len(_ONCE_OVER_HISTORY) > _HISTORY_CAP:
        del _ONCE_OVER_HISTORY[:-_HISTORY_CAP]
    await _persist_history(entry)
    return report


@router.get("/agents/once-over/history")
async def agents_once_over_history(limit: int = 30):
    """Return the compact run-trend history (oldest → newest) for the
    frontend health sparkline. Empty list if never run. Backed by MongoDB so
    the trend persists across backend restarts."""
    await _hydrate_history()
    n = max(1, min(int(limit), _HISTORY_CAP))
    items = _ONCE_OVER_HISTORY[-n:]
    return {"ok": True, "count": len(items), "history": items}


@router.get("/agents/once-over/last")
async def agents_once_over_last():
    """Return the most recent once-over report (empty if never run)."""
    if not _LAST_ONCE_OVER:
        return {"ok": True, "ran": False, "report": None}
    return {"ok": True, "ran": True, "report": _LAST_ONCE_OVER}


__all__ = ["router", "agents_once_over", "agents_once_over_last", "agents_once_over_history"]
