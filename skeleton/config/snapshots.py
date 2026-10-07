"""
Skeleton Config — Snapshots and layered settings

Provides:
- SettingsSnapshotBridge: Save/restore configuration snapshots
- ConfigSnapshot: Immutable point-in-time config capture
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ConfigSnapshot:
    """Immutable point-in-time configuration capture."""
    name: str
    timestamp: float
    data: Dict[str, Any]
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "source": self.source,
            "keys": list(self.data.keys()),
        }

    def get(self, path: str, default: Any = None) -> Any:
        """Get a value by dotted path."""
        keys = path.split(".")
        value: Any = self.data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


class SettingsSnapshotBridge:
    """Save and restore configuration snapshots for rollback safety."""

    def __init__(self, storage_path: Optional[Path] = None):
        self._storage = storage_path or Path(".skeleton/snapshots")
        self._snapshots: List[ConfigSnapshot] = []
        self._storage.mkdir(parents=True, exist_ok=True)

    def capture(self, name: str, data: Dict[str, Any], source: str = "runtime") -> ConfigSnapshot:
        """Capture a new configuration snapshot."""
        snapshot = ConfigSnapshot(
            name=name,
            timestamp=time.time(),
            data=dict(data),
            source=source,
        )
        self._snapshots.append(snapshot)
        self._persist(snapshot)
        return snapshot

    def _persist(self, snapshot: ConfigSnapshot) -> None:
        """Save snapshot to disk."""
        filename = f"{snapshot.name}_{int(snapshot.timestamp)}.json"
        filepath = self._storage / filename
        try:
            with open(filepath, "w") as f:
                json.dump({
                    "name": snapshot.name,
                    "timestamp": snapshot.timestamp,
                    "source": snapshot.source,
                    "data": snapshot.data,
                }, f, indent=2, default=str)
        except Exception:
            pass  # Best-effort persistence

    def restore(self, name: str) -> Optional[ConfigSnapshot]:
        """Find the most recent snapshot by name."""
        matches = [s for s in self._snapshots if s.name == name]
        return max(matches, key=lambda s: s.timestamp) if matches else None

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """List all captured snapshots."""
        return [s.to_dict() for s in self._snapshots]

    def diff(self, a_name: str, b_name: str) -> Dict[str, Any]:
        """Compute diff between two snapshots."""
        a = self.restore(a_name)
        b = self.restore(b_name)
        if not a or not b:
            return {"error": "One or both snapshots not found"}

        added = {k: b.data[k] for k in b.data if k not in a.data}
        removed = {k: a.data[k] for k in a.data if k not in b.data}
        changed = {}
        for k in a.data:
            if k in b.data and a.data[k] != b.data[k]:
                changed[k] = {"from": a.data[k], "to": b.data[k]}

        return {"added": added, "removed": removed, "changed": changed}

    def stats(self) -> Dict[str, Any]:
        return {"snapshots": len(self._snapshots), "storage": str(self._storage)}
