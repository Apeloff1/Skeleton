"""routes/gamefile_pipeline.py — SOTA gamefile gate pipeline API."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core import gamefile_pipeline as gp

router = APIRouter(prefix="/api/galaxy-studio/gamefile-pipeline", tags=["gamefile-pipeline"])


@router.get("/gates")
def gates():
    return gp.list_pipeline()


@router.get("/controller/status")
def controller_status():
    return gp.controller_status()


@router.get("/{build_id}/{gid}/history")
def history(build_id: str, gid: str):
    return gp.pipeline_history(build_id, gid)


class RunReq(BaseModel):
    persist: bool = True
    auto_mint_enhancer: bool = False


@router.post("/{build_id}/{gid}/run")
def run(build_id: str, gid: str, req: RunReq | None = None):
    r = req or RunReq()
    return gp.run_pipeline(build_id, gid, persist=r.persist,
                           auto_mint_enhancer=r.auto_mint_enhancer)
