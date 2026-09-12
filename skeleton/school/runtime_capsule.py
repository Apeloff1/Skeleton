"""Portable, deterministic integrity capsules for Jeeves runtime sessions.

A capsule is the smallest audit artifact that can be persisted or transported
without coupling callers to the live runtime object. It binds the runtime
snapshot, session audit, causal root, selected policy, and ledger checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.runtime_replay import RuntimeAudit, RuntimeReplaySnapshot, audit_runtime, replay_digest
from skeleton.school.session_audit import SessionAudit, audit_session


@dataclass(frozen=True)
class RuntimeIntegrityCapsule:
    session_id: str
    runtime: RuntimeReplaySnapshot
    session: SessionAudit
    ledger_head: str
    ledger_count: int
    root_decision_id: str
    selected_policy_decision_id: str | None
    capsule_digest: str

    @classmethod
    def capture(cls, runtime: RuntimeReplaySnapshot, ledger: DecisionLedger) -> "RuntimeIntegrityCapsule":
        runtime_audit = audit_runtime(runtime, ledger)
        if not runtime_audit.valid:
            raise ValueError("cannot capsule an invalid runtime snapshot")
        session = audit_session(ledger, runtime.session_id)
        if not session.valid:
            raise ValueError("cannot capsule an invalid session audit")
        records = ledger.session(runtime.session_id)
        if not records:
            raise ValueError("cannot capsule an empty session")
        roots = tuple(record for record in records if not record.predecessors)
        if len(roots) != 1:
            raise ValueError("session must have exactly one causal root")
        root = roots[0]
        selected = runtime.selected_policy_decision_id or None
        if selected is not None:
            selected_record = next((record for record in records if record.decision_id == selected), None)
            if selected_record is None or selected_record.disposition is not DecisionDisposition.ACCEPTED:
                raise ValueError("selected policy decision is not an accepted session record")
            if selected_record.action != runtime.selected_policy:
                raise ValueError("selected policy decision does not match selected policy")
        payload = {
            "session_id": runtime.session_id,
            "runtime_digest": runtime.runtime_digest,
            "replay_digest": replay_digest(runtime),
            "session_digest": session.digest,
            "session_valid": session.valid,
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
            "root_decision_id": root.decision_id,
            "selected_policy_decision_id": selected,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(runtime.session_id, runtime, session, ledger.head_hash, len(ledger.records), root.decision_id, selected, digest)

    def verify(self, ledger: DecisionLedger) -> RuntimeAudit:
        runtime_audit = audit_runtime(self.runtime, ledger)
        session_audit = audit_session(ledger, self.session_id)
        try:
            expected = RuntimeIntegrityCapsule.capture(self.runtime, ledger)
        except ValueError as exc:
            return RuntimeAudit(False, (str(exc),))
        violations = list(runtime_audit.violations)
        if not session_audit.valid:
            violations.extend(f"session audit: {item}" for item in session_audit.failures)
        if self.ledger_head != ledger.head_hash or self.ledger_count != len(ledger.records):
            violations.append("capsule-integrity divergence: ledger checkpoint has advanced")
        if self.root_decision_id != expected.root_decision_id:
            violations.append("capsule-integrity divergence: causal root identity changed")
        if self.selected_policy_decision_id != expected.selected_policy_decision_id:
            violations.append("capsule-integrity divergence: selected policy identity changed")
        if self.capsule_digest != expected.capsule_digest:
            violations.append("capsule-integrity divergence: capsule digest does not match its bound audits")
        return RuntimeAudit(not violations, tuple(dict.fromkeys(violations)))
