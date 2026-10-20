"""Authenticated REST controls for fifty real Forge Studio authoring actions.

Reuses the existing canonical game-learning workspace, scoped owner identity,
versioned project revisions and native game compiler; no second project store.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from core import game_frontier_authoring as studio
from routes.game_learning import Request, WriteRequest, _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-frontier-authoring", tags=["Game Studio authoring"])


class EditorStep(Request):
    action: str = Field(min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict, max_length=32)


class EditorMutation(WriteRequest):
    expected_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    steps: list[EditorStep] = Field(min_length=1, max_length=64)


class TileSelection(Request):
    layer: str = Field(min_length=1, max_length=128)
    x: int = Field(ge=0, le=255, strict=True)
    y: int = Field(ge=0, le=255, strict=True)
    width: int = Field(ge=1, le=256, strict=True)
    height: int = Field(ge=1, le=256, strict=True)


class NativeBuild(Request):
    seed: int = Field(default=42, ge=0, le=2**63 - 1, strict=True)
    islands: int = Field(default=12, ge=3, le=64, strict=True)
    include_godot: bool = False


def _write_scope(user):
    scope = _scope(user)
    if user.get("role") not in {"editor", "admin"}:
        raise HTTPException(403, detail={
            "code": "game_studio_write_denied",
            "message": "Project editor role required for source modification.",
        })
    return scope


@router.get("/actions")
async def actions(user=Depends(get_current_user)):
    _scope(user)
    return studio.catalog()


@router.get("/projects/{project_id}")
async def inspect(project_id: str, user=Depends(get_current_user)):
    return await _call(studio.document(_scope(user), project_id))


@router.post("/projects/{project_id}/tiles/copy")
async def copy_tile_region(project_id: str, body: TileSelection,
                           user=Depends(get_current_user)):
    return await _call(studio.copy_tiles(
        _scope(user), project_id, **body.model_dump()))


@router.post("/projects/{project_id}/edits/preview")
async def preview(project_id: str, body: EditorMutation,
                  user=Depends(get_current_user)):
    return await _call(studio.edit(
        _scope(user), project_id, body.model_dump(), preview=True))


@router.patch("/projects/{project_id}/edits")
async def edit(project_id: str, body: EditorMutation,
               user=Depends(get_current_user)):
    return await _call(studio.edit(
        _write_scope(user), project_id, body.model_dump(), preview=False))


@router.post("/projects/{project_id}/build")
async def build_playable_game(project_id: str, body: NativeBuild,
                              user=Depends(get_current_user)):
    return await _call(studio.compile_game(
        _scope(user), project_id, **body.model_dump()))
