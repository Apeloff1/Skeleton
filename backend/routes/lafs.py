"""
routes/lafs.py — Lever Arch File System API (/api/lafs).

Deep-probability knowledge ledger for Jeeves · agents · Librarian:
hierarchical Bayes, Active-Inference free energy, MCMC/VI/ASMC, graph belief
propagation and contextual acquisition. Mongo-persisted (fork-safe).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from gameforge.lafs import lafs, jeeves, librarian, HIERARCHY, TOTAL_LOG_TYPES

router = APIRouter(prefix="/api/lafs", tags=["lafs"])


class RememberReq(BaseModel):
    domain: str
    log_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    author: str = "Jeeves"
    cross_refs: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class RecallReq(BaseModel):
    query: str = Field(..., min_length=1)
    domain_filter: Optional[str] = None
    log_type_filter: Optional[str] = None
    acquisition: str = "efe"        # efe|ucb|eig|poi|thompson|hybrid-deep
    top_k: int = 10
    context_ids: List[str] = Field(default_factory=list)


class ReinforceReq(BaseModel):
    sheet_id: str
    success: bool = True
    weight: float = 1.0
    tag: Optional[str] = None
    deep: bool = False              # True = full MCMC/ASMC/VI (slow, high quality)


@router.get("/stats")
async def stats():
    return {"ok": True, **librarian.stats()}


@router.get("/hierarchy")
async def hierarchy():
    return {"ok": True, "total_log_types": TOTAL_LOG_TYPES,
            "domains": len(HIERARCHY), "hierarchy": HIERARCHY}


@router.post("/remember")
async def remember(req: RememberReq):
    try:
        sheet = lafs.add_sheet(req.domain, req.log_type, req.payload,
                               author=req.author, cross_refs=req.cross_refs, tags=req.tags)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return {"ok": True, "sheet": sheet.brief()}


@router.post("/recall")
async def recall(req: RecallReq):
    results = lafs.probability_search(
        req.query, domain_filter=req.domain_filter, log_type_filter=req.log_type_filter,
        acquisition=req.acquisition, top_k=req.top_k,
        context_ids=req.context_ids or None)
    return {"ok": True, "count": len(results), "results": results}


@router.post("/reinforce")
async def reinforce(req: ReinforceReq):
    brief = lafs.reinforce(req.sheet_id, req.success, req.weight, tag=req.tag, deep=req.deep)
    if brief is None:
        raise HTTPException(status_code=404, detail="sheet_not_found")
    return {"ok": True, "sheet": brief}


@router.get("/related/{sheet_id}")
async def related(sheet_id: str, depth: int = 1):
    return {"ok": True, "related": [s.brief() for s in lafs.get_related(sheet_id, depth)]}


@router.post("/jury/{sheet_id}")
async def jury(sheet_id: str, reason: str = "high_entropy"):
    return {"ok": True, "queued": lafs.queue_for_jury(sheet_id, reason)}


# ══════════════════════════════════════════════════════════════
# ONLINE LEARNING — Jeeves compounds its brain via FREE external
# APIs (Wikipedia REST). Direct fetch, no keys. Fail-safe.
# ══════════════════════════════════════════════════════════════
class LearnReq(BaseModel):
    topic: str = Field(..., min_length=2)
    domain: str = "Narrative"
    log_type: str = "Lore"
    reinforce: bool = True


async def _wiki_summary(topic: str) -> Optional[Dict]:
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(topic)}"
    ua = "GameForge-Jeeves/1.0 (https://emergent.sh; contact@emergent.sh) python-httpx"
    async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                 headers={"User-Agent": ua, "Accept": "application/json"}) as c:
        r = await c.get(url)
    if r.status_code != 200:
        return None
    d = r.json()
    if d.get("type") == "disambiguation" or not d.get("extract"):
        return None
    return {
        "title": d.get("title"),
        "extract": d.get("extract"),
        "description": d.get("description"),
        "source_url": (d.get("content_urls", {}).get("desktop", {}) or {}).get("page"),
        "thumbnail": (d.get("thumbnail", {}) or {}).get("source"),
    }


@router.post("/learn/online")
async def learn_online(req: LearnReq):
    """Fetch a real free knowledge summary (Wikipedia) and ingest it into the
    LAFS ledger as a Jeeves-authored sheet — self-learning, online."""
    try:
        summary = await _wiki_summary(req.topic)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"upstream_error: {type(e).__name__}: {e}")
    if not summary:
        raise HTTPException(status_code=404, detail="no_reliable_source_found")

    payload = {**summary, "topic": req.topic, "provenance": "wikipedia_rest_v1"}
    sheet = lafs.add_sheet(req.domain, req.log_type, payload,
                           author="Jeeves-Online",
                           tags=["online", "wikipedia", req.topic.lower()])
    # Learned-from-a-reliable-source → reinforce belief (fast).
    if req.reinforce:
        lafs.reinforce(sheet.id, success=True, weight=1.5, tag="online_source")
    return {"ok": True, "learned": True, "source": summary.get("source_url"),
            "sheet": lafs.sheets[sheet.id].brief()}


@router.post("/learn/batch")
async def learn_batch(topics: List[str], domain: str = "Meta", log_type: str = "Discovery"):
    """Batch online learning — compound the brain across several topics."""
    out = []
    for t in topics[:12]:
        try:
            s = await _wiki_summary(t)
            if not s:
                out.append({"topic": t, "learned": False, "reason": "no_source"})
                continue
            sheet = lafs.add_sheet(domain, log_type, {**s, "topic": t, "provenance": "wikipedia_rest_v1"},
                                   author="Jeeves-Online", tags=["online", "wikipedia", t.lower()])
            lafs.reinforce(sheet.id, success=True, weight=1.5, tag="online_source")
            out.append({"topic": t, "learned": True, "sheet_id": sheet.id, "title": s.get("title")})
        except Exception as e:  # noqa: BLE001
            out.append({"topic": t, "learned": False, "reason": f"{type(e).__name__}"})
    learned = sum(1 for o in out if o.get("learned"))
    return {"ok": True, "learned_count": learned, "total": len(out), "results": out}


# ══════════════════════════════════════════════════════════════
# STAGE C2 — multi-hop belief propagation + posterior-predictive
# ══════════════════════════════════════════════════════════════
@router.post("/belief-propagate/{sheet_id}")
async def belief_propagate(sheet_id: str, hops: int = 2, strength: float = 0.08):
    """Propagate a sheet's belief across the canon graph (multi-hop) and
    return the full update trace."""
    res = lafs.belief_propagate(sheet_id, hops=max(1, min(hops, 5)), strength=strength)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "sheet_not_found"))
    return res


@router.get("/posterior-check")
async def posterior_check(sheet_id: Optional[str] = None):
    """Posterior-predictive calibration check across the ledger (or one sheet)."""
    res = lafs.posterior_predictive_check(sheet_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "no_sheets"))
    return res


@router.get("/top-efe")
async def top_efe(k: int = 8, domain_filter: Optional[str] = None):
    """Top-k sheets by Expected Free Energy — 'what Jeeves knows best'."""
    return {"ok": True, "top": lafs.top_efe(k=max(1, min(k, 50)), domain_filter=domain_filter)}


# ══════════════════════════════════════════════════════════════
# STAGE C3 — Jeeves RAG replies (recall top-EFE canon → grounded answer)
# ══════════════════════════════════════════════════════════════
class JeevesAskReq(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = 6
    domain_filter: Optional[str] = None
    image_base64: Optional[str] = None   # optional image → multimodal grounding
    audio_base64: Optional[str] = None   # folded into Delta memory as audio modality


@router.post("/jeeves/ask")
async def jeeves_ask(req: JeevesAskReq):
    """Retrieval-augmented, MULTIMODAL Jeeves reply: recall the most relevant
    high-EFE LAFS sheets, optionally caption an attached image via a vision
    model, then generate a grounded answer. Any attached media is also folded
    into the fixed-size Delta (KDA) memory so Jeeves 'remembers' it."""
    recalled = lafs.probability_search(
        req.query, domain_filter=req.domain_filter,
        acquisition="hybrid-deep", top_k=max(1, min(req.top_k, 12)))

    grounded = [{"sheet_id": r.get("id"), "path": r.get("path"),
                 "score": r.get("score"), "efe": r.get("acq"),
                 "payload": r.get("payload")} for r in recalled]

    ctx_lines = []
    for i, r in enumerate(recalled, 1):
        payload = r.get("payload") or {}
        snippet = (payload.get("extract") or payload.get("content")
                   or payload.get("description") or str(payload))[:400]
        ctx_lines.append(f"[{i}] ({r.get('path')}) {snippet}")
    context_block = "\n".join(ctx_lines) if ctx_lines else "(no canon recalled)"

    # ── fold any attached media into the Delta (KDA) multimodal memory ──
    modalities_seen = ["text"]
    try:
        from gameforge.omega import delta_memory as _dm
        if req.image_base64:
            _dm.write(f"query:{req.query[:60]}", req.image_base64, modality="image")
            modalities_seen.append("image")
        if req.audio_base64:
            _dm.write(f"query:{req.query[:60]}", req.audio_base64, modality="audio")
            modalities_seen.append("audio")
    except Exception:  # noqa: BLE001
        pass

    import os as _os
    api_key = _os.getenv("EMERGENT_LLM_KEY", "")
    reply, model = None, "extractive"
    if api_key and (recalled or req.image_base64):
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
            import uuid as _uuid
            system = ("You are Jeeves, the GameForge master orchestrator. Answer the user "
                      "GROUNDED in the provided canon knowledge AND any attached image. "
                      "Cite sheet numbers [n]. If canon is insufficient, say so briefly.")
            # vision-capable model when an image is attached, else sonnet
            provider, mdl = ("openai", "gpt-4o") if req.image_base64 else ("anthropic", "claude-sonnet-4-6")
            chat = LlmChat(api_key=api_key, session_id=_uuid.uuid4().hex,
                           system_message=system).with_model(provider, mdl)
            prompt = f"CANON KNOWLEDGE:\n{context_block}\n\nUSER QUESTION: {req.query}"
            files = None
            if req.image_base64:
                b64 = req.image_base64.split(",", 1)[-1] if req.image_base64.startswith("data:") else req.image_base64
                files = [ImageContent(image_base64=b64)]
            reply = await chat.send_message(UserMessage(text=prompt, file_contents=files))
            model = f"{provider}:{mdl}"
        except Exception:  # noqa: BLE001
            reply = None
    if not reply:
        if recalled:
            top = recalled[0].get("payload") or {}
            head = (top.get("extract") or top.get("content")
                    or top.get("description") or "").strip()
            reply = (f"Based on {len(recalled)} recalled canon sheet(s): {head[:600]}"
                     if head else f"Recalled {len(recalled)} related canon sheet(s) but no text payload.")
        else:
            reply = "Jeeves has no canon on this yet — try /api/lafs/learn/online to teach him."

    return {"ok": True, "query": req.query, "reply": reply, "model": model,
            "modalities": modalities_seen, "grounded_in": grounded,
            "recalled_count": len(recalled)}


# ══════════════════════════════════════════════════════════════
# STAGE C1 — online-learning sweep (rotating free-knowledge topics)
# ══════════════════════════════════════════════════════════════
_SWEEP_TOPICS = [
    "Game design", "Procedural generation", "Finite-state machine", "Pathfinding",
    "Game physics", "Level design", "Narrative design", "Roguelike",
    "Entity component system", "Shader", "Quaternion", "Perlin noise",
    "Behavior tree", "Game balance", "Difficulty level", "Sprite (computer graphics)",
]
_sweep_cursor = {"i": 0}


@router.post("/sweep/online")
async def sweep_online(count: int = 4, domain: str = "Meta", log_type: str = "Discovery"):
    """Run one online-learning sweep over the next ``count`` rotating topics.
    Designed to be called on a nightly schedule (or on demand)."""
    picked, results, learned = [], [], 0
    n = len(_SWEEP_TOPICS)
    for _ in range(max(1, min(count, n))):
        t = _SWEEP_TOPICS[_sweep_cursor["i"] % n]
        _sweep_cursor["i"] += 1
        picked.append(t)
    for t in picked:
        try:
            s = await _wiki_summary(t)
            if not s:
                results.append({"topic": t, "learned": False}); continue
            sheet = lafs.add_sheet(domain, log_type, {**s, "topic": t, "provenance": "wikipedia_rest_v1"},
                                   author="Jeeves-Sweep", tags=["online", "sweep", t.lower()])
            lafs.reinforce(sheet.id, success=True, weight=1.5, tag="online_sweep", deep=True)
            results.append({"topic": t, "learned": True, "sheet_id": sheet.id})
            learned += 1
        except Exception as e:  # noqa: BLE001
            results.append({"topic": t, "learned": False, "reason": type(e).__name__})
    return {"ok": True, "swept": picked, "learned_count": learned, "results": results,
            "cursor": _sweep_cursor["i"]}
