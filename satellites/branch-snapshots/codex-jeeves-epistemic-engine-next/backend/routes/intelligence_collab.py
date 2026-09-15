"""
routes/intelligence_collab.py — Starlog + Learning + Collaboration (simple).

Extracted from server.py (Feb 2026 Phase-5 decomposition). Bundles three
small, self-contained subsystem APIs that previously lived inline:

  * /api/starlog/*       — Git-like version snapshots
  * /api/learning/*      — Mastery heatmap + knowledge-gap predictions
  * /api/collaboration/* — Lightweight session list / join / leave
                           (separate namespace from the AI-collab router
                            at /api/collab/*)

All endpoints depend only on Mongo via ``services.database.db``. No
in-memory state, no circular imports.

Registered through ``core/routes_registry.py`` with prefix ``/api``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["intelligence-collab"])


def _db():
    """Lazy access to the shared Mongo client so the module loads even if
    ``services.database`` isn't ready at import time."""
    from services.database import db
    return db


# ═══════════════════════════════════════════════════════════════════════
# STARLOG — Git-like version control
# ═══════════════════════════════════════════════════════════════════════

@router.post("/starlog/commit")
async def starlog_commit(data: dict):
    """Git-like version control commit."""
    code      = data.get("code", "")
    message   = data.get("message", "Update")
    language  = data.get("language", "python")
    parent_id = data.get("parent_id")

    entry = {
        "id":         uuid.uuid4().hex[:8],
        "code":       code,
        "language":   language,
        "message":    message,
        "timestamp":  datetime.utcnow(),
        "parent_id":  parent_id,
        "diff_stats": {
            "additions": len([ln for ln in code.splitlines() if ln.strip()]),
            "deletions": 0,
            "changes":   len(code.splitlines()),
        },
    }
    await _db().starlog_versions.insert_one(entry)
    return {
        "success":   True,
        "version":   entry["id"],
        "timestamp": entry["timestamp"].isoformat(),
    }


@router.get("/starlog/history")
async def starlog_history(limit: int = 50):
    """Get version history."""
    versions = await _db().starlog_versions.find().sort("timestamp", -1).to_list(limit)
    return {
        "versions": [
            {
                "id":         v["id"],
                "message":    v["message"],
                "timestamp":  v["timestamp"].isoformat(),
                "language":   v["language"],
                "diff_stats": v.get("diff_stats", {}),
            }
            for v in versions
        ]
    }


