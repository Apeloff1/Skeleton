"""Activity card for operator diagnostics."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.quality_state import recent_activity


def activity_card(*, root=None, limit: int = 8, surface: str = "", kind: str = "") -> Dict[str, Any]:
    card = recent_activity(root=root, limit=limit, surface=surface, kind=kind)
    return {"kind": "activity-card", "surface": surface or "all", "entry_kind": kind or "all", "n": card.get("n") or 0, "items": card.get("items") or [], "stored_prose": 0}
