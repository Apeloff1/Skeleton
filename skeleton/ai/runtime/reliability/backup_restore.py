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
import os
from pathlib import Path
import tempfile
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

    @staticmethod
    def _atomic_write_text(path: Path, data: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _save_index(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(
            self._index_file,
            json.dumps(self._index, indent=2),
        )

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
        self._atomic_write_text(out, json.dumps(blob, indent=2))
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

    def delete_backup(self, backup_id: str) -> bool:
        """Physically remove one retained backup and its index entry."""
        if not isinstance(backup_id, str) or not backup_id:
            raise ValueError("backup_id must be a non-empty string")
        match = next(
            (item for item in self._index if item.get("backup_id") == backup_id),
            None,
        )
        path = self.backup_dir / f"{backup_id}.json"
        if match is None and not path.exists():
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        self._index = [
            item for item in self._index if item.get("backup_id") != backup_id
        ]
        self._save_index()
        return True

    def purge_file_history(self, state_file: str) -> int:
        """Remove one state file's historical payload from every backup."""
        if state_file not in STATE_FILES:
            raise ValueError("state_file is not a governed backup state file")

        staged: list[tuple[Path, Dict[str, Any], Dict[str, Any]]] = []
        for entry in self._index:
            backup_id = entry.get("backup_id")
            if not isinstance(backup_id, str) or not backup_id:
                raise ValueError("backup index contains invalid backup_id")
            path = self.backup_dir / f"{backup_id}.json"
            if not path.exists():
                continue
            blob = json.loads(path.read_text(encoding="utf-8"))
            files = blob.get("files")
            checksums = blob.get("checksums")
            if not isinstance(files, dict) or not isinstance(checksums, dict):
                raise ValueError(f"backup {backup_id} has invalid payload")
            if state_file not in files:
                continue

            next_blob = dict(blob)
            next_files = dict(files)
            next_checksums = dict(checksums)
            next_files.pop(state_file, None)
            next_checksums.pop(state_file, None)
            next_blob["files"] = next_files
            next_blob["checksums"] = next_checksums

            next_entry = dict(entry)
            next_entry["files"] = sorted(next_files)
            next_entry["checksums"] = next_checksums
            staged.append((path, next_blob, next_entry))

        if not staged:
            return 0

        by_id = {
            item["backup_id"]: item
            for _, _, item in staged
        }
        for path, blob, entry in staged:
            self._atomic_write_text(path, json.dumps(blob, indent=2))
            entry["size_bytes"] = path.stat().st_size

        self._index = [
            by_id.get(item.get("backup_id"), item)
            for item in self._index
        ]
        self._save_index()
        return len(staged)

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
