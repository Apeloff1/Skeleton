"""Authenticated revision-aware authoring for canonical console targets."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from core import game_console_studio as studio
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-console-studio", tags=["Console studio"])


class CreateConsoleProject(Request):
    target_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    seed: int = Field(default=1, ge=0, le=2**63 - 1, strict=True)
    style_id: str = Field(default="arcade_score_attack", min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=512)


class EditConsoleProject(WriteRequest):
    expected_manifest_digest: str = Field(pattern="^[a-f0-9]{64}$")
    edits: list[dict[str, Any]] = Field(min_length=1, max_length=128)


@router.get("/profiles")
async def get_profiles(user=Depends(get_current_user)):
    _scope(user)
    return {"profiles": studio.profiles()}


@router.post("/projects")
async def create_project(body: CreateConsoleProject, user=Depends(get_current_user)):
    return await _call(studio.create(_scope(user), body.model_dump()))


@router.get("/projects/{project_id}/document")
async def get_document(project_id: str, user=Depends(get_current_user)):
    return await _call(studio.document(_scope(user), project_id))


@router.patch("/projects/{project_id}/document")
async def edit_document(project_id: str, body: EditConsoleProject, user=Depends(get_current_user)):
    return await _call(studio.edit(_scope(user), project_id, body.model_dump()))


@router.get("/projects/{project_id}/handoff")
async def get_handoff(project_id: str, user=Depends(get_current_user)):
    return await _call(studio.handoff(_scope(user), project_id))
