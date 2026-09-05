"""Policy versioning and rollback — track policy changes over time
and allow reverting to previous states.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.organism.policy_state import load_policy, save_policy


def _versions_path(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "policy_versions.jsonl"


def _snapshot_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Create a version snapshot of the current policy."""
    return {
        "at": int(time.time() * 1000),
        "version": policy.copy(),
    }


def record_version(policy: Dict[str, Any], *, root=None, note: str = "") -> Dict[str, Any]:
    """Record a policy version to the version ledger."""
    path = _versions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _snapshot_policy(policy)
    snapshot["note"] = note
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, sort_keys=True, default=str) + "\n")

    # Trim to last 64 versions
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 64:
            path.write_text("\n".join(lines[-64:]) + "\n", encoding="utf-8")

    return {
        "kind": "version-recorded",
        "at": snapshot["at"],
        "note": note,
        "stored_prose": 0,
    }


def load_versions(root=None, limit: int = 16) -> List[Dict[str, Any]]:
    """Load recent policy versions."""
    path = _versions_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def rollback_to_version(index: int = -1, *, root=None) -> Dict[str, Any]:
    """Rollback to a previous policy version.
    index=-1 means the most recent version, -2 means second most recent, etc."""
    versions = load_versions(root=root, limit=64)
    if not versions:
        return {
            "kind": "rollback-failed",
            "reason": "no versions recorded",
            "stored_prose": 0,
        }

    # Handle negative indexing
    if index < 0:
        target_index = len(versions) + index
    else:
        target_index = index

    if target_index < 0 or target_index >= len(versions):
        return {
            "kind": "rollback-failed",
            "reason": f"version index {index} out of range (have {len(versions)} versions)",
            "stored_prose": 0,
        }

    target = versions[target_index]
    version_data = target.get("version", {})
    if not version_data:
        return {
            "kind": "rollback-failed",
            "reason": "target version has no data",
            "stored_prose": 0,
        }

    # Save current before rollback
    current = load_policy(root=root)
    record_version(current, root=root, note="auto-snapshot-before-rollback")

    # Apply the rollback
    save_policy(version_data, root=root)

    return {
        "kind": "rollback-applied",
        "to_at": target.get("at"),
        "to_note": target.get("note", ""),
        "index": target_index,
        "stored_prose": 0,
    }


def version_card(*, root=None, limit: int = 8) -> Dict[str, Any]:
    """Operator card showing version history."""
    versions = load_versions(root=root, limit=limit)
    return {
        "kind": "policy-version-card",
        "version_count": len(versions),
        "versions": [
            {
                "at": v.get("at"),
                "note": v.get("note", ""),
                "thresholds": v.get("version", {}).get("quality_thresholds", {}),
            }
            for v in versions
        ],
        "stored_prose": 0,
    }


def diff_versions(index_a: int = -2, index_b: int = -1, *, root=None) -> Dict[str, Any]:
    """Show the diff between two policy versions."""
    versions = load_versions(root=root, limit=64)
    if not versions:
        return {"kind": "policy-diff", "error": "no versions", "stored_prose": 0}

    def _resolve_idx(idx):
        if idx < 0:
            return len(versions) + idx
        return idx

    a_idx = _resolve_idx(index_a)
    b_idx = _resolve_idx(index_b)

    if a_idx < 0 or a_idx >= len(versions) or b_idx < 0 or b_idx >= len(versions):
        return {"kind": "policy-diff", "error": "index out of range", "stored_prose": 0}

    a = versions[a_idx].get("version", {})
    b = versions[b_idx].get("version", {})

    # Diff thresholds
    a_thresh = a.get("quality_thresholds", {})
    b_thresh = b.get("quality_thresholds", {})
    all_surfaces = set(a_thresh) | set(b_thresh)
    threshold_diffs = {}
    for s in all_surfaces:
        av = a_thresh.get(s)
        bv = b_thresh.get(s)
        if av != bv:
            threshold_diffs[s] = {"from": av, "to": bv}

    # Diff repair enabled
    a_repair = a.get("repair_enabled", {})
    b_repair = b.get("repair_enabled", {})
    all_repair = set(a_repair) | set(b_repair)
    repair_diffs = {}
    for s in all_repair:
        av = a_repair.get(s)
        bv = b_repair.get(s)
        if av != bv:
            repair_diffs[s] = {"from": av, "to": bv}

    return {
        "kind": "policy-diff",
        "from_index": a_idx,
        "to_index": b_idx,
        "from_at": versions[a_idx].get("at"),
        "to_at": versions[b_idx].get("at"),
        "threshold_changes": threshold_diffs,
        "repair_enabled_changes": repair_diffs,
        "stored_prose": 0,
    }


def auto_version_on_change(*, root=None) -> Dict[str, Any]:
    """Record a version if the policy has changed since the last version."""
    current = load_policy(root=root)
    versions = load_versions(root=root, limit=1)
    if not versions:
        return record_version(current, root=root, note="initial")

    last = versions[-1].get("version", {})
    # Simple comparison: check thresholds and repair_enabled
    current_thresh = json.dumps(current.get("quality_thresholds", {}), sort_keys=True)
    last_thresh = json.dumps(last.get("quality_thresholds", {}), sort_keys=True)
    current_repair = json.dumps(current.get("repair_enabled", {}), sort_keys=True)
    last_repair = json.dumps(last.get("repair_enabled", {}), sort_keys=True)

    if current_thresh != last_thresh or current_repair != last_repair:
        return record_version(current, root=root, note="auto-change-detected")

    return {
        "kind": "version-no-change",
        "stored_prose": 0,
    }
