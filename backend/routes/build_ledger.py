"""routes/build_ledger.py — per-build context database API.

Read the full event stream and rolling context summary for any build, list all
builds, or log an explicit build event.
"""
from __future__ import annotations
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import build_ledger as bl

router = APIRouter(prefix="/api/galaxy-studio/builds", tags=["build-ledger"])


@router.get("")
async def list_builds(limit: int = 200):
    from routes.galaxy_studio_access import visible_build_rows

    result = await asyncio.to_thread(bl.list_builds, limit=min(max(limit, 1), 200))
    # The ledger is a derived projection; canonical Galaxy metadata decides
    # which build identities this account can inspect.
    visible = await visible_build_rows(result.get("builds", []))
    return {"count": len(visible), "builds": visible}


@router.get("/{build_id}/ledger")
def ledger(build_id: str, limit: int = 1000, kind: str = ""):
    return bl.get_ledger(build_id, limit=limit, kind=kind or None)


@router.get("/{build_id}/context")
def context(build_id: str):
    return bl.get_context(build_id)


class LogReq(BaseModel):
    kind: str = Field(..., min_length=1)
    data: dict = Field(default_factory=dict)
    step: str | None = None


@router.post("/{build_id}/log")
def log_event(build_id: str, req: LogReq):
    return bl.log(build_id, req.kind, req.data, step=req.step)
