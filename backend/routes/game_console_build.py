"""Authenticated console build and exact artifact transfer endpoints."""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, Response
from pydantic import Field

from core.game_console_build import (
    build_catalog,
    download_build_artifact,
    register_console_build_handler,
)
from core.game_learning import workspace
from routes.game_learning import Request, User, _call, _scope

router = APIRouter(prefix="/game-learning", tags=["Console builds"])


class ConsoleBuildBody(Request):
    expected_version: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=512)
    target_id: str = Field(min_length=1, max_length=128)
    style_id: str = Field(default="arcade_score_attack", min_length=1, max_length=64)
    optimization: int = Field(default=1, ge=0, le=2, strict=True)
    debug: bool = Field(default=False, strict=True)
    timeout_seconds: int = Field(default=60, ge=5, le=120, strict=True)


register_console_build_handler()


@router.get("/build-catalog")
async def console_build_catalog(user: User):
    _scope(user)
    return await _call(build_catalog())


@router.post("/projects/{project_id}/build")
async def start_console_build(project_id: str, body: ConsoleBuildBody, user: User):
    return {
        "job": await _call(
            workspace.start_job(_scope(user), project_id, "build", body.model_dump(exclude_none=True))
        )
    }


@router.get("/projects/{project_id}/build-artifacts/{artifact_id}")
async def build_artifact(project_id: str, artifact_id: str, user: User):
    name, data, digest = await _call(download_build_artifact(_scope(user), project_id, artifact_id))
    filename = PurePosixPath(name).name
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            "ETag": '"' + digest + '"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
