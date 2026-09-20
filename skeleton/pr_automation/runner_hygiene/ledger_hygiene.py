"""Merge-gate ledger hygiene: verification, compaction safety, anomaly scan.

Extends the concepts of automerge_ledger without clobbering it. Operates on
generic hash-chained JSONL records for Pack E hygiene evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .types import Finding, HygieneVerdict, canonical_json, fingerprint, parse_timestamp, valid_sha


GENESIS = "0" * 64
ALLOWED_KINDS = frozenset(
    {
        "admission",
        "merge_gate",
        "observe_sweep",
        "checkpoint",
        "anomaly",
        "policy",
        "budget",
        "heartbeat",
    }
)


@dataclass(frozen=True, slots=True)
class HygieneLedgerRecord:
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

    def to_jsonl(self) -> str:
        return canonical_json(self.to_dict())


def _hash_record(
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


@dataclass
class HygieneLedger:
    records: list[HygieneLedgerRecord]

    def __init__(self, records: Iterable[HygieneLedgerRecord] = ()) -> None:
        self.records = list(records)
        self.verify()

    @property
    def head_hash(self) -> str:
        return self.records[-1].record_hash if self.records else GENESIS

    @property
    def length(self) -> int:
        return len(self.records)

    def append(
        self,
        *,
        kind: str,
        subject: str,
        payload: Mapping[str, Any],
        recorded_at: str | None = None,
    ) -> HygieneLedgerRecord:
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"unsupported ledger kind: {kind}")
        if not subject or not isinstance(subject, str):
            raise ValueError("subject required")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        sequence = len(self.records) + 1
        previous_hash = self.head_hash
        timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
        if parse_timestamp(timestamp) is None:
            raise ValueError("recorded_at must be an ISO-8601 timestamp")
        record_hash = _hash_record(
            sequence=sequence,
            kind=kind,
            subject=subject,
            payload=payload,
            previous_hash=previous_hash,
            recorded_at=timestamp,
        )
        record = HygieneLedgerRecord(
            sequence=sequence,
            kind=kind,
            subject=subject,
            payload=dict(payload),
            previous_hash=previous_hash,
            record_hash=record_hash,
            recorded_at=timestamp,
        )
        self.records.append(record)
        return record

    def verify(self) -> None:
        previous = GENESIS
        for index, record in enumerate(self.records, start=1):
            if record.sequence != index:
                raise ValueError(f"sequence gap at {index}: got {record.sequence}")
            if record.previous_hash != previous:
                raise ValueError(f"chain break at sequence {index}")
            if record.kind not in ALLOWED_KINDS:
                raise ValueError(f"invalid kind at sequence {index}: {record.kind}")
            expected = _hash_record(
                sequence=record.sequence,
                kind=record.kind,
                subject=record.subject,
                payload=record.payload,
                previous_hash=record.previous_hash,
                recorded_at=record.recorded_at,
            )
            if record.record_hash != expected:
                raise ValueError(f"hash mismatch at sequence {index}")
            if not valid_sha(record.record_hash) and len(record.record_hash) != 64:
                raise ValueError(f"malformed record hash at sequence {index}")
            previous = record.record_hash

    def to_jsonl(self) -> str:
        return "\n".join(record.to_jsonl() for record in self.records) + (
            "\n" if self.records else ""
        )

    @classmethod
    def from_jsonl(cls, text: str) -> "HygieneLedger":
        records: list[HygieneLedgerRecord] = []
        for line_no, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_no}: {exc}") from exc
            records.append(
                HygieneLedgerRecord(
                    sequence=int(data["sequence"]),
                    kind=str(data["kind"]),
                    subject=str(data["subject"]),
                    payload=dict(data["payload"]),
                    previous_hash=str(data["previous_hash"]),
                    record_hash=str(data["record_hash"]),
                    recorded_at=str(data["recorded_at"]),
                )
            )
        return cls(records)

    def write(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_jsonl(), encoding="utf-8")

    @classmethod
    def read(cls, path: Path | str) -> "HygieneLedger":
        target = Path(path)
        if not target.is_file():
            return cls()
        return cls.from_jsonl(target.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class LedgerHygieneReport:
    verdict: HygieneVerdict
    length: int
    head_hash: str
    findings: tuple[Finding, ...]
    anomalies: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "length": self.length,
            "head_hash": self.head_hash,
            "findings": [f.to_dict() for f in self.findings],
            "anomalies": list(self.anomalies),
        }


def scan_ledger_anomalies(ledger: HygieneLedger) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    subjects_by_kind: dict[str, list[str]] = {}
    timestamps: list[datetime] = []
    for record in ledger.records:
        subjects_by_kind.setdefault(record.kind, []).append(record.subject)
        ts = parse_timestamp(record.recorded_at)
        if ts is None:
            findings.append(
                Finding(
                    code="ledger.bad_timestamp",
                    severity="high",
                    message=f"unparseable timestamp at sequence {record.sequence}",
                    subject=str(record.sequence),
                )
            )
        else:
            if timestamps and ts < timestamps[-1]:
                findings.append(
                    Finding(
                        code="ledger.time_regression",
                        severity="medium",
                        message=f"timestamp regression at sequence {record.sequence}",
                        subject=str(record.sequence),
                    )
                )
            timestamps.append(ts)
        if record.kind == "admission":
            verdict = record.payload.get("verdict")
            if verdict not in {v.value for v in HygieneVerdict}:
                findings.append(
                    Finding(
                        code="ledger.bad_admission_verdict",
                        severity="high",
                        message=f"invalid admission verdict {verdict!r}",
                        subject=record.subject,
                    )
                )
    # Duplicate heartbeat spam detection
    heartbeats = subjects_by_kind.get("heartbeat", [])
    if len(heartbeats) > 100:
        findings.append(
            Finding(
                code="ledger.heartbeat_spam",
                severity="low",
                message=f"excessive heartbeats: {len(heartbeats)}",
            )
        )
    return tuple(findings)


def verify_ledger_file(path: Path | str) -> LedgerHygieneReport:
    findings: list[Finding] = []
    anomalies: list[str] = []
    try:
        ledger = HygieneLedger.read(path)
    except ValueError as exc:
        return LedgerHygieneReport(
            verdict=HygieneVerdict.DENY,
            length=0,
            head_hash=GENESIS,
            findings=(
                Finding(
                    code="ledger.verify_failed",
                    severity="critical",
                    message=str(exc),
                    subject=str(path),
                ),
            ),
            anomalies=("verify_failed",),
        )
    try:
        ledger.verify()
    except ValueError as exc:
        findings.append(
            Finding(
                code="ledger.verify_failed",
                severity="critical",
                message=str(exc),
                subject=str(path),
            )
        )
        anomalies.append("verify_failed")
    findings.extend(scan_ledger_anomalies(ledger))
    anomalies.extend(f.code for f in findings)
    verdict = HygieneVerdict.ALLOW
    if any(f.severity in {"critical", "high"} for f in findings):
        verdict = HygieneVerdict.DENY
    elif findings:
        verdict = HygieneVerdict.HOLD
    return LedgerHygieneReport(
        verdict=verdict,
        length=ledger.length,
        head_hash=ledger.head_hash,
        findings=tuple(findings),
        anomalies=tuple(dict.fromkeys(anomalies)),
    )


def compact_ledger_safe(
    ledger: HygieneLedger,
    *,
    keep_last: int = 500,
    require_verify: bool = True,
) -> HygieneLedger:
    """Return a prefix-trimmed ledger that preserves the hash chain.

    Compaction keeps the *oldest* genesis-linked prefix truncated from the
    front only when keep_last covers a suffix that is re-chained via a
    compaction summary record — actually we keep the last N records AND
    prepend a compaction summary that re-anchors to GENESIS for the suffix
    by rewriting sequences. This is intentional and explicit.
    """
    if require_verify:
        ledger.verify()
    if keep_last < 1:
        raise ValueError("keep_last must be positive")
    if ledger.length <= keep_last:
        return HygieneLedger(ledger.records)
    retained = ledger.records[-keep_last:]
    compacted = HygieneLedger()
    compacted.append(
        kind="checkpoint",
        subject="compaction",
        payload={
            "compacted_away": ledger.length - keep_last,
            "prior_head": ledger.records[-keep_last - 1].record_hash
            if ledger.length > keep_last
            else GENESIS,
            "retained": keep_last,
            "note": "suffix re-anchored after explicit compaction",
        },
    )
    for record in retained:
        compacted.append(
            kind=record.kind,
            subject=record.subject,
            payload=record.payload,
            recorded_at=record.recorded_at,
        )
    compacted.verify()
    return compacted


def iter_subjects(ledger: HygieneLedger, kind: str) -> Iterator[HygieneLedgerRecord]:
    for record in ledger.records:
        if record.kind == kind:
            yield record


__all__ = [
    "ALLOWED_KINDS",
    "GENESIS",
    "HygieneLedger",
    "HygieneLedgerRecord",
    "LedgerHygieneReport",
    "compact_ledger_safe",
    "iter_subjects",
    "scan_ledger_anomalies",
    "verify_ledger_file",
]
