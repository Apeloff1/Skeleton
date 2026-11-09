"""Backup & restore — point-in-time snapshots of all persistent state.

Captures audit log, event store, feature flags, config, secrets,
RBAC assignments, and schema registry into a single versioned backup
archive. Supports full and incremental backups, integrity checksums,
and restore with dry-run preview.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


STATE_FILES = [
    "audit.jsonl",
    "events.jsonl",
    "snapshots.json",
    "feature_flags.json",
    "skeleton_config.json",
    "secrets.json",
    "rbac.json",
]


class BackupManager:
    """Versioned backup and restore for all Skeleton state."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self.backup_dir = self.root / "backups"
        self._index_file = self.backup_dir / "index.json"
        self._index: List[Dict[str, Any]] = []
        self._load_index()

    def _load_index(self) -> None:
        if self._index_file.exists():
            self._index = json.loads(self._index_file.read_text(encoding="utf-8"))

    def _save_index(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._index_file.write_text(json.dumps(self._index, indent=2), encoding="utf-8")

    def _checksum(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def backup(self, label: str = "", incremental: bool = False) -> Dict[str, Any]:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_id = f"b{len(self._index) + 1:04d}"
        last = self._index[-1] if (incremental and self._index) else None
        captured: Dict[str, str] = {}
        for name in STATE_FILES:
            path = self.root / name
            if not path.exists():
                continue
            data = path.read_text(encoding="utf-8")
            checksum = self._checksum(data)
            if last and last.get("checksums", {}).get(name) == checksum:
                continue
            captured[name] = data
        blob = {
            "backup_id": backup_id,
            "label": label,
            "timestamp_ns": time.time_ns(),
            "incremental": incremental,
            "files": captured,
            "checksums": {n: self._checksum(d) for n, d in captured.items()},
        }
        out = self.backup_dir / f"{backup_id}.json"
        out.write_text(json.dumps(blob, indent=2), encoding="utf-8")
        entry = {
            "backup_id": backup_id,
            "label": label,
            "timestamp_ns": blob["timestamp_ns"],
            "incremental": incremental,
            "files": sorted(captured.keys()),
            "checksums": blob["checksums"],
            "size_bytes": out.stat().st_size,
        }
        self._index.append(entry)
        self._save_index()
        return entry

    def list_backups(self) -> List[Dict[str, Any]]:
        return list(self._index)

    def verify(self, backup_id: str) -> Dict[str, Any]:
        path = self.backup_dir / f"{backup_id}.json"
        if not path.exists():
            return {"backup_id": backup_id, "valid": False, "error": "not found"}
        blob = json.loads(path.read_text(encoding="utf-8"))
        bad = [n for n, d in blob["files"].items() if self._checksum(d) != blob["checksums"].get(n)]
        return {"backup_id": backup_id, "valid": not bad, "corrupted": bad}

    def restore(self, backup_id: str, dry_run: bool = True) -> Dict[str, Any]:
        path = self.backup_dir / f"{backup_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"backup not found: {backup_id}")
        blob = json.loads(path.read_text(encoding="utf-8"))
        plan = {"restored": [], "dry_run": dry_run}
        for name, data in blob["files"].items():
            plan["restored"].append(name)
            if not dry_run:
                self.root.mkdir(parents=True, exist_ok=True)
                (self.root / name).write_text(data, encoding="utf-8")
        return plan

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "backup-card",
            "backups": len(self._index),
            "total_size_bytes": sum(b.get("size_bytes", 0) for b in self._index),
            "latest": self._index[-1] if self._index else None,
        }
