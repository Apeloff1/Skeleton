from __future__ import annotations
from datetime import date
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.personal.calendar.year_calendar import YearCalendar

router = APIRouter(prefix="/calendar", tags=["calendar"])
_CALS: Dict[str, YearCalendar] = {}


def _cal(user_id: str, country: str = "NO", city: str = "Lillestrøm") -> YearCalendar:
    if user_id not in _CALS:
        _CALS[user_id] = YearCalendar(user_id, country=country, city=city)
    return _CALS[user_id]


class LocationBody(BaseModel):
    country: str = "NO"
    city: str = "Lillestrøm"
    latitude: float = 59.95


class ScheduleBody(BaseModel):
    day: str  # ISO date
    title: str
    when: Optional[str] = None
    kind: str = "task"
    project_id: Optional[str] = None
    notes: str = ""


class ProgressBody(BaseModel):
    day: str
    project_id: str
    name: str
    percent: float
    note: str = ""


class NoteBody(BaseModel):
    day: str
    note: str


@router.get("/today")
async def today(principal: Principal = Depends(get_principal)):
    return _cal(principal.user_id).today_briefing()


@router.get("/day/{day}")
async def get_day(day: str, principal: Principal = Depends(get_principal)):
    try:
        d = date.fromisoformat(day)
    except Exception:
        raise HTTPException(400, "day must be YYYY-MM-DD")
    return _cal(principal.user_id).get_day(d, enrich=True).to_dict()


@router.post("/location")
async def set_location(req: LocationBody, principal: Principal = Depends(get_principal)):
    c = _cal(principal.user_id)
    c.set_location(req.country, req.city, req.latitude)
    return {"country": c.country, "city": c.city, "latitude": c.latitude}


@router.post("/schedule")
async def add_schedule(req: ScheduleBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day)
    daylog = _cal(principal.user_id).add_schedule(
        d, req.title, when=req.when, kind=req.kind, project_id=req.project_id, notes=req.notes
    )
    return daylog.to_dict()


@router.post("/progress")
async def project_progress(req: ProgressBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day)
    daylog = _cal(principal.user_id).set_project_progress(
        d, req.project_id, req.name, req.percent, req.note
    )
    return daylog.to_dict()


@router.post("/note")
async def day_note(req: NoteBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day)
    return _cal(principal.user_id).add_day_note(d, req.note).to_dict()


@router.get("/jeeves_context")
async def jeeves_context(principal: Principal = Depends(get_principal)):
    return {"context": _cal(principal.user_id).jeeves_context_block()}


@router.get("/yesteryear")
async def yesteryear(day: Optional[str] = None, principal: Principal = Depends(get_principal)):
    c = _cal(principal.user_id)
    d = date.fromisoformat(day) if day else date.today()
    mems = c.weather_log.memories_of_yesteryear(
        d, years_back=10, country=c.country, city=c.city, latitude=c.latitude
    )
    return {"day": d.isoformat(), "memories": mems}
