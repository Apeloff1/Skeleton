"""Legacy Academy compatibility routes owned by the v3 implementation.

The old ``routes.academy`` module exposed one route that was not carried into
``routes.academy_v3`` when v3 became the canonical Academy router:

    GET /api/academy/topic/{topic_id}/module/{module_id}

Keep that public contract without mounting the retired v2 router (which would
otherwise duplicate the rest of the ``/api/academy`` surface).
"""
from __future__ import annotations

from fastapi import APIRouter

from routes.academy_v3 import get_bible_section

router = APIRouter(prefix="/api/academy", tags=["academy", "legacy-compat"])


@router.get(
    "/topic/{topic_id}/module/{module_id}",
    deprecated=True,
    summary="Legacy Academy topic module compatibility",
)
async def get_topic_module_compat(topic_id: str, module_id: str):
    """Map the v2 topic/module contract onto the canonical v3 bible/section data.

    The response keeps the v2 envelope (``module`` + ``topic_name``) so old
    clients do not need to understand the v3 naming transition.
    """
    result = await get_bible_section(topic_id, module_id)
    return {
        "module": result["section"],
        "topic_name": result.get("bible_name", ""),
    }


__all__ = ["router", "get_topic_module_compat"]
