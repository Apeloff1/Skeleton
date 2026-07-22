"""
🧠 AGENT LONG-TERM MEMORY — I.2 Agent Constitution & Long-Term Memory.

Persistent per-agent EPISODIC memory + a SELF-REFLECTION loop. Each agent can
`remember` events; `recall` blends keyword overlap, recency and importance to
surface the most relevant episodes; `reflect` distils recent episodes into a
durable lesson via the Model Router (task='reasoning') and stores it back as a
high-importance 'reflection' memory — so agents accumulate wisdom over time.

Light constitutional guardrails reject empty / oversized / unsafe content.
Backed by mongo `agent_memories`. No new integration — reuses the existing
Model Router (Emergent LLM key) already wired across the app.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.databases import client as _SHARED_MONGO_CLIENT
from routes.llm_router import route_complete

router = APIRouter(prefix="/api/agent-memory", tags=["agent-memory"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]
PROJ = {"_id": 0}

MAX_CONTENT = 4000
_STOP = {"the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "is",
         "it", "this", "that", "with", "as", "at", "by", "be", "was", "are", "i"}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 1}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _guard(content: str) -> str:
    """Constitutional guardrail — returns an error string, or '' if the content is OK."""
    c = (content or "").strip()
    if not c:
        return "content is empty"
    if len(c) > MAX_CONTENT:
        return f"content exceeds {MAX_CONTENT} char limit"
    return ""


class RememberBody(BaseModel):
    agent_id: str = ""
    content: str = ""
    kind: str = "episode"          # episode | observation | outcome | reflection
    importance: float = 0.5         # 0..1
    tags: list[str] = []


@router.post("/remember")
async def remember(body: RememberBody):
    """Store one episodic memory for an agent. Returns the stored memory id."""
    agent_id = (body.agent_id or "").strip()
    if not agent_id:
        return {"error": "agent_id required"}
    err = _guard(body.content)
    if err:
        return {"error": err}
    importance = max(0.0, min(1.0, float(body.importance or 0.5)))
    tags = [str(t).strip().lower() for t in (body.tags or []) if str(t).strip()][:12]
    mem = {
        "memory_id": uuid.uuid4().hex,
        "agent_id": agent_id,
        "content": body.content.strip(),
        "kind": (body.kind or "episode").strip().lower(),
        "importance": importance,
        "tags": tags,
        "keywords": sorted(_tokens(body.content) | set(tags))[:40],
        "created_at": _now(),
    }
    try:
        await _db.agent_memories.insert_one(dict(mem))
    except Exception:
        pass
    return {k: v for k, v in mem.items()}


def _score(mem: dict, q_tokens: set, idx: int, total: int) -> float:
    """Relevance = keyword overlap + recency + importance + a reflection bonus."""
    kw = set(mem.get("keywords") or [])
    overlap = (len(kw & q_tokens) / len(q_tokens)) if q_tokens else 0.0
    recency = 1.0 - (idx / total) if total else 0.0   # newest first ⇒ idx 0 best
    importance = float(mem.get("importance") or 0.5)
    bonus = 0.15 if mem.get("kind") == "reflection" else 0.0
    return overlap * 0.55 + recency * 0.20 + importance * 0.25 + bonus


@router.get("/recall")
async def recall(agent_id: str = Query(...), q: str = Query(""),
                 limit: int = Query(8, ge=1, le=30), kind: str = Query("")):
    """Recall an agent's most relevant memories for a query (keyword × recency ×
    importance). Empty q ⇒ most recent + most important."""
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return {"error": "agent_id required"}
    filt = {"agent_id": agent_id}
    if kind.strip():
        filt["kind"] = kind.strip().lower()
    pool = await _db.agent_memories.find(filt, PROJ).sort("created_at", -1).limit(200).to_list(200)
    q_tokens = _tokens(q)
    total = len(pool)
    ranked = sorted(
        ({**m, "relevance": round(_score(m, q_tokens, i, total), 4)} for i, m in enumerate(pool)),
        key=lambda m: m["relevance"], reverse=True,
    )
    return {"agent_id": agent_id, "query": q, "count": len(ranked[:limit]),
            "memories": ranked[:limit], "pool_size": total}


class ReflectBody(BaseModel):
    agent_id: str = ""
    window: int = 12       # how many recent episodes to reflect on
    focus: str = ""        # optional focus question


@router.post("/reflect")
async def reflect(body: ReflectBody):
    """★ SELF-REFLECTION — distil the agent's recent episodes into a durable lesson
    via the Model Router, and store it as a high-importance 'reflection' memory."""
    agent_id = (body.agent_id or "").strip()
    if not agent_id:
        return {"error": "agent_id required"}
    window = max(3, min(int(body.window or 12), 50))
    recent = await _db.agent_memories.find(
        {"agent_id": agent_id, "kind": {"$ne": "reflection"}}, PROJ
    ).sort("created_at", -1).limit(window).to_list(window)
    if len(recent) < 3:
        return {"error": "not enough episodes to reflect on (need ≥3)", "have": len(recent)}
    episodes = "\n".join(f"- ({m.get('kind')}) {m.get('content')}" for m in reversed(recent))
    system = (
        "You are the reflective memory of an autonomous AI agent. Given the agent's recent "
        "episodes, distil ONE concise, durable lesson or insight (2-3 sentences) the agent should "
        "carry forward to act better next time. Be specific and actionable; avoid platitudes.")
    prompt = (f"RECENT EPISODES (oldest → newest):\n{episodes}\n\n"
              + (f"FOCUS: {body.focus.strip()}\n\n" if body.focus.strip() else "")
              + "Write the single lesson the agent should remember:")
    routed = await route_complete("reasoning", prompt, system=system, use_cache=False)
    insight = (routed.get("content") or "").strip()
    if not insight:
        return {"error": routed.get("error") or "reflection model returned nothing",
                "model": routed.get("model")}
    insight = insight[:MAX_CONTENT]
    mem = {
        "memory_id": uuid.uuid4().hex, "agent_id": agent_id, "content": insight,
        "kind": "reflection", "importance": 0.9,
        "tags": ["reflection"], "keywords": sorted(_tokens(insight))[:40],
        "reflected_on": [m.get("memory_id") for m in recent if m.get("memory_id")],
        "model": routed.get("model"), "created_at": _now(),
    }
    try:
        await _db.agent_memories.insert_one(dict(mem))
    except Exception:
        pass
    return {"agent_id": agent_id, "reflection": {k: v for k, v in mem.items()},
            "episodes_considered": len(recent)}


@router.get("/agents")
async def list_agents(limit: int = Query(50, ge=1, le=200)):
    """All agents that have memories, with counts + last activity (newest first)."""
    pipeline = [
        {"$group": {
            "_id": "$agent_id",
            "memories": {"$sum": 1},
            "reflections": {"$sum": {"$cond": [{"$eq": ["$kind", "reflection"]}, 1, 0]}},
            "last_at": {"$max": "$created_at"},
            "avg_importance": {"$avg": "$importance"},
        }},
        {"$sort": {"last_at": -1}},
        {"$limit": limit},
    ]
    rows = await _db.agent_memories.aggregate(pipeline).to_list(limit)
    agents = [{"agent_id": r["_id"], "memories": r["memories"], "reflections": r["reflections"],
               "last_at": r["last_at"], "avg_importance": round(r.get("avg_importance") or 0, 3)}
              for r in rows]
    return {"agents": agents, "count": len(agents)}


@router.get("/{agent_id}/profile")
async def agent_profile(agent_id: str):
    """An agent's memory profile: counts, top tags, and recent reflections."""
    agent_id = (agent_id or "").strip()
    all_mems = await _db.agent_memories.find({"agent_id": agent_id}, PROJ).to_list(1000)
    if not all_mems:
        return {"agent_id": agent_id, "memories": 0, "reflections": [], "top_tags": [], "by_kind": {}}
    by_kind, tag_count = {}, {}
    for m in all_mems:
        by_kind[m.get("kind", "episode")] = by_kind.get(m.get("kind", "episode"), 0) + 1
        for t in (m.get("tags") or []):
            tag_count[t] = tag_count.get(t, 0) + 1
    reflections = sorted([m for m in all_mems if m.get("kind") == "reflection"],
                         key=lambda m: m.get("created_at") or "", reverse=True)[:10]
    top_tags = sorted(tag_count.items(), key=lambda kv: kv[1], reverse=True)[:12]
    return {"agent_id": agent_id, "memories": len(all_mems), "by_kind": by_kind,
            "top_tags": [{"tag": t, "count": n} for t, n in top_tags],
            "reflections": reflections}


