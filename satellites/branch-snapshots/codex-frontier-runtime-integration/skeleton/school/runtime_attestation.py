"""Deterministic attestation chain for Jeeves runtime provenance."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.runtime_capsule import RuntimeIntegrityCapsule
from skeleton.school.runtime_replay import RuntimeReplaySnapshot, audit_runtime, replay_digest
from skeleton.school.session_audit import audit_session


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeAttestation:
    session_id: str
    runtime_digest: str
    replay_digest: str
    capsule_digest: str
    session_audit_digest: str
    ledger_head: str
    ledger_count: int
    session_root_decision_id: str
    selected_policy_decision_id: str | None
    accepted_decision_ids: tuple[str, ...]
    rejected_decision_ids: tuple[str, ...]
    session_record_hashes: tuple[str, ...]
    attestation_digest: str

    @classmethod
    def capture(cls, snapshot: RuntimeReplaySnapshot, ledger: DecisionLedger) -> "RuntimeAttestation":
        runtime_audit = audit_runtime(snapshot, ledger)
        session_audit = audit_session(ledger, snapshot.session_id)
        if not runtime_audit.valid:
            raise ValueError("cannot attest an invalid runtime snapshot")
        if not session_audit.valid:
            raise ValueError("cannot attest an invalid session audit")
        capsule = RuntimeIntegrityCapsule.capture(snapshot, ledger)
        capsule_audit = capsule.verify(ledger)
        if not capsule_audit.valid:
            raise ValueError("cannot attest an invalid integrity capsule")
        records = ledger.session(snapshot.session_id)
        if not records:
            raise ValueError("cannot attest an empty session")
        roots = tuple(record for record in records if not record.predecessors)
        if len(roots) != 1:
            raise ValueError("session must have exactly one causal root")
        root = roots[0]
        accepted = tuple(record.decision_id for record in records if record.disposition is DecisionDisposition.ACCEPTED)
        rejected = tuple(record.decision_id for record in records if record.disposition is DecisionDisposition.REJECTED)
        record_hashes = tuple(record.record_hash for record in records)
        selected = snapshot.selected_policy_decision_id or None
        if selected is not None:
            selected_record = next((record for record in records if record.decision_id == selected), None)
            if selected_record is None or selected_record.disposition is not DecisionDisposition.ACCEPTED:
                raise ValueError("selected policy decision is not an accepted session record")
            if selected_record.action != snapshot.selected_policy:
                raise ValueError("selected policy decision does not match selected policy")
        payload = {
            "session_id": snapshot.session_id,
            "runtime_digest": snapshot.runtime_digest,
            "replay_digest": replay_digest(snapshot),
            "capsule_digest": capsule.capsule_digest,
            "session_audit_digest": session_audit.digest,
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
            "session_root_decision_id": root.decision_id,
            "selected_policy_decision_id": selected,
            "accepted_decision_ids": accepted,
            "rejected_decision_ids": rejected,
            "session_record_hashes": record_hashes,
        }
        return cls(
            snapshot.session_id,
            snapshot.runtime_digest,
            payload["replay_digest"],
            capsule.capsule_digest,
            session_audit.digest,
            ledger.head_hash,
            len(ledger.records),
            root.decision_id,
            selected,
            accepted,
            rejected,
            record_hashes,
            _digest(payload),
        )


def verify_attestation(attestation: RuntimeAttestation, snapshot: RuntimeReplaySnapshot, ledger: DecisionLedger) -> tuple[str, ...]:
    """Return deterministic integrity violations for an attestation."""
    failures: list[str] = []
    runtime = audit_runtime(snapshot, ledger)
    session = audit_session(ledger, snapshot.session_id)
    try:
        expected = RuntimeAttestation.capture(snapshot, ledger)
        capsule = RuntimeIntegrityCapsule.capture(snapshot, ledger)
        capsule_audit = capsule.verify(ledger)
    except ValueError as exc:
        failures.append(str(exc))
        expected = None
        capsule = None
        capsule_audit = None
    if not runtime.valid:
        failures.append("runtime audit is invalid")
    if not session.valid:
        failures.append("session audit is invalid")
    if capsule_audit is not None and not capsule_audit.valid:
        failures.append("integrity capsule is invalid")
    if attestation.session_id != snapshot.session_id:
        failures.append("attestation session identity diverges")
    if attestation.runtime_digest != snapshot.runtime_digest:
        failures.append("attestation runtime digest diverges")
    if attestation.replay_digest != replay_digest(snapshot):
        failures.append("attestation replay digest diverges")
    if capsule is not None and attestation.capsule_digest != capsule.capsule_digest:
        failures.append("attestation capsule digest diverges")
    if attestation.session_audit_digest != session.digest:
        failures.append("attestation session audit digest diverges")
    if attestation.ledger_head != ledger.head_hash or attestation.ledger_count != len(ledger.records):
        failures.append("attestation ledger identity diverges")
    if attestation.session_root_decision_id != (expected.session_root_decision_id if expected else ""):
        failures.append("attestation causal root diverges")
    if attestation.selected_policy_decision_id != (expected.selected_policy_decision_id if expected else None):
        failures.append("attestation selected policy identity diverges")
    if attestation.accepted_decision_ids != (expected.accepted_decision_ids if expected else ()):
        failures.append("attestation accepted decision identities diverge")
    if attestation.rejected_decision_ids != (expected.rejected_decision_ids if expected else ()):
        failures.append("attestation rejected decision identities diverge")
    if attestation.session_record_hashes != (expected.session_record_hashes if expected else ()):
        failures.append("attestation session record hashes diverge")
    if expected is not None and attestation.attestation_digest != expected.attestation_digest:
        failures.append("attestation digest diverges")
    return tuple(dict.fromkeys(failures))
