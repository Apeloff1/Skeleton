"""Activity card for operator diagnostics."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.quality_state import recent_activity


def activity_card(*, root=None, limit: int = 8) -> Dict[str, Any]:
    card = recent_activity(root=root, limit=limit)
    return {
        "kind": "activity-card",
        "n": card.get("n") or 0,
        "items": card.get("items") or [],
        "stored_prose": 0,
    }
