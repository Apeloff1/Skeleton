"""Durable evidence registry for empirical verification.

The registry preserves historical evidence independently from truth eligibility.
Evidence is eligible for authoritative verification only after a claim-level
citation binding has been validated by the epistemic gate and its attestation is
persisted here. Legacy/unbound evidence remains searchable and retractable through
explicit historical access, but cannot silently regain authority during later
re-verification.
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
from typing import Any, Iterable

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
    citation_binding_attestation_sha256: str = ""
    citation_bound_at: str = ""
    retracted: bool = False
    retraction_reason: str = ""
    retracted_at: str = ""

    @property
    def citation_bound(self) -> bool:
        return bool(self.citation_binding_attestation_sha256)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _attestation(value: str) -> str:
    value = str(value or "").lower().strip()
    if value and not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("citation binding attestation must be a 64-character sha256")
    return value


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
            registered_at=str(raw["registered_at"]),
            citation_binding_attestation_sha256=str(raw.get("citation_binding_attestation_sha256", "")),
            citation_bound_at=str(raw.get("citation_bound_at", "")),
            retracted=bool(raw.get("retracted", False)),
            retraction_reason=str(raw.get("retraction_reason", "")), retracted_at=str(raw.get("retracted_at", "")),
        )

    def register(self, claim: str, item: EvidenceItem, *, registered_at: str | None = None,
                 citation_binding_attestation_sha256: str = "") -> EvidenceRecord:
        claim = " ".join(str(claim).split()).strip()
        if not claim: raise ValueError("claim cannot be blank")
        stamp = registered_at or datetime.now(UTC).isoformat()
        citation_attestation = _attestation(citation_binding_attestation_sha256)
        identity = {"claim": claim, "source_id": item.source_id, "locator": item.locator,
                    "kind": item.kind.value, "independence_group": item.independence_group,
                    "observed_at": item.observed_at}
        record_id = _digest(identity)[:24]
        serialized_item = self._serialize_item(item)
        serialized = {"id": record_id, "claim": claim, "item": serialized_item,
                      "registered_at": stamp,
                      "citation_binding_attestation_sha256": citation_attestation,
                      "citation_bound_at": stamp if citation_attestation else "",
                      "retracted": False, "retraction_reason": "", "retracted_at": ""}
        with self._lease.acquire():
            records = self._load(); existing = records.get(record_id)
            if existing is not None:
                restored = self._restore(existing)
                normalized_existing_item = self._serialize_item(restored.item)
                if normalized_existing_item != serialized_item or restored.claim != claim:
                    raise EvidenceRegistryIntegrityError("evidence identity collision with different evidence payload")
                existing_attestation = restored.citation_binding_attestation_sha256
                if citation_attestation and not existing_attestation:
                    # One-way migration: old historical evidence becomes eligible
                    # only when the epistemic gate supplies a validated binding.
                    existing["citation_binding_attestation_sha256"] = citation_attestation
                    existing["citation_bound_at"] = stamp
                    records[record_id] = existing; self._write(records)
                    return self._restore(existing)
                # If a replay supplies another valid binding for an already-bound
                # immutable evidence identity, keep the first provenance anchor.
                # The gate has already validated the replay, so no mutation is needed.
                return restored
            records[record_id] = serialized; self._write(records)
        return self._restore(serialized)

    def retract(self, record_id: str, reason: str, *, retracted_at: str | None = None) -> bool:
        reason = " ".join(str(reason).split()).strip()
        if not reason: raise ValueError("retraction reason required")
        stamp = retracted_at or datetime.now(UTC).isoformat()
        with self._lease.acquire():
            records = self._load(); raw = records.get(record_id)
            if raw is None: return False
            raw["retracted"] = True; raw["retraction_reason"] = reason[:2000]; raw["retracted_at"] = stamp
            records[record_id] = raw; self._write(records); return True

    def retract_sources(self, source_ids: Iterable[str], reason: str, *, retracted_at: str | None = None) -> dict[str, tuple[str, ...]]:
        ids = {str(x).strip() for x in source_ids if str(x).strip()}
        if not ids: return {"record_ids": (), "claims": ()}
        reason = " ".join(str(reason).split()).strip()
        if not reason: raise ValueError("retraction reason required")
        stamp = retracted_at or datetime.now(UTC).isoformat()
        record_ids: list[str] = []; claims: set[str] = set()
        with self._lease.acquire():
            records = self._load()
            for record_id, raw in records.items():
                item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
                if str(item.get("source_id", "")) not in ids: continue
                raw["retracted"] = True; raw["retraction_reason"] = reason[:2000]; raw["retracted_at"] = stamp
                records[record_id] = raw; record_ids.append(record_id); claims.add(str(raw.get("claim", "")))
            if record_ids: self._write(records)
        return {"record_ids": tuple(sorted(record_ids)), "claims": tuple(sorted(x for x in claims if x))}

    def evidence_for(self, claim: str, *, include_retracted: bool = False,
                     citation_bound_only: bool = True) -> tuple[EvidenceItem, ...]:
        """Return truth-eligible evidence by default.

        Historical/unbound evidence requires ``citation_bound_only=False``. This
        fail-safe default prevents a future caller from accidentally reintroducing
        pre-gate evidence into authoritative verification.
        """
        claim = " ".join(str(claim).split()).strip()
        with self._lease.acquire(): records = self._load()
        restored = [self._restore(raw) for raw in records.values()]
        return tuple(record.item for record in restored
                     if record.claim == claim and (include_retracted or not record.retracted)
                     and (not citation_bound_only or record.citation_bound))

    def records_for(self, claim: str, *, citation_bound_only: bool = False) -> tuple[EvidenceRecord, ...]:
        with self._lease.acquire(): records = self._load()
        rows = [self._restore(raw) for raw in records.values() if str(raw.get("claim")) == claim]
        if citation_bound_only: rows = [row for row in rows if row.citation_bound]
        return tuple(rows)

    def records_for_sources(self, source_ids: Iterable[str], *, include_retracted: bool = True,
                            citation_bound_only: bool = False) -> tuple[EvidenceRecord, ...]:
        ids = {str(x).strip() for x in source_ids if str(x).strip()}
        with self._lease.acquire(): records = self._load()
        out: list[EvidenceRecord] = []
        for raw in records.values():
            item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
            if str(item.get("source_id", "")) not in ids: continue
            record = self._restore(raw)
            if not include_retracted and record.retracted: continue
            if citation_bound_only and not record.citation_bound: continue
            out.append(record)
        return tuple(out)

    def snapshot(self, *, include_retracted: bool = True) -> tuple[EvidenceRecord, ...]:
        with self._lease.acquire(): records = self._load()
        rows = [self._restore(raw) for raw in records.values()]
        if not include_retracted: rows = [row for row in rows if not row.retracted]
        return tuple(sorted(rows, key=lambda row: (row.claim.casefold(), row.item.source_id, row.id)))

    def all_claims(self, *, include_only_active: bool = False) -> tuple[str, ...]:
        with self._lease.acquire(): records = self._load()
        claims = {str(raw.get("claim", "")) for raw in records.values()
                  if str(raw.get("claim", "")) and (not include_only_active or not raw.get("retracted"))}
        return tuple(sorted(claims))

    def stats(self) -> dict[str, Any]:
        with self._lease.acquire(): records = self._load()
        retracted = sum(1 for raw in records.values() if raw.get("retracted"))
        citation_bound = sum(bool(raw.get("citation_binding_attestation_sha256")) for raw in records.values())
        active_bound = sum(bool(raw.get("citation_binding_attestation_sha256")) and not raw.get("retracted") for raw in records.values())
        groups = {raw.get("item", {}).get("independence_group") for raw in records.values()}
        claims = {str(raw.get("claim", "")) for raw in records.values() if str(raw.get("claim", ""))}
        return {"version": REGISTRY_VERSION, "records": len(records), "active_records": len(records) - retracted,
                "citation_bound_records": citation_bound, "active_citation_bound_records": active_bound,
                "unbound_records": len(records) - citation_bound, "retracted": retracted, "claims": len(claims),
                "independence_groups": len({g for g in groups if g}), "sha256": self._checksum(records),
                "cross_process_locking": True, "lock_backend": self._lease.backend,
                "truth_eligible_default": True}
