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
