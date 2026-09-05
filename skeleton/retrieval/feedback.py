"""Retrieval feedback — close the plane-weight learning loop (BACKLOG F-2).

HTTP stays thin: validate used/all planes, then :meth:`QuadRetriever.observe`.
Pure enough to unit-test without booting the FastAPI app.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from skeleton.kernel.errors import RetrievalFeedbackError
from skeleton.retrieval.plane_weights import PLANES


def _normalize_planes(raw: Sequence[Any], *, field: str) -> List[str]:
    planes = [str(p).strip().lower() for p in raw]
    unknown = sorted({p for p in planes if p not in PLANES})
    if unknown:
        raise RetrievalFeedbackError(
            f"unknown plane(s){' in ' + field if field != 'used_planes' else ''}: {', '.join(unknown)}",
            context={"unknown": unknown, "allowed": list(PLANES), "field": field},
        )
    return planes


def record_plane_feedback(
    quad: Any,
    used_planes: Iterable[Any],
    *,
    all_planes: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Validate plane names and feed them into ``quad.observe``."""
    if used_planes is None:
        raise RetrievalFeedbackError(
            "used_planes is required",
            context={"field": "used_planes"},
        )
    if not isinstance(used_planes, (list, tuple)) or not used_planes:
        raise RetrievalFeedbackError(
            "used_planes must be a non-empty list",
            context={"field": "used_planes", "got": type(used_planes).__name__},
        )
    used = _normalize_planes(list(used_planes), field="used_planes")

    considered = None
    if all_planes is not None:
        if not isinstance(all_planes, (list, tuple)):
            raise RetrievalFeedbackError(
                "all_planes must be a list when provided",
                context={"field": "all_planes"},
            )
        considered = _normalize_planes(list(all_planes), field="all_planes")

    stats = quad.observe(used, all_planes=considered)
    return {"status": "ok", "used_planes": used, "learner": stats}
