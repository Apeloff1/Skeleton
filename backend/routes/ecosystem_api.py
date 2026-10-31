"""Full-stack ecosystem API.

Exposes session create, run, status, export, list, and health for the
IntegratedStudio pipeline. All inputs are bounded; errors never leak traces.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.ecosystem_orchestrator import get_orchestrator
from backend.core.security_augmentation import bound_text

router = APIRouter(prefix="/api/ecosystem", tags=["ecosystem"])


class CreateSessionBody(BaseModel):
    brief: str = Field(min_length=4, max_length=8000)
    era: str = Field(default="ash", max_length=32)


class RunBody(BaseModel):
    session_id: str = Field(min_length=8, max_length=32)


@router.get("/health")
async def ecosystem_health():
    return get_orchestrator().health()


@router.post("/session")
async def create_session(body: CreateSessionBody):
    brief = bound_text(body.brief, max_len=8000)
    result = get_orchestrator().create_session(brief, era=body.era, actor="api")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("reason", "bad_request"))
    return result


@router.post("/run")
async def run_session(body: RunBody):
    result = get_orchestrator().run(body.session_id, actor="api")
    if not result.get("ok") and result.get("reason") in ("session_not_found", "invalid_session"):
        raise HTTPException(status_code=404, detail=result.get("reason"))
    return result


@router.get("/session/{session_id}")
async def session_status(session_id: str):
    result = get_orchestrator().status(session_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason", "not_found"))
    return result


@router.get("/session/{session_id}/export")
async def session_export(session_id: str):
    result = get_orchestrator().export_godot(session_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason", "not_found"))
    return result


@router.get("/sessions")
async def list_sessions(limit: int = 20):
    return get_orchestrator().list_sessions(limit=limit)


@router.get("/studio/status")
async def studio_status():
    orch = get_orchestrator()
    return {"ok": True, "studio": orch.studio.status(), "sessions": len(orch.sessions)}
