from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.personal.logs.kinds import PersonalLogKind
from gameforge.personal.logs.service import PersonalLogService
from gameforge.personal.logs.recording_ledger import RecordingLedgerService

router = APIRouter(prefix="/logs", tags=["personal-logs"])
_LOGS: Dict[str, PersonalLogService] = {}
_LEDGERS: Dict[str, RecordingLedgerService] = {}


def _svc(user_id: str) -> PersonalLogService:
    if user_id not in _LOGS:
        _LOGS[user_id] = PersonalLogService(user_id=user_id)
    return _LOGS[user_id]


def _ledger(user_id: str) -> RecordingLedgerService:
    if user_id not in _LEDGERS:
        _LEDGERS[user_id] = RecordingLedgerService(user_id=user_id, log_service=_svc(user_id))
    return _LEDGERS[user_id]


class LogWrite(BaseModel):
    kind: str
    title: str = "note"
    body: str
    tags: List[str] = []
    mood: Optional[float] = None
    intensity: Optional[float] = None
    metadata: Dict[str, Any] = {}
    mirror_to_diary: bool = False


class ConsentBody(BaseModel):
    granted: bool


@router.post("/entries")
async def write_log(req: LogWrite, principal: Principal = Depends(get_principal)):
    try:
        kind = PersonalLogKind(req.kind)
    except Exception:
        raise HTTPException(400, detail=f"kind must be one of {[k.value for k in PersonalLogKind]}")
    svc = _svc(principal.user_id)
    e = await svc.add(
        kind, req.title, req.body,
        tags=req.tags, mood=req.mood, intensity=req.intensity,
        metadata=req.metadata, mirror_to_diary=req.mirror_to_diary,
    )
    return {
        "entry_id": e.entry_id, "kind": e.kind.value, "title": e.title,
        "insight_hints": e.insight_hints, "created_at": e.created_at.isoformat(),
    }


@router.get("/context")
async def logs_context(principal: Principal = Depends(get_principal)):
    svc = _svc(principal.user_id)
    return {"context": svc.export_context(n_per_kind=2), "wellness": svc.wellness_snapshot()}


@router.get("/wellness")
async def wellness(principal: Principal = Depends(get_principal)):
    return _svc(principal.user_id).wellness_snapshot()


@router.get("/kinds")
async def list_kinds(principal: Principal = Depends(get_principal)):
    from gameforge.personal.logs.kinds import LOG_FOCUS
    return {"kinds": [{ "kind": k.value, "focus": LOG_FOCUS[k]} for k in PersonalLogKind]}


@router.post("/recording/consent")
async def recording_consent(req: ConsentBody, principal: Principal = Depends(get_principal)):
    led = _ledger(principal.user_id)
    led.set_consent(req.granted)
    return led.status()


@router.get("/recording/status")
async def recording_status(principal: Principal = Depends(get_principal)):
    return _ledger(principal.user_id).status()


@router.post("/recording/purge")
async def recording_purge(principal: Principal = Depends(get_principal)):
    n = await _ledger(principal.user_id).purge_expired_audio()
    return {"deleted": n, "status": _ledger(principal.user_id).status()}
