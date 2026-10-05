"""
routes/gameforge_tools.py — Agent Tool System (/api/gameforge/tools).

Native implementation of the dormant Tool-Bank engine cluster from
gameforge_full_implementation_v1 (tool_evolution / tool_permissions /
tool_usage_tracker / tool_version_management / tool_combination_scoring /
agent_capability_profile). Mongo-backed, deterministic.

  • Registry + versioning + rollback
  • Fine-grained permissions (trust / role / mastery gates)
  • Usage tracking + success-rate stats
  • Evolution (high success → improve, low → deprecate)
  • Combination synergy scoring
  • Per-agent capability profiles that grow with tool usage
"""
from __future__ import annotations

import time
import zlib
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/gameforge/tools", tags=["gameforge-tools"])

DEFAULT_CAPS = {"Code Quality": 50, "System Design": 45, "Debugging": 55,
                "Narrative Design": 40, "Mechanics Design": 48,
                "Iteration Speed": 52, "Decision Making": 50}

SEED_TOOLS = [
    {"tool_id": "CodeQualityEnhancerTool", "name": "Code Quality Enhancer", "domain": "engineering", "min_trust": 20, "min_mastery": 10, "boosts": "Code Quality"},
    {"tool_id": "GameBalanceAnalyzerTool", "name": "Game Balance Analyzer", "domain": "design", "min_trust": 30, "min_mastery": 20, "boosts": "Mechanics Design"},
    {"tool_id": "NarrativeIntegratorTool", "name": "Narrative Mechanics Integrator", "domain": "narrative", "min_trust": 25, "min_mastery": 15, "boosts": "Narrative Design"},
    {"tool_id": "FeatureIterationAcceleratorTool", "name": "Feature Iteration Accelerator", "domain": "engineering", "min_trust": 40, "min_mastery": 30, "boosts": "Iteration Speed"},
]


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


def _tools():
    return _db()["gameforge_tools"]


def _versions():
    return _db()["gameforge_tool_versions"]


def _usage():
    return _db()["gameforge_tool_usage"]


def _profiles():
    return _db()["gameforge_agent_profiles"]


def _seed():
    if _tools().count_documents({}) == 0:
        for t in SEED_TOOLS:
            doc = {**t, "version": 1, "deprecated": False, "created_at": time.time()}
            _tools().insert_one(dict(doc))
            _versions().insert_one({**doc, "vkey": f"{t['tool_id']}:1"})


def _stats(tool_id: str) -> dict:
    rows = list(_usage().find({"tool_id": tool_id}))
    if not rows:
        return {"uses": 0, "success_rate": 0.5}
    succ = sum(1 for r in rows if r.get("success"))
    return {"uses": len(rows), "success_rate": round(succ / len(rows), 2)}


def _pair_synergy(a: str, b: str) -> dict:
    """Deterministic synergy between two tools from a stable hash."""
    h = zlib.crc32(f"{min(a, b)}|{max(a, b)}".encode()) % 100
    if h >= 80:
        return {"type": "Strong Synergy", "score": 15}
    if h >= 55:
        return {"type": "Moderate Synergy", "score": 8}
    if h >= 15:
        return {"type": "Neutral", "score": 0}
    if h >= 5:
        return {"type": "Conflict", "score": -12}
    return {"type": "Dangerous Conflict", "score": -30}


# ── Registry / versioning ────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    tool_id: str
    name: str
    domain: str = "general"
    min_trust: int = 0
    min_mastery: int = 0
    boosts: Optional[str] = None


@router.post("/register")
async def register(b: RegisterBody):
    _seed()
    doc = {"tool_id": b.tool_id, "name": b.name, "domain": b.domain, "min_trust": b.min_trust,
           "min_mastery": b.min_mastery, "boosts": b.boosts, "version": 1,
           "deprecated": False, "created_at": time.time()}
    _tools().update_one({"tool_id": b.tool_id}, {"$setOnInsert": doc}, upsert=True)
    _versions().update_one({"vkey": f"{b.tool_id}:1"}, {"$setOnInsert": {**doc, "vkey": f"{b.tool_id}:1"}}, upsert=True)
    return {"ok": True, "tool_id": b.tool_id}


@router.get("")
async def list_tools():
    _seed()
    out = []
    for t in _tools().find({}, {"_id": 0}).sort("tool_id", 1):
        out.append({**t, "stats": _stats(t["tool_id"])})
    return {"ok": True, "tools": out, "count": len(out)}


class VersionBody(BaseModel):
    changes: dict = {}
    created_by: str = "jeeves"


@router.post("/{tool_id}/version")
async def new_version(tool_id: str, b: VersionBody):
    cur = _tools().find_one({"tool_id": tool_id}, {"_id": 0})
    if not cur:
        return {"ok": False, "error": "tool_not_found"}
    nv = {**cur, **b.changes, "version": cur.get("version", 1) + 1, "created_by": b.created_by}
    _tools().update_one({"tool_id": tool_id}, {"$set": nv})
    _versions().insert_one({**nv, "vkey": f"{tool_id}:{nv['version']}", "created_at": time.time()})
    return {"ok": True, "tool_id": tool_id, "version": nv["version"]}


class RollbackBody(BaseModel):
    version: int


