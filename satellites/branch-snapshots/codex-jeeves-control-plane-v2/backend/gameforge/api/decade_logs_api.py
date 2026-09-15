
from __future__ import annotations
from datetime import date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gameforge.enterprise.auth import Principal, get_principal
from gameforge.personal.calendar.decade_logs import DecadeLogHub
from gameforge.personal.calendar.era_log import EraLog
from gameforge.personal.calendar.year_calendar import YearCalendar

router = APIRouter(prefix="/decade", tags=["decade-logs"])
_HUBS: Dict[str, DecadeLogHub] = {}
_ERAS: Dict[str, EraLog] = {}
_CALS: Dict[str, YearCalendar] = {}


def _hub(uid: str) -> DecadeLogHub:
    if uid not in _HUBS:
        _HUBS[uid] = DecadeLogHub(uid)
    return _HUBS[uid]


def _era(uid: str) -> EraLog:
    if uid not in _ERAS:
        _ERAS[uid] = EraLog(uid)
    return _ERAS[uid]


def _cal(uid: str) -> YearCalendar:
    if uid not in _CALS:
        _CALS[uid] = YearCalendar(uid)
    return _CALS[uid]


class CatchBody(BaseModel):
    day: str
    body: str
    title: str = "Catch of the day"
    importance: float = 0.8
    schedule_item_id: Optional[str] = None
    tags: List[str] = []


class GuestBody(BaseModel):
    day: str
    person_label: str
    body: str
    relationship: Optional[str] = None
    schedule_item_id: Optional[str] = None


class BuildingBody(BaseModel):
    day: str
    place: str
    body: str
    change_type: str = "observe"
    schedule_item_id: Optional[str] = None


@router.post("/fisherman/catch")
async def catch(req: CatchBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day)
    e = _hub(principal.user_id).fisherman.catch(
        d, req.body, title=req.title, importance=req.importance,
        schedule_item_id=req.schedule_item_id, tags=req.tags,
    )
    return e.to_dict()


@router.post("/guest")
async def guest(req: GuestBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day)
    e = _hub(principal.user_id).guest.note_guest(
        d, req.person_label, req.body, relationship=req.relationship,
        schedule_item_id=req.schedule_item_id,
    )
    return e.to_dict()


@router.post("/building")
async def building(req: BuildingBody, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(req.day)
    e = _hub(principal.user_id).building.note_building(
        d, req.place, req.body, change_type=req.change_type,
        schedule_item_id=req.schedule_item_id,
    )
    return e.to_dict()


@router.get("/day/{day}")
async def day_bundle(day: str, principal: Principal = Depends(get_principal)):
    d = date.fromisoformat(day)
    return _hub(principal.user_id).linked_day(d)


@router.get("/overview")
async def overview(principal: Principal = Depends(get_principal)):
    return _hub(principal.user_id).decade_overview()


@router.post("/era/distill")
async def distill_era(year: Optional[int] = None, principal: Principal = Depends(get_principal)):
    cal = _cal(principal.user_id)
    if year and year != cal.year:
        cal = YearCalendar(principal.user_id, year=year, country=cal.country, city=cal.city)
    hub = _hub(principal.user_id)
    rec = _era(principal.user_id).distill_year(cal, hub, year=year)
    if not rec:
        return {"distilled": False, "reason": "insufficient filled days / schedule signal"}
    return {"distilled": True, "era": rec.to_dict()}


@router.get("/era/chain")
async def era_chain(principal: Principal = Depends(get_principal)):
    el = _era(principal.user_id)
    return {"eras": el.list_eras(), "summary": el.chain_summary()}
