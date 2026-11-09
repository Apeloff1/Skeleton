from __future__ import annotations
from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.personal.synergy.coherence import CoherenceEngine
from gameforge.personal.synergy.triggers import trigger_matrix

router = APIRouter(prefix="/coherence", tags=["coherence"])
_ENGINES: Dict[str, CoherenceEngine] = {}


def _eng(uid: str) -> CoherenceEngine:
    if uid not in _ENGINES:
        _ENGINES[uid] = CoherenceEngine(uid)
    return _ENGINES[uid]


class TranscriptBody(BaseModel):
    segment: str


class SleepBody(BaseModel):
    sleep_hours: float


class ScheduleBody(BaseModel):
    title: str
    day: Optional[str] = None
    kind: str = "task"
    project_id: Optional[str] = None


class ProgressBody(BaseModel):
    project_id: str
    name: str
    percent: float
    day: Optional[str] = None
    note: str = ""


class PainBody(BaseModel):
    pain_level: float


class MidnightBody(BaseModel):
    segments: List[str]


class LocationBody(BaseModel):
    country: str
    city: str
    latitude: float = 59.95


@router.get("/triggers")
async def list_triggers(principal: Principal = Depends(get_principal)):
    return {"triggers": trigger_matrix()}


@router.post("/day_start")
async def day_start(principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).on_day_start().to_dict()


@router.post("/transcript")
async def transcript(req: TranscriptBody, principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).on_transcript(req.segment).to_dict()


@router.post("/sleep")
async def sleep(req: SleepBody, principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).on_sleep(req.sleep_hours).to_dict()


@router.post("/schedule")
async def schedule(req: ScheduleBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day) if req.day else None
    return _eng(principal.user_id).on_schedule_add(
        req.title, day=d, kind=req.kind, project_id=req.project_id
    ).to_dict()


@router.post("/progress")
async def progress(req: ProgressBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day) if req.day else None
    return _eng(principal.user_id).on_progress(
        req.project_id, req.name, req.percent, day=d, note=req.note
    ).to_dict()


@router.post("/pain")
async def pain(req: PainBody, principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).on_pain(req.pain_level).to_dict()


@router.post("/midnight")
async def midnight(req: MidnightBody, principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).on_midnight(req.segments).to_dict()


@router.post("/location")
async def location(req: LocationBody, principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).on_location(req.country, req.city, req.latitude).to_dict()


@router.get("/jeeves_context")
async def jeeves_context(principal: Principal = Depends(get_principal)):
    return {"context": _eng(principal.user_id).jeeves_context_block()}


@router.get("/history")
async def history(principal: Principal = Depends(get_principal)):
    eng = _eng(principal.user_id)
    return {"events": [e.to_dict() for e in eng.history[-50:]]}


@router.get("/trigger_logs")
async def trigger_logs(n: int = 50, principal: Principal = Depends(get_principal)):
    eng = _eng(principal.user_id)
    return {"logs": eng.trigger_logs(n), "stats": eng.trigger_stats()}


@router.post("/reliable/day_start")
async def reliable_day_start(principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).reliable_day_start()


@router.post("/reliable/transcript")
async def reliable_transcript(req: TranscriptBody, principal: Principal = Depends(get_principal)):
    return _eng(principal.user_id).reliable_transcript(req.segment)


@router.post("/reliable/schedule")
async def reliable_schedule(req: ScheduleBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day) if req.day else None
    return _eng(principal.user_id).reliable_schedule(
        req.title, day=d, kind=req.kind, project_id=req.project_id
    )
