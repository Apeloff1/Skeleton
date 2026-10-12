"""Authenticated, read-only web projection of the three Dragon hatchlings.

Mount only an application-created canonical DragonThreeHatchlingCoordinator,
not an owner-provided DB path or a model-supplied permission. Fail closed if
the production source authority was not configured.
"""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from routes.dragon_academy import _principal
from routes.gameforge_auth import require_role
from skeleton.ai.game_builder.dragon_three_hatchling_coordinator import (
    DragonThreeHatchlingCoordinator,
)

router = APIRouter(prefix="/api/dragon-research", tags=["Dragon Research"])
_SOURCE = re.compile(r"source-[0-9a-f]{64}\Z")


def install_dragon_research_dashboard(app, coordinator):
    """One-time trusted backend composition. No authority in HTTP payload."""
    if not isinstance(coordinator, DragonThreeHatchlingCoordinator):
        raise TypeError("canonical three-child research coordinator required")
    if getattr(app.state, "dragon_research_dashboard", None) is not None:
        raise ValueError("Dragon dashboard is already configured")
    app.state.dragon_research_dashboard = coordinator


def _runtime(request: Request) -> DragonThreeHatchlingCoordinator:
    runtime = getattr(request.app.state, "dragon_research_dashboard", None)
    if not isinstance(runtime, DragonThreeHatchlingCoordinator):
        raise HTTPException(
            status_code=503,
            detail="Dragon research evidence runtime is not configured",
        )
    return runtime


def _identity(value: str, name: str) -> str:
    if not isinstance(value, str) or not _SOURCE.fullmatch(value):
        raise HTTPException(status_code=422, detail=f"Invalid {name} identity")
    return value


@router.get("/status")
def three_hatchlings_status(
    request: Request,
    article: str = Query(..., min_length=71, max_length=71),
    video: str = Query(..., min_length=71, max_length=71),
    updates: str = Query(..., min_length=71, max_length=71),
    owner: str = Depends(_principal),
) -> dict:
    coordinator = _runtime(request)
    ids = (
        _identity(article, "article"), _identity(video, "video"),
        _identity(updates, "updates"),
    )
    try:
        return coordinator.status(
            owner, article_source_id=ids[0],
            video_source_id=ids[1], update_source_id=ids[2],
            authorized=True,
        )
    except (ValueError, PermissionError, LookupError) as exc:
        # No source-specific secret data, SQL fragments or hidden policy
        # details in the public error envelope.
        raise HTTPException(
            status_code=409, detail="Research evidence not available for these sources"
        ) from None


@router.get("/mother-review")
def mother_three_lane_review(
    request: Request,
    article: str = Query(..., min_length=71, max_length=71),
    video: str = Query(..., min_length=71, max_length=71),
    updates: str = Query(..., min_length=71, max_length=71),
    owner: str = Depends(_principal),
    reviewer=Depends(require_role("editor")),
) -> dict:
    coordinator = _runtime(request)
    ids = (
        _identity(article, "article"), _identity(video, "video"),
        _identity(updates, "updates"),
    )
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
