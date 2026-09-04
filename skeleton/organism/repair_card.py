"""Repair summary card for operator surfaces."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.quality_state import latest_failure, latest_repair, quality_snapshot


def repair_card(*, root=None) -> Dict[str, Any]:
    snap = quality_snapshot(root=root)
    latest_fix = latest_repair(root=root)
    latest_fail = latest_failure(root=root)
    return {
        "kind": "repair-card",
        "quality": snap.get("rollup") or {},
        "failures": snap.get("failures") or {},
        "repairs": snap.get("repairs") or {},
        "activity": snap.get("activity") or {},
        "latest_failure": {
            "surface": latest_fail.get("surface") or "",
            "reason": latest_fail.get("reason") or "",
            "target": latest_fail.get("weakest_path") or "",
            "issues": (latest_fail.get("evidence") or {}).get("issue_names") or [],
            "top_files": (latest_fail.get("evidence") or {}).get("top_paths") or [],
        },
        "latest_repair": {
            "surface": latest_fix.get("surface") or "",
            "reason": latest_fix.get("reason") or "",
            "changed": (latest_fix.get("metadata") or {}).get("changed", 0),
            "before_reason": (latest_fix.get("metadata") or {}).get("before_reason") or "",
            "after_reason": (latest_fix.get("metadata") or {}).get("after_reason") or "",
            "target": latest_fix.get("weakest_path") or "",
            "targeted_path": (latest_fix.get("evidence") or {}).get("targeted_path") or "",
        },
        "top_target": (snap.get("repairs") or {}).get("top_target") or "",
        "top_issue": (snap.get("failures") or {}).get("top_issue") or "",
        "top_surface": (snap.get("failures") or {}).get("top_surface") or "",
        "stored_prose": 0,
    }
