"""
routes/gameforge_knowledge.py — Queryable knowledge + self-learning / self-improvement.

  • A large catalog of FREE, no-auth public APIs (gameforge.knowledge.free_apis) so
    agents + Jeeves can QUERY external knowledge on demand.
  • /learn acquires knowledge for a request, folds a summary into Jeeves' trainable
    brain (jeeves_knowledge, domain 'acquired'), and records a lesson.
  • Self-improvement via the exocortex SelfLearningEngine + SelfImprovingAgentEngine.
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from gameforge.knowledge import free_apis as FA

router = APIRouter(prefix="/api/gameforge/knowledge", tags=["gameforge-knowledge"])

_self_learn = None
_self_improve = None


def _learner():
    global _self_learn
    if _self_learn is None:
        from gameforge.exocortex.zaibatsu.self_systems import SelfLearningEngine
        _self_learn = SelfLearningEngine("jeeves")
    return _self_learn


def _improver():
    global _self_improve
    if _self_improve is None:
        from gameforge.agents.self_improving_agent_engine import SelfImprovingAgentEngine
        _self_improve = SelfImprovingAgentEngine()
    return _self_improve


def _db():
    from core.databases import get_sync_db
    return get_sync_db()


# ── FREE API catalog + queries ────────────────────────────────────────────────
@router.get("/apis")
async def apis():
    return {"ok": True, **FA.catalog()}


@router.get("/apis/{key}")
async def api_detail(key: str):
    api = FA.FREE_APIS.get(key)
    if not api:
        return {"ok": False, "error": "unknown api", "available": sorted(FA.FREE_APIS.keys())}
    return {"ok": True, "key": key, **api}


class QueryBody(BaseModel):
    api: str
    params: dict = {}


@router.post("/query")
async def query(b: QueryBody):
    """Agents/Jeeves query a chosen free API directly."""
    res = await FA.fetch(b.api, b.params)
    return res


class LearnBody(BaseModel):
    query: str
    store: bool = True


@router.post("/learn")
async def learn(b: LearnBody):
    """Acquire knowledge for a natural-language request: pick the best free API,
    fetch it, summarize, fold it into Jeeves' brain, and record a lesson."""
    api_key, params = FA.pick_api(b.query)
    res = await FA.fetch(api_key, params)
    if not res.get("ok"):
        return {"ok": False, "query": b.query, "api": api_key, "error": res.get("error", "fetch failed")}
    summary = FA.summarize(api_key, res.get("data"))
    stored = False
    if b.store and summary:
        topic = f"acquired:{params.get('q', b.query)[:60]}"
        try:
            _db()["jeeves_knowledge"].update_one(
                {"topic": topic},
                {"$set": {"topic": topic, "text": summary, "domain": "acquired",
                          "source_api": api_key, "acquired_at": time.time()}}, upsert=True)
            stored = True
        except Exception:  # noqa: BLE001
            pass
    try:
        _learner().learn(source=f"free_api:{api_key}", pattern=b.query, action="acquired_knowledge")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "query": b.query, "api": api_key, "summary": summary,
            "stored_in_brain": stored, "raw_status": res.get("status")}


# ── Self-learning lessons ─────────────────────────────────────────────────────
class LessonBody(BaseModel):
    source: str
    pattern: str
    action: str
    weight: float = 1.0


@router.get("/lessons")
async def lessons(context: Optional[str] = None):
    L = _learner()
    if context:
        return {"ok": True, "suggestions": L.suggest(context)}
    return {"ok": True, "status": L.status(), "recent": [x.to_dict() for x in L.lessons[-15:]]}


@router.post("/lessons")
async def add_lesson(b: LessonBody):
    lesson = _learner().learn(b.source, b.pattern, b.action, b.weight)
    return {"ok": True, "lesson": lesson.to_dict()}


# ── Self-improvement loop ─────────────────────────────────────────────────────
class ImproveBody(BaseModel):
    agent_id: str = "jeeves"
    quality: float = 0.9
    coherence: float = 0.9
    synergy: float = 0.7


@router.post("/self-improve")
async def self_improve(b: ImproveBody):
    """Run one reflect-and-improve cycle; persist a lesson so the brain compounds."""
    reflection = _improver().reflect_and_improve(
        b.agent_id, {"quality": b.quality, "coherence": b.coherence, "synergy": b.synergy})
    for imp in reflection.get("improvements", []):
        try:
            _learner().learn(source="self_improve", pattern=imp, action="apply_improvement", weight=1.2)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "reflection": reflection}


@router.get("/self-improve/summary")
async def self_improve_summary(agent_id: str = "jeeves"):
    return {"ok": True, "summary": _improver().get_agent_improvement_summary(agent_id),
            "lessons": _learner().status()}
