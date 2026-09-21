"""Read-only user-facing product runtime telemetry."""
from __future__ import annotations

from fastapi import APIRouter

from core.product_control_runtime import public_readiness

router = APIRouter(prefix="/api/product", tags=["product"])


@router.get("/readiness")
async def product_readiness() -> dict:
    """Expose canonical action readiness without admin control-plane state."""

    return public_readiness()
