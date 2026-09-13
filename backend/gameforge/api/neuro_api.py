from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.personal.neuro.orchestrator import NeuroOrchestrator

router = APIRouter(prefix="/neuro", tags=["neuro"])
_ORCH: Dict[str, NeuroOrchestrator] = {}


def _orch(user_id: str) -> NeuroOrchestrator:
    if user_id not in _ORCH:
        _ORCH[user_id] = NeuroOrchestrator(user_id)
    return _ORCH[user_id]


class FilterBody(BaseModel):
    segments: List[str] = Field(..., min_length=1, max_length=200)


class ControlBody(BaseModel):
    sleep_hours: float = Field(7.0, ge=0, le=24)
    weather_condition: str = Field("clear", max_length=100)
    noise_db: float = Field(45.0, ge=0, le=200)
    affect_energy: float = Field(0.55, ge=-1, le=1)
    affect_valence: float = Field(0.1, ge=-1, le=1)
    pain_level: float = Field(0.0, ge=0, le=10)
    progress_delta: float = Field(0.0, ge=-100, le=100)
    scheduled_count: int = Field(0, ge=0, le=10000)
    stress_hints: int = Field(0, ge=0, le=10000)


class ConsolidateBody(BaseModel):
    segments: List[str] = Field(..., min_length=1, max_length=200)
    extra_notes: Optional[List[str]] = Field(None, max_length=200)


class RewardBody(BaseModel):
    magnitude: float = Field(0.3, ge=-1, le=1)


@router.post("/salience/filter")
async def salience_filter(req: FilterBody, principal: Principal = Depends(get_principal)):
    return _orch(principal.user_id).filter_transcripts(req.segments)


@router.post("/control")
async def daily_control(req: ControlBody, principal: Principal = Depends(get_principal)):
    return _orch(principal.user_id).daily_control_plane(**req.model_dump())


@router.post("/consolidate")
async def midnight_consolidate(req: ConsolidateBody, principal: Principal = Depends(get_principal)):
    return _orch(principal.user_id).midnight_consolidation(req.segments, extra_notes=req.extra_notes)


@router.post("/reward")
async def register_reward(req: RewardBody, principal: Principal = Depends(get_principal)):
    o = _orch(principal.user_id)
    o.neuromod.register_reward(req.magnitude)
    return {"ok": True, "magnitude": req.magnitude}


@router.get("/schedule_gate")
async def schedule_gate(principal: Principal = Depends(get_principal)):
    return _orch(principal.user_id).homeostasis.assert_can_schedule()


@router.get("/jeeves_context")
async def jeeves_ctx(principal: Principal = Depends(get_principal)):
    o = _orch(principal.user_id)
    control = o.daily_control_plane()
    return {"context": o.jeeves_context_block(control), "control": control}