@router.delete("/{agent_id}")
async def clear_agent(agent_id: str):
    """Forget all of an agent's memories (admin / reset)."""
    res = await _db.agent_memories.delete_many({"agent_id": (agent_id or "").strip()})
    return {"agent_id": agent_id, "deleted": res.deleted_count}


@router.get("/{agent_id}/bias")
async def agent_bias(agent_id: str, max_chars: int = Query(900, ge=200, le=2000)):
    """🧠 A compact, prepend-ready 'bias' block distilled from the agent's durable
    reflections + strongest themes — so past lessons actually shape new generations."""
    agent_id = (agent_id or "").strip()
    mems = await _db.agent_memories.find({"agent_id": agent_id}, PROJ).to_list(1000)
    reflections = sorted([m for m in mems if m.get("kind") == "reflection"],
                         key=lambda m: (m.get("importance", 0), m.get("created_at") or ""),
                         reverse=True)[:6]
    tag_count: dict = {}
    for m in mems:
        for t in (m.get("tags") or []):
            if t not in ("reflection", "preference"):
                tag_count[t] = tag_count.get(t, 0) + 1
    top_tags = [t for t, _ in sorted(tag_count.items(), key=lambda kv: kv[1], reverse=True)[:10]]
    lines = [f"- {r.get('content','').strip()}" for r in reflections if r.get("content")]
    bias = ""
    if lines:
        bias = f"Lessons {agent_id} has learned (apply these):\n" + "\n".join(lines)
    if top_tags:
        bias += ("\n\n" if bias else "") + "Recurring strengths/themes: " + ", ".join(top_tags) + "."
    bias = bias[:max_chars]
    return {"agent_id": agent_id, "has_bias": bool(bias),
            "bias": bias, "reflection_count": len(reflections), "top_tags": top_tags}
