"""
routes/lafs.py — Lever Arch File System API (/api/lafs).

Deep-probability knowledge ledger for Jeeves · agents · Librarian:
hierarchical Bayes, Active-Inference free energy, MCMC/VI/ASMC, graph belief
propagation and contextual acquisition. Mongo-persisted (fork-safe).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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
