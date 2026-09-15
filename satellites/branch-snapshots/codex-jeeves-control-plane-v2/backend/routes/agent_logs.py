"""
📜 AGENT LOGS — expose ALL app logs to agents for maximum learning.

Aggregates: live backend service logs (supervisor), the AI Log Vault (query/action logs),
recent audit + auto-improve + heal + groupchat history. One read-only surface so any agent can
study what happened across the whole app.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/agent-logs", tags=["agent-logs"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]

_LOG_FILES = {
    "backend_err": "/var/log/supervisor/backend.err.log",
    "backend_out": "/var/log/supervisor/backend.out.log",
    "expo_err": "/var/log/supervisor/expo.err.log",
}


def _tail(path: str, n: int) -> list[str]:
    try:
        with open(path, "r", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f.readlines()[-n:]]
    except Exception:
        return []


async def _recent(coll: str, proj: dict, sort_field: str, limit: int) -> list:
    try:
        return await _db[coll].find({}, proj).sort(sort_field, -1).limit(limit).to_list(limit)
    except Exception:
        return []


@router.get("/all")
async def all_logs(lines: int = Query(120, ge=10, le=500), game_id: str = Query("")):
    """🗂️ Everything-in-one log surface for agents. Optional game_id narrows DB logs."""
    gq = {"game_id": game_id} if game_id else {}

    async def _coll(name, proj, sort_field, limit):
        try:
            return await _db[name].find(gq, proj).sort(sort_field, -1).limit(limit).to_list(limit)
        except Exception:
            return []

    services = {k: _tail(p, lines) for k, p in _LOG_FILES.items()}
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "service_logs": services,
        "ai_query_logs": await _recent("ai_query_logs", {"_id": 0}, "timestamp", 40),
        "user_action_logs": await _recent("user_action_logs", {"_id": 0}, "timestamp", 40),
        "audit_history": await _coll("snowball_audits",
                                     {"_id": 0, "at": 1, "title": 1, "gate_floor": 1, "deliverable": 1,
                                      "blocker_count": 1, "levels": 1}, "at", 15),
        "improve_runs": await _coll("snowball_improve_runs",
                                    {"_id": 0, "at": 1, "gate_floor": 1, "weak_stages": 1,
                                     "upgrades": 1, "log": 1}, "at", 8),
        "groupchat_jobs": await _coll("groupchat_jobs",
                                      {"_id": 0, "job_id": 1, "game_id": 1, "job_status": 1,
                                       "done": 1, "total": 1, "transcript": 1}, "created_at", 6),
    }


@router.get("/stream")
async def log_stream(source: str = Query("backend_err"), lines: int = Query(200, ge=10, le=800)):
    """📡 Tail one named service log (backend_err | backend_out | expo_err)."""
    path = _LOG_FILES.get(source)
    if not path:
        return {"error": f"unknown source '{source}'", "valid": list(_LOG_FILES.keys())}
    return {"source": source, "lines": _tail(path, lines)}


@router.get("/summary")
async def log_summary():
    """📊 Quick counts agents can use to gauge activity."""
    out = {}
    for c in ("snowball_audits", "snowball_improve_runs", "groupchat_jobs",
              "ai_query_logs", "user_action_logs", "canon_patches"):
        try:
            out[c] = await _db[c].estimated_document_count()
        except Exception:
            out[c] = 0
    return {"counts": out, "log_files": list(_LOG_FILES.keys())}
