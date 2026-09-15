"""Era catalog API — the technical envelopes a game can be forged within."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core import eras

router = APIRouter(prefix="/api/galaxy-studio/eras", tags=["eras"])


@router.get("")
def list_eras() -> dict:
    return {"count": len(eras.ERA_ORDER), "default": eras.DEFAULT_ERA,
            "eras": eras.catalog()}


@router.get("/{era_key}")
def get_era(era_key: str) -> dict:
    e = eras.get_era(era_key)
    if not e:
        raise HTTPException(404, "unknown era")
    return e
