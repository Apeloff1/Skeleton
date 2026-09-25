"""Retrieval feedback — close the plane-weight learning loop (BACKLOG F-2).

HTTP stays thin: validate used/all planes, then QuadRetriever.observe.
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
    return list(dict.fromkeys(planes))


def record_plane_feedback(
    quad: Any,
    used_planes: Iterable[Any],
    *,
    all_planes: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Validate plane names and feed them into quad.observe."""
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
        if not isinstance(all_planes, (list, tuple)) or not all_planes:
            raise RetrievalFeedbackError(
                "all_planes must be a non-empty list when provided",
                context={"field": "all_planes"},
            )
        considered = _normalize_planes(list(all_planes), field="all_planes")
        missing = sorted(set(used) - set(considered))
        if missing:
            raise RetrievalFeedbackError(
                "used_planes must be a subset of all_planes",
                context={
                    "field": "all_planes",
                    "missing": missing,
                    "used_planes": used,
                    "all_planes": considered,
                },
            )

    stats = quad.observe(used, all_planes=considered)
    return {"status": "ok", "used_planes": used, "learner": stats}


def record_attributed_feedback(
    quad: Any,
    receipt_id: str,
    used_fragment_ids: Iterable[Any],
) -> Dict[str, Any]:
    """Apply feedback to one concrete retrieval receipt exactly once."""
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise RetrievalFeedbackError(
            "receipt_id must be a non-empty string",
            context={"field": "receipt_id"},
        )
    if isinstance(used_fragment_ids, (str, bytes)) or not isinstance(
        used_fragment_ids, (list, tuple)
    ):
        raise RetrievalFeedbackError(
            "used_fragment_ids must be a list",
            context={"field": "used_fragment_ids"},
        )
    if any(not isinstance(item, str) or not item for item in used_fragment_ids):
        raise RetrievalFeedbackError(
            "used_fragment_ids must contain non-empty strings",
            context={"field": "used_fragment_ids"},
        )

    try:
        stats = quad.observe_receipt(receipt_id.strip(), list(used_fragment_ids))
    except (KeyError, ValueError, TypeError) as exc:
        raise RetrievalFeedbackError(
            str(exc),
            context={
                "field": "receipt_id",
                "receipt_id": receipt_id.strip(),
            },
        ) from exc

    return {
        "status": "ok",
        "receipt_id": receipt_id.strip(),
        "used_fragment_ids": list(dict.fromkeys(used_fragment_ids)),
        "learner": stats,
    }
