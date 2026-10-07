"""Recurring diagnostics card for operator surfaces."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.quality_state import quality_snapshot


def recurring_card(*, root=None, surface: str = "") -> Dict[str, Any]:
    snap = quality_snapshot(root=root, surface=surface)
    return {"kind": "recurring-card", "surface": surface or "all", "top_issue": (snap.get("failures") or {}).get("top_issue") or "", "top_surface": (snap.get("failures") or {}).get("top_surface") or "", "top_target": (snap.get("repairs") or {}).get("top_target") or "", "repair_surfaces": (snap.get("repairs") or {}).get("surfaces") or {}, "repair_reasons": (snap.get("repairs") or {}).get("reasons") or {}, "stored_prose": 0}
