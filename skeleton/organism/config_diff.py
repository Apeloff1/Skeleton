"""Config diff — configuration drift detection and change auditing.

Snapshots configuration state at points in time, diffs any two
snapshots (or live vs snapshot), classifies changes by risk (add /
remove / modify / sensitive-key), and enforces review gates for
high-risk changes. All diffs feed the audit log.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


SENSITIVE_KEYS = {"secret", "password", "token", "key", "credential", "master"}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class Change:
    path: str
    kind: str           # added | removed | modified
    old: Any = None
    new: Any = None
    risk: str = "low"

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "kind": self.kind, "risk": self.risk,
                "old": None if self.risk in ("high", "critical") else self.old,
                "new": None if self.risk in ("high", "critical") else self.new}


@dataclass
class Snapshot:
    snapshot_id: str
    taken_ns: int
    config: Dict[str, Any]
    digest: str


class ConfigDiff:
    """Config snapshotting with risk-classified diffs."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._snapshots: Dict[str, Snapshot] = {}
        self._counter = 0
        self._diff_log: List[Dict[str, Any]] = []

    def _flatten(self, config: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in config.items():
            path = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict):
                out.update(self._flatten(v, path))
            else:
                out[path] = v
        return out

    def _digest(self, config: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def snapshot(self, config: Dict[str, Any]) -> Snapshot:
        self._counter += 1
        snap = Snapshot(
            snapshot_id=f"snap-{self._counter:04d}",
            taken_ns=time.time_ns(),
            config=json.loads(json.dumps(config, default=str)),
            digest=self._digest(config),
        )
        self._snapshots[snap.snapshot_id] = snap
        return snap

    def _is_sensitive(self, path: str) -> bool:
        return any(s in path.lower() for s in SENSITIVE_KEYS)

    def _risk_for(self, path: str, kind: str, old: Any, new: Any) -> str:
        if self._is_sensitive(path):
            return "critical"
        if kind == "removed":
            return "high"
        if kind == "modified" and isinstance(old, (int, float)) and isinstance(new, (int, float)):
            if old != 0 and abs(new - old) / abs(old) > 0.5:
                return "medium"
        if kind == "added":
            return "low"
        return "medium"

    def diff(self, base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
        flat_a = self._flatten(base)
        flat_b = self._flatten(other)
        changes: List[Change] = []
        for path in sorted(set(flat_a) | set(flat_b)):
            in_a, in_b = path in flat_a, path in flat_b
            if in_a and not in_b:
                changes.append(Change(path, "removed", old=flat_a[path], risk=self._risk_for(path, "removed", flat_a[path], None)))
            elif in_b and not in_a:
                changes.append(Change(path, "added", new=flat_b[path], risk=self._risk_for(path, "added", None, flat_b[path])))
            elif flat_a[path] != flat_b[path]:
                changes.append(Change(path, "modified", old=flat_a[path], new=flat_b[path],
                                      risk=self._risk_for(path, "modified", flat_a[path], flat_b[path])))
        max_risk = "low"
        for c in changes:
            if RISK_ORDER[c.risk] > RISK_ORDER[max_risk]:
                max_risk = c.risk
        record = {
            "changes": [c.to_dict() for c in changes],
            "total": len(changes),
            "max_risk": max_risk,
            "requires_review": RISK_ORDER[max_risk] >= RISK_ORDER["high"],
            "timestamp_ns": time.time_ns(),
        }
        self._diff_log.append(record)
        return record

    def diff_snapshots(self, id_a: str, id_b: str) -> Dict[str, Any]:
        a = self._snapshots.get(id_a)
        b = self._snapshots.get(id_b)
        if not a or not b:
            return {"error": "snapshot not found"}
        return self.diff(a.config, b.config)

    def drift(self, snapshot_id: str, live_config: Dict[str, Any]) -> Dict[str, Any]:
        snap = self._snapshots.get(snapshot_id)
        if not snap:
            return {"error": "snapshot not found"}
        result = self.diff(snap.config, live_config)
        result["drifted"] = result["total"] > 0
        return result

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "config-diff-card",
            "snapshots": len(self._snapshots),
            "diffs_run": len(self._diff_log),
            "high_risk_diffs": len([d for d in self._diff_log if d["max_risk"] in ("high", "critical")]),
            "latest": self._diff_log[-1] if self._diff_log else None,
        }
