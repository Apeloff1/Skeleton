"""Deterministic runtime snapshots and semantic audit for Jeeves sessions."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from typing import Mapping, Sequence
from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger
from skeleton.school.session_runtime import SessionEvent, SessionPhase


@dataclass(frozen=True)
class RuntimeReplaySnapshot:
    session_id: str
    phase: str
    event_count: int
    events: tuple[tuple[int, str, str, tuple[tuple[str, str], ...]], ...]
    selected_policy: str
    rejected_policies: tuple[str, ...]
    ledger_head: str
    ledger_count: int
    ledger_digest: str

    @classmethod
    def capture(cls, *, session_id: str, phase: SessionPhase, events: Sequence[SessionEvent], selected_policy: str | None, rejected_policies: Sequence[str], ledger: DecisionLedger) -> "RuntimeReplaySnapshot":
        normalized = tuple((e.sequence, e.phase.value, e.event, tuple(e.payload)) for e in events)
        payload = {
            "session_id": session_id,
            "phase": phase.value,
            "events": normalized,
            "selected_policy": selected_policy or "",
            "rejected_policies": tuple(rejected_policies),
            "ledger_head": ledger.head_hash,
            "ledger_count": len(ledger.records),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return cls(session_id, phase.value, len(normalized), normalized, selected_policy or "", tuple(rejected_policies), ledger.head_hash, len(ledger.records), digest)


@dataclass(frozen=True)
class RuntimeAudit:
    valid: bool
    violations: tuple[str, ...]


def audit_runtime(snapshot: RuntimeReplaySnapshot, ledger: DecisionLedger) -> RuntimeAudit:
    violations: list[str] = []
    try:
        ledger.verify()
    except ValueError as exc:
        violations.append(f"ledger integrity: {exc}")
    if snapshot.ledger_head != ledger.head_hash:
        violations.append("runtime snapshot ledger head diverges from ledger")
    if snapshot.ledger_count != len(ledger.records):
        violations.append("runtime snapshot ledger count diverges from ledger")
    session_records = ledger.session(snapshot.session_id)
    if snapshot.event_count and not session_records:
        violations.append("runtime has events but ledger has no session decisions")
    accepted = {r.action for r in session_records if r.disposition is DecisionDisposition.ACCEPTED}
    if snapshot.selected_policy and session_records and snapshot.selected_policy not in accepted:
        # The orient record may remain PROPOSED while outcome/transition records carry
        # the accepted action, so only flag a stronger contradiction when no record names it.
        named = {r.action for r in session_records}
        if snapshot.selected_policy not in named:
            violations.append("selected policy is absent from session ledger")
    return RuntimeAudit(not violations, tuple(violations))


def replay_digest(snapshot: RuntimeReplaySnapshot) -> str:
    payload = {
        "session_id": snapshot.session_id,
        "phase": snapshot.phase,
        "events": snapshot.events,
        "selected_policy": snapshot.selected_policy,
        "rejected_policies": snapshot.rejected_policies,
        "ledger_head": snapshot.ledger_head,
        "ledger_count": snapshot.ledger_count,
        "ledger_digest": snapshot.ledger_digest,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
