"""Tamper-evident in-process ledger for auto-merge decisions and mutations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .automerge_model import MergeDecision, MutationReceipt, canonical_json, valid_sha


GENESIS = "0" * 64


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    sequence: int
    kind: str
    subject: str
    payload: Mapping[str, Any]
    previous_hash: str
    record_hash: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "subject": self.subject,
            "payload": dict(self.payload),
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
            "recorded_at": self.recorded_at,
        }


class MergeLedger:
    def __init__(self, records: Iterable[LedgerRecord] = ()) -> None:
        self._records: list[LedgerRecord] = list(records)
        self.verify()

    @property
    def records(self) -> tuple[LedgerRecord, ...]:
        return tuple(self._records)

    @property
    def head_hash(self) -> str:
        return self._records[-1].record_hash if self._records else GENESIS

    def _hash(
        self,
        *,
        sequence: int,
        kind: str,
        subject: str,
        payload: Mapping[str, Any],
        previous_hash: str,
        recorded_at: str,
    ) -> str:
        material = {
            "sequence": sequence,
            "kind": kind,
            "subject": subject,
            "payload": dict(payload),
            "previous_hash": previous_hash,
            "recorded_at": recorded_at,
        }
        return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()

    def append(
        self,
        *,
        kind: str,
        subject: str,
        payload: Mapping[str, Any],
        recorded_at: str | None = None,
    ) -> LedgerRecord:
        if not kind or not subject:
            raise ValueError("ledger kind and subject are required")
        sequence = len(self._records) + 1
        previous_hash = self.head_hash
        timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
        record_hash = self._hash(
            sequence=sequence,
            kind=kind,
            subject=subject,
            payload=payload,
            previous_hash=previous_hash,
            recorded_at=timestamp,
        )
        record = LedgerRecord(
            sequence=sequence,
            kind=kind,
            subject=subject,
            payload=dict(payload),
            previous_hash=previous_hash,
            record_hash=record_hash,
            recorded_at=timestamp,
        )
        self._records.append(record)
        return record

    def append_decision(self, decision: MergeDecision) -> LedgerRecord:
        return self.append(
            kind="decision",
            subject=f"pr:{decision.pr_number}",
            payload=asdict(decision),
        )

    def append_receipt(self, receipt: MutationReceipt) -> LedgerRecord:
        return self.append(
            kind="mutation",
            subject=f"pr:{receipt.pr_number}",
            payload=asdict(receipt),
        )

    def append_base_transition(
        self,
        *,
        before: str,
        after: str,
        reason: str,
    ) -> LedgerRecord:
        if not valid_sha(before) or not valid_sha(after):
            raise ValueError("base transition requires canonical SHAs")
        return self.append(
            kind="base_transition",
            subject="default_branch",
            payload={"before": before, "after": after, "reason": reason},
        )

    def verify(self) -> None:
        previous = GENESIS
        for index, record in enumerate(self._records, start=1):
            if record.sequence != index:
                raise ValueError("ledger sequence discontinuity")
            if record.previous_hash != previous:
                raise ValueError("ledger previous hash mismatch")
            expected = self._hash(
                sequence=record.sequence,
                kind=record.kind,
                subject=record.subject,
                payload=record.payload,
                previous_hash=record.previous_hash,
                recorded_at=record.recorded_at,
            )
            if record.record_hash != expected:
                raise ValueError("ledger record hash mismatch")
            previous = record.record_hash

    def to_jsonl(self) -> str:
        return "".join(
            json.dumps(record.to_dict(), sort_keys=True) + "\n"
            for record in self._records
        )

    @classmethod
    def from_jsonl(cls, text: str) -> "MergeLedger":
        records: list[LedgerRecord] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid ledger JSON on line {line_number}") from exc
            if not isinstance(raw, Mapping):
                raise ValueError(f"ledger line {line_number} is not an object")
            payload = raw.get("payload")
            if not isinstance(payload, Mapping):
                raise ValueError(f"ledger line {line_number} has invalid payload")
            records.append(
                LedgerRecord(
                    sequence=int(raw.get("sequence") or 0),
                    kind=str(raw.get("kind") or ""),
                    subject=str(raw.get("subject") or ""),
                    payload=dict(payload),
                    previous_hash=str(raw.get("previous_hash") or ""),
                    record_hash=str(raw.get("record_hash") or ""),
                    recorded_at=str(raw.get("recorded_at") or ""),
                )
            )
        return cls(records)

    def write(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_jsonl(), encoding="utf-8")

    @classmethod
    def read(cls, path: str | Path) -> "MergeLedger":
        target = Path(path)
        if not target.exists():
            return cls()
        return cls.from_jsonl(target.read_text(encoding="utf-8"))

    def decision_count(self) -> int:
        return sum(record.kind == "decision" for record in self._records)

    def mutation_count(self) -> int:
        return sum(record.kind == "mutation" for record in self._records)

    def subject_records(self, subject: str) -> tuple[LedgerRecord, ...]:
        return tuple(record for record in self._records if record.subject == subject)

    def latest_subject_record(self, subject: str) -> LedgerRecord | None:
        for record in reversed(self._records):
            if record.subject == subject:
                return record
        return None

    def has_action_key(self, action_key: str) -> bool:
        for record in self._records:
            if record.kind != "mutation":
                continue
            if str(record.payload.get("action_key") or "") == action_key:
                return True
        return False

    def compact_summary(self) -> dict[str, Any]:
        return {
            "records": len(self._records),
            "decisions": self.decision_count(),
            "mutations": self.mutation_count(),
            "head_hash": self.head_hash,
            "first_recorded_at": (
                self._records[0].recorded_at if self._records else None
            ),
            "last_recorded_at": (
                self._records[-1].recorded_at if self._records else None
            ),
        }


def verify_jsonl(text: str) -> tuple[bool, str]:
    try:
        ledger = MergeLedger.from_jsonl(text)
    except ValueError as exc:
        return False, str(exc)
    return True, ledger.head_hash


def merge_ledgers(ledgers: Sequence[MergeLedger]) -> MergeLedger:
    """Replay records from multiple verified ledgers into a new canonical chain."""
    result = MergeLedger()
    for ledger in ledgers:
        ledger.verify()
        for record in ledger.records:
            result.append(
                kind=record.kind,
                subject=record.subject,
                payload=record.payload,
                recorded_at=record.recorded_at,
            )
    return result


__all__ = [
    "GENESIS",
    "LedgerRecord",
    "MergeLedger",
    "merge_ledgers",
    "verify_jsonl",
]
