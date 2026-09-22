"""Policy rollback control card — operator-facing rollback UI surface.

Wires version commands into the organism product/nervous/doctor cards.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.organism.policy_versioning import (
    diff_versions,
    get_version,
    list_versions,
    rollback,
    version_card,
    version_lineage,
)


def rollback_control_card(
    *,
    root=None,
    show_lineage: bool = True,
    show_diff_latest: bool = True,
    limit: int = 8,
) -> Dict[str, Any]:
    """Rich operator card for rollback control."""
    versions = list_versions(root=root, limit=limit)
    latest = versions[0] if versions else None
    previous = versions[1] if len(versions) > 1 else None
    diff = None
    if show_diff_latest and latest and previous:
        diff = diff_versions(latest["version_id"], previous["version_id"], root=root)
    lineage = None
    if show_lineage and latest:
        lineage = version_lineage(latest["version_id"], root=root)
    return {
        "kind": "rollback-control-card",
        "latest_version": latest,
        "previous_version": previous,
        "version_count": len(versions),
        "diff_latest": diff,
        "lineage": lineage,
        "actions": [
            {"action": "rollback", "params": {"version_id": v["version_id"]}, "label": f"Rollback to {v['version_id'][:16]}"}
            for v in versions[:3]
        ],
        "stored_prose": 0,
    }


def rollback_by_surface(surface: str, *, root=None, comment: str = "") -> Dict[str, Any]:
    """Rollback to the most recent version that touched a specific surface."""
    versions = list_versions(root=root, surface=surface, limit=32)
    if not versions:
        return {
            "kind": "rollback-by-surface",
            "ok": 0,
            "surface": surface,
            "reason": "no-versions-for-surface",
            "stored_prose": 0,
        }
    target = versions[0]
    result = rollback(target["version_id"], root=root, comment=comment or f"surface rollback for {surface}")
    result["surface"] = surface
    return result


def rollback_preview(version_id: str, *, root=None) -> Dict[str, Any]:
    """Preview what would change if we rolled back to a version."""
    target = get_version(version_id, root)
    if target is None:
        return {"kind": "rollback-preview", "ok": 0, "reason": "version-not-found", "stored_prose": 0}
    from skeleton.organism.policy_state import load_policy
    current = load_policy(root=root)
    snapshot = target.get("policy_snapshot") or {}
    changes: Dict[str, Any] = {}
    for key in set(current.keys()) | set(snapshot.keys()):
        cv = current.get(key)
        sv = snapshot.get(key)
        if cv != sv:
            changes[key] = {"current": cv, "would_become": sv}
    return {
        "kind": "rollback-preview",
        "ok": 1,
        "version_id": version_id,
        "version_comment": target.get("comment", ""),
        "changes": changes,
        "change_count": len(changes),
        "stored_prose": 0,
    }
