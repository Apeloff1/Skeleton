"""Portable, deterministic integrity capsules for Jeeves runtime sessions.

A capsule is the smallest audit artifact that can be persisted or transported
without coupling callers to the live runtime object.  It binds the runtime
snapshot, session audit, and both digest layers into one immutable record.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.school.decision_ledger import DecisionLedger
from skeleton.school.runtime_replay import RuntimeAudit, RuntimeReplaySnapshot, audit_runtime, replay_digest
from skeleton.school.session_audit import SessionAudit, audit_session


@dataclass(frozen=True)
class RuntimeIntegrityCapsule:
    session_id: str
    runtime: RuntimeReplaySnapshot
    session: SessionAudit
    capsule_digest: str

    @classmethod
    def capture(cls, runtime: RuntimeReplaySnapshot, ledger: DecisionLedger) -> "RuntimeIntegrityCapsule":
        session = audit_session(ledger, runtime.session_id)
        payload = {
            "session_id": runtime.session_id,
            "runtime_digest": runtime.runtime_digest,
            "replay_digest": replay_digest(runtime),
            "session_digest": session.digest,
            "session_valid": session.valid,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(runtime.session_id, runtime, session, digest)

    def verify(self, ledger: DecisionLedger) -> RuntimeAudit:
        runtime_audit = audit_runtime(self.runtime, ledger)
        session_audit = audit_session(ledger, self.session_id)
        payload = {
            "session_id": self.runtime.session_id,
            "runtime_digest": self.runtime.runtime_digest,
            "replay_digest": replay_digest(self.runtime),
            "session_digest": session_audit.digest,
            "session_valid": session_audit.valid,
        }
        expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        violations = list(runtime_audit.violations)
        if not session_audit.valid:
            violations.extend(f"session audit: {item}" for item in session_audit.failures)
        if self.capsule_digest != expected:
            violations.append("capsule-integrity divergence: capsule digest does not match its bound audits")
        return RuntimeAudit(not violations, tuple(dict.fromkeys(violations)))