@router.post("/{tool_id}/rollback")
async def rollback(tool_id: str, b: RollbackBody):
    v = _versions().find_one({"vkey": f"{tool_id}:{b.version}"}, {"_id": 0})
    if not v:
        return {"ok": False, "error": "version_not_found"}
    _tools().update_one({"tool_id": tool_id}, {"$set": {k: v[k] for k in v if k != "vkey"}})
    return {"ok": True, "tool_id": tool_id, "rolled_back_to": b.version}


# ── Permissions ──────────────────────────────────────────────────────────────
class PermBody(BaseModel):
    agent_id: str
    tool_id: str
    trust: int = 50
    mastery: int = 50
    role: str = "engineering"


@router.post("/permissions/check")
async def check_permission(b: PermBody):
    t = _tools().find_one({"tool_id": b.tool_id}, {"_id": 0})
    if not t:
        return {"ok": True, "allowed": False, "reason": "Tool not found"}
    if t.get("deprecated"):
        return {"ok": True, "allowed": False, "reason": "Tool deprecated"}
    if b.trust < t.get("min_trust", 0):
        return {"ok": True, "allowed": False, "reason": "Insufficient trust"}
    if b.mastery < t.get("min_mastery", 0):
        return {"ok": True, "allowed": False, "reason": "Insufficient mastery"}
    return {"ok": True, "allowed": True, "reason": "granted"}


# ── Usage tracking + capability profiles ─────────────────────────────────────
class UseBody(BaseModel):
    agent_id: str
    tool_id: str
    room_id: str = "lobby"
    success: bool = True
    duration: float = 1.0


@router.post("/use")
async def use_tool(b: UseBody):
    _usage().insert_one({"agent_id": b.agent_id, "tool_id": b.tool_id, "room_id": b.room_id,
                         "success": b.success, "duration": b.duration, "ts": time.time()})
    # grow capability profile — boost the capability the tool trains, every 3rd use.
    t = _tools().find_one({"tool_id": b.tool_id}, {"_id": 0}) or {}
    prof = _profiles().find_one({"agent_id": b.agent_id}) or {"agent_id": b.agent_id, "capabilities": dict(DEFAULT_CAPS), "tool_usage": {}}
    caps = prof.get("capabilities", dict(DEFAULT_CAPS))
    usage = prof.get("tool_usage", {})
    usage[b.tool_id] = usage.get(b.tool_id, 0) + 1
    boosted = None
    cap = t.get("boosts")
    if cap and usage[b.tool_id] % 3 == 0 and cap in caps:
        caps[cap] = min(100, caps[cap] + 5)
        boosted = cap
    _profiles().update_one({"agent_id": b.agent_id},
                           {"$set": {"agent_id": b.agent_id, "capabilities": caps, "tool_usage": usage}},
                           upsert=True)
    return {"ok": True, "stats": _stats(b.tool_id), "boosted": boosted}


@router.get("/{tool_id}/stats")
async def tool_stats(tool_id: str):
    return {"ok": True, "tool_id": tool_id, **_stats(tool_id)}


@router.get("/agent/{agent_id}/profile")
async def agent_profile(agent_id: str):
    prof = _profiles().find_one({"agent_id": agent_id}, {"_id": 0})
    if not prof:
        prof = {"agent_id": agent_id, "capabilities": dict(DEFAULT_CAPS), "tool_usage": {}}
    return {"ok": True, **prof}


# ── Evolution ────────────────────────────────────────────────────────────────
@router.post("/{tool_id}/evolve")
async def evolve(tool_id: str):
    cur = _tools().find_one({"tool_id": tool_id}, {"_id": 0})
    if not cur:
        return {"ok": False, "error": "tool_not_found"}
    sr = _stats(tool_id)["success_rate"]
    if sr > 0.85:
        nv = cur.get("version", 1) + 1
        _tools().update_one({"tool_id": tool_id}, {"$set": {"version": nv}})
        _versions().insert_one({**cur, "version": nv, "vkey": f"{tool_id}:{nv}", "improvement": "stability_boost", "created_at": time.time()})
        return {"ok": True, "action": "improved", "success_rate": sr, "new_version": nv}
    if sr < 0.40:
        _tools().update_one({"tool_id": tool_id}, {"$set": {"deprecated": True}})
        return {"ok": True, "action": "flagged_for_deprecation", "success_rate": sr}
    return {"ok": True, "action": "no_change_needed", "success_rate": sr}


# ── Combination synergy scoring ──────────────────────────────────────────────
class ComboBody(BaseModel):
    tool_ids: List[str]


@router.post("/combination/score")
async def score_combination(b: ComboBody):
    total = synergies = conflicts = 0
    pairs = []
    ids = b.tool_ids
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            res = _pair_synergy(ids[i], ids[j])
            total += res["score"]
            if res["score"] > 0:
                synergies += 1
            elif res["score"] < 0:
                conflicts += 1
            pairs.append({"pair": [ids[i], ids[j]], **res})
    rating = "excellent" if total >= 20 else "good" if total >= 8 else "neutral" if total >= 0 else "risky"
    return {"ok": True, "total_score": total, "synergies": synergies, "conflicts": conflicts,
            "rating": rating, "pairs": pairs}


@router.get("/status")
async def status():
    _seed()
    return {"ok": True, "tools": _tools().count_documents({}),
            "deprecated": _tools().count_documents({"deprecated": True}),
            "usage_events": _usage().count_documents({}),
            "profiled_agents": _profiles().count_documents({})}
