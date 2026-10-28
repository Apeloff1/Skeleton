"""routes/text_gamefile.py — 10 text→gamefile systems API (gate-crosswired)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import text_gamefile as tg

router = APIRouter(prefix="/api/galaxy-studio/text-gamefile", tags=["text-gamefile"])


@router.get("/generators")
def generators():
    return tg.list_generators()


class GenReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    enrich: bool = False
    contexts: dict | None = None
    tier: str | None = None


@router.post("/{key}/generate")
def generate(key: str, req: GenReq):
    return tg.generate(key, req.build_id, req.text, enrich=req.enrich,
                       contexts=req.contexts, tier=req.tier)


class PruneReq(BaseModel):
    build_id: str | None = None      # None → prune ALL forged gamefiles


@router.post("/prune")
def prune(req: PruneReq | None = None):
    return tg.prune_gamefiles((req.build_id if req else None))


@router.get("/{build_id}/list")
def list_files(build_id: str):
    return tg.list_gamefiles(build_id)


@router.get("/{build_id}/{gid}")
def get_file(build_id: str, gid: str):
    doc = tg.get_gamefile(build_id, gid)
    return doc or {"error": "not_found"}
