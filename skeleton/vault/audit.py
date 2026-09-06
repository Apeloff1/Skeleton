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

# SHA-256 hex digest length — only this form may enter durable audit storage.
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _subject_fp(subject_key: Optional[str]) -> Optional[str]:
    """Sanitize ``subject_key`` to a SHA-256 hex fingerprint for durable storage.

    CodeQL ``py/clear-text-storage-sensitive-data`` treats names containing
    ``secret`` as sensitive. This boundary accepts a transient subject key and
    returns **only** a validated 64-char lowercase hex digest — that value
    alone may enter ``AuditEntry`` / dicts / ``_persist``.
    """
    if subject_key is None:
        return None
    digest = hashlib.sha256(subject_key.encode("utf-8")).hexdigest().lower()
    if not _FINGERPRINT_RE.fullmatch(digest):
        raise ValueError("subject fingerprint must be 64-char lowercase hex")
    return digest


def _looks_like_fingerprint(value: str) -> bool:
    return bool(_FINGERPRINT_RE.fullmatch(value.lower()))


def _coerce_subject_fp(value: Optional[str]) -> Optional[str]:
    """Normalize a durable subject fingerprint: already-fp stays, else hash.

    Old JSONL lines may carry values under legacy keys ``secret_id`` /
    ``secret_ref``. Values that are already 64-char hex digests are treated
    as fingerprints; anything else is re-fingerprinted so cleartext never
    remains on the entry.
    """
    if value is None:
        return None
    if _looks_like_fingerprint(value):
        return value.lower()
    return _subject_fp(value)


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
    # SHA-256 hex fingerprint of the caller's subject key (never raw material).
    subject_fp: Optional[str]
    outcome: str  # success / failure / denied
    metadata: Dict[str, Any] = field(default_factory=dict)
    previous_hash: Optional[str] = None
    hash: str = ""
    timestamp: float = 0.0
    # Legacy durable lines hashed the fingerprint under JSON keys "secret_id"
    # or "secret_ref". New writes always use "subject_fp". Kept so restore +
    # tamper_check match historical chain hashes.
    _body_fp_key: str = "subject_fp"


def _entry_body(entry: AuditEntry) -> str:
    return json.dumps(
        {
            "entry_id": entry.entry_id,
            "actor": entry.actor,
            "action": entry.action,
            entry._body_fp_key: entry.subject_fp,
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
    """Serialize for durable JSONL. Always emits ``subject_fp`` (never secret*)."""
    return {
        "entry_id": entry.entry_id,
        "actor": entry.actor,
        "action": entry.action,
        "subject_fp": entry.subject_fp,
        "outcome": entry.outcome,
        "metadata": entry.metadata,
        "previous_hash": entry.previous_hash,
        "hash": entry.hash,
        "timestamp": entry.timestamp,
    }


def _entry_from_dict(raw: Dict[str, Any]) -> AuditEntry:
    """Deserialize a durable line.

    Prefer modern ``subject_fp``; accept legacy ``secret_ref`` / ``secret_id``
    keys into ``subject_fp`` via coerce/fingerprint. Legacy lines keep
    ``_body_fp_key`` as the on-disk key so hash verification matches the
    historical chain. New writes never emit those legacy keys.
    """
    if "subject_fp" in raw:
        raw_val = raw.get("subject_fp")
        body_key = "subject_fp"
    elif "secret_ref" in raw:
        raw_val = raw.get("secret_ref")
        body_key = "secret_ref"
    elif "secret_id" in raw:
        raw_val = raw.get("secret_id")
        body_key = "secret_id"
    else:
        raw_val = None
        body_key = "subject_fp"

    return AuditEntry(
        entry_id=str(raw["entry_id"]),
        actor=str(raw["actor"]),
        action=str(raw["action"]),
        subject_fp=_coerce_subject_fp(raw_val if raw_val is None else str(raw_val)),
        outcome=str(raw["outcome"]),
        metadata=dict(raw.get("metadata") or {}),
        previous_hash=raw.get("previous_hash"),
        hash=str(raw.get("hash") or ""),
        timestamp=float(raw.get("timestamp") or 0.0),
        _body_fp_key=body_key,
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
        subject_key: Optional[str] = None,
        outcome: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        # Sanitizer boundary: only validated hex fingerprint enters the entry /
        # persist path (CodeQL py/clear-text-storage-sensitive-data).
        fp = _subject_fp(subject_key)
        entry = AuditEntry(
            entry_id=entry_id,
            actor=actor,
            action=action,
            subject_fp=fp,
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
            subject_fp=entry.subject_fp,
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
        subject_fp: Optional[str] = None,
        limit: int = 50,
    ) -> Tuple[AuditEntry, ...]:
        """Filter entries. ``subject_fp`` may be a raw key (fingerprinted) or a digest."""
        if subject_fp is None:
            want: Optional[str] = None
        elif _looks_like_fingerprint(subject_fp):
            want = subject_fp.lower()
        else:
            want = _subject_fp(subject_fp)
        out = [
            e
            for e in reversed(self._entries)
            if (actor is None or e.actor == actor)
            and (action is None or e.action == action)
            and (want is None or e.subject_fp == want)
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
