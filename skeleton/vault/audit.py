"""Vault audit log — immutable, append-only record of every secret operation.

The vault protects secrets; the audit log protects the vault. Every seal,
unseal, rotation, and access request is stamped with actor, timestamp,
outcome, and a hash chain so tampering is detectable.

- AuditEntry: one operation record
- AuditLog: append-only storage with merkle-style chaining
- tamper_check: verifies chain integrity on startup
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import VaultError


class AuditError(VaultError):
    code = "VLT.AUDIT"


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    actor: str
    action: str  # seal / unseal / rotate / access / denied
    secret_id: Optional[str]
    outcome: str  # success / failure / denied
    metadata: Dict[str, Any] = field(default_factory=dict)
    previous_hash: Optional[str] = None
    hash: str = ""
    timestamp: float = 0.0


class AuditLog:
    """Append-only, hash-chained audit log for vault operations."""

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._now = clock or time.time
        self._entries: List[AuditEntry] = []
        self._last_hash: Optional[str] = None

    def append(
        self,
        *,
        entry_id: str,
        actor: str,
        action: str,
        secret_id: Optional[str] = None,
        outcome: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=entry_id,
            actor=actor,
            action=action,
            secret_id=secret_id,
            outcome=outcome,
            metadata=metadata or {},
            previous_hash=self._last_hash,
            timestamp=self._now(),
        )
        # hash the canonical form
        body = json.dumps(
            {
                "entry_id": entry.entry_id,
                "actor": entry.actor,
                "action": entry.action,
                "secret_id": entry.secret_id,
                "outcome": entry.outcome,
                "metadata": entry.metadata,
                "previous_hash": entry.previous_hash,
                "timestamp": entry.timestamp,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        hash_value = hashlib.sha256(body.encode()).hexdigest()
        # rebuild with hash
        entry = AuditEntry(
            entry_id=entry.entry_id,
            actor=entry.actor,
            action=entry.action,
            secret_id=entry.secret_id,
            outcome=entry.outcome,
            metadata=entry.metadata,
            previous_hash=entry.previous_hash,
            hash=hash_value,
            timestamp=entry.timestamp,
        )
        self._entries.append(entry)
        self._last_hash = entry.hash
        return entry

    def tamper_check(self) -> Tuple[bool, int]:
        """Verify chain integrity. Returns (ok, first_bad_index)."""
        prev: Optional[str] = None
        for i, entry in enumerate(self._entries):
            if entry.previous_hash != prev:
                return False, i
            # recompute hash
            body = json.dumps(
                {
                    "entry_id": entry.entry_id,
                    "actor": entry.actor,
                    "action": entry.action,
                    "secret_id": entry.secret_id,
                    "outcome": entry.outcome,
                    "metadata": entry.metadata,
                    "previous_hash": entry.previous_hash,
                    "timestamp": entry.timestamp,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            expected = hashlib.sha256(body.encode()).hexdigest()
            if entry.hash != expected:
                return False, i
            prev = entry.hash
        return True, -1

    def query(
        self,
        *,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        secret_id: Optional[str] = None,
        limit: int = 50,
    ) -> Tuple[AuditEntry, ...]:
        out = [
            e
            for e in reversed(self._entries)
            if (actor is None or e.actor == actor)
            and (action is None or e.action == action)
            and (secret_id is None or e.secret_id == secret_id)
        ]
        return tuple(out[:limit])

    def report(self) -> Dict[str, Any]:
        ok, bad = self.tamper_check()
        return {
            "total_entries": len(self._entries),
            "chain_intact": ok,
            "first_bad_index": bad if not ok else None,
            "by_action": self._count_by("action"),
            "by_outcome": self._count_by("outcome"),
        }

    def _count_by(self, field: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self._entries:
            key = getattr(e, field)
            counts[key] = counts.get(key, 0) + 1
        return counts
