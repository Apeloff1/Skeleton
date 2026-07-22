"""routes/refine_gates.py — Galaxy Studio Refine/Polish/QC gate API."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import refine_gates as rg

router = APIRouter(prefix="/api/galaxy-studio/gates", tags=["refine-gates"])


@router.get("/stages")
def stages():
    return rg.list_stages()


class RunReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    kind: str = "system"           # "system" | "construct"
    key: str = Field(..., min_length=1)
    seed: int = 0
    ai: bool = False
    persist: bool = True


@router.post("/{stage}/run")
def run(stage: str, req: RunReq):
    return rg.run_stage_on(stage, req.kind, req.build_id, req.key,
                           seed=req.seed, ai=req.ai, persist=req.persist)


class RunAllReq(BaseModel):
    build_id: str | None = None  # taken from URL path; body field optional
    seed: int = 0
    ai: bool = False
    include_panel: bool = True


@router.post("/build/{build_id}/run-all")
def run_all(build_id: str, req: RunAllReq):
    return rg.run_all(build_id, seed=req.seed, ai=req.ai, include_panel=req.include_panel)


@router.get("/build/{build_id}/coverage")
def coverage(build_id: str):
    return rg.coverage(build_id)


class RunTargetReq(BaseModel):
    kind: str = "gamefile"        # "gamefile" | "system" | "construct"
    seed: int = 0
    ai: bool = False              # deterministic by default (fast, no 504)


@router.post("/target/{build_id}/{key}/run-all")
def run_all_target(build_id: str, key: str, req: RunTargetReq):
    """Run all 14 gates on a SINGLE target (e.g. a generated gamefile)."""
    return rg.run_all_target(req.kind, build_id, key, seed=req.seed, ai=req.ai)
