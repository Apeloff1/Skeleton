"""Field catalog card — every SOTA pointer as topic/url/house."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.social.sources import SOTA_POINTERS, catalog


def field_card() -> Dict[str, Any]:
    rows = [dict(p) for p in SOTA_POINTERS]
    houses = sorted({r["house"] for r in rows})
    return {
        "kind": "field",
        "n": len(rows),
        "houses": houses,
        "families": len(catalog()),
        "pointers": rows,
        "stored_prose": 0,
        "law": "cite-do-not-copy",
    }
