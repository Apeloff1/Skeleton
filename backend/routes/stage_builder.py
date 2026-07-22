"""routes/stage_builder.py — THE STAGE PAGE API.

Lay out a build as an ordered list of game stages from a large hand-authored
catalogue of distinct stage types. Building a stage CREATES THE FIRST GAMEFILES
for the build (crosswired to text→gamefile + the 14-gate engine).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core import stage_builder as sb

router = APIRouter(prefix="/api/galaxy-studio/stages", tags=["stage-builder"])


@router.get("/catalog")
def catalog():
    return sb.catalog()


@router.get("/{build_id}/list")
def list_stages(build_id: str):
    return sb.list_stages(build_id)


@router.get("/{build_id}/summary")
def summary(build_id: str):
    return sb.summary(build_id)


class AddReq(BaseModel):
    type: str = Field(..., min_length=1)
    title: str = ""
    note: str = ""


@router.post("/{build_id}/add")
def add_stage(build_id: str, req: AddReq):
    return sb.add_stage(build_id, req.type, title=req.title, note=req.note)


class UpdateReq(BaseModel):
    title: str | None = None
    note: str | None = None


@router.put("/{build_id}/{stage_id}")
def update_stage(build_id: str, stage_id: str, req: UpdateReq):
    return sb.update_stage(build_id, stage_id, title=req.title, note=req.note)


@router.delete("/{build_id}/{stage_id}")
def delete_stage(build_id: str, stage_id: str):
    return sb.delete_stage(build_id, stage_id)


class ReorderReq(BaseModel):
    order: list[str] = Field(default_factory=list)


@router.post("/{build_id}/reorder")
def reorder(build_id: str, req: ReorderReq):
    return sb.reorder(build_id, req.order)


class BuildReq(BaseModel):
    enrich: bool = False
    contexts: dict | None = None


@router.post("/{build_id}/{stage_id}/build")
def build_stage(build_id: str, stage_id: str, req: BuildReq):
    return sb.build_stage(build_id, stage_id, enrich=req.enrich,
                          contexts=req.contexts)
