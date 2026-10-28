"""routes/build_journey.py — Galaxy Studio's single gamified Build Journey.

GET /api/galaxy-studio/journey/{build_id} → the 7-milestone journey, completion
score, XP/rank, badges, the ONE next-best-action, and a shareable card. Derived
from live persisted state so Rolling/Locking/Forging advances it instantly.
"""
from __future__ import annotations

from routes.playable_access import project_router, scoped_database

from fastapi import APIRouter

from core import build_journey as bj

router = project_router(prefix="/api/galaxy-studio/journey", tags=["build-journey"], project_aliases=("build_id",))


@router.get("/{build_id}")
async def journey(build_id: str):
    return await bj.compute(build_id)