@router.get("/starlog/version/{version_id}")
async def starlog_get_version(version_id: str):
    """Get specific version."""
    version = await _db().starlog_versions.find_one({"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    version["_id"] = str(version["_id"])
    return version


@router.post("/starlog/diff")
async def starlog_diff(data: dict):
    """Compare two versions."""
    from_id = data.get("from_id")
    to_id   = data.get("to_id")
    from_ver = await _db().starlog_versions.find_one({"id": from_id})
    to_ver   = await _db().starlog_versions.find_one({"id": to_id})
    if not from_ver or not to_ver:
        raise HTTPException(status_code=404, detail="Version not found")
    from_lines = from_ver["code"].splitlines()
    to_lines   = to_ver["code"].splitlines()
    additions = len([ln for ln in to_lines   if ln not in from_lines])
    deletions = len([ln for ln in from_lines if ln not in to_lines])
    return {
        "from_version": from_id,
        "to_version":   to_id,
        "stats": {
            "additions":     additions,
            "deletions":     deletions,
            "total_changes": additions + deletions,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# LEARNING INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════

@router.post("/learning/track")
async def track_learning(data: dict):
    """Track learning activity."""
    activity = {
        "id":          uuid.uuid4().hex[:8],
        "type":        data.get("type", "code_execution"),
        "language":    data.get("language"),
        "concept":     data.get("concept"),
        "success":     data.get("success", True),
        "duration_ms": data.get("duration_ms", 0),
        "timestamp":   datetime.utcnow(),
    }
    await _db().learning_activities.insert_one(activity)
    return {"success": True, "activity_id": activity["id"]}


@router.get("/learning/mastery")
async def get_mastery():
    """Get mastery heatmap data."""
    activities = await _db().learning_activities.find().to_list(1000)
    mastery: dict[str, dict] = {}
    for a in activities:
        key = f"{a.get('language', 'general')}_{a.get('concept', 'basics')}"
        if key not in mastery:
            mastery[key] = {"total": 0, "success": 0}
        mastery[key]["total"] += 1
        if a.get("success"):
            mastery[key]["success"] += 1
    heatmap = []
    for key, m in mastery.items():
        parts = key.split("_", 1)
        heatmap.append({
            "language":       parts[0],
            "concept":        parts[1] if len(parts) > 1 else "general",
            "mastery":        round(m["success"] / m["total"] * 100, 1) if m["total"] > 0 else 0,
            "practice_count": m["total"],
        })
    return {"heatmap": heatmap}


@router.get("/learning/predictions")
async def get_predictions():
    """Get knowledge gap predictions."""
    activities = await _db().learning_activities.find().sort("timestamp", -1).to_list(100)
    concept_stats: dict[str, dict] = {}
    for a in activities:
        concept = a.get("concept", "general")
        if concept not in concept_stats:
            concept_stats[concept] = {"success": 0, "fail": 0}
        if a.get("success"):
            concept_stats[concept]["success"] += 1
        else:
            concept_stats[concept]["fail"] += 1
    predictions: list[dict] = []
    for concept, stats in concept_stats.items():
        if stats["fail"] > stats["success"]:
            predictions.append({
                "type":           "knowledge_gap",
                "concept":        concept,
                "confidence":     round(stats["fail"] / (stats["success"] + stats["fail"]) * 100, 1),
                "recommendation": f"Practice more {concept} exercises",
            })
    if not predictions:
        predictions = [
            {"type": "suggestion", "concept": "advanced_functions", "recommendation": "Try exploring decorators and generators"},
            {"type": "suggestion", "concept": "error_handling",     "recommendation": "Practice exception handling patterns"},
        ]
    return {"predictions": predictions}


# ═══════════════════════════════════════════════════════════════════════
# COLLABORATION (simple sessions — separate from /api/collab/* AI router)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/collaboration/session")
async def create_collaboration_session(data: dict):
    """Create a collaboration session for backend tracking."""
    session = {
        "id":           f"session-{uuid.uuid4().hex[:8]}",
        "name":         data.get("name", "Unnamed Session"),
        "created_by":   data.get("user_name", "Anonymous"),
        "language":     data.get("language", "python"),
        "created_at":   datetime.utcnow(),
        "participants": [data.get("user_name", "Anonymous")],
        "active":       True,
    }
    await _db().collaboration_sessions.insert_one(session)
    # Mongo mutated the dict with an ObjectId — strip / stringify before
    # returning so FastAPI's JSON encoder doesn't choke.
    session["_id"] = str(session["_id"])
    return session


@router.get("/collaboration/sessions")
async def list_collaboration_sessions():
    """List active collaboration sessions."""
    sessions = await _db().collaboration_sessions.find({"active": True}).to_list(50)
    return {"sessions": [{**s, "_id": str(s["_id"])} for s in sessions]}


@router.post("/collaboration/session/{session_id}/join")
async def join_collaboration_session(session_id: str, data: dict):
    """Join a collaboration session."""
    user_name = data.get("user_name", "Anonymous")
    await _db().collaboration_sessions.update_one(
        {"id": session_id},
        {"$addToSet": {"participants": user_name}},
    )
    return {"success": True, "session_id": session_id}


@router.post("/collaboration/session/{session_id}/leave")
async def leave_collaboration_session(session_id: str, data: dict):
    """Leave a collaboration session."""
    user_name = data.get("user_name", "Anonymous")
    await _db().collaboration_sessions.update_one(
        {"id": session_id},
        {"$pull": {"participants": user_name}},
    )
    return {"success": True}
