"""Authenticated, read-only web projection of the three Dragon hatchlings.

Mount only an application-created canonical DragonThreeHatchlingCoordinator,
not an owner-provided DB path or a model-supplied permission. Fail closed if
the production source authority was not configured.
"""
from __future__ import annotations

from contextlib import contextmanager
import re
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from routes.dragon_academy import _principal
from routes.gameforge_auth import require_role
from core.dragon_research_session import DragonResearchSessionFactory
from skeleton.ai.game_builder.dragon_three_hatchling_coordinator import (
    DragonThreeHatchlingCoordinator,
)

router = APIRouter(prefix="/api/dragon-research", tags=["Dragon Research"])
_SOURCE = re.compile(r"source-[0-9a-f]{64}\Z")


def install_dragon_research_dashboard(app, coordinator):
    """One-time trusted backend composition. No authority in HTTP payload."""
    if not isinstance(coordinator, (DragonThreeHatchlingCoordinator,DragonResearchSessionFactory)):
        raise TypeError("trusted three-child research session authority required")
    if getattr(app.state, "dragon_research_dashboard", None) is not None:
        raise ValueError("Dragon dashboard is already configured")
    app.state.dragon_research_dashboard = coordinator


@contextmanager
def _runtime(request: Request):
    runtime = getattr(request.app.state, "dragon_research_dashboard", None)
    if isinstance(runtime, DragonThreeHatchlingCoordinator):
        yield runtime
    elif isinstance(runtime, DragonResearchSessionFactory):
        try:
            with runtime.open() as coordinator:
                yield coordinator
        except (sqlite3.DatabaseError, OSError, ValueError, PermissionError):
            raise HTTPException(
                status_code=409, detail="Dragon research storage verification failed"
            ) from None
    else:
        raise HTTPException(
            status_code=503,
            detail="Dragon research evidence runtime is not configured",
        )


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SOURCE.fullmatch(value):
        raise HTTPException(status_code=422, detail=f"Invalid {name} identity")
    return value


@router.get("/sources")
def source_catalog(
    request: Request,
    response: Response,
    limit: int = Query(30, ge=1, le=60),
    after_source: str | None = Query(None, min_length=71, max_length=71),
    owner: str = Depends(_principal),
) -> dict:
    if after_source is not None:
        _identity(after_source, "source cursor")
    response.headers["Cache-Control"] = "private, no-store"
    with _runtime(request) as coordinator:
        try:
            return coordinator.source_catalog(
                owner, authorized=True, limit=limit, after_source=after_source,
            )
        except (ValueError, PermissionError, LookupError):
            raise HTTPException(
                status_code=409,
                detail="Research source index cannot be verified",
            ) from None


@router.get("/workboard")
def research_workboard(
    request: Request,
    response: Response,
    limit: int = Query(30, ge=1, le=60),
    after_source: str | None = Query(None, min_length=71, max_length=71),
    owner: str = Depends(_principal),
) -> dict:
    """Bounded, source-backed needs for article, video and update hatchlings."""
    if after_source is not None:
        _identity(after_source, "source cursor")
    response.headers["Cache-Control"] = "private, no-store"
    with _runtime(request) as coordinator:
        try:
            return coordinator.workboard(
                owner,authorized=True,limit=limit,after_source=after_source)
        except (ValueError, PermissionError, LookupError):
            raise HTTPException(
                status_code=409,
                detail="Research workboard integrity verification failed",
            ) from None


@router.get("/task-plan")
def game_task_research_plan(
    request: Request,
    response: Response,
    task: str = Query(..., min_length=3, max_length=160),
    max_sources: int = Query(300, ge=1, le=300),
    limit: int = Query(12, ge=1, le=18),
    owner: str = Depends(_principal),
) -> dict:
    """Suggest owner-scoped research, never approve or dispatch a worker."""
    terms=tuple(t for t in re.split(r"[,\s]+",task.strip()) if t)
    from skeleton.ai.game_builder.dragon_task_research_planner import (
        DragonTaskResearchPlanner,
    )
    try:
        DragonTaskResearchPlanner._terms(terms)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="One to eight unique lowercase game task terms required",
        ) from None
    response.headers["Cache-Control"]="private, no-store"
    with _runtime(request) as coordinator:
        try:
            return coordinator.task_research_plan(
                owner, authorized=True, task_terms=terms,
                max_sources=max_sources, limit=limit,
            )
        except (ValueError, PermissionError, LookupError):
            raise HTTPException(
                status_code=409,detail="Dragon task research evidence cannot be verified",
            ) from None


@router.get("/status")
def three_hatchlings_status(
    request: Request,
    response: Response,
    article: str = Query(..., min_length=71, max_length=71),
    video: str = Query(..., min_length=71, max_length=71),
    updates: str = Query(..., min_length=71, max_length=71),
    owner: str = Depends(_principal),
) -> dict:
    ids = (
        _identity(article, "article"), _identity(video, "video"),
        _identity(updates, "updates"),
    )
    response.headers["Cache-Control"] = "private, no-store"
    with _runtime(request) as coordinator:
        try:
            return coordinator.status(
                owner, article_source_id=ids[0],
                video_source_id=ids[1], update_source_id=ids[2],
                authorized=True,
            )
        except (ValueError, PermissionError, LookupError):
            raise HTTPException(
                status_code=409, detail="Research evidence not available for these sources"
            ) from None


@router.get("/history")
def family_research_history(
    request: Request,
    response: Response,
    article: str = Query(..., min_length=71, max_length=71),
    video: str = Query(..., min_length=71, max_length=71),
    updates: str = Query(..., min_length=71, max_length=71),
    limit: int = Query(40, ge=1, le=100),
    owner: str = Depends(_principal),
) -> dict:
    """Show verified historical changes with digests, never raw article text."""
    source_ids=(
        _identity(article,"article"),_identity(video,"video"),
        _identity(updates,"updates"),
    )
    response.headers["Cache-Control"]="private, no-store"
    with _runtime(request) as coordinator:
        try:
            return coordinator.family_history(
                owner,article_source_id=source_ids[0],
                video_source_id=source_ids[1],
                update_source_id=source_ids[2],
                authorized=True,limit=limit,
            )
        except (ValueError,PermissionError,LookupError):
            raise HTTPException(
                status_code=409,detail="Dragon historical custody verification failed"
            ) from None


@router.get("/mother-review")
def mother_three_lane_review(
    request: Request,
    response: Response,
    article: str = Query(..., min_length=71, max_length=71),
    video: str = Query(..., min_length=71, max_length=71),
    updates: str = Query(..., min_length=71, max_length=71),
    owner: str = Depends(_principal),
    reviewer=Depends(require_role("editor")),
) -> dict:
    ids = (
        _identity(article, "article"), _identity(video, "video"),
        _identity(updates, "updates"),
    )
    response.headers["Cache-Control"] = "private, no-store"
    with _runtime(request) as coordinator:
        try:
            return coordinator.mother_review(
                owner, article_source_id=ids[0],
                video_source_id=ids[1], update_source_id=ids[2],
                authorized=True,
            )
        except (ValueError, PermissionError, LookupError):
            raise HTTPException(
                status_code=409, detail="Research evidence not available for these sources"
            ) from None
