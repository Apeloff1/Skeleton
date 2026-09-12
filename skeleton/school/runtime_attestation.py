"""Deterministic attestation chain for Jeeves runtime provenance."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.runtime_replay import RuntimeReplaySnapshot, audit_runtime, replay_digest
from skeleton.school.session_audit import SessionAudit, audit_session


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeAttestation:
    session_id: str
    runtime_digest: str
    replay_digest: str
    session_audit_digest: str
    ledger_head: str
    ledger_count: int
    accepted_decision_ids: tuple[str, ...]
    rejected_decision_ids: tuple[str, ...]
    attestation_digest: str

    @classmethod
    def capture(cls, snapshot: RuntimeReplaySnapshot, ledger: DecisionLedger) -> "RuntimeAttestation":
        runtime_audit = audit_runtime(snapshot, ledger)
        session_audit = audit_session(ledger, snapshot.session_id)
        accepted = tuple(record.decision_id for record in ledger.session(snapshot.session_id) if record.disposition is DecisionDisposition.ACCEPTED)
        rejected = tuple(record.decision_id for record in ledger.session(snapshot.session_id) if record.disposition is DecisionDisposition.REJECTED)
        payload = {
            "session_id": snapshot.session_id,
            "runtime_digest": snapshot.runtime_digest,
            "replay_digest": replay_digest(snapshot),
            "session_audit_digest": session_audit.digest,
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
            "accepted_decision_ids": accepted,
            "rejected_decision_ids": rejected,
            "runtime_valid": runtime_audit.valid,
            "session_valid": session_audit.valid,
        }
        return cls(snapshot.session_id, snapshot.runtime_digest, payload["replay_digest"], session_audit.digest, ledger.head_hash, len(ledger.records), accepted, rejected, _digest(payload))


def verify_attestation(attestation: RuntimeAttestation, snapshot: RuntimeReplaySnapshot, ledger: DecisionLedger) -> tuple[str, ...]:
    """Return deterministic integrity violations for an attestation."""
    failures: list[str] = []
    runtime = audit_runtime(snapshot, ledger)
    session = audit_session(ledger, snapshot.session_id)
    expected = RuntimeAttestation.capture(snapshot, ledger)
    if not runtime.valid:
        failures.append("runtime audit is invalid")
    if not session.valid:
        failures.append("session audit is invalid")
    if attestation.session_id != snapshot.session_id:
        failures.append("attestation session identity diverges")
    if attestation.runtime_digest != snapshot.runtime_digest:
        failures.append("attestation runtime digest diverges")
    if attestation.replay_digest != replay_digest(snapshot):
        failures.append("attestation replay digest diverges")
    if attestation.session_audit_digest != session.digest:
        failures.append("attestation session audit digest diverges")
    if attestation.ledger_head != ledger.head_hash or attestation.ledger_count != len(ledger.records):
        failures.append("attestation ledger identity diverges")
    if attestation.accepted_decision_ids != expected.accepted_decision_ids:
        failures.append("attestation accepted decision identities diverge")
    if attestation.rejected_decision_ids != expected.rejected_decision_ids:
        failures.append("attestation rejected decision identities diverge")
    if attestation.attestation_digest != expected.attestation_digest:
        failures.append("attestation digest diverges")
    return tuple(dict.fromkeys(failures))
