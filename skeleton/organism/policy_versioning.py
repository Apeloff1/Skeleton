"""Policy versioning and rollback — immutable policy snapshots with lineage.

Provides versioned policy storage, rollback to any prior version,
audit trail, and cross-surface policy inheritance with version
propagation.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.organism.policy_state import default_policy, load_policy, save_policy


def _version_dir(root=None) -> Path:
    from skeleton.organism.paths import organism_dir
    return organism_dir(root) / "policy_versions"


def _version_index_path(root=None) -> Path:
    return _version_dir(root) / "index.jsonl"


def _version_path(version_id: str, root=None) -> Path:
    return _version_dir(root) / f"{version_id}.json"


@dataclass
class PolicyVersion:
    version_id: str
    parent_id: str
    created_at: int
    author: str
    surfaces: List[str]
    comment: str
    policy_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "author": self.author,
            "surfaces": self.surfaces,
            "comment": self.comment,
            "policy_snapshot": self.policy_snapshot,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _make_version_id() -> str:
    import uuid
    return f"pv-{uuid.uuid4().hex[:12]}"


def list_versions(root=None, surface: str = "", limit: int = 32) -> List[Dict[str, Any]]:
    """List policy versions, newest first. Optionally filter by surface."""
    path = _version_index_path(root)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if not surface or surface in row.get("surfaces", []):
                rows.append(row)
        except json.JSONDecodeError:
            continue
    rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return rows[:limit]


def get_version(version_id: str, root=None) -> Optional[Dict[str, Any]]:
    """Load a specific version snapshot."""
    path = _version_path(version_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data


def save_version(
    policy: Optional[Dict[str, Any]] = None,
    *,
    surfaces: Optional[List[str]] = None,
    comment: str = "",
    author: str = "system",
    parent_id: str = "",
    root=None,
) -> str:
    """Snapshot current policy as a new version. Returns version_id."""
    version_id = _make_version_id()
    snapshot = policy if policy is not None else load_policy(root=root)
    surfaces = surfaces or list(snapshot.get("quality_thresholds", {}).keys())
    if not surfaces:
        surfaces = ["global"]
    version = PolicyVersion(
        version_id=version_id,
        parent_id=parent_id,
        created_at=_now_ms(),
        author=author,
        surfaces=surfaces,
        comment=comment,
        policy_snapshot=dict(snapshot),
    )
    vdir = _version_dir(root)
    vdir.mkdir(parents=True, exist_ok=True)
    _version_path(version_id, root).write_text(
        json.dumps(version.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    idx = _version_index_path(root)
    with idx.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(version.to_dict(), sort_keys=True, default=str) + "\n")
    # Trim index
    if idx.exists():
        lines = idx.read_text(encoding="utf-8").splitlines()
        if len(lines) > 256:
            idx.write_text("\n".join(lines[-256:]) + "\n", encoding="utf-8")
    return version_id


def rollback(version_id: str, *, root=None, comment: str = "") -> Dict[str, Any]:
    """Rollback active policy to a saved version. Creates a new version
    pointing to the rolled-back snapshot."""
    target = get_version(version_id, root)
    if target is None:
        return {
            "kind": "policy-rollback",
            "ok": 0,
            "version_id": version_id,
            "reason": "version-not-found",
            "stored_prose": 0,
        }
    snapshot = target.get("policy_snapshot") or {}
    if not snapshot:
        return {
            "kind": "policy-rollback",
            "ok": 0,
            "version_id": version_id,
            "reason": "empty-snapshot",
            "stored_prose": 0,
        }
    save_policy(snapshot, root=root)
    new_id = save_version(
        policy=snapshot,
        surfaces=target.get("surfaces"),
        comment=comment or f"rollback to {version_id}",
        author="rollback",
        parent_id=version_id,
        root=root,
    )
    return {
        "kind": "policy-rollback",
        "ok": 1,
        "version_id": version_id,
        "new_version_id": new_id,
        "surfaces": target.get("surfaces", []),
        "stored_prose": 0,
    }


def diff_versions(a_id: str, b_id: str, root=None) -> Dict[str, Any]:
    """Compute a shallow diff between two policy versions."""
    a = get_version(a_id, root)
    b = get_version(b_id, root)
    if a is None or b is None:
        return {"kind": "policy-diff", "ok": 0, "reason": "version-not-found", "stored_prose": 0}
    a_pol = a.get("policy_snapshot") or {}
    b_pol = b.get("policy_snapshot") or {}
    changed: Dict[str, Any] = {}
    all_keys = set(a_pol.keys()) | set(b_pol.keys())
    for key in sorted(all_keys):
        av = a_pol.get(key)
        bv = b_pol.get(key)
        if av != bv:
            changed[key] = {"before": av, "after": bv}
    return {
        "kind": "policy-diff",
        "ok": 1,
        "version_a": a_id,
        "version_b": b_id,
        "changed_keys": list(changed.keys()),
        "changes": changed,
        "stored_prose": 0,
    }


def version_lineage(version_id: str, root=None, max_depth: int = 8) -> List[str]:
    """Walk parent chain from a version back to root."""
    lineage: List[str] = []
    current = version_id
    for _ in range(max_depth):
        v = get_version(current, root)
        if v is None:
            break
        lineage.append(current)
        parent = v.get("parent_id") or ""
        if not parent:
            break
        current = parent
    return lineage


def inherit_version(
    parent_version_id: str,
    child_surfaces: List[str],
    overrides: Optional[Dict[str, Any]] = None,
    *,
    comment: str = "",
    author: str = "inheritance",
    root=None,
) -> str:
    """Create a child version that inherits from a parent, applying
    overrides only for the specified child surfaces."""
    parent = get_version(parent_version_id, root)
    if parent is None:
        parent_snapshot = load_policy(root=root)
    else:
        parent_snapshot = parent.get("policy_snapshot") or {}
    child_snapshot = dict(parent_snapshot)
    overrides = overrides or {}
    # Apply overrides only to child surfaces
    for section in ("quality_thresholds", "repair_enabled", "repair_classes"):
        child_section = dict(child_snapshot.get(section) or {})
        override_section = overrides.get(section) or {}
        for surf, val in override_section.items():
            if surf in child_surfaces or surf == "global":
                child_section[surf] = val
        if child_section:
            child_snapshot[section] = child_section
    return save_version(
        policy=child_snapshot,
        surfaces=child_surfaces,
        comment=comment or f"inherit from {parent_version_id}",
        author=author,
        parent_id=parent_version_id,
        root=root,
    )


def version_card(root=None, limit: int = 8) -> Dict[str, Any]:
    """Operator card showing version history."""
    versions = list_versions(root=root, limit=limit)
    return {
        "kind": "policy-version-card",
        "total_versions": len(versions),
        "latest": versions[0] if versions else None,
        "versions": versions,
        "stored_prose": 0,
    }


def rollback_by_surface(surface: str, *, root=None, comment: str = "") -> Dict[str, Any]:
    from skeleton.organism.policy_rollback_control import rollback_by_surface as _r
    return _r(surface, root=root, comment=comment)
