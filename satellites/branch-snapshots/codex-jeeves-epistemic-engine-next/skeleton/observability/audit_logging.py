"""Audit logging — append-only, tamper-evident operator action log.

Every policy change, rollback, repair trigger, and threshold update
is recorded with a chain hash linking entries. Supports export,
query by time range, and integrity verification.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AuditEntry:
    timestamp_ns: int
    actor: str
    action: str
    resource: str
    details: Dict[str, Any]
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        payload = json.dumps({
            "timestamp_ns": self.timestamp_ns,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def seal(self) -> None:
        self.entry_hash = self.compute_hash()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


class AuditLog:
    """Append-only audit log with chain hashing."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._entries: List[AuditEntry] = []
        self._file = self.root / "audit.jsonl"
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            for line in self._file.read_text(encoding="utf-8").strip().splitlines():
                if line.strip():
                    data = json.loads(line)
                    self._entries.append(AuditEntry(
                        timestamp_ns=data["timestamp_ns"],
                        actor=data["actor"],
                        action=data["action"],
                        resource=data["resource"],
                        details=data["details"],
                        prev_hash=data["prev_hash"],
                        entry_hash=data["entry_hash"],
                    ))

    def _save(self, entry: AuditEntry) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), default=str) + "\n")

    def _last_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else "0" * 32

    def record(self, actor: str, action: str, resource: str, details: Optional[Dict[str, Any]] = None) -> AuditEntry:
        entry = AuditEntry(
            timestamp_ns=time.time_ns(),
            actor=actor,
            action=action,
            resource=resource,
            details=details or {},
            prev_hash=self._last_hash(),
        )
        entry.seal()
        self._entries.append(entry)
        self._save(entry)
        return entry

    def query(self, *, actor: Optional[str] = None, action: Optional[str] = None, resource: Optional[str] = None, since_ns: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for e in reversed(self._entries):
            if actor and e.actor != actor:
                continue
            if action and e.action != action:
                continue
            if resource and e.resource != resource:
                continue
            if since_ns and e.timestamp_ns < since_ns:
                continue
            results.append(e.to_dict())
            if len(results) >= limit:
                break
        return results

    def verify_integrity(self) -> Dict[str, Any]:
        broken: List[int] = []
        for i, e in enumerate(self._entries):
            if e.entry_hash != e.compute_hash():
                broken.append(i)
            if i > 0 and e.prev_hash != self._entries[i - 1].entry_hash:
                broken.append(i)
        return {
            "kind": "audit-integrity",
            "total_entries": len(self._entries),
            "broken_indices": broken,
            "intact": len(broken) == 0,
        }

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "audit-card",
            "total_entries": len(self._entries),
            "last_actor": self._entries[-1].actor if self._entries else None,
            "last_action": self._entries[-1].action if self._entries else None,
            "integrity": self.verify_integrity(),
        }
