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
    segments: List[str]


class ControlBody(BaseModel):
    sleep_hours: float = 7.0
    weather_condition: str = "clear"
    noise_db: float = 45.0
    affect_energy: float = 0.55
    affect_valence: float = 0.1
    pain_level: float = 0.0
    progress_delta: float = 0.0
    scheduled_count: int = 0
    stress_hints: int = 0


class ConsolidateBody(BaseModel):
    segments: List[str]
    extra_notes: Optional[List[str]] = None


class RewardBody(BaseModel):
    magnitude: float = 0.3


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
