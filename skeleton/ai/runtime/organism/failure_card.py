"""Failure card for operator diagnostics."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.quality_state import latest_failure, quality_snapshot


def failure_card(*, root=None, surface: str = "") -> Dict[str, Any]:
    snap = quality_snapshot(root=root, surface=surface)
    latest = latest_failure(root=root, surface=surface)
    return {"kind": "failure-card", "surface": surface or "all", "latest": latest, "top_issue": (snap.get("failures") or {}).get("top_issue") or "", "top_surface": (snap.get("failures") or {}).get("top_surface") or "", "count": (snap.get("failures") or {}).get("count") or 0, "stored_prose": 0}
