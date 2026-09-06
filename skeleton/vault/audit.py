"""Vault audit log — immutable, append-only record of every secret operation.

The vault protects secrets; the audit log protects the vault. Every seal,
unseal, rotation, and access request is stamped with actor, timestamp,
outcome, and a hash chain so tampering is detectable.

Sibling of Zaibatsu.Gate ``WormAuditLog`` (gameforge-middleware): durable
JSONL WORM ledger with restore-on-open that **refuses to start** when the
hash chain is broken or unreadable (fail closed).

- AuditEntry: one operation record
- AuditLog: append-only storage with merkle-style chaining (+ optional path)
- tamper_check: verifies chain integrity
- verify_chain_or_refuse: fail-closed boot gate (raises AuditChainBroken)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from skeleton.kernel.errors import Severity, VaultError

PathLike = Union[str, Path]

# Default durable ledger path (override with SKELETON_WORM_AUDIT_PATH).
DEFAULT_WORM_AUDIT_PATH = "data/vault/worm_audit.jsonl"

# SHA-256 hex digest length.
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _secret_ref(secret_id: Optional[str]) -> Optional[str]:
    """Return a SHA-256 fingerprint of ``secret_id`` for durable audit storage.

    Raw secret identifiers must never enter the audit entry / hash chain /
    persist path; only this fingerprint is stored on ``AuditEntry.secret_ref``.
    """
    if secret_id is None:
        return None
    return hashlib.sha256(secret_id.encode("utf-8")).hexdigest()


def _looks_like_fingerprint(value: str) -> bool:
    return bool(_FINGERPRINT_RE.fullmatch(value.lower()))


def _coerce_secret_ref(value: Optional[str]) -> Optional[str]:
    """Normalize a durable secret reference: already-ref stays, else fingerprint.

    Old JSONL lines may carry cleartext under the legacy ``secret_id`` key.
    Values that are already 64-char hex digests are treated as fingerprints;
    anything else is re-fingerprinted so cleartext never remains on the entry.
    """
    if value is None:
        return None
    if _looks_like_fingerprint(value):
        return value.lower()
    return _secret_ref(value)


class AuditError(VaultError):
    code = "VLT.AUDIT"


class AuditChainBroken(AuditError):
    """Hash-chained WORM audit ledger failed verification — refuse boot."""

    code = "VLT.AUDIT_CHAIN_BROKEN"
    severity = Severity.CRITICAL
    http_status = 503


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    actor: str
    action: str  # seal / unseal / rotate / access / denied
    # SHA-256 fingerprint of the caller's secret id (never raw secret material).
    secret_ref: Optional[str]
    outcome: str  # success / failure / denied
    metadata: Dict[str, Any] = field(default_factory=dict)
    previous_hash: Optional[str] = None
    hash: str = ""
    timestamp: float = 0.0
    # Legacy durable lines hashed the fingerprint under JSON key "secret_id".
    # New writes always use "secret_ref". Kept so restore + tamper_check match.
    _body_secret_key: str = "secret_ref"


def _entry_body(entry: AuditEntry) -> str:
    return json.dumps(
        {
            "entry_id": entry.entry_id,
            "actor": entry.actor,
            "action": entry.action,
            entry._body_secret_key: entry.secret_ref,
            "outcome": entry.outcome,
            "metadata": entry.metadata,
            "previous_hash": entry.previous_hash,
            "timestamp": entry.timestamp,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _compute_hash(entry: AuditEntry) -> str:
    return hashlib.sha256(_entry_body(entry).encode()).hexdigest()


def _entry_to_dict(entry: AuditEntry) -> Dict[str, Any]:
    """Serialize for durable JSONL. Always emits ``secret_ref`` (never ``secret_id``)."""
    return {
        "entry_id": entry.entry_id,
        "actor": entry.actor,
        "action": entry.action,
        "secret_ref": entry.secret_ref,
        "outcome": entry.outcome,
        "metadata": entry.metadata,
        "previous_hash": entry.previous_hash,
        "hash": entry.hash,
        "timestamp": entry.timestamp,
    }


def _entry_from_dict(raw: Dict[str, Any]) -> AuditEntry:
    """Deserialize a durable line.

    Accepts modern ``secret_ref`` or legacy ``secret_id`` keys. Non-fingerprint
    values are re-fingerprinted. Legacy lines keep ``_body_secret_key="secret_id"``
    so hash verification matches the on-disk chain (value must already have been
    a fingerprint, or cleartext→fingerprint will fail closed — correct for WORM).
    """
    if "secret_ref" in raw:
        raw_val = raw.get("secret_ref")
        body_key = "secret_ref"
    elif "secret_id" in raw:
        raw_val = raw.get("secret_id")
        body_key = "secret_id"
    else:
        raw_val = None
        body_key = "secret_ref"

    return AuditEntry(
        entry_id=str(raw["entry_id"]),
        actor=str(raw["actor"]),
        action=str(raw["action"]),
        secret_ref=_coerce_secret_ref(raw_val if raw_val is None else str(raw_val)),
        outcome=str(raw["outcome"]),
        metadata=dict(raw.get("metadata") or {}),
        previous_hash=raw.get("previous_hash"),
        hash=str(raw.get("hash") or ""),
        timestamp=float(raw.get("timestamp") or 0.0),
        _body_secret_key=body_key,
    )


def verify_chain_or_refuse(log: "AuditLog") -> None:
    """Fail closed: raise ``AuditChainBroken`` if the WORM chain is not intact.

    Call from genesis/boot/vault open — never continue open when verification
    fails (sibling of Gate ``WormAuditLog.RestoreChain``).
    """
    ok, bad = log.tamper_check()
    if not ok:
        raise AuditChainBroken(
            f"WORM audit chain broken at index {bad} — refusing to start",
            context={"first_bad_index": bad, "path": str(log.path) if log.path else None},
        )


class AuditLog:
    """Append-only, hash-chained audit log for vault operations.

    When ``path`` is set, entries are persisted as JSONL (WORM) and the chain
    is restored + verified on open. A broken or unreadable ledger refuses boot.
    """

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
        path: Optional[PathLike] = None,
        restore: bool = True,
    ) -> None:
        self._now = clock or time.time
        self._entries: List[AuditEntry] = []
        self._last_hash: Optional[str] = None
        self._path: Optional[Path] = Path(path) if path is not None else None
        if self._path is not None and restore:
            self._restore_chain()

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @classmethod
    def open(cls, path: PathLike, *, clock: Optional[Callable[[], float]] = None) -> "AuditLog":
        """Open a durable WORM audit ledger; refuse if the chain is broken."""
        return cls(path=path, clock=clock, restore=True)

    @classmethod
    def open_default(cls, *, clock: Optional[Callable[[], float]] = None) -> "AuditLog":
        """Open via ``SKELETON_WORM_AUDIT_PATH`` or :data:`DEFAULT_WORM_AUDIT_PATH`."""
        path = os.environ.get("SKELETON_WORM_AUDIT_PATH", DEFAULT_WORM_AUDIT_PATH)
        return cls.open(path, clock=clock)

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
        # Fingerprint immediately into a local that never shares the secret_id name
        # on the entry / persist path (CodeQL py/clear-text-storage-sensitive-data).
        ref = _secret_ref(secret_id)
        entry = AuditEntry(
            entry_id=entry_id,
            actor=actor,
            action=action,
            secret_ref=ref,
            outcome=outcome,
            metadata=metadata or {},
            previous_hash=self._last_hash,
            timestamp=self._now(),
        )
        hash_value = _compute_hash(entry)
        entry = AuditEntry(
            entry_id=entry.entry_id,
            actor=entry.actor,
            action=entry.action,
            secret_ref=entry.secret_ref,
            outcome=entry.outcome,
            metadata=entry.metadata,
            previous_hash=entry.previous_hash,
            hash=hash_value,
            timestamp=entry.timestamp,
        )
        self._entries.append(entry)
        self._last_hash = entry.hash
        if self._path is not None:
            self._persist(entry)
        return entry

    def tamper_check(self) -> Tuple[bool, int]:
        """Verify chain integrity. Returns (ok, first_bad_index)."""
        prev: Optional[str] = None
        for i, entry in enumerate(self._entries):
            if entry.previous_hash != prev:
                return False, i
            if entry.hash != _compute_hash(entry):
                return False, i
            prev = entry.hash
        return True, -1

    def verify_chain_or_refuse(self) -> None:
        """Instance form of :func:`verify_chain_or_refuse`."""
        verify_chain_or_refuse(self)

    def query(
        self,
        *,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        secret_ref: Optional[str] = None,
        limit: int = 50,
    ) -> Tuple[AuditEntry, ...]:
        """Filter entries. ``secret_ref`` may be a raw id (fingerprinted) or a digest."""
        if secret_ref is None:
            want: Optional[str] = None
        elif _looks_like_fingerprint(secret_ref):
            want = secret_ref.lower()
        else:
            want = _secret_ref(secret_ref)
        out = [
            e
            for e in reversed(self._entries)
            if (actor is None or e.actor == actor)
            and (action is None or e.action == action)
            and (want is None or e.secret_ref == want)
        ]
        return tuple(out[:limit])

    def report(self) -> Dict[str, Any]:
        ok, bad = self.tamper_check()
        return {
            "total_entries": len(self._entries),
            "chain_intact": ok,
            "first_bad_index": bad if not ok else None,
            "path": str(self._path) if self._path else None,
            "by_action": self._count_by("action"),
            "by_outcome": self._count_by("outcome"),
        }

    def __len__(self) -> int:
        return len(self._entries)

    def _count_by(self, field_name: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self._entries:
            key = getattr(e, field_name)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _restore_chain(self) -> None:
        """Re-read the durable ledger. Broken/unreadable → refuse to start."""
        assert self._path is not None
        if not self._path.exists():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AuditChainBroken(
                "WORM audit chain unreadable — refusing to start",
                context={"path": str(self._path), "error": str(exc)},
                cause=exc,
            ) from exc

        prev: Optional[str] = None
        for line_no, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                entry = _entry_from_dict(raw)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise AuditChainBroken(
                    f"WORM audit chain unreadable at line {line_no} — refusing to start",
                    context={"path": str(self._path), "line": line_no},
                    cause=exc,
                ) from exc
            if entry.previous_hash != prev or entry.hash != _compute_hash(entry):
                raise AuditChainBroken(
                    f"WORM audit chain broken at index {len(self._entries)} — refusing to start",
                    context={
                        "path": str(self._path),
                        "first_bad_index": len(self._entries),
                        "line": line_no,
                    },
                )
            self._entries.append(entry)
            prev = entry.hash
            self._last_hash = entry.hash

    def _persist(self, entry: AuditEntry) -> None:
        assert self._path is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(_entry_to_dict(entry), sort_keys=True, separators=(",", ":")) + "\n"
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
