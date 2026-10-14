"""Authenticated, fail-closed Dragon knowledge-to-design delivery projections.

Uses the canonical reviewed source/Almanakk store. These endpoints do not
execute a compiler, grant training rights, mutate review status, or claim a
native build. Source generation requires a separately admitted resource lane.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import os
import re
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from routes.dragon_academy import _principal
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_delivery import DragonDelivery
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_game_design import parse_design
from skeleton.ai.webcrawler.dragon_execution_pool import DragonExecutionPool

router = APIRouter(prefix="/api/dragon-academy/delivery", tags=["Dragon Delivery"])
_TOPIC = re.compile(r"[a-f0-9]{64}\Z")
_MAX_CLOCK = 4_102_444_800


class DeliveryBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    design: dict[str, object]
    query: str = Field(min_length=1, max_length=300)


def _clock() -> int:
    now = int(time.time())
    if not 0 <= now <= _MAX_CLOCK:
        raise HTTPException(status_code=503, detail="Current knowledge clock unavailable")
    return now


def _knowledge_path() -> Path:
    raw = os.environ.get("SKL_DRAGON_KNOWLEDGE_DB_PATH", "").strip()
    if not raw:
        raise HTTPException(status_code=503, detail="Dragon knowledge database not configured")
    path = Path(raw).expanduser()
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or not path.parent.is_dir()):
        raise HTTPException(status_code=503, detail="Dragon knowledge database unavailable")
    return path


@contextmanager
def _delivery() -> Iterator[DragonDelivery]:
    path = _knowledge_path()
    try:
        with ReviewedKnowledgeStore(path) as library:
            yield DragonDelivery(DragonAlmanacs(library))
    except (sqlite3.DatabaseError, OSError):
        raise HTTPException(status_code=503, detail="Dragon knowledge storage unavailable") from None


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"


def _project(work) -> dict:
    try:
        return {"ok": True, **work()}
    except HTTPException:
        raise
    except (ValueError, TypeError, LookupError, PermissionError):
        raise HTTPException(status_code=422, detail="Canonical delivery evidence or request is invalid") from None


@router.get("/overview")
def delivery_overview(request: Request, response: Response,
                      owner: str = Depends(_principal)) -> dict:
    _private(response)
    with _delivery() as delivery:
        result = _project(lambda: delivery.overview(owner, now=_clock(), authorized=True))
    pool = getattr(request.app.state, "dragon_execution_pool", None)
    raw = os.environ.get("SKL_DRAGON_PRACTICE_DB_PATH", "").strip()
    path = Path(raw).expanduser() if raw else None
    result["practice_storage_ready"] = bool(
        path and path.is_absolute() and not path.is_symlink() and path.is_file()
    )
    # Explicitly not a production-generation claim: the delivery source
    # dispatch endpoint is not wired here.
    result["resource_runtime_ready"] = False
    result["resource_runtime_configured"] = isinstance(pool, DragonExecutionPool)
    result["generation_available"] = False
    return result


@router.get("/knowledge")
def delivery_knowledge(response: Response, query: str = Query(min_length=1, max_length=300),
                       owner: str = Depends(_principal)) -> dict:
    _private(response)
    with _delivery() as delivery:
        return _project(lambda: delivery.search(owner, query, now=_clock(),
                                                 authorized=True, limit=12))


@router.get("/almanacs")
def delivery_almanacs(response: Response, offset: int = Query(default=0, ge=0, le=100000),
                      owner: str = Depends(_principal)) -> dict:
    _private(response)
    with _delivery() as delivery:
        return _project(lambda: delivery.almanacs.report(
            owner, authorized=True, limit=32, offset=offset
        ))


@router.get("/almanacs/{topic}/learning")
def delivery_learning(topic: str, response: Response,
                      owner: str = Depends(_principal)) -> dict:
    _private(response)
    if not _TOPIC.fullmatch(topic):
        raise HTTPException(status_code=422, detail="Invalid Almanakk topic identity")
    with _delivery() as delivery:
        return _project(lambda: delivery.almanacs.learning_view(
            owner, topic, authorized=True, limit=100
        ))


@router.post("/brief")
def delivery_brief(body: DeliveryBriefRequest, response: Response,
                   owner: str = Depends(_principal)) -> dict:
    _private(response)
    try:
        design = parse_design(body.design)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Unsupported native design controls") from None
    with _delivery() as delivery:
        return _project(lambda: delivery.brief(
            owner, design, body.query, now=_clock(), authorized=True
        ))
