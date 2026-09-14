"""Quorum-finalized transparency state.

Publication is not finality. A root becomes FINAL only when the local transparency
log is coherent, gossip reports no equivocation/rollback, and enough independent
trusted witness groups attest the exact same root. Finality records are themselves
hash-chained and monotonic; rollback or witness conflict freezes advancement.
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

from core.epistemic_transparency import EpistemicTransparency
from core.file_lease import FileLease
from core.transparency_gossip import TransparencyGossip
from core.transparency_witness import TransparencyWitnessLedger, WitnessQuorum

FINALITY_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FinalityIntegrityError(RuntimeError):
    pass


class FinalityBlocked(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FinalityRecord:
    version: int
    sequence: int
    log_id: str
    tree_size: int
    root_sha256: str
    witness_quorum_sha256: str
    witness_groups: tuple[str, ...]
    finalized_at: str
    previous_sha256: str
    sha256: str


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: str) -> datetime:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("finality timestamp must be timezone-aware")
    return stamp.astimezone(UTC)


def _record_hash(*, sequence: int, log_id: str, tree_size: int, root_sha256: str,
                 witness_quorum_sha256: str, witness_groups: tuple[str, ...],
                 finalized_at: str, previous_sha256: str) -> str:
    return _sha({"version": FINALITY_VERSION, "sequence": sequence, "log_id": log_id,
                 "tree_size": tree_size, "root_sha256": root_sha256,
                 "witness_quorum_sha256": witness_quorum_sha256, "witness_groups": witness_groups,
                 "finalized_at": finalized_at, "previous_sha256": previous_sha256})


class TransparencyFinality:
    def __init__(self, root: str | Path, *, transparency: EpistemicTransparency,
                 gossip: TransparencyGossip, witnesses: TransparencyWitnessLedger) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "transparency-finality.jsonl"
        self._lease = FileLease(self.root / ".transparency-finality.lock")
        self.transparency = transparency; self.gossip = gossip; self.witnesses = witnesses
        with self._lease.acquire():
            if not self.path.exists(): self.path.touch()
            self._load_verified()

    @staticmethod
    def _restore(raw: dict[str, Any]) -> FinalityRecord:
        return FinalityRecord(
            version=int(raw["version"]), sequence=int(raw["sequence"]), log_id=str(raw["log_id"]),
            tree_size=int(raw["tree_size"]), root_sha256=str(raw["root_sha256"]),
            witness_quorum_sha256=str(raw["witness_quorum_sha256"]),
            witness_groups=tuple(str(x) for x in raw.get("witness_groups", ())),
            finalized_at=str(raw["finalized_at"]), previous_sha256=str(raw.get("previous_sha256", "")),
            sha256=str(raw["sha256"]),
        )

    def _load_verified(self) -> tuple[FinalityRecord, ...]:
        try: lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc: raise FinalityIntegrityError("finality ledger unreadable") from exc
        rows: list[FinalityRecord] = []; previous = ""; last_size = -1
        for line in lines:
            if not line.strip(): continue
            try: row = self._restore(json.loads(line))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise FinalityIntegrityError("finality ledger malformed") from exc
            if row.version != FINALITY_VERSION or row.sequence != len(rows) + 1:
                raise FinalityIntegrityError("finality sequence/version mismatch")
            if row.tree_size <= last_size:
                raise FinalityIntegrityError("finality tree size must be strictly monotonic")
            if row.previous_sha256 != previous:
                raise FinalityIntegrityError("finality ancestry mismatch")
            if not _SHA256.fullmatch(row.root_sha256) or not _SHA256.fullmatch(row.witness_quorum_sha256):
                raise FinalityIntegrityError("finality digest malformed")
            try: _parse_time(row.finalized_at)
            except ValueError as exc: raise FinalityIntegrityError("finality timestamp malformed") from exc
            expected = _record_hash(sequence=row.sequence, log_id=row.log_id, tree_size=row.tree_size,
                                    root_sha256=row.root_sha256, witness_quorum_sha256=row.witness_quorum_sha256,
                                    witness_groups=row.witness_groups, finalized_at=row.finalized_at,
                                    previous_sha256=row.previous_sha256)
            if not hmac.compare_digest(expected, row.sha256):
                raise FinalityIntegrityError("finality hash mismatch")
            previous = row.sha256; last_size = row.tree_size; rows.append(row)
        return tuple(rows)

    def _candidate(self, *, now: datetime | None = None) -> tuple[dict[str, Any], WitnessQuorum]:
        transparency = self.transparency.health(); gossip = self.gossip.status()
        if transparency.get("verified") is not True or transparency.get("prefix_aligned") is not True:
            raise FinalityBlocked("transparency state is not internally verified")
        if gossip.get("healthy") is not True:
            raise FinalityBlocked("transparency gossip reports split-view/rollback evidence")
        descriptor = transparency.get("transparency") if isinstance(transparency.get("transparency"), dict) else {}
        log_id = str(descriptor.get("log_id") or ""); tree_size = int(descriptor.get("tree_size", 0) or 0)
        root = str(descriptor.get("root_sha256") or "")
        if not log_id or tree_size < 1 or not _SHA256.fullmatch(root):
            raise FinalityBlocked("no publishable transparency head")
        quorum = self.witnesses.quorum(log_id=log_id, tree_size=tree_size, root_sha256=root, now=now)
        if not quorum.reached or quorum.frozen:
            stale = f", stale_receipts={quorum.stale_receipts}" if quorum.stale_receipts else ""
            raise FinalityBlocked(
                f"trusted witness quorum not reached: groups={quorum.independent_groups}/{quorum.required_groups}{stale}"
            )
        return descriptor, quorum

    def finalize(self, *, finalized_at: str | None = None) -> FinalityRecord:
        stamp = finalized_at or datetime.now(UTC).isoformat()
        try: evaluation_time = _parse_time(stamp)
        except ValueError as exc: raise FinalityBlocked(str(exc)) from exc
        descriptor, quorum = self._candidate(now=evaluation_time)
        with self._lease.acquire():
            rows = self._load_verified(); latest = rows[-1] if rows else None
            size = int(descriptor["tree_size"]); root = str(descriptor["root_sha256"]); log_id = str(descriptor["log_id"])
            if latest is not None:
                if size < latest.tree_size:
                    raise FinalityBlocked("cannot finalize transparency rollback")
                if size == latest.tree_size:
                    if latest.root_sha256 != root:
                        raise FinalityBlocked("conflicting root for already-finalized tree size")
                    return latest
            sequence = len(rows) + 1; previous = latest.sha256 if latest else ""
            digest = _record_hash(sequence=sequence, log_id=log_id, tree_size=size, root_sha256=root,
                                  witness_quorum_sha256=quorum.attestation_sha256,
                                  witness_groups=quorum.groups, finalized_at=stamp, previous_sha256=previous)
            record = FinalityRecord(FINALITY_VERSION, sequence, log_id, size, root,
                                    quorum.attestation_sha256, quorum.groups, stamp, previous, digest)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            return record

    def latest(self) -> FinalityRecord | None:
        with self._lease.acquire(): rows = self._load_verified()
        return rows[-1] if rows else None

    def snapshot(self) -> tuple[FinalityRecord, ...]:
        with self._lease.acquire(): return self._load_verified()

    def status(self) -> dict[str, Any]:
        with self._lease.acquire(): rows = self._load_verified()
        latest = rows[-1] if rows else None
        blocked_reason = ""; candidate_quorum: dict[str, Any] | None = None
        try:
            _, quorum = self._candidate(now=datetime.now(UTC)); candidate_quorum = asdict(quorum)
        except FinalityBlocked as exc:
            blocked_reason = str(exc)
        return {"version": FINALITY_VERSION, "finalized_entries": len(rows),
                "latest": asdict(latest) if latest else None,
                "candidate_quorum": candidate_quorum, "finalizable": candidate_quorum is not None,
                "blocked_reason": blocked_reason, "verified": True,
                "cross_process_locking": True, "lock_backend": self._lease.backend,
                "head_sha256": latest.sha256 if latest else ""}
