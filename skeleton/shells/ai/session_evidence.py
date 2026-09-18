"""Session-scoped execution evidence commitments for recovery."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.plan_executor import PlanExecutionReport


@dataclass(frozen=True)
class SessionReceiptEvidence:
    step_id: str
    correlation_id: str
    receipt_ids: tuple[str, ...]
    receipt_fingerprints: tuple[str, ...]
    returncodes: tuple[int | None, ...]
    attempts: int
    ok: bool

    def __post_init__(self) -> None:
        if not self.step_id or len(self.step_id) > 128:
            raise ValueError("invalid session evidence step_id")
        if len(self.correlation_id) > 160:
            raise ValueError("session evidence correlation_id too long")
        receipt_ids = tuple(self.receipt_ids)
        fingerprints = tuple(self.receipt_fingerprints)
        returncodes = tuple(self.returncodes)
        if not (
            len(receipt_ids)
            == len(fingerprints)
            == len(returncodes)
            == self.attempts
        ):
            raise ValueError("session receipt evidence attempt vectors differ")
        if any(len(value) > 128 for value in receipt_ids):
            raise ValueError("session evidence receipt_id too long")
        if any(len(value) != 64 for value in fingerprints):
            raise ValueError("session evidence fingerprint must be SHA-256 hex")
        object.__setattr__(self, "receipt_ids", receipt_ids)
        object.__setattr__(self, "receipt_fingerprints", fingerprints)
        object.__setattr__(self, "returncodes", returncodes)

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "correlation_id": self.correlation_id,
            "receipt_ids": list(self.receipt_ids),
            "receipt_fingerprints": list(self.receipt_fingerprints),
            "returncodes": list(self.returncodes),
            "attempts": self.attempts,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class SessionExecutionEvidence:
    schema_version: int
    session_id: str
    plan_id: str
    plan_fingerprint: str
    report_ok: bool
    steps: tuple[SessionReceiptEvidence, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported session evidence schema")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid session evidence session_id")
        if not self.plan_id or len(self.plan_id) > 128:
            raise ValueError("invalid session evidence plan_id")
        if len(self.plan_fingerprint) != 64:
            raise ValueError("session evidence plan fingerprint must be SHA-256 hex")
        steps = tuple(self.steps)
        ids = [item.step_id for item in steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate session evidence step_id")
        object.__setattr__(self, "steps", steps)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "plan_id": self.plan_id,
            "plan_fingerprint": self.plan_fingerprint,
            "report_ok": self.report_ok,
            "steps": [item.to_dict() for item in self.steps],
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def from_report(
        cls,
        session_id: str,
        report: PlanExecutionReport,
    ) -> "SessionExecutionEvidence":
        steps = []
        for step in report.steps:
            if step.dispatch is None:
                steps.append(
                    SessionReceiptEvidence(
                        step.step_id,
                        "",
                        (),
                        (),
                        (),
                        0,
                        step.ok,
                    )
                )
                continue
            receipts = step.dispatch.outcome.receipts
            steps.append(
                SessionReceiptEvidence(
                    step.step_id,
                    step.dispatch.outcome.correlation_id,
                    tuple(item.receipt_id for item in receipts),
                    tuple(item.fingerprint for item in receipts),
                    tuple(item.returncode for item in receipts),
                    len(receipts),
                    step.ok,
                )
            )
        return cls(
            1,
            session_id,
            report.plan_id,
            report.fingerprint,
            report.ok,
            tuple(steps),
        )


@dataclass(frozen=True)
class StoredSessionEvidence:
    revision: int
    evidence: SessionExecutionEvidence


class SessionEvidenceConflict(RuntimeError):
    pass


class SessionEvidenceStore:
    """CAS store for the latest immutable evidence commitment per AI session."""

    def __init__(
        self,
        backend,
        *,
        namespace: str = "shell-ai-session-evidence",
    ) -> None:
        self.backend = backend
        self.namespace = namespace

    def put(
        self,
        evidence: SessionExecutionEvidence,
        *,
        expected_revision: int | None = None,
    ) -> StoredSessionEvidence:
        current = self.backend.get(self.namespace, evidence.session_id)
        if current is None:
            if expected_revision not in {None, 0}:
                raise SessionEvidenceConflict("session evidence does not exist")
            try:
                record = self.backend.put_if_absent(
                    self.namespace,
                    evidence.session_id,
                    evidence,
                )
            except Exception as exc:
                winner = self.backend.get(self.namespace, evidence.session_id)
                if winner is None:
                    raise
                current = winner
            else:
                return StoredSessionEvidence(record.revision, evidence)
        if not isinstance(current.value, SessionExecutionEvidence):
            raise RuntimeError("session evidence backend value type mismatch")
        if current.value.digest == evidence.digest:
            return StoredSessionEvidence(current.revision, current.value)
        if expected_revision is not None and current.revision != expected_revision:
            raise SessionEvidenceConflict("session evidence revision conflict")
        try:
            record = self.backend.compare_and_swap(
                self.namespace,
                evidence.session_id,
                expected_revision=current.revision,
                value=evidence,
            )
        except Exception as exc:
            latest = self.backend.get(self.namespace, evidence.session_id)
            if latest is None or latest.revision == current.revision:
                raise
            raise SessionEvidenceConflict("session evidence CAS conflict") from exc
        return StoredSessionEvidence(record.revision, evidence)

    def current(self, session_id: str) -> StoredSessionEvidence | None:
        record = self.backend.get(self.namespace, session_id)
        if record is None:
            return None
        if not isinstance(record.value, SessionExecutionEvidence):
            raise RuntimeError("session evidence backend value type mismatch")
        return StoredSessionEvidence(record.revision, record.value)
