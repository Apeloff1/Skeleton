"""Public application assembly/bootstrap surface."""
from __future__ import annotations

from fastapi import APIRouter

from skeleton.app.bootstrap import public_bootstrap_payload

router = APIRouter(prefix="/api/app", tags=["application"])


@router.get("/bootstrap")
def app_bootstrap() -> dict[str, object]:
    """Expose the sanitized canonical application contract to clients."""

    return public_bootstrap_payload()
