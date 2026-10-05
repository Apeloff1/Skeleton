"""Forge registry API — active + deferred specialized forges roadmap."""
from __future__ import annotations

from fastapi import APIRouter

from core import forge_registry

router = APIRouter(prefix="/api/galaxy-studio/forges", tags=["forges"])


@router.get("")
def list_forges() -> dict:
    return forge_registry.catalog()
