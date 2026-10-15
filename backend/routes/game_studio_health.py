"""Authenticated observed readiness and issued project activity."""

from fastapi import APIRouter, Depends
from core.game_studio_health import readiness
from routes.game_learning import _call, _scope
from routes.gameforge_auth import get_current_user

router = APIRouter(prefix="/game-studio-health", tags=["Studio readiness"])


@router.get("")
async def studio_readiness(user=Depends(get_current_user)):
    return await _call(readiness(_scope(user)))


@router.get("/projects/{project_id}")
async def project_readiness(project_id: str, user=Depends(get_current_user)):
    return await _call(readiness(_scope(user), project_id))
