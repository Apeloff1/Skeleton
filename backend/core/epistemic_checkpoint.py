"""Hash-chained checkpoints for externally pinnable epistemic state roots.

A proof that carries its own root proves consistency, not trust. Checkpoints provide
an append-only sequence that can be pinned by operators, deployments, or external
auditors. Portable proofs can then be checked against an expected checkpoint hash.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any

from core.file_lease import FileLease

CHECKPOINT_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EpistemicCheckpointIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EpistemicCheckpoint:
    version: int
    sequence: int
    authority_root_sha256: str
    epistemic_root_sha256: str
    observed_at: str
    previous_sha256: str
    sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: str, field: str, *, allow_empty: bool = False) -> str:
    value = str(value or "").lower().strip()
    if allow_empty and not value:
        return ""
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be sha256")
    return value


def _entry_hash(*, sequence: int, authority_root_sha256: str, epistemic_root_sha256: str,
                observed_at: str, previous_sha256: str) -> str:
    return _sha({
        "version": CHECKPOINT_VERSION, "sequence": sequence,
        "authority_root_sha256": authority_root_sha256,
        "epistemic_root_sha256": epistemic_root_sha256,
        "observed_at": observed_at, "previous_sha256": previous_sha256,
    })


class EpistemicCheckpointLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "epistemic-checkpoints.jsonl"
        self._lease = FileLease(self.root / ".epistemic-checkpoints.lock")
        with self._lease.acquire():
            if not self.path.exists():
                self.path.touch()
            self._load_verified()

    @staticmethod
    def _restore(raw: dict[str, Any]) -> EpistemicCheckpoint:
        return EpistemicCheckpoint(
            version=int(raw["version"]), sequence=int(raw["sequence"]),
            authority_root_sha256=str(raw["authority_root_sha256"]),
            epistemic_root_sha256=str(raw["epistemic_root_sha256"]),
            observed_at=str(raw["observed_at"]), previous_sha256=str(raw.get("previous_sha256", "")),
            sha256=str(raw["sha256"]),
        )

    def _load_verified(self) -> tuple[EpistemicCheckpoint, ...]:
        rows: list[EpistemicCheckpoint] = []; previous = ""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise EpistemicCheckpointIntegrityError("checkpoint ledger unreadable") from exc
        for index, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                entry = self._restore(json.loads(line))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise EpistemicCheckpointIntegrityError("checkpoint ledger malformed") from exc
            if entry.version != CHECKPOINT_VERSION or entry.sequence != index:
                raise EpistemicCheckpointIntegrityError("checkpoint sequence/version mismatch")
            try:
                authority = _digest(entry.authority_root_sha256, "authority root")
                epistemic = _digest(entry.epistemic_root_sha256, "epistemic root")
                predecessor = _digest(entry.previous_sha256, "previous", allow_empty=True)
                claimed = _digest(entry.sha256, "checkpoint")
            except ValueError as exc:
                raise EpistemicCheckpointIntegrityError(str(exc)) from exc
            if predecessor != previous:
                raise EpistemicCheckpointIntegrityError("checkpoint ancestry mismatch")
            expected = _entry_hash(sequence=entry.sequence, authority_root_sha256=authority,
                                   epistemic_root_sha256=epistemic, observed_at=entry.observed_at,
                                   previous_sha256=predecessor)
            if not hmac.compare_digest(expected, claimed):
                raise EpistemicCheckpointIntegrityError("checkpoint hash mismatch")
            previous = claimed; rows.append(entry)
        return tuple(rows)

    def record(self, *, authority_root_sha256: str, epistemic_root_sha256: str,
               observed_at: str | None = None) -> EpistemicCheckpoint:
        authority = _digest(authority_root_sha256, "authority root")
        epistemic = _digest(epistemic_root_sha256, "epistemic root")
        stamp = observed_at or datetime.now(UTC).isoformat()
        with self._lease.acquire():
            rows = self._load_verified()
            if rows and rows[-1].authority_root_sha256 == authority and rows[-1].epistemic_root_sha256 == epistemic:
                return rows[-1]
            sequence = len(rows) + 1; previous = rows[-1].sha256 if rows else ""
            digest = _entry_hash(sequence=sequence, authority_root_sha256=authority,
                                 epistemic_root_sha256=epistemic, observed_at=stamp, previous_sha256=previous)
            entry = EpistemicCheckpoint(CHECKPOINT_VERSION, sequence, authority, epistemic, stamp, previous, digest)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            return entry

    def latest(self) -> EpistemicCheckpoint | None:
        with self._lease.acquire():
            rows = self._load_verified()
        return rows[-1] if rows else None

    def snapshot(self) -> tuple[EpistemicCheckpoint, ...]:
        with self._lease.acquire():
            return self._load_verified()

    def health(self) -> dict[str, Any]:
        with self._lease.acquire():
            rows = self._load_verified()
        return {
            "version": CHECKPOINT_VERSION, "entries": len(rows),
            "head_sha256": rows[-1].sha256 if rows else "",
            "authority_root_sha256": rows[-1].authority_root_sha256 if rows else "",
            "epistemic_root_sha256": rows[-1].epistemic_root_sha256 if rows else "",
            "verified": True, "cross_process_locking": True, "lock_backend": self._lease.backend,
        }
