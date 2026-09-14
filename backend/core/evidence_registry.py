"""Durable evidence registry for empirical verification.

Tracks evidence provenance, independence groups, freshness and retraction status.
The registry does not decide truth; it provides the verifier with auditable source
state and prevents retracted/stale/duplicate evidence from counting as independent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from core.file_lease import FileLease
from core.truth_verifier import EvidenceItem, EvidenceKind


REGISTRY_VERSION = 1


class EvidenceRegistryIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    id: str
    claim: str
    item: EvidenceItem
    registered_at: str
    retracted: bool = False
    retraction_reason: str = ""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class EvidenceRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "evidence-registry.json"
        self._lease = FileLease(self.root / ".evidence.lock")
        with self._lease.acquire():
            if not self.path.exists(): self._write({})
            else: self._load()

    @staticmethod
    def _checksum(records: dict[str, dict[str, Any]]) -> str:
        return _digest({"version": REGISTRY_VERSION, "records": records})

    def _load(self) -> dict[str, dict[str, Any]]:
        try: envelope = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise EvidenceRegistryIntegrityError("evidence registry unreadable") from exc
        if envelope.get("version") != REGISTRY_VERSION: raise EvidenceRegistryIntegrityError("unsupported evidence registry version")
        records = envelope.get("records"); checksum = envelope.get("sha256")
        if not isinstance(records, dict) or not isinstance(checksum, str): raise EvidenceRegistryIntegrityError("evidence registry malformed")
        if not hmac.compare_digest(checksum, self._checksum(records)): raise EvidenceRegistryIntegrityError("evidence registry checksum mismatch")
        return {str(k): dict(v) for k, v in records.items() if isinstance(v, dict)}

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        envelope = {"version": REGISTRY_VERSION, "records": records, "sha256": self._checksum(records)}
        temp = self.path.with_suffix(f".{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(_canonical(envelope)); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    @staticmethod
    def _serialize_item(item: EvidenceItem) -> dict[str, Any]:
        raw = asdict(item); raw["kind"] = item.kind.value; return raw

    @staticmethod
    def _restore(raw: dict[str, Any]) -> EvidenceRecord:
        item_raw = dict(raw["item"]); item_raw["kind"] = EvidenceKind(item_raw["kind"])
        return EvidenceRecord(
            id=str(raw["id"]), claim=str(raw["claim"]), item=EvidenceItem(**item_raw),
            registered_at=str(raw["registered_at"]), retracted=bool(raw.get("retracted", False)),
            retraction_reason=str(raw.get("retraction_reason", "")),
        )

    def register(self, claim: str, item: EvidenceItem, *, registered_at: str | None = None) -> EvidenceRecord:
        claim = " ".join(str(claim).split()).strip()
        if not claim: raise ValueError("claim cannot be blank")
        stamp = registered_at or datetime.now(UTC).isoformat()
        identity = {
            "claim": claim,
            "source_id": item.source_id,
            "locator": item.locator,
            "kind": item.kind.value,
            "independence_group": item.independence_group,
            "observed_at": item.observed_at,
        }
        record_id = _digest(identity)[:24]
        record = EvidenceRecord(record_id, claim, item, stamp)
        serialized = {
            "id": record.id, "claim": record.claim, "item": self._serialize_item(record.item),
            "registered_at": record.registered_at, "retracted": record.retracted,
            "retraction_reason": record.retraction_reason,
        }
        with self._lease.acquire():
            records = self._load(); existing = records.get(record_id)
            if existing is not None:
                return self._restore(existing)
            records[record_id] = serialized; self._write(records)
        return record

    def retract(self, record_id: str, reason: str) -> bool:
        reason = " ".join(str(reason).split()).strip()
        if not reason: raise ValueError("retraction reason required")
        with self._lease.acquire():
            records = self._load(); raw = records.get(record_id)
            if raw is None: return False
            raw["retracted"] = True; raw["retraction_reason"] = reason[:2000]
            records[record_id] = raw; self._write(records); return True

    def evidence_for(self, claim: str, *, include_retracted: bool = False) -> tuple[EvidenceItem, ...]:
        claim = " ".join(str(claim).split()).strip()
        with self._lease.acquire(): records = self._load()
        restored = [self._restore(raw) for raw in records.values()]
        return tuple(r.item for r in restored if r.claim == claim and (include_retracted or not r.retracted))

    def records_for(self, claim: str) -> tuple[EvidenceRecord, ...]:
        with self._lease.acquire(): records = self._load()
        return tuple(self._restore(raw) for raw in records.values() if str(raw.get("claim")) == claim)

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire(): records = self._load()
        retracted = sum(1 for raw in records.values() if raw.get("retracted"))
        groups = {raw.get("item", {}).get("independence_group") for raw in records.values()}
        return {"version": REGISTRY_VERSION, "records": len(records), "retracted": retracted,
                "independence_groups": len({g for g in groups if g}), "sha256": self._checksum(records),
                "cross_process_locking": True, "lock_backend": self._lease.backend}
