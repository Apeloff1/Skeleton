"""Append-only architecture and repository evolution ledger."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

MAX_RECORD_BYTES = 64 * 1024
MAX_READ_BYTES = 16 * 1024 * 1024


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LedgerRecord:
    sequence: int
    timestamp: int
    kind: str
    repository_fingerprint: str
    subject: str
    summary: str
    evidence: tuple[str, ...] = ()
    previous_digest: str = ""
    digest: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "repository_fingerprint": self.repository_fingerprint,
            "subject": self.subject,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "previous_digest": self.previous_digest,
        }

    def with_digest(self) -> "LedgerRecord":
        value = _digest(self.payload())
        return LedgerRecord(
            sequence=self.sequence,
            timestamp=self.timestamp,
            kind=self.kind,
            repository_fingerprint=self.repository_fingerprint,
            subject=self.subject,
            summary=self.summary,
            evidence=self.evidence,
            previous_digest=self.previous_digest,
            digest=value,
        )

    def as_dict(self) -> dict[str, object]:
        payload = self.payload()
        payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "LedgerRecord":
        return cls(
            sequence=int(value.get("sequence", 0)),
            timestamp=int(value.get("timestamp", 0)),
            kind=str(value.get("kind", "")),
            repository_fingerprint=str(value.get("repository_fingerprint", "")),
            subject=str(value.get("subject", "")),
            summary=str(value.get("summary", "")),
            evidence=tuple(value.get("evidence", ())),
            previous_digest=str(value.get("previous_digest", "")),
            digest=str(value.get("digest", "")),
        )


class ArchitectureLedger:
    def __init__(self, records: Iterable[LedgerRecord] = ()) -> None:
        self.records = list(records)
        self.validate()

    def validate(self) -> None:
        previous = ""
        for expected_sequence, record in enumerate(self.records, start=1):
            if record.sequence != expected_sequence:
                raise ValueError("ledger sequence gap")
            if record.previous_digest != previous:
                raise ValueError("ledger hash chain mismatch")
            expected = record.with_digest().digest
            if record.digest != expected:
                raise ValueError("ledger record digest mismatch")
            previous = record.digest

    @property
    def head_digest(self) -> str:
        return self.records[-1].digest if self.records else ""

    def append(
        self,
        *,
        timestamp: int,
        kind: str,
        repository_fingerprint: str,
        subject: str,
        summary: str,
        evidence: Iterable[str] = (),
    ) -> LedgerRecord:
        if not kind or not subject or not summary:
            raise ValueError("ledger kind, subject, and summary are required")
        record = LedgerRecord(
            sequence=len(self.records) + 1,
            timestamp=timestamp,
            kind=kind,
            repository_fingerprint=repository_fingerprint,
            subject=subject,
            summary=summary[:4000],
            evidence=tuple(sorted({str(item) for item in evidence if str(item)}))[:128],
            previous_digest=self.head_digest,
        ).with_digest()
        self.records.append(record)
        return record

    def append_to_file(self, path: str | Path, record: LedgerRecord) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        rendered = _canonical(record.as_dict()) + "\n"
        if len(rendered.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError("ledger record exceeds byte budget")
        with destination.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)

    @classmethod
    def load(cls, path: str | Path) -> "ArchitectureLedger":
        source = Path(path)
        raw = source.read_bytes()
        if len(raw) > MAX_READ_BYTES:
            raise ValueError("ledger exceeds read budget")
        records: list[LedgerRecord] = []
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"ledger line {line_number} is not an object")
            records.append(LedgerRecord.from_dict(value))
        return cls(records)
