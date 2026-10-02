"""Backup & restore — point-in-time snapshots of all persistent state.

Captures audit log, event store, feature flags, config, secrets,
RBAC assignments, and schema registry into a single versioned backup
archive. Supports full and incremental backups, integrity checksums,
and restore with dry-run preview.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
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

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def _save_index(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(self._index_file, self._index)

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
        self._write_json_atomic(out, blob)
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

    @staticmethod
    def _validated_state_name(name: str) -> str:
        if not isinstance(name, str) or name not in STATE_FILES:
            raise ValueError("state name is not backup-managed")
        return name

    def delete_state(self, name: str) -> Dict[str, Any]:
        """Delete live state and purge all historical backup copies.

        Historical backups are preflighted before the live source is touched.
        This makes malformed or missing backup state fail closed instead of
        deleting the source while silently retaining an undeletable copy.
        """
        state_name = self._validated_state_name(name)
        prepared: list[tuple[Path, Dict[str, Any]]] = []

        for entry in self._index:
            backup_id = str(entry.get("backup_id") or "").strip()
            if not backup_id:
                raise RuntimeError("backup index contains invalid backup identity")
            path = self.backup_dir / f"{backup_id}.json"
            if not path.exists():
                raise RuntimeError(f"indexed backup is missing: {backup_id}")
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"indexed backup is unreadable: {backup_id}"
                ) from exc
            if not isinstance(blob, dict):
                raise RuntimeError(f"indexed backup is malformed: {backup_id}")
            files = blob.get("files")
            checksums = blob.get("checksums")
            if not isinstance(files, dict) or not isinstance(checksums, dict):
                raise RuntimeError(f"indexed backup is malformed: {backup_id}")
            updated = dict(blob)
            updated_files = dict(files)
            updated_checksums = dict(checksums)
            updated_files.pop(state_name, None)
            updated_checksums.pop(state_name, None)
            updated["files"] = updated_files
            updated["checksums"] = updated_checksums
            prepared.append((path, updated))

        purged_backups: list[str] = []
        for path, blob in prepared:
            self._write_json_atomic(path, blob)
            purged_backups.append(str(blob["backup_id"]))

        live = self.root / state_name
        live_existed = live.exists()
        if live_existed:
            live.unlink()

        changed_index = False
        for entry in self._index:
            files = list(entry.get("files") or [])
            checksums = dict(entry.get("checksums") or {})
            if state_name in files or state_name in checksums:
                entry["files"] = [item for item in files if item != state_name]
                checksums.pop(state_name, None)
                entry["checksums"] = checksums
                backup_path = self.backup_dir / f"{entry['backup_id']}.json"
                entry["size_bytes"] = backup_path.stat().st_size
                changed_index = True
        if changed_index:
            self._save_index()

        return {
            "state": state_name,
            "live_deleted": live_existed,
            "purged_backups": tuple(purged_backups),
        }

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
